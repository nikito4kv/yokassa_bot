from aiohttp import web
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from yookassa import Payment as YooKassaPayment

from src.models import Payment, PaymentStatus, Subscription, SubscriptionStatus
from src.config import GROUP_ID

async def yookassa_webhook_handler(request: web.Request) -> web.Response:
    """
    This handler receives webhooks from YooKassa.
    """
    bot: Bot = request.app["bot"]
    async_session: AsyncSession = request.app["async_session"]

    try:
        event_json = await request.json()
    except Exception as e:
        return web.Response(status=400, text="Invalid JSON")

    event_type = event_json.get("event")
    payment_object = event_json.get("object")

    if event_type == "payment.succeeded" and payment_object:
        yookassa_payment_id = payment_object.get("id")
        
        # --- Webhook Validation: Object Status Check ---
        payment_info = YooKassaPayment.find_one(yookassa_payment_id)
        if not payment_info or payment_info.status != 'succeeded':
            return web.Response(status=400, text="Invalid payment status")

        async with async_session() as session:
            payment = await session.execute(
                select(Payment).filter_by(yookassa_id=yookassa_payment_id)
            )
            payment = payment.scalar_one_or_none()

            if payment and payment.status != PaymentStatus.succeeded: # Process only once
                payment.status = PaymentStatus.succeeded
                
                subscription = await session.get(Subscription, payment.subscription_id)
                if subscription:
                    try:
                        chat_member = await bot.get_chat_member(chat_id=int(GROUP_ID), user_id=subscription.user_id)
                        is_member = chat_member.status in ["member", "administrator", "creator"]
                    except Exception:
                        is_member = False

                    if is_member:
                        subscription.status = SubscriptionStatus.active
                        subscription.start_date = datetime.now()
                        await session.commit()
                        await bot.send_message(
                            chat_id=subscription.user_id,
                            text="Ваша подписка успешно продлена!"
                        )
                    else:
                        invite_link = await bot.create_chat_invite_link(
                            chat_id=int(GROUP_ID),
                            member_limit=1,
                            expire_date=subscription.end_date,
                            name=f"Subscription for user {subscription.user_id}"
                        )
                        
                        subscription.invite_link = invite_link.invite_link
                        await session.commit()

                        await bot.send_message(
                            chat_id=subscription.user_id,
                            text=f"Ваш платеж успешно обработан! Вот ваша ссылка для вступления в группу: {invite_link.invite_link}"
                        )
    
    return web.Response(status=200)

def setup_webhook_routes(app: web.Application):
    app.router.add_post("/yookassa_webhook", yookassa_webhook_handler)
