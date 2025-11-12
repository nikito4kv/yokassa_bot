from aiogram import Router, Bot
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from yookassa import Configuration, Payment as YooKassaPayment
import uuid

from src.config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY
from src.models import Payment, PaymentStatus, Subscription, SubscriptionStatus
from datetime import datetime, timedelta

payment_router = Router()

Configuration.configure(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)

@payment_router.message(lambda message: message.text == "Оплатить")
async def process_payment(message: Message, bot: Bot, async_session: AsyncSession) -> None:
    user_id = message.from_user.id

    async with async_session() as session:
        # Create a subscription record
        end_date = datetime.now() + timedelta(days=30)
        new_subscription = Subscription(
            user_id=user_id,
            end_date=end_date,
            status=SubscriptionStatus.pending,
            amount_paid=100.00,  # Placeholder amount
            start_date=datetime.now()
        )
        session.add(new_subscription)
        await session.commit()
        await session.refresh(new_subscription)

        # Create a payment in YooKassa
        idempotence_key = str(uuid.uuid4())
        payment = YooKassaPayment.create({
            "amount": {
                "value": "100.00",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/sever_human_vznos_bot" # Replace with your bot's username
            },
            "capture": True,
            "description": f"Subscription for user {user_id}",
            "metadata": {
                "subscription_id": new_subscription.id
            }
        }, idempotence_key)

        # Save payment details to our database
        new_payment = Payment(
            yookassa_id=payment.id,
            user_id=user_id,
            status=PaymentStatus.pending,
            subscription_id=new_subscription.id
        )
        session.add(new_payment)
        await session.commit()

        await message.answer(f"Для оплаты подписки, пожалуйста, перейдите по ссылке: {payment.confirmation.confirmation_url}")

