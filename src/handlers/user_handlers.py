from aiogram import Router, html, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from src.models import User, Subscription, SubscriptionStatus
from src.keyboards.user_keyboards import get_main_menu_keyboard, get_my_subscription_keyboard
from src.lexicon import lexicon

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
            await message.answer(lexicon['welcome']['new_user_registered'])
    
    await message.answer(
        lexicon['welcome']['start_message'].format(
            full_name=html.bold(message.from_user.full_name)
        ),
        reply_markup=get_main_menu_keyboard()
    )

@user_router.message(F.text == lexicon['buttons']['main_menu']['my_subscription'])
async def my_subscription_handler(message: Message, async_session: AsyncSession) -> None:
    """
    Handler for the 'My Subscription' button.
    """
    async with async_session() as session:
        result = await session.execute(
            select(Subscription)
            .filter_by(user_id=message.from_user.id)
            .order_by(Subscription.end_date.desc())
        )
        subscription = result.first()

        if subscription and subscription[0].status == SubscriptionStatus.active and subscription[0].end_date > datetime.now():
            days_left = (subscription[0].end_date - datetime.now()).days
            text = lexicon['subscription']['active_status'].format(
                end_date=subscription[0].end_date.strftime("%d.%m.%Y"),
                days_left=days_left
            )
            is_active = True
        else:
            text = lexicon['subscription']['inactive_status']
            is_active = False
            
        await message.answer(text, reply_markup=get_my_subscription_keyboard(is_active))

@user_router.message()
async def echo_handler(message: Message) -> None:
    """
    Handler for unhandled messages.
    """
    await message.answer(lexicon['general']['unhandled_message'])

@user_router.message(F.text == lexicon['buttons']['main_menu']['help'])
@user_router.message(Command('help'))
async def help_handler(message: Message) -> None:
    """
    Handler for the 'Help' button and /help command.
    """
    await message.answer(lexicon['general']['help_message'])

