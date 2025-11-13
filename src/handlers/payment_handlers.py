from aiogram import Router, Bot, html, F # Added html
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from yookassa import Configuration, Payment as YooKassaPayment
import uuid
from datetime import datetime, timedelta
import logging

from src.config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, MIN_AMOUNT
from src.models import Payment, PaymentStatus, Subscription, SubscriptionStatus
from src.keyboards.user_keyboards import get_tariffs_keyboard
from src.lexicon import lexicon

payment_router = Router()

Configuration.configure(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)

class CustomAmount(StatesGroup):
    waiting_for_amount = State()

class ConfirmOverwrite(StatesGroup): # New FSM state for confirmation
    waiting_for_confirmation = State()
    tariff_data = {} # To store tariff data temporarily

# --- Helper function to create payment ---
async def create_payment(amount: float, user_id: int, async_session: AsyncSession) -> tuple[Payment, str]:
    """
    Creates a subscription and a YooKassa payment, returns the new Payment object and confirmation URL.
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
        yookassa_payment = YooKassaPayment.create({
            "amount": {
                "value": str(amount),
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me/sever_human_vznos_bot" # TODO: This should be configurable
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
        await session.refresh(new_payment)

        return new_payment, yookassa_payment.confirmation.confirmation_url

# --- Handlers ---

@payment_router.message(F.text == lexicon['buttons']['main_menu']['tariffs'])
async def tariffs_handler(message: Message):
    await message.answer(lexicon['payment']['choose_tariff'], reply_markup=get_tariffs_keyboard())

@payment_router.callback_query(F.data.startswith("tariff_"))
async def tariff_callback_handler(query: CallbackQuery, async_session: AsyncSession, state: FSMContext):
    tariff = query.data.split("_")[1]
    amount = float(tariff) if tariff != "custom" else None # Store amount if not custom

    async with async_session() as session:
        active_subscription = await session.execute(
            select(Subscription)
            .filter_by(user_id=query.from_user.id, status=SubscriptionStatus.active)
            .order_by(Subscription.end_date.desc())
        )
        active_subscription = active_subscription.scalar_one_or_none()

        if active_subscription and active_subscription.end_date > datetime.now():
            # User has an active subscription, ask for confirmation
            confirm_keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text=lexicon['buttons']['confirm_yes'], callback_data="confirm_overwrite_yes"),
                        InlineKeyboardButton(text=lexicon['buttons']['confirm_cancel'], callback_data="confirm_overwrite_no")
                    ]
                ]
            )
            await state.set_state(ConfirmOverwrite.waiting_for_confirmation)
            await state.update_data(tariff=tariff, amount=amount) # Store chosen tariff/amount
            
            await query.message.answer(
                lexicon['payment']['confirm_overwrite'].format(end_date=active_subscription.end_date.strftime("%d.%m.%Y")),
                reply_markup=confirm_keyboard,
                parse_mode="HTML" # Ensure HTML formatting for bold text
            )
        else:
            # No active subscription, proceed directly
            if tariff == "custom":
                await state.set_state(CustomAmount.waiting_for_amount)
                await query.message.answer(lexicon['payment']['enter_custom_amount'].format(min_amount=MIN_AMOUNT))
            else:
                new_payment, confirmation_url = await create_payment(amount, query.from_user.id, async_session)
                
                payment_keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text=lexicon['buttons']['pay'], url=confirmation_url)],
                        [InlineKeyboardButton(text=lexicon['buttons']['payment_check'], callback_data=f"check_payment_{new_payment.id}")]
                    ]
                )
                
                sent_message = await query.message.answer(
                    lexicon['payment']['payment_link_message'],
                    reply_markup=payment_keyboard
                )
                
                async with async_session() as session_update: # Use a new session for update
                    payment_to_update = await session_update.get(Payment, new_payment.id)
                    if payment_to_update:
                        payment_to_update.bot_message_id = sent_message.message_id
                        await session_update.commit()
    
    await query.answer()

@payment_router.message(CustomAmount.waiting_for_amount)
async def custom_amount_handler(message: Message, async_session: AsyncSession, state: FSMContext):
    try:
        amount = float(message.text)
        if amount < MIN_AMOUNT:
            await message.answer(lexicon['payment']['min_amount_error'].format(min_amount=MIN_AMOUNT))
            return
    except ValueError:
        await message.answer(lexicon['payment']['invalid_amount_error'])
        return

    async with async_session() as session:
        active_subscription = await session.execute(
            select(Subscription)
            .filter_by(user_id=message.from_user.id, status=SubscriptionStatus.active)
            .order_by(Subscription.end_date.desc())
        )
        active_subscription = active_subscription.scalar_one_or_none()

        if active_subscription and active_subscription.end_date > datetime.now():
            # User has an active subscription, ask for confirmation
            confirm_keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text=lexicon['buttons']['confirm_yes'], callback_data="confirm_overwrite_yes"),
                        InlineKeyboardButton(text=lexicon['buttons']['confirm_cancel'], callback_data="confirm_overwrite_no")
                    ]
                ]
            )
            await state.set_state(ConfirmOverwrite.waiting_for_confirmation)
            await state.update_data(tariff="custom", amount=amount) # Store chosen tariff/amount
            
            await message.answer(
                lexicon['payment']['confirm_overwrite'].format(end_date=active_subscription.end_date.strftime("%d.%m.%Y")),
                reply_markup=confirm_keyboard,
                parse_mode="HTML"
            )
        else:
            # No active subscription, proceed directly
            new_payment, confirmation_url = await create_payment(amount, message.from_user.id, async_session)
            
            payment_keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=lexicon['buttons']['pay'], url=confirmation_url)],
                    [InlineKeyboardButton(text=lexicon['buttons']['payment_check'], callback_data=f"check_payment_{new_payment.id}")]
                ]
            )
            
            sent_message = await message.answer(
                lexicon['payment']['payment_link_message'],
                reply_markup=payment_keyboard
            )
            
            async with async_session() as session_update: # Use a new session for update
                payment_to_update = await session_update.get(Payment, new_payment.id)
                if payment_to_update:
                    payment_to_update.bot_message_id = sent_message.message_id
                    await session_update.commit()
                
            await state.clear() # Clear CustomAmount state

@payment_router.callback_query(F.data == "confirm_overwrite_yes", ConfirmOverwrite.waiting_for_confirmation)
async def process_overwrite_confirmation_yes(query: CallbackQuery, async_session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    tariff = data.get("tariff")
    amount = data.get("amount")

    if not tariff or not amount:
        await query.message.answer("Произошла ошибка. Пожалуйста, попробуйте снова.")
        await state.clear()
        await query.answer()
        return

    # Proceed with payment creation
    new_payment, confirmation_url = await create_payment(amount, query.from_user.id, async_session)
    
    payment_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=lexicon['buttons']['pay'], url=confirmation_url)],
            [InlineKeyboardButton(text=lexicon['buttons']['payment_check'], callback_data=f"check_payment_{new_payment.id}")]
        ]
    )
    
    sent_message = await query.message.answer(
        lexicon['payment']['payment_link_message'],
        reply_markup=payment_keyboard
    )
    
    async with async_session() as session_update: # Use a new session for update
        payment_to_update = await session_update.get(Payment, new_payment.id)
        if payment_to_update:
            payment_to_update.bot_message_id = sent_message.message_id
            await session_update.commit()
            
    await state.clear() # Clear confirmation state
    await query.answer()

@payment_router.callback_query(F.data == "confirm_overwrite_no", ConfirmOverwrite.waiting_for_confirmation)
async def process_overwrite_confirmation_no(query: CallbackQuery, state: FSMContext):
    await query.message.answer(lexicon['payment']['overwrite_cancelled'])
    await state.clear() # Clear confirmation state
    await query.answer()

@payment_router.callback_query(F.data.in_({"renew_subscription", "buy_subscription"}))
async def renew_buy_callback_handler(query: CallbackQuery):
    await query.message.answer(lexicon['payment']['choose_tariff'], reply_markup=get_tariffs_keyboard())
    await query.answer()

@payment_router.callback_query(F.data == "renew_subscription_from_warning")
async def renew_from_warning_callback_handler(query: CallbackQuery):
    await query.message.answer(lexicon['payment']['choose_tariff'], reply_markup=get_tariffs_keyboard())
    await query.answer()

@payment_router.callback_query(F.data.startswith("check_payment_"))
async def check_payment_callback_handler(query: CallbackQuery, async_session: AsyncSession):
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