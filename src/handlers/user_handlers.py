from aiogram import Router, html
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models import User

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
            await message.answer(f"Hello, {html.bold(message.from_user.full_name)}! You have been added to the database.")
        else:
            await message.answer(f"Welcome back, {html.bold(message.from_user.full_name)}!")

@user_router.message()
async def echo_handler(message: Message) -> None:
    """
    Handler will forward receive a message back to the sender

    By default, message handler will handle all message types (like a text, photo, sticker etc.)
    """
    try:
        # Send a copy of the received message
        await message.send_copy(chat_id=message.chat.id)
    except TypeError:
        # But not all the types is supported to be copied so need to handle it
        await message.answer("Nice try!")
