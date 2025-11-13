import logging
from aiohttp import web
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime, timedelta
from yookassa import Payment as YooKassaPayment

from src.models import Payment, PaymentStatus, Subscription, SubscriptionStatus
from src.config import GROUP_ID
from src.lexicon import lexicon

async def yookassa_webhook_handler(request: web.Request) -> web.Response:
    """
    This handler receives webhooks from YooKassa.
    """
    bot: Bot = request.app["bot"]
    async_session: AsyncSession = request.app["async_session"]

    try:
        event_json = await request.json()
    except Exception as e:
        logging.error(f"Invalid JSON in webhook: {e}")
        return web.Response(status=400, text="Invalid JSON")

    event_type = event_json.get("event")
    payment_object = event_json.get("object")

    if event_type == "payment.succeeded" and payment_object:
        yookassa_payment_id = payment_object.get("id")
        logging.info(f"Received successful payment webhook for yookassa_id: {yookassa_payment_id}")
        
        # --- Webhook Validation: Object Status Check ---
        try:
            payment_info = YooKassaPayment.find_one(yookassa_payment_id)
            if not payment_info or payment_info.status != 'succeeded':
                logging.warning(f"Invalid payment status for yookassa_id: {yookassa_payment_id}. Status: {payment_info.status if payment_info else 'Not Found'}")
                return web.Response(status=400, text="Invalid payment status")
        except Exception as e:
            logging.error(f"Error validating payment with YooKassa API: {e}")
            return web.Response(status=500, text="Error validating payment")

        async with async_session() as session:
            payment = await session.execute(
                select(Payment).filter_by(yookassa_id=yookassa_payment_id)
            )
            payment = payment.scalar_one_or_none()

            if payment:
                logging.info(f"Found payment record with ID: {payment.id} and subscription_id: {payment.subscription_id}")
                if payment.status != PaymentStatus.succeeded: # Process only once
                    payment.status = PaymentStatus.succeeded
                    
                    subscription = await session.get(Subscription, payment.subscription_id)
                    if subscription:
                        # --- Step 3.1: Find and Expire Old Active Subscriptions ---
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

                        # --- Step 3.2: Activate the New Subscription (Overwrite logic) ---
                        subscription.status = SubscriptionStatus.active
                        subscription.start_date = datetime.now()
                        subscription.end_date = datetime.now() + timedelta(days=30)
                        
                        # --- Step 3.3: Cleanup Pending Subscriptions and Payments ---
                        pending_subs_to_delete = await session.execute(
                            select(Subscription).where(
                                Subscription.user_id == subscription.user_id,
                                Subscription.status == SubscriptionStatus.pending,
                                Subscription.id != subscription.id
                            )
                        )
                        for sub_to_delete in pending_subs_to_delete.scalars().all():
                            # First, delete the associated payment
                            await session.execute(
                                delete(Payment).where(Payment.subscription_id == sub_to_delete.id)
                            )
                            # Then, delete the subscription
                            await session.delete(sub_to_delete)
                        
                        logging.info(f"Cleaned up pending subscriptions and payments for user {subscription.user_id}")

                        await session.commit() # Commit all changes

                        # --- Send confirmation message ---
                        try:
                            chat_member = await bot.get_chat_member(chat_id=int(GROUP_ID), user_id=subscription.user_id)
                            is_member = chat_member.status in ["member", "administrator", "creator"]
                        except Exception:
                            is_member = False

                        if is_member:
                            if payment.bot_message_id:
                                await bot.edit_message_text(
                                    chat_id=subscription.user_id,
                                    message_id=payment.bot_message_id,
                                    text=lexicon['subscription']['renewed_successfully']
                                )
                            else:
                                await bot.send_message(
                                    chat_id=subscription.user_id,
                                    text=lexicon['subscription']['renewed_successfully']
                                )
                        else:
                            try:
                                await bot.unban_chat_member(chat_id=int(GROUP_ID), user_id=subscription.user_id)
                            except Exception as e:
                                logging.info(f"Could not unban user {subscription.user_id} (they were likely not banned): {e}")

                            invite_link = await bot.create_chat_invite_link(
                                chat_id=int(GROUP_ID),
                                member_limit=1,
                                expire_date=subscription.end_date,
                                name=f"Subscription for user {subscription.user_id}"
                            )
                            
                            subscription.invite_link = invite_link.invite_link
                            await session.commit()

                            if payment.bot_message_id:
                                await bot.edit_message_text(
                                    chat_id=subscription.user_id,
                                    message_id=payment.bot_message_id,
                                    text=lexicon['subscription']['payment_processed_invite_link'].format(invite_link=invite_link.invite_link)
                                )
                            else:
                                await bot.send_message(
                                    chat_id=subscription.user_id,
                                    text=lexicon['subscription']['payment_processed_invite_link'].format(invite_link=invite_link.invite_link)
                                )
                else:
                    logging.error(f"Subscription with ID {payment.subscription_id} not found for payment {payment.id}")
            else:
                logging.warning(f"Payment record not found for yookassa_id: {yookassa_payment_id}")
    
    return web.Response(status=200)

def setup_webhook_routes(app: web.Application):
    app.router.add_post("/yookassa_webhook", yookassa_webhook_handler)