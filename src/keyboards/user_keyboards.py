from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from src.lexicon import lexicon

def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Returns the main menu keyboard.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=lexicon['buttons']['main_menu']['tariffs']),
                KeyboardButton(text=lexicon['buttons']['main_menu']['my_subscription']),
            ],
            [
                KeyboardButton(text=lexicon['buttons']['main_menu']['help']),
            ]
        ],
        resize_keyboard=True,
    )

def get_tariffs_keyboard() -> InlineKeyboardMarkup:
    """
    Returns the tariff selection keyboard.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1500р - 1 месяц", callback_data="tariff_1500")],
            [InlineKeyboardButton(text="2900р - 1 месяц", callback_data="tariff_2900")],
            [InlineKeyboardButton(text="3900р - 1 месяц", callback_data="tariff_3900")],
            [InlineKeyboardButton(text="4900р - 1 месяц", callback_data="tariff_4900")],
            [InlineKeyboardButton(text=lexicon['buttons']['tariffs_menu']['custom_amount'], callback_data="tariff_custom")],
        ]
    )

def get_my_subscription_keyboard(is_active: bool) -> InlineKeyboardMarkup:
    """
    Returns the keyboard for the 'My Subscription' section.
    """
    if is_active:
        button_text = lexicon['buttons']['my_subscription_menu']['renew_subscription']
        callback_data = "renew_subscription"
    else:
        button_text = lexicon['buttons']['my_subscription_menu']['buy_subscription']
        callback_data = "buy_subscription"
        
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_text, callback_data=callback_data)]
        ]
    )

def get_payment_confirmation_keyboard() -> InlineKeyboardMarkup:
    """
    Returns the keyboard for payment confirmation.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=lexicon['buttons']['pay'], callback_data="confirm_payment"),
                InlineKeyboardButton(text=lexicon['buttons']['confirm_cancel'], callback_data="cancel_payment")
            ]
        ]
    )