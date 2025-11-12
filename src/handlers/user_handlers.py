from aiogram import Router, html, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from src.models import User, Subscription, SubscriptionStatus
from src.keyboards.user_keyboards import get_main_menu_keyboard, get_my_subscription_keyboard

user_router = Router()

@user_router.message(CommandStart())
async def command_start_handler(message: Message, async_session: AsyncSession) -> None:
    """
    This handler receives messages with `/start` command
    """
    async with async_session() as session:
        user = await session.execute(select(User).filter_by(telegram_id=message.from_user.id))
        user = user.scalar_one_or_none()

        if not user:
            new_user = User(
                telegram_id=message.from_user.id,
                full_name=message.from_user.full_name,
                username=message.from_user.username
            )
            session.add(new_user)
            await session.commit()
    
    await message.answer(
        f"Привет, {html.bold(message.from_user.full_name)}! Это бот для управления подпиской на закрытый канал.",
        reply_markup=get_main_menu_keyboard()
    )

@user_router.message(F.text == "Моя подписка")
async def my_subscription_handler(message: Message, async_session: AsyncSession) -> None:
    """
    Handler for the 'My Subscription' button.
    """
    async with async_session() as session:
        subscription = await session.execute(
            select(Subscription)
            .filter_by(user_id=message.from_user.id)
            .order_by(Subscription.end_date.desc())
        )
        subscription = subscription.scalar_one_or_none()

        if subscription and subscription.status == SubscriptionStatus.active and subscription.end_date > datetime.now():
            days_left = (subscription.end_date - datetime.now()).days
            text = f"Ваша подписка активна. Осталось дней: {days_left}"
            is_active = True
        else:
            text = "У вас нет активной подписки."
            is_active = False
            
        await message.answer(text, reply_markup=get_my_subscription_keyboard(is_active))

@user_router.message()
async def echo_handler(message: Message) -> None:
    """
    Handler for unhandled messages.
    """
    await message.answer("Пожалуйста, используйте кнопки меню для навигации.")

