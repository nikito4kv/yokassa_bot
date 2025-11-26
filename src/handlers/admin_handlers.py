from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
import logging

from src.models import Payment, PaymentStatus, User
from src.config import ADMIN_IDS
from src.lexicon import lexicon
from src.logic import process_successful_payment, get_system_settings

admin_router = Router()

@admin_router.message(Command("toggle_manual_payment"), F.from_user.id.in_(ADMIN_IDS))
async def toggle_manual_payment(message: Message, async_session: async_sessionmaker[AsyncSession]):
    async with async_session() as session:
        settings = await get_system_settings(session)
        settings.manual_payment_enabled = not settings.manual_payment_enabled
        await session.commit()
        
        if settings.manual_payment_enabled:
            await message.answer(lexicon['admin']['mode_switched_manual'])
        else:
            await message.answer(lexicon['admin']['mode_switched_yookassa'])

@admin_router.callback_query(F.data.startswith("admin_confirm_payment_"), F.from_user.id.in_(ADMIN_IDS))
async def admin_confirm_payment_handler(query: CallbackQuery, bot: Bot, async_session: async_sessionmaker[AsyncSession]):
    try:
        payment_id = int(query.data.split("_")[3])
    except (IndexError, ValueError):
        await query.answer("Ошибка в данных кнопки", show_alert=True)
        return
    
    async with async_session() as session:
        payment = await session.get(Payment, payment_id)
        if not payment:
            await query.answer("Платеж не найден", show_alert=True)
            return
            
        if payment.status == PaymentStatus.succeeded:
            await query.answer("Платеж уже подтвержден", show_alert=True)
            return

    # Process payment (activates subscription etc.)
    await process_successful_payment(bot, async_session, payment_id=payment_id)
    
    # Notify user manually
    async with async_session() as session:
        payment = await session.get(Payment, payment_id) # Re-fetch
        try:
             await bot.send_message(payment.user_id, lexicon['payment']['payment_confirmed_notification'])
        except Exception as e:
             logging.error(f"Failed to notify user {payment.user_id}: {e}")

    # Update admin message
    admin_name = query.from_user.full_name
    new_text = f"{query.message.caption}\n\n{lexicon['admin']['payment_confirmed'].format(admin_name=admin_name)}"
    await query.message.edit_caption(caption=new_text, reply_markup=None)
    await query.answer("Подтверждено")

@admin_router.callback_query(F.data.startswith("admin_reject_payment_"), F.from_user.id.in_(ADMIN_IDS))
async def admin_reject_payment_handler(query: CallbackQuery, bot: Bot, async_session: async_sessionmaker[AsyncSession]):
    try:
        payment_id = int(query.data.split("_")[3])
    except (IndexError, ValueError):
        await query.answer("Ошибка в данных кнопки", show_alert=True)
        return

    async with async_session() as session:
        payment = await session.get(Payment, payment_id)
        if not payment:
            await query.answer("Платеж не найден", show_alert=True)
            return
        
        if payment.status == PaymentStatus.succeeded:
            await query.answer("Платеж уже подтвержден, нельзя отклонить", show_alert=True)
            return
            
        payment.status = PaymentStatus.rejected
        await session.commit()
        
        # Notify user
        try:
             await bot.send_message(payment.user_id, lexicon['payment']['payment_rejected_notification'])
        except Exception as e:
             logging.error(f"Failed to notify user {payment.user_id}: {e}")

    # Update admin message
    admin_name = query.from_user.full_name
    new_text = f"{query.message.caption}\n\n{lexicon['admin']['payment_rejected'].format(admin_name=admin_name)}"
    await query.message.edit_caption(caption=new_text, reply_markup=None)
    await query.answer("Отклонено")
