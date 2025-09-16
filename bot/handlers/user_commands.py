from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import (
    main_menu_keyboard,
    main_reply_keyboard,
    subscription_list_keyboard,
)
from database.models import Subscription, User

router = Router()


@router.message(CommandStart())
async def handle_start_command(message: Message, session: AsyncSession, user: User):
    text = f"👋 Привет, {user.username or 'пользователь'}! Я бот для поиска вакансий.\n\nНажми «☰ Меню», чтобы начать."
    await message.answer(text, reply_markup=main_reply_keyboard())


@router.message(F.text == "☰ Меню")
@router.callback_query(F.data == "start")
async def handle_start_menu(event: Message | CallbackQuery, session: AsyncSession):
    text = "Выберите действие:"
    keyboard = main_menu_keyboard()

    if isinstance(event, Message):
        await event.answer(text, reply_markup=keyboard)
    elif isinstance(event, CallbackQuery):
        if event.message.text != text:
            await event.message.edit_text(text, reply_markup=keyboard)
        await event.answer()


@router.callback_query(F.data == "my_subscriptions")
async def handle_my_subscriptions(
    callback: CallbackQuery, session: AsyncSession, user: User, state: FSMContext
):
    query = (
        select(Subscription)
        .where(Subscription.user_id == user.telegram_id)
        .order_by(Subscription.name)
    )
    result = await session.execute(query)
    subscriptions = result.scalars().all()

    if not subscriptions:
        await callback.answer("У вас еще нет ни одной подписки.", show_alert=True)
        await handle_start_menu(callback, session)
        return

    text = "Ваши активные подписки. Нажмите на любую для просмотра деталей."
    keyboard = subscription_list_keyboard(subscriptions)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
