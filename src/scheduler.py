from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, date

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

async def send_expiration_warnings(bot: Bot, async_session: AsyncSession):
    """
    Sends warnings to users whose subscriptions are about to expire.
    """
    async with async_session() as session:
        active_subscriptions = await session.execute(
            select(Subscription).where(Subscription.status == SubscriptionStatus.active)
        )
        
        today = date.today()
        
        for sub_tuple in active_subscriptions:
            subscription = sub_tuple[0]
            days_left = (subscription.end_date.date() - today).days
            
            warning_sent_today = subscription.last_warning_sent == today
            
            if warning_sent_today:
                continue

            message = None
            if days_left <= 0:
                message = "Ваша подписка истекла. Если вы не продлите ее в течение 5 дней, вы будете удалены из группы."
            elif days_left <= 3:
                message = f"Ваша подписка истекает через {days_left} дня(дней)."
            elif days_left <= 7:
                message = "Ваша подписка истекает через неделю."
            elif days_left <= 14:
                message = "Ваша подписка истекает через 2 недели."

            if message:
                try:
                    await bot.send_message(chat_id=subscription.user_id, text=message)
                    subscription.last_warning_sent = today
                    await session.commit()
                except Exception as e:
                    print(f"Could not send warning to user {subscription.user_id}: {e}")

