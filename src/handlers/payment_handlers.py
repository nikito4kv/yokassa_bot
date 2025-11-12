from aiogram import Router, Bot
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from src.config import GROUP_ID
from src.models import Subscription, SubscriptionStatus

payment_router = Router()

@payment_router.message(lambda message: message.text == "Оплатить") # Placeholder for actual payment trigger
async def process_payment(message: Message, bot: Bot, async_session: AsyncSession) -> None:
    user_id = message.from_user.id
    chat_id = int(GROUP_ID) # Ensure GROUP_ID is an integer

    # Placeholder for actual payment processing logic
    # For now, we'll assume payment is successful and create a subscription
    
    async with async_session() as session:
        # Create a new subscription
        end_date = datetime.now() + timedelta(days=30) # 30-day subscription
        new_subscription = Subscription(
            user_id=user_id,
            end_date=end_date,
            status=SubscriptionStatus.pending, # Set to pending until user joins
            amount_paid=100.00, # Placeholder amount
            start_date=datetime.now()
        )
        session.add(new_subscription)
        await session.commit()
        await session.refresh(new_subscription) # Refresh to get the ID

        # Generate invite link
        invite_link = await bot.create_chat_invite_link(
            chat_id=chat_id,
            member_limit=1,
            expire_date=end_date,
            name=f"Subscription for user {user_id}"
        )

        # Update subscription with invite link
        new_subscription.invite_link = invite_link.invite_link
        await session.commit()

        await message.answer(f"Ваша подписка оформлена. Вот ваша ссылка для вступления в группу: {invite_link.invite_link}")
