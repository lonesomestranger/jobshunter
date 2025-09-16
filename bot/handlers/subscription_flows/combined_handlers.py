import json

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.fsm import CombinedSubscriptionStates
from bot.handlers.subscription_flows.common_handlers import (
    _start_next_platform_configuration,
)
from database.models import User

router = Router()

with open("filters.json", "r", encoding="utf-8") as f:
    ALL_FILTERS = json.load(f)


@router.callback_query(
    F.data.in_(["rabota_finish", "habr_finish", "belmeta_finish", "praca_finish"]),
    CombinedSubscriptionStates.configuring_platform,
)
async def finish_platform_configuration(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, user: User
):
    data = await state.get_data()
    platform_key = data["platforms_to_configure"][data["current_platform_index"]]
    collected_configs = data.get("collected_configs", {})
    collected_configs[platform_key] = data["current_config_params"]

    await state.update_data(
        collected_configs=collected_configs,
        current_platform_index=data["current_platform_index"] + 1,
    )

    await _start_next_platform_configuration(callback.message, state, user, session)
