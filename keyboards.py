from aiogram.types import (
    ReplyKeyboardMarkup, 
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
def get_user_keyboard(has_subscription: bool):
    """Клавиатура для пользователя с учетом статуса подписки"""
    if has_subscription:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📖 Инструкция", callback_data='instruction_from_vpn')],
            [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data='renew_sub')]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оформить подписку", callback_data='subscribe')]
        ])

def get_profile_keyboard(has_subscription: bool):
    """Клавиатура для профиля пользователя"""
    buttons = []
    
    if has_subscription:
        buttons.append([InlineKeyboardButton(text="🔄 Продлить подписку", callback_data='renew_sub')])
    else:
        buttons.append([InlineKeyboardButton(text="💳 Оформить подписку", callback_data='subscribe_from_profile')])
    
    # Добавляем кнопку рефералов в любом случае
    buttons.append([InlineKeyboardButton(text="🤝 Партнерская программа", callback_data='referrals')])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)
def create_main_keyboard():
    """Основная клавиатура"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🌐Активировать VPN")],
            [KeyboardButton(text="👾Аккаунт"), KeyboardButton(text="🔒О VPN")]
        ],
        resize_keyboard=True
    )

def get_subscription_keyboard(show_special: bool = False):
    """Клавиатура выбора подписки"""
    buttons = []
    
    # Специальная подписка для новых пользователей
    if show_special:
        buttons.append([
            InlineKeyboardButton(text="7 дней - 1₽", callback_data="sub_special")
        ])
    
    # Обычные подписки (по 2 на строку)
    buttons.extend([
        [
            InlineKeyboardButton(text="1 месяц - 99₽", callback_data="sub_1"),
            InlineKeyboardButton(text="3 месяца - 279₽", callback_data="sub_3")
        ],
        [
            InlineKeyboardButton(text="6 месяцев - 549₽", callback_data="sub_6"),
            InlineKeyboardButton(text="12 месяцев - 999₽", callback_data="sub_12")
        ]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_payment_check_keyboard(payment_id: str):
    """Клавиатура для проверки платежа"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔄 Проверить оплату",
                callback_data=f"check_pay:{payment_id}"
            )],
            [InlineKeyboardButton(
                text="🧑‍💻 Поддержка",
                url="https://t.me/xmakedon"
            )]
        ]
    )