from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta

from src.models import Subscription, SubscriptionStatus
from src.config import GROUP_ID

async def check_expired_subscriptions(bot: Bot, async_session: AsyncSession):
    """
    Checks for subscriptions that expired more than 5 days ago, 
    removes users from the group, and updates their status.
    """
    async with async_session() as session:
        five_days_ago = datetime.now() - timedelta(days=5)
        expired_subscriptions = await session.execute(
            select(Subscription).where(
                Subscription.end_date < five_days_ago,
                Subscription.status == SubscriptionStatus.active
            )
        )
        
        for sub_tuple in expired_subscriptions:
            subscription = sub_tuple[0]
            try:
                # Kick user from the group
                await bot.ban_chat_member(chat_id=int(GROUP_ID), user_id=subscription.user_id)
                
                # Update subscription status
                subscription.status = SubscriptionStatus.expired
                await session.commit()
                
                # Notify user
                await bot.send_message(
                    chat_id=subscription.user_id,
                    text="С момента окончания вашей подписки прошло 5 дней, и вы были удалены из группы. Вы можете оформить новую подписку в любой момент."
                )
            except Exception as e:
                # Log the error, e.g., if the bot can't ban a user (admin) or user not found
                print(f"Could not process expired subscription for user {subscription.user_id}: {e}")

