# Настройки бота
from dotenv import load_dotenv
import os
load_dotenv()

# Telegram Bot Configuration
TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    raise ValueError("BOT_TOKEN не установлен в переменных окружения")

CHANNEL_ID = os.getenv('CHANNEL_ID')
if not CHANNEL_ID:
    raise ValueError("CHANNEL_ID не установлен в переменных окружения")
# Single ADMIN_ID no longer required; use ADMIN_IDS instead

WELCOME_GIF_URL = os.getenv('WELCOME_GIF_URL', '')

# Parse ADMIN_IDS from comma-separated string
admin_ids_str = os.getenv('ADMIN_IDS')
if not admin_ids_str:
    raise ValueError("ADMIN_IDS не установлены в переменных окружения")
ADMIN_IDS = [int(admin_id.strip()) for admin_id in admin_ids_str.split(',') if admin_id.strip()]

# YooKassa Payment Configuration
YOOKASSA_SHOP_ID = os.getenv('YOOKASSA_SHOP_ID')
if not YOOKASSA_SHOP_ID:
    raise ValueError("YOOKASSA_SHOP_ID не установлен в переменных окружения")

YOOKASSA_SECRET_KEY = os.getenv('YOOKASSA_SECRET_KEY')
if not YOOKASSA_SECRET_KEY:
    raise ValueError("YOOKASSA_SECRET_KEY не установлен в переменных окружения")

YOOKASSA_RETURN_URL = os.getenv('YOOKASSA_RETURN_URL')
if not YOOKASSA_RETURN_URL:
    raise ValueError("YOOKASSA_RETURN_URL не установлен в переменных окружения")

# VPN Server Configuration
VPN_SERVER_URL = os.getenv('VPN_SERVER_URL')
if not VPN_SERVER_URL:
    raise ValueError("VPN_SERVER_URL не установлен в переменных окружения")

VPN_AUTH_KEY = os.getenv('VPN_AUTH_KEY')
if not VPN_AUTH_KEY:
    raise ValueError("VPN_AUTH_KEY не установлен в переменных окружения")

GIF_FILE_ID = os.getenv('GIF_FILE_ID', '')

# Telegram Stars Configuration
STARS_PROVIDER_TOKEN = os.getenv('STARS_PROVIDER_TOKEN', '')

# Database Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.getenv('DB_NAME', 'users.db')
DB_PATH = os.path.join(BASE_DIR, DB_NAME)

# Miniapp Configuration
MINIAPP_BASE_URL = os.getenv('MINIAPP_BASE_URL')
if not MINIAPP_BASE_URL:
    raise ValueError("MINIAPP_BASE_URL не установлен в переменных окружения")

# Subscription Prices (in kopecks) - from environment variables
def get_price(env_var, default_value):
    """Получает цену из переменной окружения с проверкой"""
    value = os.getenv(env_var)
    if value is None:
        return default_value
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Неверный формат цены в {env_var}: {value}")

PRICES = {
    '1': get_price('PRICE_1_MONTH', 9900),     # 99₽ за месяц
    '3': get_price('PRICE_3_MONTHS', 27900),   # 279₽ за 3 месяца
    '6': get_price('PRICE_6_MONTHS', 54900),   # 549₽ за 6 месяцев
    '12': get_price('PRICE_12_MONTHS', 99900)  # 999₽ за год
}