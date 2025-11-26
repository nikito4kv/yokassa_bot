import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select, delete
from datetime import datetime, timedelta
from typing import Optional, cast # Import cast

from src.models import Payment, PaymentStatus, Subscription, SubscriptionStatus, SystemSettings
from src.config import GROUP_ID, ADMIN_IDS
from src.lexicon import lexicon

async def get_admins(session: AsyncSession) -> list[int]:
    """
    Retrieves a list of admin IDs. In this setup, it's a static list from config.
    Can be extended to fetch from DB if admin management becomes dynamic.
    """
    return ADMIN_IDS

async def get_system_settings(session: AsyncSession) -> SystemSettings:
    """
    Retrieves system settings, creating them if they don't exist.
    """
    settings_result = await session.execute(select(SystemSettings))
    settings = settings_result.scalars().first()
    if not settings:
        settings = SystemSettings(manual_payment_enabled=False)
        session.add(settings)
        await session.commit()
    return settings



async def process_successful_payment(bot: Bot, async_session_factory: async_sessionmaker[AsyncSession], yookassa_payment_id: Optional[str] = None, payment_id: Optional[int] = None):
    """
    Handles all the logic for a successful payment:
    - Updates payment and subscription statuses in the DB.
    - Expires old subscriptions.
    - Cleans up pending subscriptions.
    - Sends a confirmation message to the user with an invite link.
    """
    async with async_session_factory() as session:
        payment: Optional[Payment] = None # Explicitly type payment
        if yookassa_payment_id:
            payment_result = await session.execute(
                select(Payment).filter_by(yookassa_id=yookassa_payment_id)
            )
            payment = payment_result.scalars().first()
        elif payment_id:
            payment = await session.get(Payment, payment_id)
        else:
            logging.error("process_successful_payment called without yookassa_payment_id or payment_id")
            return

        if not payment: # payment is Optional[Payment], check for None
            logging.warning(f"Payment record not found for yookassa_id: {yookassa_payment_id} or payment_id: {payment_id}")
            return

        if payment.status == PaymentStatus.succeeded:
            logging.info(f"Payment {payment.id} has already been processed.")
            return

        logging.info(f"Found payment record with ID: {payment.id} and subscription_id: {payment.subscription_id}")
        
        payment.status = PaymentStatus.succeeded
        
        subscription = await session.get(Subscription, payment.subscription_id)
        if not subscription:
            logging.error(f"Subscription with ID {payment.subscription_id} not found for payment {payment.id}")
            await session.commit() # Commit payment status change anyway
            return

        # --- Step 1: Find and Expire Old Active Subscriptions ---
        other_active_subscriptions_result = await session.execute(
            select(Subscription).where(
                Subscription.user_id == subscription.user_id,
                Subscription.status == SubscriptionStatus.active,
                Subscription.id != subscription.id
            )
        )
        for old_active_sub in other_active_subscriptions_result.scalars().all():
            old_active_sub.status = SubscriptionStatus.expired
            logging.info(f"Expired old active subscription {old_active_sub.id} for user {subscription.user_id}")

        # --- Step 2: Activate the New Subscription ---
        subscription.status = SubscriptionStatus.active
        subscription.start_date = datetime.now()
        subscription.end_date = datetime.now() + timedelta(days=30) # TODO: Use duration from payment/subscription
        
        # --- Step 3: Cleanup Pending Subscriptions and Payments for the same user ---
        pending_subs_to_delete_result = await session.execute(
            select(Subscription).where(
                Subscription.user_id == subscription.user_id,
                Subscription.status == SubscriptionStatus.pending,
                Subscription.id != subscription.id
            )
        )
        for sub_to_delete in pending_subs_to_delete_result.scalars().all():
            # Check if sub_to_delete.id is not None before using it
            if sub_to_delete.id is not None:
                await session.execute(delete(Payment).where(Payment.subscription_id == sub_to_delete.id))
            await session.delete(sub_to_delete)
        
        logging.info(f"Cleaned up other pending subscriptions and payments for user {subscription.user_id}")

        await session.commit() # Commit all changes

        # --- Step 4: Send confirmation message ---
        try:
            # GROUP_ID is a string in src/config.py, convert to int
            group_id_int = int(GROUP_ID) if GROUP_ID else 0 # Default to 0 or handle error
            chat_member = await bot.get_chat_member(chat_id=group_id_int, user_id=subscription.user_id)
            is_member = chat_member.status in ["member", "administrator", "creator"]
        except Exception: # Broad except for simplicity, can be refined
            is_member = False

        if is_member:
            group_chat = await bot.get_chat(group_id_int)
            invite_link = await bot.create_chat_invite_link(
                chat_id=group_id_int,
                member_limit=1,
                expire_date=datetime.now() + timedelta(days=3)
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"Перейти в \"{group_chat.title}\"", url=invite_link.invite_link)]
            ])
            
            text_to_send = lexicon['subscription']['renewed_successfully']
            
            if payment.bot_message_id: # Check payment.bot_message_id for None
                await bot.edit_message_text(
                    chat_id=subscription.user_id,
                    message_id=cast(int, payment.bot_message_id), # Cast to int because bot_message_id can be Optional[int]
                    text=text_to_send,
                    reply_markup=keyboard
                )
            else:
                await bot.send_message(
                    chat_id=subscription.user_id,
                    text=text_to_send,
                    reply_markup=keyboard
                )
        else:
            try:
                await bot.unban_chat_member(chat_id=group_id_int, user_id=subscription.user_id)
            except Exception as e:
                logging.info(f"Could not unban user {subscription.user_id} (they were likely not banned): {e}")

            invite_link = await bot.create_chat_invite_link(
                chat_id=group_id_int,
                member_limit=1,
                expire_date=datetime.now() + timedelta(days=3)
            )
            
            subscription.invite_link = invite_link.invite_link
            await session.commit()

            text_to_send = lexicon['subscription']['payment_processed_invite_link'].format(invite_link=invite_link.invite_link)

            if payment.bot_message_id: # Check payment.bot_message_id for None
                await bot.edit_message_text(
                    chat_id=subscription.user_id,
                    message_id=cast(int, payment.bot_message_id),
                    text=text_to_send
                )
            else:
                await bot.send_message(
                    chat_id=subscription.user_id,
                    text=text_to_send
                )