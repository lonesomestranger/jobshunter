import json

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.fsm import CombinedSubscriptionStates, SubscriptionStates
from bot.keyboards import (
    praca_config_keyboard,
    praca_filter_options_keyboard,
    praca_salary_keyboard,
)
from database.models import Subscription, User

router = Router()

with open("filters.json", "r", encoding="utf-8") as f:
    ALL_FILTERS = json.load(f)


@router.callback_query(
    F.data.startswith("praca_config:"),
    StateFilter(
        SubscriptionStates.configuring_praca_filters,
        CombinedSubscriptionStates.configuring_platform,
    ),
)
async def configure_praca_filter(callback: CallbackQuery, state: FSMContext):
    param_key = callback.data.split(":")[1]
    data = await state.get_data()
    params_key = (
        "current_config_params"
        if data.get("platforms_to_configure")
        else "search_params"
    )
    current_params = data.get(params_key, {})

    if param_key == "back":
        await callback.message.edit_text(
            "Настройте фильтры для Praca.by:",
            reply_markup=praca_config_keyboard(current_params),
        )
        return

    if ALL_FILTERS["praca_by"][param_key]["type"] == "text_input":
        await state.set_state(SubscriptionStates.waiting_for_praca_salary)
        await state.update_data(current_praca_filter_key=param_key)
        await callback.message.edit_text(
            f"Введите значение для '{ALL_FILTERS['praca_by'][param_key]['label']}':",
            reply_markup=praca_salary_keyboard(),
        )
    else:
        selected = current_params.get(param_key, {})
        await callback.message.edit_text(
            f"Выберите значение для '{ALL_FILTERS['praca_by'][param_key]['label']}':",
            reply_markup=praca_filter_options_keyboard(param_key, selected),
        )
    await callback.answer()


@router.message(SubscriptionStates.waiting_for_praca_salary)
async def process_praca_salary(message: Message, state: FSMContext):
    data = await state.get_data()
    param_key = data.get("current_praca_filter_key")
    is_combined_flow = data.get("platforms_to_configure")
    params_key = "current_config_params" if is_combined_flow else "search_params"
    search_params = data.get(params_key, {})

    search_params[param_key] = {message.text.strip(): "1"}

    await state.update_data({params_key: search_params})
    new_state = (
        CombinedSubscriptionStates.configuring_platform
        if is_combined_flow
        else SubscriptionStates.configuring_praca_filters
    )
    await state.set_state(new_state)

    prompt_message_id = data.get("prompt_message_id")
    await message.delete()
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=prompt_message_id,
        text="Настройте фильтры:",
        reply_markup=praca_config_keyboard(search_params),
    )


@router.callback_query(
    F.data.startswith("praca_select:"),
    StateFilter(
        SubscriptionStates.configuring_praca_filters,
        CombinedSubscriptionStates.configuring_platform,
    ),
)
async def select_praca_filter_option(callback: CallbackQuery, state: FSMContext):
    _, param_key, value = callback.data.split(":")
    data = await state.get_data()
    params_key = (
        "current_config_params"
        if data.get("platforms_to_configure")
        else "search_params"
    )
    search_params = data.get(params_key, {})

    if param_key not in search_params:
        search_params[param_key] = {}

    if value == "all_belarus":
        search_params[param_key] = {}
    elif value in search_params[param_key]:
        del search_params[param_key][value]
        if not search_params[param_key]:
            del search_params[param_key]
    else:
        search_params[param_key][value] = value if param_key != "c_rad" else "1"

    await state.update_data({params_key: search_params})
    await callback.message.edit_reply_markup(
        reply_markup=praca_filter_options_keyboard(
            param_key, search_params.get(param_key, {})
        )
    )
    await callback.answer()


@router.callback_query(
    F.data == "praca_finish", SubscriptionStates.configuring_praca_filters
)
async def finish_praca_subscription(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User
):
    data = await state.get_data()
    sub_id = data.get("sub_id")
    if sub_id:
        stmt = (
            update(Subscription)
            .where(Subscription.id == sub_id)
            .values(name=data["name"], search_params=data["search_params"])
        )
        await session.execute(stmt)
        await session.commit()
        await state.clear()
        await callback.message.edit_text(
            f"✅ Подписка '{data['name']}' на Praca.by успешно обновлена!"
        )
    else:
        new_subscription = Subscription(
            name=data["name"],
            search_type="praca_by",
            search_params=data["search_params"],
            user_id=user.telegram_id,
        )
        session.add(new_subscription)
        await session.commit()
        await state.clear()
        await callback.message.edit_text(
            f"✅ Подписка '{data['name']}' на Praca.by успешно создана!"
        )

    from bot.handlers.user_commands import handle_start_menu

    await handle_start_menu(callback, session)
