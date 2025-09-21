#!/usr/bin/env python3
"""
🚀 БЫСТРОЕ ОБНОВЛЕНИЕ: Просто скопируйте эту функцию и вызовите
"""

import asyncio
import aiohttp
import aiosqlite
from datetime import datetime
from config import DB_PATH

async def quick_update_users(location_code, server_url, api_key):
    """
    Быстрое обновление всех активных пользователей новой локацией
    
    Использование:
    await quick_update_users("us", "https://us.shardtg.ru", "18181818")
    """
    
    print(f"🔄 Обновление пользователей локацией: {location_code}")
    
    updated = 0
    errors = 0
    
    # Получаем активных пользователей
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT user_id, expiry_date FROM users WHERE subscribed = 1"
        )
        users = await cursor.fetchall()
        
        print(f"📊 Найдено {len(users)} активных пользователей")
        
        for user_id, expiry_date in users:
            try:
                # Вычисляем оставшиеся дни
                expiry_dt = datetime.strptime(expiry_date, '%d.%m.%Y %H:%M')
                days = (expiry_dt - datetime.now()).days
                
                if days <= 0:
                    print(f"⏰ {user_id}: подписка истекла")
                    continue
                
                # POST запрос к VPN серверу
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{server_url}/giveconfig",
                        json={"time": days, "id": str(user_id), "server": location_code},
                        headers={"X-API-Key": api_key, "Content-Type": "application/json"}
                    ) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            config = result.get("config")
                            
                            if config:
                                # Обновляем конфиг в базе данных
                                await conn.execute(
                                    "UPDATE users SET config = ?, last_update = ? WHERE user_id = ?",
                                    (config, datetime.now().strftime('%d.%m.%Y %H:%M'), user_id)
                                )
                                updated += 1
                                print(f"✅ {user_id}: {days} дней - обновлен")
                            else:
                                print(f"⚠️ {user_id}: сервер не вернул конфиг")
                        else:
                            print(f"❌ {user_id}: HTTP {resp.status}")
                            errors += 1
                
            except Exception as e:
                print(f"❌ {user_id}: {e}")
                errors += 1
        
        # Сохраняем изменения
        await conn.commit()
    
    print(f"🎉 Обновлено {updated} пользователей, ошибок: {errors}")
    return updated

async def update_specific_users(user_ids, location_code, server_url, api_key):
    """
    Обновляет конфиги для конкретных пользователей
    
    Использование:
    await update_specific_users([123456789, 987654321], "us", "https://us.shardtg.ru", "18181818")
    """
    
    print(f"🔄 Обновление {len(user_ids)} пользователей локацией: {location_code}")
    
    updated = 0
    errors = 0
    
    async with aiosqlite.connect(DB_PATH) as conn:
        for user_id in user_ids:
            try:
                # Получаем данные пользователя
                cursor = await conn.execute(
                    "SELECT expiry_date FROM users WHERE user_id = ? AND subscribed = 1",
                    (user_id,)
                )
                row = await cursor.fetchone()
                
                if not row:
                    print(f"⚠️ {user_id}: пользователь не найден или неактивен")
                    continue
                
                expiry_date = row[0]
                
                # Вычисляем оставшиеся дни
                expiry_dt = datetime.strptime(expiry_date, '%d.%m.%Y %H:%M')
                days = (expiry_dt - datetime.now()).days
                
                if days <= 0:
                    print(f"⏰ {user_id}: подписка истекла")
                    continue
                
                # POST запрос к VPN серверу
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{server_url}/giveconfig",
                        json={"time": days, "id": str(user_id), "server": location_code},
                        headers={"X-API-Key": api_key, "Content-Type": "application/json"}
                    ) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            config = result.get("config")
                            
                            if config:
                                # Обновляем конфиг в базе данных
                                await conn.execute(
                                    "UPDATE users SET config = ?, last_update = ? WHERE user_id = ?",
                                    (config, datetime.now().strftime('%d.%m.%Y %H:%M'), user_id)
                                )
                                updated += 1
                                print(f"✅ {user_id}: {days} дней - обновлен")
                            else:
                                print(f"⚠️ {user_id}: сервер не вернул конфиг")
                        else:
                            print(f"❌ {user_id}: HTTP {resp.status}")
                            errors += 1
                
            except Exception as e:
                print(f"❌ {user_id}: {e}")
                errors += 1
        
        # Сохраняем изменения
        await conn.commit()
    
    print(f"🎉 Обновлено {updated} пользователей, ошибок: {errors}")
    return updated

async def get_active_users_count():
    """Получает количество активных пользователей"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM users WHERE subscribed = 1"
        )
        count = await cursor.fetchone()[0]
        return count

# ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ:
async def main():
    print("🚀 Скрипт быстрого обновления пользователей")
    print("=" * 50)
    
    # Проверяем количество активных пользователей
    active_count = await get_active_users_count()
    print(f"📊 Активных пользователей: {active_count}")
    
    if active_count == 0:
        print("❌ Нет активных пользователей для обновления")
        return
    
    # Обновляем всех активных пользователей
    print("\n🔄 Обновление всех активных пользователей...")
    await quick_update_users("us", "https://us.shardtg.ru", "18181818")
    
    # Пример обновления конкретных пользователей
    # await update_specific_users([123456789, 987654321], "us", "https://us.shardtg.ru", "18181818")

if __name__ == "__main__":
    asyncio.run(main())
