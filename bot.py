import logging
import asyncio
import aiohttp
from aiogram import types, F, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, LabeledPrice
from datetime import datetime

from config import TOKEN, WELCOME_GIF_URL, STARS_PROVIDER_TOKEN, ADMIN_IDS, PRICES, CHANNEL_ID
from database import (
    init_db, check_user_payment, add_payment, get_user_data, add_bot_user,
    get_users_expiring_in_days, get_all_users_expiring_in_days, 
    mark_user_notified, has_paid_subscription
)
from payment import create_payment, check_payment_status, cancel_all_payment_tasks
from yookassa import Payment
from keyboards import (
    create_main_keyboard, get_subscription_keyboard, get_profile_keyboard, get_user_keyboard
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
from admin_panel import register_admin_handlers
dp = Dispatcher()
register_admin_handlers(dp)

def get_price_for_period(period: str) -> int:
    """Возвращает цену для указанного периода"""
    if period == 'special':
        return 10
    return PRICES.get(period, PRICES['1']) // 100

# Стоимость подписки в звёздах (1 звезда ≈ 1₽)
STARS_PRICES = {
    'special': 10,  # ~10₽
    '1': 99,   # 99₽ за месяц
    '3': 279,  # 279₽ за 3 месяца
    '6': 549,  # 549₽ за 6 месяцев
    '12': 999  # 999₽ за год
}

def get_stars_price(period: str) -> int:
    """Возвращает количество звёзд для указанного периода"""
    return STARS_PRICES.get(period, STARS_PRICES['1'])

async def check_subscription(user_id: int) -> bool:
    """Проверяет подписку пользователя на канал"""
    try:
        if user_id in ADMIN_IDS:
            return True
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return False

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Единственный обработчик команды /start"""
    user = message.from_user
    
    
    success = await add_bot_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    if success:
        logging.info(f"Пользователь {user.id} ({user.first_name}) добавлен в базу бота")
    else:
        logging.error(f"Ошибка добавления пользователя {user.id} в базу бота")
    
    welcome_text = f"""🌍 Добро пожаловать в <b>Shard VPN!</b>

Свобода интернета без ограничений, блокировок и замедлений. С <b>Shard VPN</b> ты получаешь:
• ⚡️ Молниеносную скорость
• 🔒 Надёжную защиту
• 🌐 Доступ к любым сервисам без границ

<blockquote><i>💳Купи подписку и получи полный доступ к интернету без ограничений!</i></blockquote>"""
    
    await message.answer_animation(
        animation=WELCOME_GIF_URL,
        caption=welcome_text,
        reply_markup=create_main_keyboard()
    )



async def get_vpn_info(user_id: int):
    """Получает информацию о VPN для пользователя"""
    user_data = await get_user_data(user_id)
    has_paid = await check_user_payment(user_id)
    
    if not user_data:
        return None, None, None
    
    expiry_date, config = user_data
    is_active = has_paid

    # Получаем sub_key от сервера
    timeout = aiohttp.ClientTimeout(total=10)
    headers = {"X-API-Key": "18181818", "Accept": "application/json"}
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"https://shardtg.ru/sub/{user_id}", headers=headers) as resp:
                if resp.status != 200:
                    return None, None, None
                data = await resp.json()
    except Exception:
        return None, None, None

    sub_key = data.get("sub_key")
    if not sub_key:
        return None, None, None

    miniapp_link = f"https://shardtg.ru/subscription/{sub_key}"
    return miniapp_link, expiry_date, is_active

async def send_vpn_message(message_or_callback, user_id: int, is_edit: bool = False):
    """Отправляет или редактирует сообщение с информацией о VPN"""
    vpn_info = await get_vpn_info(user_id)
    
    if vpn_info[0] is None:
        if is_edit:
            await message_or_callback.message.edit_text("Не удалось получить информацию о VPN. Попробуйте позже.")
        else:
            await message_or_callback.answer("Не удалось получить информацию о VPN. Попробуйте позже.")
        return

    miniapp_link, expiry_date, is_active = vpn_info

    if is_active:
        text = f"""<b>🌐 Shard VPN</b>

<b>🔗 Ключ:</b>
<code>{miniapp_link}</code>

📌Статус подписки - <b>Активна 🟢</b>
⏳Действует до - <b>{expiry_date}</b>

<blockquote><i>💡 Нажмите "Инструкция" для подключения.</i></blockquote>"""
    else:
        text = f"""<b>🌐 Shard VPN</b>

<b>🔗 Ключ:</b>
<code>{miniapp_link}</code>

Статус подписки - <b>не Активна 🔴</b>

<blockquote><i>💡 Для использования VPN продлите подписку.</i></blockquote>"""

    if is_edit:
        await message_or_callback.message.edit_text(
            text, reply_markup=get_user_keyboard(True), 
            parse_mode="HTML", disable_web_page_preview=True
        )
    else:
        await message_or_callback.answer(
            text, reply_markup=get_user_keyboard(True), 
            parse_mode="HTML", disable_web_page_preview=True
        )

@dp.message(F.text == "🌐Активировать VPN")
async def connect_vpn(message: Message):
    user_id = message.from_user.id
    user_data = await get_user_data(user_id)
    
    if not user_data:
        return await show_subscription_options(message)
    
    await send_vpn_message(message, user_id)
                                                
async def show_subscription_options(message: Message):
    """Показывает варианты подписки"""
    user_id = message.from_user.id
    
    # Проверяем, была ли у пользователя платная подписка
    has_paid = await has_paid_subscription(user_id)
    
    # Проверяем, есть ли данные о подписке (для истекших подписок)
    user_data = await get_user_data(user_id)
    
    # Показываем специальную подписку только для новых пользователей (без платежей и без данных)
    show_special = not has_paid and not user_data
    
    if user_data and not has_paid:
        # Истекшая подписка
        text = """<b>👨🏻‍💻Ваша подписка истекла — продлите её:</b>

<blockquote><i>🔐 Быстрый, стабильный и защищённый VPN.</i></blockquote>
"""
    else:
        # Новая подписка
        text = """<b>👨🏻‍💻Чтобы подключиться — выбери подписку:</b>

<blockquote><i>🔐 Быстрый, стабильный и защищённый VPN.</i></blockquote>
"""
    
    await message.answer(
        text=text,
        reply_markup=get_subscription_keyboard(show_special),
    )

@dp.callback_query(F.data.startswith('sub_'))
async def subscription_callback(callback: types.CallbackQuery):
    """Обработчик выбора подписки"""
    try:
        period = callback.data.split('_')[1]
        
        payment_info = await create_payment(period, callback.from_user.id)
        if not payment_info:
            await callback.answer("Ошибка при создании платежа", show_alert=True)
            return
        
        # Формируем данные для проверки платежа в виде словаря
        payment_data = {
            'payment_id': payment_info['payment_id'],
            'user_id': callback.from_user.id,
            'message_id': callback.message.message_id,
            'chat_id': callback.message.chat.id,
            'period': payment_info['period']
        }
        
        # Правильный вызов функции с 2 аргументами
        asyncio.create_task(check_payment_status(payment_data, bot))
        
        pay_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="💳 Оплатить ЮKassa",
                url=payment_info['confirmation_url']
            )],
            [InlineKeyboardButton(
                text="🌟 Оплатить Stars",
                callback_data=f"pay_stars_{period}"
            )],
            [InlineKeyboardButton(
                text="🔙 Назад",
                callback_data="back"
            )]
        ])

        # Определяем текст в зависимости от типа подписки
        if period == 'special':
            period_text = "7 дней"
        else:
            period_text = f"{period} мес."
        
        await callback.message.edit_text(
            text=f'''<b>🗓 Вы выбрали подписку на {period_text}</b>

<b>💰Сумма к оплате:</b> {get_price_for_period(period)}₽

<blockquote><i>Нажмите кнопку ниже для перехода к оплате:</i></blockquote>

            ''',
            reply_markup=pay_keyboard
        )
        
    except Exception as e:
        logger.error(f"Ошибка в обработчике подписки: {e}")
        await callback.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)

@dp.callback_query(F.data == 'back')
async def back_to_subscriptions(callback: types.CallbackQuery):
    """Возврат к выбору подписки"""
    try:
        user_id = callback.from_user.id
        
        # Проверяем, была ли у пользователя платная подписка
        has_paid = await has_paid_subscription(user_id)
        
        # Проверяем, есть ли данные о подписке (для истекших подписок)
        user_data = await get_user_data(user_id)
        
        # Показываем специальную подписку только для новых пользователей (без платежей и без данных)
        show_special = not has_paid and not user_data
        
        if user_data and not has_paid:
            # Истекшая подписка
            text = """<b>👨🏻‍💻Ваша подписка истекла — продлите её:</b>

<blockquote><i>🔐 Быстрый, стабильный и защищённый VPN.</i></blockquote>
"""
        else:
            # Новая подписка
            text = """<b>👨🏻‍💻Чтобы подключиться — выбери подписку:</b>

<blockquote><i>🔐 Быстрый, стабильный и защищённый VPN.</i></blockquote>
"""
        
        await callback.message.edit_text(
            text=text,
            reply_markup=get_subscription_keyboard(show_special)
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при возврате к подпискам: {e}")
        await callback.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)
        
@dp.callback_query(F.data.startswith('check_pay:'))
async def check_payment_callback(callback: types.CallbackQuery):
    """Ручная проверка платежа"""
    payment_id = callback.data.split(':')[1]
    
    try:
        payment = await Payment.find_one(payment_id)
        
        if payment.status == "succeeded":
            await callback.answer("Оплата уже подтверждена!", show_alert=True)
        elif payment.status == "pending":
            await callback.answer(
                "Оплата еще не прошла. Попробуйте позже.",
                show_alert=True
            )
        else:
            await callback.answer(
                f"Статус платежа: {payment.status}",
                show_alert=True
            )
    except Exception as e:
        logger.error(f"Ошибка проверки платежа: {e}")
        await callback.answer(
            "Ошибка при проверке платежа",
            show_alert=True
        )

async def get_profile_info(user_id: int):
    """Получает информацию профиля пользователя"""
    has_paid = await check_user_payment(user_id)
    user_data = await get_user_data(user_id)
    
    if has_paid and user_data:
        expiry_date, _ = user_data
        text = f"""<b>👾 Ваш профиль</b>

📌Статус подписки - <b>Активна 🟢</b>
⏳Действует до - <b>{expiry_date}</b>"""
        return text, get_profile_keyboard(True)
    elif user_data:
        text = f"""<b>👾 Ваш профиль</b>

Статус подписки - <b>не Активна 🔴</b>

<blockquote><i>Ваша подписка истекла. Для продления нажмите кнопку ниже.</i></blockquote>"""
        return text, get_profile_keyboard(True)
    else:
        text = f"""<b>👾 Ваш профиль</b>

Статус подписки - <b>не Активна 🔴</b>

<blockquote><i>Для подключения VPN оформите подписку.</i></blockquote>"""
        return text, get_profile_keyboard(False)

@dp.message(F.text == "👾Аккаунт")
async def profile(message: Message):
    """Показывает профиль пользователя"""
    user_id = message.from_user.id
    text, reply_markup = await get_profile_info(user_id)
    await message.answer(text, reply_markup=reply_markup)



@dp.callback_query(F.data == 'subscribe_from_profile')
async def subscribe_from_profile(callback: types.CallbackQuery):
    """Обработчик кнопки оформления подписки из профиля"""
    await show_subscription_options(callback.message)
    await callback.answer()

@dp.callback_query(F.data == 'referrals')
async def referrals_callback(callback: types.CallbackQuery):
    """Обработчик кнопки партнерской программы"""
    await callback.answer("Скоро", show_alert=True)



@dp.callback_query(F.data == 'back_to_profile')
async def back_to_profile_callback(callback: types.CallbackQuery):
    """Возврат к профилю"""
    user_id = callback.from_user.id
    text, reply_markup = await get_profile_info(user_id)
    await callback.message.edit_text(text, reply_markup=reply_markup)
    await callback.answer()

@dp.message(F.text == "🔒О VPN")
async def info(message: Message):
    """Показывает информацию о боте"""
    await message.answer(
        text="""🌐 <b>Shard VPN — быстрый и безопасный интернет без ограничений.</b>

В основе Shard VPN лежит передовой протокол с открытым исходным кодом. Он даёт максимальную производительность и надёжность, а каналы <b>10 Гбит/с</b> на всех серверах обеспечивают стабильно высокую скорость.

🔒 <b>Конфиденциальность на первом месте</b>
Журналы логов удаляются моментально — мы <b>не храним историю посещений</b>, не собираем и не продаём ваши данные.

⚡️ <b>Преимущества Shard VPN:</b>
— Высокая скорость и стабильность соединения
— Полное шифрование трафика
— Подключение в 1 клик

<blockquote><i>📩 Вопросы? Напиши в поддержку — мы всегда на связи.</i></blockquote>""",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧑‍💻 Поддержка", url="https://t.me/xmakedon")]
        ])
    )

@dp.callback_query(F.data == 'instruction_from_vpn')
async def show_instructions_from_vpn(callback: types.CallbackQuery):
    """Показывает инструкцию по подключению с выбором устройства (из активации VPN)"""
    devices_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
        InlineKeyboardButton(text="📱 iOS", callback_data='instruction_ios'),
        InlineKeyboardButton(text="🤖 Android", callback_data='instruction_android')
        ],
        [
        InlineKeyboardButton(text="💻 Windows", callback_data='instruction_win'),
        InlineKeyboardButton(text="🍎 macOS", callback_data='instruction_mac')
        ],
        [InlineKeyboardButton(text="🧑‍💻 Поддержка", url="https://t.me/xmakedon")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data='back_to_vpn')]
    ])
    
    await callback.message.edit_text(
        text="""📖 <b>Инструкция по подключению</b>

Просто выберите устройство — мы сразу покажем, что делать.""",
        reply_markup=devices_keyboard
    )
    await callback.answer()

@dp.callback_query(F.data == 'back_to_vpn')
async def back_to_vpn_callback(callback: types.CallbackQuery):
    """Возврат к отображению VPN информации"""
    user_id = callback.from_user.id
    user_data = await get_user_data(user_id)
    
    if not user_data:
        await callback.message.edit_text(
            text="""<b>👨🏻‍💻Чтобы подключиться — выбери подписку:</b>

<blockquote><i>🔐 Быстрый, стабильный и защищённый VPN.</i></blockquote>""",
            reply_markup=get_subscription_keyboard(True)
        )
    else:
        await send_vpn_message(callback, user_id, is_edit=True)
    
    await callback.answer()

@dp.callback_query(F.data == 'instruction')
async def show_instructions(callback: types.CallbackQuery):
    """Показывает инструкцию по подключению с выбором устройства (назад из инструкции)"""
    devices_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
        InlineKeyboardButton(text="📱 iOS", callback_data='instruction_ios'),
        InlineKeyboardButton(text="🤖 Android", callback_data='instruction_android')
        ],
        [
        InlineKeyboardButton(text="💻 Windows", callback_data='instruction_win'),
        InlineKeyboardButton(text="🍎 macOS", callback_data='instruction_mac')
        ],
        [InlineKeyboardButton(text="🧑‍💻 Поддержка", url="https://t.me/xmakedon")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data='back_to_vpn')]
    ])
    
    await callback.message.edit_text(
        text="""📖 <b>Инструкция по подключению</b>

Просто выберите устройство — мы сразу покажем, что делать.""",
        reply_markup=devices_keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith('instruction_'))
async def show_device_instructions(callback: types.CallbackQuery):
    """Показывает инструкцию для конкретного устройства"""
    device = callback.data.split('_')[1]
    user_id = callback.from_user.id
    
    # Получаем конфиг пользователя
    user_data = await get_user_data(user_id)
    if not user_data:
        await callback.answer("Ошибка получения конфигурации", show_alert=True)
        return
    
    expiry_date, config = user_data
    config_clean = str(config).strip('\"\'')
    
    # Отладочная информация
    print(f"DEBUG instructions: user_id={user_id}, config={config}, config_clean={config_clean}")
    
    # Проверяем, что config не пустой
    if not config_clean or config_clean == 'None':
        await callback.answer("❌ Ошибка: конфигурация VPN не найдена. Обратитесь в поддержку.", show_alert=True)
        return
    
    # Получаем sub_key для ссылки (как в активации VPN)
    timeout = aiohttp.ClientTimeout(total=10)
    headers = {
        "X-API-Key": "18181818",
        "Accept": "application/json",
    } 
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"https://shardtg.ru/sub/{user_id}", headers=headers) as resp:
                if resp.status != 200:
                    await callback.answer("Не удалось получить ссылку. Попробуйте позже.", show_alert=True)
                    return
                data = await resp.json()
    except Exception:
        await callback.answer("Сервер временно недоступен. Попробуйте позже.", show_alert=True)
        return

    sub_key = data.get("sub_key")
    if not sub_key:
        await callback.answer("Ошибка получения ссылки. Попробуйте позже.", show_alert=True)
        return

    miniapp_link = f"https://shardtg.ru/subscription/{sub_key}"
    
    # Создаем клавиатуру с кнопками для приложения
    buttons = []
    
    # Добавляем кнопку скачивания приложения
    if device in ['ios', 'android', 'win', 'mac']:
        app_url = {
            'ios': 'https://apps.apple.com/us/app/v2raytun/id6476628951?l=ru',
            'android': 'https://play.google.com/store/apps/details?id=com.v2raytun.android&hl=ru&pli=1',
            'win': 'https://v2raytun.com',
            'mac': 'https://v2raytun.com'
        }.get(device)
        
        if app_url:
            buttons.append([InlineKeyboardButton(text="💻 Скачать V2RayTun", url=app_url)])
    
    # Добавляем кнопку "Установить VPN" с ссылкой на subscription с конфигами
    buttons.append([InlineKeyboardButton(text="💎 Установить VPN", url=miniapp_link)])
    
    reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    # Инструкции для разных устройств
    instructions = {
        'ios': f"""
📖 <b>Подключение SHARD VPN на IPhone:</b>

<blockquote><i>1. Скачайте приложение v2RayTun из App Store (кнопка ниже).

2. Нажмите кнопку "Установить VPN" (кнопка ниже).

3. В открытой странице нажмите «Открыть в v2RayTun», чтобы загрузить ключ в приложение.

4. Всё готово 🎉 VPN подключён, интернет работает быстро и безопасно.</i></blockquote>

<b>👨‍💻 Если что-то не получается напишите в поддержку, мы поможем.</b>
""",
        'android': f"""
📖 <b>Подключение SHARD VPN на Android:</b>

<blockquote><i>1. Скачайте приложение v2RayTun из Google Play (кнопка ниже).

2. Нажмите кнопку "Установить VPN" (кнопка ниже).

3. В открытой странице нажмите «Открыть в v2RayTun», чтобы загрузить ключ в приложение.

4. Всё готово 🎉 VPN подключён, интернет работает быстро и безопасно.</i></blockquote>

<b>👨‍💻 Если что-то не получается напишите в поддержку, мы поможем.</b>
""",
        'win': f"""
📖 <b>Подключение SHARD VPN на Windows:</b>
 
<blockquote><i>1. Cкачайте v2RayTun с официального сайта (кнопка ниже).

2. Нажмите кнопку "Установить VPN" (кнопка ниже).

3. В открытой странице нажмите «Копировать конфигурацию».

4. Откройте v2RayTun и вставьте скопированную конфигурацию.

5. Всё готово 🎉 VPN подключён, интернет работает быстро и безопасно.</i></blockquote>

<b>👨‍💻 Если что-то не получается напишите в поддержку, мы поможем.</b>
""",
        'mac': f"""
📖 <b>Как подключить Shard VPN на MacOS (2021+):</b>
    
<blockquote><i>1. Cкачайте v2RayTun с официального сайта (кнопка ниже).

2. Нажмите кнопку "Установить VPN" (кнопка ниже).

3. На открывшейся странице нажмите «Открыть в v2RayTun».

4. Всё готово 🎉 VPN подключён, интернет работает быстро и безопасно.</i></blockquote>


<b>👨‍💻 Если что-то не получается напишите в поддержку, мы поможем.</b>
"""
    }
    
    if device in instructions:
        # Добавляем кнопку "Назад" в клавиатуру
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data='instruction')])
        reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await callback.message.edit_text(
            text=instructions[device],
            reply_markup=reply_markup
        )
    else:
        await callback.answer("Устройство не найдено", show_alert=True)
    
    await callback.answer()

@dp.callback_query(F.data == 'renew_sub')
async def renew_subscription(callback: types.CallbackQuery):
    """Продление подписки"""
    user_id = callback.from_user.id
    
    # Проверяем, есть ли у пользователя данные о подписке (активной или истекшей)
    user_data = await get_user_data(user_id)
    has_paid = await check_user_payment(user_id)
    
    if user_data or has_paid:
        # У пользователя есть подписка (активная или истекшая) - показываем варианты продления
        await callback.message.answer(
            text="""<b>🔒Продли подписку и оставайся в безопасности!</b>

<blockquote><i>Выбери удобный вариант:</i></blockquote>
""",
            reply_markup=get_subscription_keyboard()
        )
    else:
        # У пользователя нет подписки вообще
        await callback.answer(
            "У вас нет подписки. Оформите новую подписку.",
            show_alert=True
        )
        await show_subscription_options(callback.message)
    
    await callback.answer()

# ----- Обработка оплаты через Telegram Stars -----
@dp.callback_query(F.data.startswith('pay_stars_'))
async def pay_stars_callback(callback: types.CallbackQuery):
    """Отправляет пользователю счёт на оплату в Telegram Stars"""
    period = callback.data.split('_')[2]
    stars_price = get_stars_price(period)
    prices = [LabeledPrice(label=f"{period} мес.", amount=stars_price)]

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Shard VPN подписка",
        description=f"{period} мес. подписки",
        payload=f"stars_sub_{period}_{callback.from_user.id}",
        provider_token=STARS_PROVIDER_TOKEN,
        currency="XTR",
        prices=prices,
    )
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout: types.PreCheckoutQuery):
    """Подтверждаем подготовительный запрос перед оплатой звёздами"""
    await bot.answer_pre_checkout_query(pre_checkout.id, ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    """Обработка успешного платежа через Telegram Stars"""
    payload = message.successful_payment.invoice_payload
    if payload.startswith('stars_sub_'):
        try:
            _, _, period_str, user_id_str = payload.split('_')
            period = int(period_str)
            user_id = int(user_id_str)
        except ValueError:
            period = 1
            user_id = message.from_user.id

        # Определяем, была ли подписка активной до продления
        was_active = await check_user_payment(user_id)

        success = await add_payment(user_id, period)
        if not success:
            await message.answer("Ошибка активации подписки. Обратитесь в поддержку.")
            return


        user_data = await get_user_data(user_id)
        expiry_date = user_data[0] if user_data else "не определена"

        action_word = "продлена" if was_active else "активирована"

        # Определяем текст периода для отображения
        if period == 'special':
            period_text = "7 дней"
        else:
            period_text = f"{period} мес."
        
        await message.answer(
            text=f"""<b>✅ Оплата успешно выполнена</b>

✨Ваша подписка на <b>Shard VPN</b> {action_word}!

📅Срок подписки: <b>{period_text}</b>
⏳Дата окончания: <b>{expiry_date}</b>

<blockquote><i>🔹 Нажмите «Активировать VPN», чтобы начать пользоваться.</i></blockquote>""",
            reply_markup=create_main_keyboard()
        )
async def send_notification(user_id: int, text: str, notification_type: str):
    """Отправляет уведомление пользователю"""
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data='renew_sub')]
        ])
        await bot.send_message(chat_id=user_id, text=text, reply_markup=keyboard)
        await mark_user_notified(user_id, notification_type)
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления {user_id}: {e}")

async def main():
    await init_db()
    shutdown_event = asyncio.Event()
    
    # Запускаем фоновую задачу уведомления об истечении подписки через 2 дня
    async def notify_expiring_loop():
        while not shutdown_event.is_set():
            try:
                users = await get_users_expiring_in_days(2, 500)
                for user_id, expiry in users:
                    if shutdown_event.is_set():
                        break
                    text = (
                        "⏳ <b>Ваша подписка скоро истечёт</b>\n\n"
                        "<blockquote><i>Осталось 2 дня. Не теряйте защиту и скорость — продлите заранее.</i></blockquote>\n\n"
                        f"Дата окончания: <code>{expiry}</code>"
                    )
                    await send_notification(user_id, text, '2d')
                
                await asyncio.wait_for(shutdown_event.wait(), timeout=60 * 60)
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.error(f"Ошибка в notify_expiring_loop: {e}")
                await asyncio.wait_for(shutdown_event.wait(), timeout=60 * 10)

    # Запускаем фоновую задачу уведомлений для всех пользователей
    async def notify_all_expiring_loop():
        while not shutdown_event.is_set():
            try:
                # Уведомления за 3 дня
                users_3d = await get_all_users_expiring_in_days(3, 500)
                for user_id, expiry, _ in users_3d:
                    if shutdown_event.is_set():
                        break
                    text = (
                        f"⏳ <b>Ваша подписка истекает через 3 дня</b>\n\n"
                        "<blockquote><i>Не теряйте доступ к быстрому и безопасному VPN — продлите подписку заранее.</i></blockquote>\n\n"
                        f"Дата окончания: <code>{expiry}</code>"
                    )
                    await send_notification(user_id, text, '3d')

                if shutdown_event.is_set():
                    break

                # Уведомления за 1 день
                users_1d = await get_all_users_expiring_in_days(1, 500)
                for user_id, expiry, _ in users_1d:
                    if shutdown_event.is_set():
                        break
                    text = (
                        f"⚠️ <b>Ваша подписка истекает завтра!</b>\n\n"
                        "<blockquote><i>Последний день доступа. Продлите подписку, чтобы не потерять защиту.</i></blockquote>\n\n"
                        f"Дата окончания: <code>{expiry}</code>"
                    )
                    await send_notification(user_id, text, '1d')

                if shutdown_event.is_set():
                    break

                # Уведомления об истечении
                users_expired = await get_all_users_expiring_in_days(0, 500)
                for user_id, expiry, _ in users_expired:
                    if shutdown_event.is_set():
                        break
                    text = (
                        f"❌ <b>Ваша подписка истёкла</b>\n\n"
                        f"<blockquote><i>Доступ завершён. Продлите подписку, чтобы продолжить пользоваться VPN.</i></blockquote>\n\n"
                        f"Дата окончания: <code>{expiry}</code>"
                    )
                    await send_notification(user_id, text, 'expired')

                await asyncio.wait_for(shutdown_event.wait(), timeout=60 * 60)
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.error(f"Ошибка в notify_all_expiring_loop: {e}")
                await asyncio.wait_for(shutdown_event.wait(), timeout=60 * 10)

    # Создаем задачи и сохраняем ссылки на них
    task1 = asyncio.create_task(notify_expiring_loop())
    task2 = asyncio.create_task(notify_all_expiring_loop())
    
    try:
        await dp.start_polling(bot)
    finally:
        # Устанавливаем флаг завершения
        shutdown_event.set()
        
        # Отменяем все активные задачи проверки платежей
        await cancel_all_payment_tasks()
        
        # Ждем завершения задач с таймаутом
        try:
            await asyncio.wait_for(asyncio.gather(task1, task2, return_exceptions=True), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Некоторые фоновые задачи не завершились в течение 5 секунд")
        
        # Отменяем оставшиеся задачи
        for task in [task1, task2]:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
