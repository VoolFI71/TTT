#!/usr/bin/env python3
"""
🔍 Скрипт проверки конфигурации для продакшена
"""

import os
from dotenv import load_dotenv

def check_env_file():
    """Проверяет наличие и содержимое .env файла"""
    print("🔍 Проверка конфигурации...")
    print("=" * 50)
    
    # Проверяем наличие .env файла
    if not os.path.exists('.env'):
        print("❌ Файл .env не найден!")
        print("📝 Создайте файл .env на основе ENV_SETUP.md")
        return False
    
    print("✅ Файл .env найден")
    
    # Загружаем переменные окружения
    load_dotenv()
    
    # Список обязательных переменных
    required_vars = {
        'BOT_TOKEN': 'Токен Telegram бота',
        'CHANNEL_ID': 'ID канала',
        'ADMIN_ID': 'ID администратора',
        'ADMIN_IDS': 'ID всех администраторов',
        'YOOKASSA_SHOP_ID': 'ID магазина ЮKassa',
        'YOOKASSA_SECRET_KEY': 'Секретный ключ ЮKassa',
        'YOOKASSA_RETURN_URL': 'URL возврата после оплаты',
        'VPN_SERVER_URL': 'URL VPN сервера',
        'VPN_AUTH_KEY': 'Ключ авторизации VPN',
        'MINIAPP_BASE_URL': 'URL мини-приложения'
    }
    
    # Список опциональных переменных
    optional_vars = {
        'STARS_PROVIDER_TOKEN': 'Токен Telegram Stars',
        'WELCOME_GIF_URL': 'URL приветственного GIF',
        'GIF_FILE_ID': 'ID GIF файла в Telegram',
        'MINIAPP_BASE_URL': 'URL мини-приложения'
    }
    
    print("\n📋 Обязательные переменные:")
    missing_required = []
    
    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            # Скрываем чувствительные данные
            if 'TOKEN' in var or 'KEY' in var or 'SECRET' in var:
                display_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
            else:
                display_value = value
            print(f"✅ {var}: {display_value}")
        else:
            print(f"❌ {var}: НЕ УСТАНОВЛЕНА")
            missing_required.append(var)
    
    print("\n📋 Опциональные переменные:")
    for var, description in optional_vars.items():
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: установлена")
        else:
            print(f"⚠️ {var}: не установлена (опционально)")
    
    # Проверяем цены
    print("\n💰 Цены подписок:")
    prices = {
        'PRICE_1_MONTH': '1 месяц',
        'PRICE_3_MONTHS': '3 месяца', 
        'PRICE_6_MONTHS': '6 месяцев',
        'PRICE_12_MONTHS': '12 месяцев'
    }
    
    for var, period in prices.items():
        value = os.getenv(var)
        if value:
            try:
                price_rub = int(value) / 100
                print(f"✅ {period}: {price_rub}₽")
            except ValueError:
                print(f"❌ {period}: неверный формат цены")
        else:
            print(f"⚠️ {period}: цена не установлена")
    
    # Итоговая проверка
    print("\n" + "=" * 50)
    if missing_required:
        print(f"❌ ОШИБКА: Отсутствуют обязательные переменные: {', '.join(missing_required)}")
        print("📝 Заполните недостающие переменные в файле .env")
        return False
    else:
        print("✅ ВСЕ ОБЯЗАТЕЛЬНЫЕ ПЕРЕМЕННЫЕ УСТАНОВЛЕНЫ")
        print("🚀 Конфигурация готова к продакшену!")
        return True

def check_production_ready():
    """Проверяет готовность к продакшену"""
    print("\n🛡️ Проверка готовности к продакшену:")
    print("-" * 40)
    
    load_dotenv()
    
    # Проверяем, что используются не тестовые ключи
    yookassa_key = os.getenv('YOOKASSA_SECRET_KEY', '')
    if yookassa_key.startswith('test_'):
        print("⚠️ ВНИМАНИЕ: Используется тестовый ключ ЮKassa!")
        print("🔧 Замените на продакшен ключ для реальных платежей")
    else:
        print("✅ Используется продакшен ключ ЮKassa")
    
    # Проверяем токен бота
    bot_token = os.getenv('BOT_TOKEN', '')
    if not bot_token:
        print("❌ Токен бота не установлен")
    elif len(bot_token) < 20:
        print("⚠️ Токен бота выглядит неполным")
    else:
        print("✅ Токен бота установлен")
    
    # Проверяем права доступа к .env
    if os.path.exists('.env'):
        stat = os.stat('.env')
        mode = oct(stat.st_mode)[-3:]
        if mode in ['600', '640']:
            print("✅ Права доступа к .env файлу корректные")
        else:
            print(f"⚠️ Права доступа к .env: {mode} (рекомендуется 600)")

if __name__ == "__main__":
    try:
        success = check_env_file()
        check_production_ready()
        
        if success:
            print("\n🎉 Конфигурация готова!")
            exit(0)
        else:
            print("\n💥 Требуется настройка!")
            exit(1)
            
    except Exception as e:
        print(f"\n❌ Ошибка при проверке: {e}")
        exit(1)
