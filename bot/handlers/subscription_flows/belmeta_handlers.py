import json

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.fsm import CombinedSubscriptionStates, SubscriptionStates
from bot.keyboards import belmeta_config_keyboard, belmeta_filter_options_keyboard
from database.models import Subscription, User

router = Router()

with open("filters.json", "r", encoding="utf-8") as f:
    ALL_FILTERS = json.load(f)


@router.callback_query(
    F.data.startswith("belmeta_config:"),
    StateFilter(
        SubscriptionStates.configuring_belmeta_filters,
        CombinedSubscriptionStates.configuring_platform,
    ),
)
async def configure_belmeta_filter(callback: CallbackQuery, state: FSMContext):
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
            "Настройте фильтры для Belmeta.com:",
            reply_markup=belmeta_config_keyboard(current_params),
        )
        return

    selected = current_params.get(param_key, "").split(",")
    await callback.message.edit_text(
        f"Выберите значение для '{ALL_FILTERS['belmeta_com'][param_key]['label']}':",
        reply_markup=belmeta_filter_options_keyboard(param_key, selected),
    )
    await callback.answer()


@router.callback_query(
    F.data.startswith("belmeta_select:"),
    StateFilter(
        SubscriptionStates.configuring_belmeta_filters,
        CombinedSubscriptionStates.configuring_platform,
    ),
)
async def select_belmeta_filter_option(callback: CallbackQuery, state: FSMContext):
    _, key, value = callback.data.split(":")
    data = await state.get_data()
    params_key = (
        "current_config_params"
        if data.get("platforms_to_configure")
        else "search_params"
    )
    search_params = data.get(params_key, {})
    info = ALL_FILTERS["belmeta_com"][key]

    current_selection = []
    if key == "l":
        if value == "all":
            if "l" in search_params:
                del search_params["l"]
        else:
            search_params["l"] = value

        if "l" in search_params:
            current_selection = [search_params["l"]]
    else:
        current_selection = search_params.get(key, "").split(",")
        current_selection = [v for v in current_selection if v]

        if info["type"] == "single_choice":
            current_selection = [value] if value not in current_selection else []
        else:
            if value in current_selection:
                current_selection.remove(value)
            else:
                current_selection.append(value)

        if current_selection:
            search_params[key] = ",".join(current_selection)
        elif key in search_params:
            del search_params[key]

    await state.update_data({params_key: search_params})
    await callback.message.edit_reply_markup(
        reply_markup=belmeta_filter_options_keyboard(key, current_selection)
    )
    await callback.answer()


@router.callback_query(
    F.data == "belmeta_finish", SubscriptionStates.configuring_belmeta_filters
)
async def finish_belmeta_subscription(
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
            f"✅ Подписка '{data['name']}' на Belmeta.com успешно обновлена!"
        )
    else:
        new_subscription = Subscription(
            name=data["name"],
            search_type="belmeta_com",
            search_params=data["search_params"],
            user_id=user.telegram_id,
        )
        session.add(new_subscription)
        await session.commit()
        await state.clear()
        await callback.message.edit_text(
            f"✅ Подписка '{data['name']}' на Belmeta.com успешно создана!"
        )

    from bot.handlers.user_commands import handle_start_menu

    await handle_start_menu(callback, session)
