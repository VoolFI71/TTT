# Скрипт для исправления форматов дат в базе данных
import asyncio
import aiosqlite
from datetime import datetime
from config import DB_PATH

async def fix_database_dates():
    """Исправляет форматы дат в базе данных"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT user_id, payment_date, expiry_date FROM users"
        )
        users = await cursor.fetchall()
        
        print(f"Обрабатываю {len(users)} пользователей...")
        
        for user_id, payment_date, expiry_date in users:
            updated = False
            new_payment_date = payment_date
            new_expiry_date = expiry_date
            
            # Исправляем payment_date
            if payment_date:
                try:
                    formats = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y %H:%M']
                    for fmt in formats:
                        try:
                            parsed_date = datetime.strptime(payment_date, fmt)
                            new_payment_date = parsed_date.strftime('%d.%m.%Y %H:%M')
                            if new_payment_date != payment_date:
                                updated = True
                            break
                        except ValueError:
                            continue
                except:
                    pass
            
            # Исправляем expiry_date
            if expiry_date:
                try:
                    formats = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y %H:%M']
                    for fmt in formats:
                        try:
                            parsed_date = datetime.strptime(expiry_date, fmt)
                            new_expiry_date = parsed_date.strftime('%d.%m.%Y %H:%M')
                            if new_expiry_date != expiry_date:
                                updated = True
                            break
                        except ValueError:
                            continue
                except:
                    pass
            
            # Обновляем если нужно
            if updated:
                await conn.execute(
                    "UPDATE users SET payment_date = ?, expiry_date = ? WHERE user_id = ?",
                    (new_payment_date, new_expiry_date, user_id)
                )
                print(f"Обновлен пользователь {user_id}")
                print(f"  Payment: {payment_date} -> {new_payment_date}")
                print(f"  Expiry: {expiry_date} -> {new_expiry_date}")
        
        await conn.commit()
        print("Исправление завершено!")

if __name__ == "__main__":
    asyncio.run(fix_database_dates())
