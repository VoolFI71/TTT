import asyncio
import aiosqlite
from datetime import datetime
from config import DB_PATH

async def check_database():
    """Проверяет содержимое базы данных"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            print("=== ПРОВЕРКА БАЗЫ ДАННЫХ ===\n")
            
            # Проверяем таблицы
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = await cursor.fetchall()
            print(f"Таблицы в БД: {[table[0] for table in tables]}\n")
            
            # Проверяем bot_users
            cursor = await conn.execute("SELECT COUNT(*) FROM bot_users")
            bot_users_count = (await cursor.fetchone())[0]
            print(f"Всего пользователей бота: {bot_users_count}")
            
            if bot_users_count > 0:
                cursor = await conn.execute(
                    "SELECT user_id, first_name, first_interaction FROM bot_users ORDER BY first_interaction DESC LIMIT 5"
                )
                recent_users = await cursor.fetchall()
                print("Последние пользователи:")
                for user_id, first_name, first_interaction in recent_users:
                    print(f"  - {user_id} ({first_name}) - {first_interaction}")
            
            print()
            
            # Проверяем users (VPN подписки)
            cursor = await conn.execute("SELECT COUNT(*) FROM users")
            vpn_users_count = (await cursor.fetchone())[0]
            print(f"Пользователей с VPN подписками: {vpn_users_count}")
            
            if vpn_users_count > 0:
                cursor = await conn.execute(
                    "SELECT user_id, subscribed, expiry_date FROM users ORDER BY payment_date DESC LIMIT 5"
                )
                vpn_users = await cursor.fetchall()
                print("VPN пользователи:")
                for user_id, subscribed, expiry_date in vpn_users:
                    status = "Активна" if subscribed else "Неактивна"
                    print(f"  - {user_id} - {status} до {expiry_date}")
            
            print()
            
            # Проверяем payments
            cursor = await conn.execute("SELECT COUNT(*) FROM payments")
            payments_count = (await cursor.fetchone())[0]
            print(f"Всего платежей: {payments_count}")
            
    except Exception as e:
        print(f"Ошибка проверки БД: {e}")

if __name__ == "__main__":
    asyncio.run(check_database())
