from aiohttp import web
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models import Payment, PaymentStatus, Subscription
from src.config import GROUP_ID

async def yookassa_webhook_handler(request: web.Request) -> web.Response:
    """
    This handler receives webhooks from YooKassa.
    
    NOTE: For production, it's crucial to validate the incoming webhook's source IP address
    to ensure it's from YooKassa's trusted servers. This implementation bypasses that check
    for local development purposes (e.g., when using ngrok).
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
        payment_id = payment_object.get("id")
        
        async with async_session() as session:
            payment = await session.execute(
                select(Payment).filter_by(yookassa_id=payment_id)
            )
            payment = payment.scalar_one_or_none()

            if payment:
                payment.status = PaymentStatus.succeeded
                
                subscription = await session.get(Subscription, payment.subscription_id)
                if subscription:
                    # Generate invite link
                    invite_link = await bot.create_chat_invite_link(
                        chat_id=int(GROUP_ID),
                        member_limit=1,
                        expire_date=subscription.end_date,
                        name=f"Subscription for user {subscription.user_id}"
                    )
                    
                    subscription.invite_link = invite_link.invite_link
                    await session.commit()

                    # Send invite link to user
                    await bot.send_message(
                        chat_id=subscription.user_id,
                        text=f"Ваш платеж успешно обработан! Вот ваша ссылка для вступления в группу: {invite_link.invite_link}"
                    )
    
    return web.Response(status=200)

def setup_webhook_routes(app: web.Application):
    app.router.add_post("/yookassa_webhook", yookassa_webhook_handler)
