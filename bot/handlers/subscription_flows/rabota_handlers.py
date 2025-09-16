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
    city_selection_keyboard,
    rabota_config_keyboard,
    rabota_filter_options_keyboard,
    rabota_salary_keyboard,
)
from database.models import Subscription, User

router = Router()

with open("filters.json", "r", encoding="utf-8") as f:
    ALL_FILTERS = json.load(f)


@router.callback_query(
    F.data.startswith("rabota_config:"),
    StateFilter(
        SubscriptionStates.configuring_rabota_filters,
        CombinedSubscriptionStates.configuring_platform,
    ),
)
async def configure_rabota_filter(callback: CallbackQuery, state: FSMContext):
    param_key = callback.data.split(":")[1]
    data = await state.get_data()

    params_key = (
        "current_config_params"
        if data.get("platforms_to_configure")
        else "search_params"
    )
    current_params = data.get(params_key, {})

    if param_key == "back":
        platforms = data.get("platforms_to_configure", [])
        current_index = data.get("current_platform_index", 0)
        text = "Настройте фильтры для Rabota.by:"
        if platforms:
            platform_info = PLATFORM_CONFIG[platforms[current_index]]
            text = f"Шаг {current_index + 1}/{len(platforms)}. Настройте фильтры для {platform_info['name']}:"

        await callback.message.edit_text(
            text, reply_markup=rabota_config_keyboard(current_params)
        )
        return

    if param_key == "city":
        await callback.message.edit_text(
            "Выберите регион:", reply_markup=city_selection_keyboard()
        )
    elif ALL_FILTERS["rabota_by"][param_key]["type"] == "text_input":
        await state.set_state(SubscriptionStates.waiting_for_rabota_salary)
        await state.update_data(current_rabota_filter_key=param_key)
        await callback.message.edit_text(
            f"Введите значение для '{ALL_FILTERS['rabota_by'][param_key]['label']}':",
            reply_markup=rabota_salary_keyboard(),
        )
    else:
        selected = current_params.get("params", {}).get(
            ALL_FILTERS["rabota_by"][param_key]["param_name"], []
        )
        await callback.message.edit_text(
            f"Выберите значение для '{ALL_FILTERS['rabota_by'][param_key]['label']}':",
            reply_markup=rabota_filter_options_keyboard(
                param_key, selected if isinstance(selected, list) else [selected]
            ),
        )
    await callback.answer()


@router.message(SubscriptionStates.waiting_for_rabota_salary)
async def process_rabota_salary(message: Message, state: FSMContext):
    data = await state.get_data()
    param_key = data.get("current_rabota_filter_key")

    is_combined_flow = data.get("platforms_to_configure")
    params_key = "current_config_params" if is_combined_flow else "search_params"
    search_params = data.get(params_key, {})

    if "params" not in search_params:
        search_params["params"] = {}

    param_name = ALL_FILTERS["rabota_by"][param_key]["param_name"]
    search_params["params"][param_name] = message.text.strip()

    await state.update_data({params_key: search_params})

    new_state = (
        CombinedSubscriptionStates.configuring_platform
        if is_combined_flow
        else SubscriptionStates.configuring_rabota_filters
    )
    await state.set_state(new_state)

    prompt_message_id = data.get("prompt_message_id")
    await message.delete()
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=prompt_message_id,
        text="Настройте фильтры:",
        reply_markup=rabota_config_keyboard(search_params),
    )


@router.callback_query(
    F.data.startswith("city_"),
    StateFilter(
        SubscriptionStates.configuring_rabota_filters,
        CombinedSubscriptionStates.configuring_platform,
    ),
)
async def process_rabota_city_selection(callback: CallbackQuery, state: FSMContext):
    selected_city_key = callback.data.split("_", 1)[1]
    data = await state.get_data()

    params_key = (
        "current_config_params"
        if data.get("platforms_to_configure")
        else "search_params"
    )
    search_params = data.get(params_key, {})

    city_map = {"all_rb_only": "16", "minsk": "1002"}
    if selected_city_key in city_map:
        search_params["params"]["area"] = city_map[selected_city_key]
        search_params["city"] = "minsk"
    else:
        if "area" in search_params["params"]:
            del search_params["params"]["area"]
        search_params["city"] = (
            selected_city_key if selected_city_key != "all_with_hh" else "minsk"
        )

    search_params["original_city_choice"] = selected_city_key
    await state.update_data({params_key: search_params})

    await callback.message.edit_text(
        "Настройте фильтры:", reply_markup=rabota_config_keyboard(search_params)
    )
    await callback.answer()


@router.callback_query(
    F.data.startswith("rabota_select:"),
    StateFilter(
        SubscriptionStates.configuring_rabota_filters,
        CombinedSubscriptionStates.configuring_platform,
    ),
)
async def select_rabota_filter_option(callback: CallbackQuery, state: FSMContext):
    _, param_key, value = callback.data.split(":")
    data = await state.get_data()

    params_key = (
        "current_config_params"
        if data.get("platforms_to_configure")
        else "search_params"
    )
    search_params = data.get(params_key, {})
    param_info = ALL_FILTERS["rabota_by"][param_key]
    param_name = param_info["param_name"]

    if "params" not in search_params:
        search_params["params"] = {}

    current_selection = search_params.get("params", {}).get(param_name, [])
    if not isinstance(current_selection, list):
        current_selection = [current_selection] if current_selection else []

    if param_info["type"] == "single_choice":
        current_selection = [value]
    else:
        if value in current_selection:
            current_selection.remove(value)
        else:
            current_selection.append(value)

    if not current_selection:
        if param_name in search_params["params"]:
            del search_params["params"][param_name]
    else:
        search_params["params"][param_name] = (
            current_selection if len(current_selection) > 1 else current_selection[0]
        )

    await state.update_data({params_key: search_params})
    await callback.message.edit_reply_markup(
        reply_markup=rabota_filter_options_keyboard(param_key, current_selection)
    )
    await callback.answer()


@router.callback_query(
    F.data == "rabota_finish", SubscriptionStates.configuring_rabota_filters
)
async def finish_rabota_subscription(
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
            f"✅ Подписка '{data['name']}' на Rabota.by успешно обновлена!"
        )
    else:
        new_subscription = Subscription(
            name=data["name"],
            search_type="rabota_by",
            search_params=data["search_params"],
            user_id=user.telegram_id,
        )
        session.add(new_subscription)
        await session.commit()
        await state.clear()
        await callback.message.edit_text(
            f"✅ Подписка '{data['name']}' на Rabota.by успешно создана!"
        )

    from bot.handlers.user_commands import handle_start_menu

    await handle_start_menu(callback, session)
