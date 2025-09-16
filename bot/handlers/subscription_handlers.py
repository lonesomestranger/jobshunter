from aiogram import Router

from bot.handlers.subscription_flows import (
    belmeta_handlers,
    combined_handlers,
    common_handlers,
    habr_handlers,
    praca_handlers,
    rabota_handlers,
)

router = Router()

router.include_router(common_handlers.router)
router.include_router(combined_handlers.router)
router.include_router(rabota_handlers.router)
router.include_router(habr_handlers.router)
router.include_router(belmeta_handlers.router)
router.include_router(praca_handlers.router)
