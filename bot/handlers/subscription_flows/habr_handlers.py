import json

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.fsm import CombinedSubscriptionStates, SubscriptionStates
from bot.handlers.subscription_flows.common_handlers import PLATFORM_CONFIG
from bot.keyboards import (
    habr_config_keyboard,
    habr_filter_options_keyboard,
    habr_salary_keyboard,
)
from database.models import Subscription, User

router = Router()

with open("filters.json", "r", encoding="utf-8") as f:
    ALL_FILTERS = json.load(f)


@router.callback_query(
    F.data.startswith("habr_config:"),
    StateFilter(
        SubscriptionStates.configuring_habr_filters,
        CombinedSubscriptionStates.configuring_platform,
    ),
)
async def configure_habr_filter(callback: CallbackQuery, state: FSMContext):
    filter_key = callback.data.split(":")[1]
    data = await state.get_data()

    params_key = (
        "current_config_params"
        if data.get("platforms_to_configure")
        else "search_params"
    )
    current_params = data.get(params_key, {})

    if filter_key == "back":
        platforms = data.get("platforms_to_configure", [])
        current_index = data.get("current_platform_index", 0)
        text = "Настройте фильтры для Habr Career:"
        if platforms:
            platform_info = PLATFORM_CONFIG[platforms[current_index]]
            text = f"Шаг {current_index + 1}/{len(platforms)}. Настройте фильтры для {platform_info['name']}:"

        await callback.message.edit_text(
            text, reply_markup=habr_config_keyboard(current_params)
        )
        return

    if filter_key == "salary":
        await state.set_state(SubscriptionStates.waiting_for_habr_salary)
        await callback.message.edit_text(
            "Введите минимальную зарплату в USD (только цифры):",
            reply_markup=habr_salary_keyboard(),
        )
    else:
        selected = current_params.get(filter_key, [])
        await callback.message.edit_text(
            f"Выберите значение для '{ALL_FILTERS['habr_career'][filter_key]['label']}':",
            reply_markup=habr_filter_options_keyboard(
                filter_key, selected if isinstance(selected, list) else [selected]
            ),
        )
    await callback.answer()


@router.message(SubscriptionStates.waiting_for_habr_salary)
async def process_habr_salary(message: Message, state: FSMContext):
    if message.text.isdigit():
        data = await state.get_data()

        is_combined_flow = data.get("platforms_to_configure")
        params_key = "current_config_params" if is_combined_flow else "search_params"
        search_params = data.get(params_key, {})

        search_params["salary"] = message.text
        await state.update_data({params_key: search_params})

        new_state = (
            CombinedSubscriptionStates.configuring_platform
            if is_combined_flow
            else SubscriptionStates.configuring_habr_filters
        )
        await state.set_state(new_state)

        prompt_message_id = data.get("prompt_message_id")
        await message.delete()
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=prompt_message_id,
            text="Настройте фильтры:",
            reply_markup=habr_config_keyboard(search_params),
        )
    else:
        await message.answer("Пожалуйста, введите только цифры.")


@router.callback_query(
    F.data.startswith("habr_select:"),
    StateFilter(
        SubscriptionStates.configuring_habr_filters,
        CombinedSubscriptionStates.configuring_platform,
    ),
)
async def select_habr_filter_option(callback: CallbackQuery, state: FSMContext):
    _, key, value = callback.data.split(":")
    data = await state.get_data()

    params_key = (
        "current_config_params"
        if data.get("platforms_to_configure")
        else "search_params"
    )
    search_params = data.get(params_key, {})

    current_selection = search_params.get(key, [])
    if not isinstance(current_selection, list):
        current_selection = [current_selection] if current_selection else []

    if value in current_selection:
        current_selection.remove(value)
    else:
        current_selection.append(value)

    search_params[key] = current_selection
    await state.update_data({params_key: search_params})

    await callback.message.edit_reply_markup(
        reply_markup=habr_filter_options_keyboard(key, current_selection)
    )
    await callback.answer()


@router.callback_query(
    F.data == "habr_finish", SubscriptionStates.configuring_habr_filters
)
async def finish_habr_subscription(
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
            f"✅ Подписка '{data['name']}' на Habr Career успешно обновлена!"
        )
    else:
        new_subscription = Subscription(
            name=data["name"],
            search_type="habr_career",
            search_params=data["search_params"],
            user_id=user.telegram_id,
        )
        session.add(new_subscription)
        await session.commit()
        await state.clear()
        await callback.message.edit_text(
            f"✅ Подписка '{data['name']}' на Habr Career успешно создана!"
        )

    from bot.handlers.user_commands import handle_start_menu

    await handle_start_menu(callback, session)
