# Скрипт для отладки пользователей в базе данных
import asyncio
import aiosqlite
from datetime import datetime
from config import DB_PATH

async def debug_users():
    """Отладка пользователей в базе данных"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT user_id, subscribed, payment_date, expiry_date FROM users ORDER BY payment_date DESC"
        )
        users = await cursor.fetchall()
        
        print(f"=== ОТЛАДКА ПОЛЬЗОВАТЕЛЕЙ ===")
        print(f"Всего пользователей в БД: {len(users)}")
        print()
        
        active_count = 0
        expired_count = 0
        
        for user_id, subscribed, payment_date, expiry_date in users:
            print(f"User ID: {user_id}")
            print(f"  Subscribed: {subscribed}")
            print(f"  Payment Date: {payment_date}")
            print(f"  Expiry Date: {expiry_date}")
            
            # Проверяем активность
            is_active = False
            if subscribed and expiry_date:
                try:
                    formats = ['%d.%m.%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']
                    for fmt in formats:
                        try:
                            exp_date = datetime.strptime(expiry_date, fmt)
                            is_active = datetime.now() < exp_date
                            print(f"  Parsed Date: {exp_date} (format: {fmt})")
                            break
                        except ValueError:
                            continue
                except Exception as e:
                    print(f"  Date Parse Error: {e}")
            
            status = "АКТИВНА" if is_active else "НЕАКТИВНА/ИСТЕКЛА"
            print(f"  Status: {status}")
            
            if is_active:
                active_count += 1
            elif subscribed:
                expired_count += 1
            
            print("-" * 40)
        
        print(f"\n=== ИТОГИ ===")
        print(f"Активных подписок: {active_count}")
        print(f"Истекших подписок: {expired_count}")
        print(f"Всего пользователей: {len(users)}")

if __name__ == "__main__":
    asyncio.run(debug_users())
