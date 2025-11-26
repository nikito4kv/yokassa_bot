from aiogram import Router, Bot, html, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select
from yookassa import Configuration, Payment as YooKassaPayment
import uuid
from datetime import datetime, timedelta
import logging

from src.config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, MIN_AMOUNT, ADMIN_IDS
from src.models import Payment, PaymentStatus, Subscription, SubscriptionStatus, ManualPayment
from src.keyboards.user_keyboards import get_tariffs_keyboard, get_payment_confirmation_keyboard
from src.lexicon import lexicon
from src.logic import get_system_settings, process_successful_payment

payment_router = Router()

Configuration.configure(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)

# --- FSM States ---
class CustomAmount(StatesGroup):
    waiting_for_amount = State()

class FSMCreatePayment(StatesGroup):
    confirming_payment = State()

class ManualPaymentFSM(StatesGroup):
    waiting_for_screenshot = State()

# --- Constants & Helpers ---
TARIFF_DURATIONS = {
    1500.0: timedelta(days=30),
    2900.0: timedelta(days=30),
    3900.0: timedelta(days=30),
    4900.0: timedelta(days=30),
}

async def create_payment(amount: float, user_id: int, async_session: AsyncSession, bot: Bot, duration: timedelta) -> tuple[Payment, str]:
    """
    Creates a subscription and a YooKassa payment, returns the new Payment object and confirmation URL.
    """
    async with async_session() as session:
        end_date = datetime.now() + duration
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

        idempotence_key = str(uuid.uuid4())
        bot_user = await bot.get_me()
        return_url = f"https://t.me/{bot_user.username}"
        
        yookassa_payment = YooKassaPayment.create({
            "amount": {"value": str(amount), "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "capture": True,
            "description": lexicon['payment']['description'].format(user_id=user_id),
            "metadata": {"subscription_id": new_subscription.id}
        }, idempotence_key)

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

async def proceed_to_payment_confirmation(message: Message, amount: float, state: FSMContext, duration: timedelta, active_subscription: Subscription | None = None):
    """
    Sends the payment confirmation message and sets the state.
    """
    duration_str = f"{duration.days} дней" if duration.days > 0 else "бессрочно"
    
    confirmation_text = lexicon['payment']['payment_confirmation'].format(duration=duration_str, amount=int(amount))

    if active_subscription and active_subscription.end_date > datetime.now():
        confirmation_text += "\n\n" + lexicon['payment']['overwrite_warning'].format(end_date=active_subscription.end_date.strftime("%d.%m.%Y"))
    
    await state.set_state(FSMCreatePayment.confirming_payment)
    await state.update_data(amount=amount, duration=duration)

    await message.answer(
        confirmation_text,
        reply_markup=get_payment_confirmation_keyboard(),
        parse_mode="HTML"
    )

# --- Handlers ---

@payment_router.message(Command('plans'))
@payment_router.message(F.text == lexicon['buttons']['main_menu']['tariffs'])
async def tariffs_handler(message: Message):
    await message.answer(lexicon['payment']['choose_tariff'], reply_markup=get_tariffs_keyboard())

@payment_router.callback_query(F.data.startswith("tariff_"))
async def tariff_callback_handler(query: CallbackQuery, async_session: AsyncSession, state: FSMContext):
    await query.message.delete() # Remove the tariffs keyboard
    tariff = query.data.split("_")[1]
    
    if tariff == "custom":
        await state.set_state(CustomAmount.waiting_for_amount)
        await query.message.answer(lexicon['payment']['enter_custom_amount'].format(min_amount=MIN_AMOUNT))
        await query.answer()
        return

    amount = float(tariff)
    duration = TARIFF_DURATIONS.get(amount, timedelta(days=30)) # Default to 30 days if not found

    async with async_session() as session:
        active_subscription = (await session.execute(
            select(Subscription)
            .filter_by(user_id=query.from_user.id, status=SubscriptionStatus.active)
            .order_by(Subscription.end_date.desc())
        )).scalar_one_or_none()

        if active_subscription and active_subscription.end_date > datetime.now():
            await proceed_to_payment_confirmation(query.message, amount, state, duration, active_subscription)
        else:
            await proceed_to_payment_confirmation(query.message, amount, state, duration)
    
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
    
    await state.clear() # Clear CustomAmount state before proceeding
    duration = timedelta(days=30) # Default duration for custom amounts

    async with async_session() as session:
        active_subscription = (await session.execute(
            select(Subscription)
            .filter_by(user_id=message.from_user.id, status=SubscriptionStatus.active)
            .order_by(Subscription.end_date.desc())
        )).scalar_one_or_none()

        if active_subscription and active_subscription.end_date > datetime.now():
            await proceed_to_payment_confirmation(message, amount, state, duration, active_subscription)
        else:
            await proceed_to_payment_confirmation(message, amount, state, duration)

@payment_router.callback_query(F.data == "confirm_payment", FSMCreatePayment.confirming_payment)
async def confirm_payment_callback_handler(query: CallbackQuery, async_session: AsyncSession, state: FSMContext, bot: Bot):
    data = await state.get_data()
    amount = data.get("amount")
    duration = data.get("duration")

    if not amount or not duration:
        await query.message.edit_text("Произошла ошибка. Пожалуйста, попробуйте снова.")
        await state.clear()
        await query.answer()
        return

    # Check payment mode
    async with async_session() as session:
        settings = await get_system_settings(session)
        is_manual = settings.manual_payment_enabled

    if is_manual:
        await state.set_state(ManualPaymentFSM.waiting_for_screenshot)
        # Data (amount, duration) is preserved in FSMContext
        
        details_text = lexicon['payment']['manual_payment_details'].format(amount=int(amount))
        
        await query.message.edit_text(
            f"{details_text}\n\n{lexicon['payment']['send_screenshot']}",
            parse_mode="HTML",
            reply_markup=None
        )
        await query.answer()
        return

    new_payment, confirmation_url = await create_payment(amount, query.from_user.id, async_session, bot, duration)
    
    payment_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=lexicon['buttons']['pay'], url=confirmation_url)],
            [InlineKeyboardButton(text=lexicon['buttons']['payment_check'], callback_data=f"check_payment_{new_payment.id}")]
        ]
    )
    
    sent_message = await query.message.edit_text(
        lexicon['payment']['payment_link_message'],
        reply_markup=payment_keyboard
    )
    
    async with async_session() as session_update:
        payment_to_update = await session_update.get(Payment, new_payment.id)
        if payment_to_update:
            payment_to_update.bot_message_id = sent_message.message_id
            await session_update.commit()
            
    await state.clear()
    await query.answer()

@payment_router.callback_query(F.data == "cancel_payment", FSMCreatePayment.confirming_payment)
async def cancel_payment_callback_handler(query: CallbackQuery, state: FSMContext):
    await query.message.edit_text(lexicon['payment']['overwrite_cancelled'])
    await state.clear()
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
                if payment.status != PaymentStatus.succeeded:
                    await process_successful_payment(bot, async_session, payment_id=payment.id)
                    await query.answer("Платеж подтвержден! Ссылка отправлена.", show_alert=True)
                else:
                    await query.answer("Платеж уже успешно обработан!", show_alert=True)
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

@payment_router.message(ManualPaymentFSM.waiting_for_screenshot, F.photo | F.document)
async def manual_payment_screenshot_handler(message: Message, state: FSMContext, bot: Bot, async_session: async_sessionmaker[AsyncSession]):
    data = await state.get_data()
    amount = data.get("amount")
    duration = data.get("duration")
    
    if not amount:
        await message.answer("Ошибка состояния. Попробуйте заново выбрать тариф.")
        await state.clear()
        return

    async with async_session() as session:
        end_date = datetime.now() + duration
        new_subscription = Subscription(
            user_id=message.from_user.id,
            end_date=end_date,
            status=SubscriptionStatus.pending,
            amount_paid=amount,
            start_date=datetime.now()
        )
        session.add(new_subscription)
        await session.commit()
        await session.refresh(new_subscription)
        
        new_payment = Payment(
            yookassa_id=None, 
            user_id=message.from_user.id,
            status=PaymentStatus.manual_review,
            subscription_id=new_subscription.id
        )
        session.add(new_payment)
        await session.commit()
        await session.refresh(new_payment)
        
        if message.photo:
            photo_id = message.photo[-1].file_id
        elif message.document:
            photo_id = message.document.file_id
        else:
            photo_id = "unknown"

        manual_payment = ManualPayment(
            user_id=message.from_user.id,
            photo_id=photo_id,
        )
        session.add(manual_payment)
        await session.commit()
        
        admin_text = lexicon['payment']['admin_new_payment'].format(
            user=message.from_user.full_name,
            user_id=message.from_user.id,
            amount=amount,
            duration=f"{duration.days} дней"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=lexicon['buttons']['admin_confirm_payment'], callback_data=f"admin_confirm_payment_{new_payment.id}"),
                InlineKeyboardButton(text=lexicon['buttons']['admin_reject_payment'], callback_data=f"admin_reject_payment_{new_payment.id}")
            ]
        ])
        
        for admin_id in ADMIN_IDS:
            try:
                if message.photo:
                    await bot.send_photo(chat_id=admin_id, photo=photo_id, caption=admin_text, reply_markup=keyboard)
                else:
                    await bot.send_document(chat_id=admin_id, document=photo_id, caption=admin_text, reply_markup=keyboard)
            except Exception as e:
                logging.error(f"Failed to send manual payment notification to admin {admin_id}: {e}")

    await message.answer(lexicon['payment']['screenshot_received'])
    await state.clear()