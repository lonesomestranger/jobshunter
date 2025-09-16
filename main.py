import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.handlers import (
    admin_commands,
    dork_handlers,
    subscription_handlers,
    user_commands,
)
from config import settings
from database.engine import async_session_factory, engine
from database.models import Base, User
from scheduler import setup_scheduler


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_pool: async_sessionmaker[AsyncSession]):
        super().__init__()
        self.session_pool = session_pool

    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        async with self.session_pool() as session:
            data["session"] = session
            return await handler(event, data)


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any],
    ) -> Any:
        user_id = data.get("event_from_user").id
        session: AsyncSession = data["session"]

        query = select(User).where(User.telegram_id == user_id)
        result = await session.execute(query)
        user = result.scalars().first()

        if not user:
            if user_id == settings.ADMIN_CHAT_ID:
                admin_user = User(
                    telegram_id=user_id, username=data.get("event_from_user").username
                )
                session.add(admin_user)
                await session.commit()
                data["user"] = admin_user
            else:
                await event.answer("⛔️ У вас нет доступа к этому боту.")
                return
        else:
            data["user"] = user

        return await handler(event, data)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    await init_db()

    storage: BaseStorage = MemoryStorage()
    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher(storage=storage)

    dp.update.middleware(DbSessionMiddleware(session_pool=async_session_factory))
    dp.update.middleware(AccessMiddleware())

    dp.include_router(admin_commands.router)
    dp.include_router(user_commands.router)
    dp.include_router(subscription_handlers.router)
    dp.include_router(dork_handlers.router)

    scheduler = setup_scheduler(bot, async_session_factory)

    try:
        scheduler.start()
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
