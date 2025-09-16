from aiogram import Router
from aiogram.filters import BaseFilter, Command
from aiogram.types import Message
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import User

router = Router()


class IsAdmin(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id == settings.ADMIN_CHAT_ID


@router.message(Command("add_user"), IsAdmin())
async def add_user(message: Message, command: Command, session: AsyncSession):
    if not command.args or not command.args.isdigit():
        await message.answer(
            "Пожалуйста, укажите ID пользователя. \nПример: `/add_user 123456789`"
        )
        return

    user_id = int(command.args)

    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    existing_user = result.scalars().first()

    if existing_user:
        await message.answer(f"Пользователь с ID `{user_id}` уже существует.")
        return

    new_user = User(telegram_id=user_id, username=f"user_{user_id}")
    session.add(new_user)
    await session.commit()
    await message.answer(f"✅ Пользователь с ID `{user_id}` успешно добавлен.")


@router.message(Command("del_user"), IsAdmin())
async def del_user(message: Message, command: Command, session: AsyncSession):
    if not command.args or not command.args.isdigit():
        await message.answer(
            "Пожалуйста, укажите ID пользователя. \nПример: `/del_user 123456789`"
        )
        return

    user_id = int(command.args)

    if user_id == settings.ADMIN_CHAT_ID:
        await message.answer("Вы не можете удалить самого себя.")
        return

    query = delete(User).where(User.telegram_id == user_id)
    result = await session.execute(query)

    if result.rowcount > 0:
        await session.commit()
        await message.answer(
            f"✅ Пользователь с ID `{user_id}` и все его подписки были удалены."
        )
    else:
        await message.answer(f"Пользователь с ID `{user_id}` не найден.")
