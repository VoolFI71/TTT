import asyncio
import aiosqlite
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
import logging
from config import DB_PATH

async def send_broadcast_message(bot: Bot, message_text: str, target_type: str = "all"):
    """
    Отправляет рассылку пользователям
    target_type: "all", "active", "inactive", "expiring"
    """
    
    # Получаем список пользователей в зависимости от типа
    if target_type == "all":
        query = "SELECT user_id FROM users"
    elif target_type == "active":
        query = """SELECT user_id FROM users 
                   WHERE subscribed = 1 AND datetime(expiry_date, 'localtime') > datetime('now', 'localtime')"""
    elif target_type == "inactive":
        query = """SELECT user_id FROM users 
                   WHERE subscribed = 0 OR datetime(expiry_date, 'localtime') <= datetime('now', 'localtime')"""
    elif target_type == "expiring":
        query = """SELECT user_id FROM users 
                   WHERE subscribed = 1 AND datetime(expiry_date, 'localtime') BETWEEN datetime('now', 'localtime') 
                   AND datetime('now', '+3 days', 'localtime')"""
    else:
        return {"success": 0, "failed": 0, "blocked": 0}
    
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(query)
        users = await cursor.fetchall()
    
    success_count = 0
    failed_count = 0
    blocked_count = 0
    
    for (user_id,) in users:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=message_text,
                parse_mode="HTML"
            )
            success_count += 1
            
            # Небольшая задержка чтобы не превысить лимиты API
            await asyncio.sleep(0.05)
            
        except TelegramForbiddenError:
            # Пользователь заблокировал бота
            blocked_count += 1
            logging.info(f"User {user_id} blocked the bot")
            
        except TelegramBadRequest as e:
            # Другие ошибки Telegram API
            failed_count += 1
            logging.error(f"Failed to send message to {user_id}: {e}")
            
        except Exception as e:
            failed_count += 1
            logging.error(f"Unexpected error sending to {user_id}: {e}")
    
    return {
        "success": success_count,
        "failed": failed_count,
        "blocked": blocked_count,
        "total": len(users)
    }

async def get_broadcast_stats():
    """Получает статистику для рассылки"""
    async with aiosqlite.connect(DB_PATH) as conn:
        # Всего пользователей
        cursor = await conn.execute("SELECT COUNT(*) FROM users")
        total = (await cursor.fetchone())[0]
        
        # Активные
        cursor = await conn.execute(
            """SELECT COUNT(*) FROM users 
               WHERE subscribed = 1 AND datetime(expiry_date, 'localtime') > datetime('now', 'localtime')"""
        )
        active = (await cursor.fetchone())[0]
        
        # Неактивные
        cursor = await conn.execute(
            """SELECT COUNT(*) FROM users 
               WHERE subscribed = 0 OR datetime(expiry_date, 'localtime') <= datetime('now', 'localtime')"""
        )
        inactive = (await cursor.fetchone())[0]
        
        # Истекающие (в течение 3 дней)
        cursor = await conn.execute(
            """SELECT COUNT(*) FROM users 
               WHERE subscribed = 1 AND datetime(expiry_date, 'localtime') BETWEEN datetime('now', 'localtime') 
               AND datetime('now', '+3 days', 'localtime')"""
        )
        expiring = (await cursor.fetchone())[0]
        
        return {
            "total": total,
            "active": active,
            "inactive": inactive,
            "expiring": expiring
        }
