from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from yookassa import Configuration, Payment as YooKassaPayment
import uuid
from datetime import datetime, timedelta

from src.config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY
from src.models import Payment, PaymentStatus, Subscription, SubscriptionStatus
from src.keyboards.user_keyboards import get_tariffs_keyboard

payment_router = Router()

Configuration.configure(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)

class CustomAmount(StatesGroup):
    waiting_for_amount = State()

# --- Helper function to create payment ---
async def create_payment(amount: float, user_id: int, async_session: AsyncSession) -> str:
    """
    Creates a subscription and a YooKassa payment, returns the confirmation URL.
    """
    async with async_session() as session:
        # Create a subscription record
        end_date = datetime.now() + timedelta(days=30)
        new_subscription = Subscription(
            user_id=user_id,
            end_date=end_date,
            status=SubscriptionStatus.pending,
            amount_paid=amount,
            start_date=datetime.now()
        )
        session.add(new_subscription)
        await session.commit()
        await session.refresh(new_subscription)

        # Create a payment in YooKassa
        idempotence_key = str(uuid.uuid4())
        payment = YooKassaPayment.create({
            "amount": {
                "value": str(amount),
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/sever_human_vznos_bot" # Replace with your bot's username
            },
            "capture": True,
            "description": f"Подписка на 1 месяц для пользователя {user_id}",
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

        return payment.confirmation.confirmation_url

# --- Handlers ---

@payment_router.message(F.text == "Тарифы")
async def tariffs_handler(message: Message):
    await message.answer("Выберите тариф:", reply_markup=get_tariffs_keyboard())

@payment_router.callback_query(F.data.startswith("tariff_"))
async def tariff_callback_handler(query: CallbackQuery, async_session: AsyncSession, state: FSMContext):
    tariff = query.data.split("_")[1]
    
    if tariff == "custom":
        await state.set_state(CustomAmount.waiting_for_amount)
        await query.message.answer("Введите сумму, которую вы хотите оплатить (минимальная сумма 1500р):")
    else:
        amount = float(tariff)
        confirmation_url = await create_payment(amount, query.from_user.id, async_session)
        await query.message.answer(f"Для оплаты подписки, пожалуйста, перейдите по ссылке: {confirmation_url}")
    
    await query.answer()

@payment_router.message(CustomAmount.waiting_for_amount)
async def custom_amount_handler(message: Message, async_session: AsyncSession, state: FSMContext):
    try:
        amount = float(message.text)
        if amount < 1500:
            await message.answer("Минимальная сумма для оплаты - 1500р. Пожалуйста, введите другую сумму.")
            return
    except ValueError:
        await message.answer("Пожалуйста, введите числовое значение.")
        return

    confirmation_url = await create_payment(amount, message.from_user.id, async_session)
    await message.answer(f"Для оплаты подписки, пожалуйста, перейдите по ссылке: {confirmation_url}")
    await state.clear()

@payment_router.callback_query(F.data.in_({"renew_subscription", "buy_subscription"}))
async def renew_buy_callback_handler(query: CallbackQuery):
    await query.message.answer("Выберите тариф:", reply_markup=get_tariffs_keyboard())
    await query.answer()