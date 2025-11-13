from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton # Added InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select # Added select for fetching payment
from yookassa import Configuration, Payment as YooKassaPayment
import uuid
from datetime import datetime, timedelta

from src.config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, MIN_AMOUNT
from src.models import Payment, PaymentStatus, Subscription, SubscriptionStatus
from src.keyboards.user_keyboards import get_tariffs_keyboard
from src.lexicon import lexicon

payment_router = Router()

Configuration.configure(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)

class CustomAmount(StatesGroup):
    waiting_for_amount = State()

# --- Helper function to create payment ---
async def create_payment(amount: float, user_id: int, async_session: AsyncSession) -> Payment: # Changed return type to Payment
    """
    Creates a subscription and a YooKassa payment, returns the new Payment object.
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
        yookassa_payment = YooKassaPayment.create({ # Renamed variable to avoid conflict
            "amount": {
                "value": str(amount),
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/sever_human_vznos_bot" # TODO: This should be configurable, possibly from config.py
            },
            "capture": True,
            "description": lexicon['payment']['description'].format(user_id=user_id),
            "metadata": {
                "subscription_id": new_subscription.id
            }
        }, idempotence_key)

        # Save payment details to our database
        new_payment = Payment(
            yookassa_id=yookassa_payment.id,
            user_id=user_id,
            status=PaymentStatus.pending,
            subscription_id=new_subscription.id
        )
        session.add(new_payment)
        await session.commit()
        await session.refresh(new_payment) # Refresh to get the ID

        return new_payment # Return the Payment object

# --- Handlers ---

@payment_router.message(F.text == lexicon['buttons']['main_menu']['tariffs'])
async def tariffs_handler(message: Message):
    await message.answer(lexicon['payment']['choose_tariff'], reply_markup=get_tariffs_keyboard())

@payment_router.callback_query(F.data.startswith("tariff_"))
async def tariff_callback_handler(query: CallbackQuery, async_session: AsyncSession, state: FSMContext, bot: Bot): # Added bot
    tariff = query.data.split("_")[1]
    
    if tariff == "custom":
        await state.set_state(CustomAmount.waiting_for_amount)
        await query.message.answer(lexicon['payment']['enter_custom_amount'].format(min_amount=MIN_AMOUNT))
    else:
        amount = float(tariff)
        new_payment = await create_payment(amount, query.from_user.id, async_session) # Get Payment object
        
        check_payment_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=lexicon['buttons']['payment_check'], url=new_payment.yookassa_id)] # Changed to URL for direct payment
            ]
        )
        
        sent_message = await query.message.answer(
            lexicon['payment']['payment_link_message'].format(confirmation_url=new_payment.yookassa_id), # Use yookassa_id as confirmation_url
            reply_markup=check_payment_keyboard
        )
        
        async with async_session() as session: # New session for updating payment
            payment_to_update = await session.get(Payment, new_payment.id)
            if payment_to_update:
                payment_to_update.bot_message_id = sent_message.message_id
                await session.commit()
    
    await query.answer()

@payment_router.message(CustomAmount.waiting_for_amount)
async def custom_amount_handler(message: Message, async_session: AsyncSession, state: FSMContext, bot: Bot): # Added bot
    try:
        amount = float(message.text)
        if amount < MIN_AMOUNT:
            await message.answer(lexicon['payment']['min_amount_error'].format(min_amount=MIN_AMOUNT))
            return
    except ValueError:
        await message.answer(lexicon['payment']['invalid_amount_error'])
        return

    new_payment = await create_payment(amount, message.from_user.id, async_session) # Get Payment object
    
    check_payment_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=lexicon['buttons']['payment_check'], url=new_payment.yookassa_id)] # Changed to URL for direct payment
        ]
    )
    
    sent_message = await message.answer(
        lexicon['payment']['payment_link_message'].format(confirmation_url=new_payment.yookassa_id), # Use yookassa_id as confirmation_url
        reply_markup=check_payment_keyboard
    )
    
    async with async_session() as session: # New session for updating payment
        payment_to_update = await session.get(Payment, new_payment.id)
        if payment_to_update:
            payment_to_update.bot_message_id = sent_message.message_id
            await session.commit()
            
    await state.clear()

@payment_router.callback_query(F.data.in_({"renew_subscription", "buy_subscription"}))
async def renew_buy_callback_handler(query: CallbackQuery):
    await query.message.answer(lexicon['payment']['choose_tariff'], reply_markup=get_tariffs_keyboard())
    await query.answer()

@payment_router.callback_query(F.data == "renew_subscription_from_warning")
async def renew_from_warning_callback_handler(query: CallbackQuery):
    await query.message.answer(lexicon['payment']['choose_tariff'], reply_markup=get_tariffs_keyboard())
    await query.answer()

@payment_router.callback_query(F.data.startswith("check_payment_"))
async def check_payment_callback_handler(query: CallbackQuery, async_session: AsyncSession, bot: Bot):
    payment_id = int(query.data.split("_")[2])
    
    async with async_session() as session:
        payment = await session.get(Payment, payment_id)
        
        if not payment:
            await query.answer("Платеж не найден.", show_alert=True)
            return
            
        if payment.status == PaymentStatus.succeeded:
            await query.answer("Платеж уже успешно обработан!", show_alert=True)
            return
            
        try:
            yookassa_payment_info = YooKassaPayment.find_one(payment.yookassa_id)
            
            if yookassa_payment_info.status == 'succeeded':
                # This case should ideally be handled by webhook, but good to have a fallback
                # The webhook handler will update the subscription and send invite link
                await query.answer("Платеж успешно завершен! Ожидайте ссылку-приглашение.", show_alert=True)
            elif yookassa_payment_info.status == 'pending':
                await query.answer("Платеж все еще в обработке. Пожалуйста, подождите.", show_alert=True)
            elif yookassa_payment_info.status == 'canceled' or yookassa_payment_info.status == 'failed':
                await query.answer("Платеж отменен или не удался. Пожалуйста, попробуйте снова.", show_alert=True)
            else:
                await query.answer(f"Статус платежа: {yookassa_payment_info.status}", show_alert=True)
                
        except Exception as e:
            logging.error(f"Error checking payment status for payment_id {payment_id}: {e}")
            await query.answer("Произошла ошибка при проверке статуса платежа.", show_alert=True)
            
    await query.answer()