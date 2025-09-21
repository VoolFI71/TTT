import aiosqlite
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from config import DB_PATH

async def find_user_by_id(user_id: int) -> Optional[Dict]:
    """Находит пользователя по ID"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """SELECT user_id, subscribed, payment_date, expiry_date, config, last_update 
               FROM users WHERE user_id = ?""",
            (user_id,)
        )
        row = await cursor.fetchone()
        
        if row:
            return {
                "user_id": row[0],
                "subscribed": bool(row[1]),
                "payment_date": row[2],
                "expiry_date": row[3],
                "config": row[4],
                "last_update": row[5],
                "is_active": is_subscription_active(row[3]) if row[3] else False
            }
        return None

def is_subscription_active(expiry_date_str: str) -> bool:
    """Проверяет активность подписки"""
    try:
        expiry_date = datetime.strptime(expiry_date_str, '%d.%m.%Y %H:%M')
        return datetime.now() < expiry_date
    except (ValueError, TypeError):
        return False

async def get_expiring_subscriptions(days: int = 3) -> List[Dict]:
    """Получает подписки, истекающие в ближайшие дни"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """SELECT user_id, expiry_date FROM users 
               WHERE subscribed = 1 AND datetime(expiry_date, 'localtime') BETWEEN datetime('now', 'localtime') 
               AND datetime('now', '+{} days', 'localtime')
               ORDER BY expiry_date ASC""".format(days)
        )
        rows = await cursor.fetchall()
        
        return [{"user_id": row[0], "expiry_date": row[1]} for row in rows]

async def extend_subscription(user_id: int, days: int) -> bool:
    """Продлевает подписку пользователя на указанное количество дней"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT expiry_date FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        
        if row and row[0]:
            try:
                current_expiry = datetime.strptime(row[0], '%d.%m.%Y %H:%M')
                
                # Если подписка еще активна, продлеваем от даты окончания
                # Если истекла, продлеваем от текущей даты
                if current_expiry > datetime.now():
                    new_expiry = current_expiry + timedelta(days=days)
                else:
                    new_expiry = datetime.now() + timedelta(days=days)
                
                await conn.execute(
                    "UPDATE users SET expiry_date = ?, subscribed = 1 WHERE user_id = ?",
                    (new_expiry.strftime('%d.%m.%Y %H:%M'), user_id)
                )
                await conn.commit()
                return True
            except ValueError:
                return False
        return False

async def block_user(user_id: int) -> bool:
    """Блокирует пользователя (деактивирует подписку)"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET subscribed = 0 WHERE user_id = ?",
            (user_id,)
        )
        await conn.commit()
        return True

async def unblock_user(user_id: int) -> bool:
    """Разблокирует пользователя"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT expiry_date FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        
        if row and row[0]:
            # Проверяем, не истекла ли подписка
            if is_subscription_active(row[0]):
                await conn.execute(
                    "UPDATE users SET subscribed = 1 WHERE user_id = ?",
                    (user_id,)
                )
                await conn.commit()
                return True
        return False

async def get_user_statistics() -> Dict:
    """Получает детальную статистику по пользователям"""
    async with aiosqlite.connect(DB_PATH) as conn:
        stats = {}
        
        # Общее количество пользователей
        cursor = await conn.execute("SELECT COUNT(*) FROM users")
        stats['total_users'] = (await cursor.fetchone())[0]
        
        # Активные подписки
        cursor = await conn.execute(
            """SELECT COUNT(*) FROM users 
               WHERE subscribed = 1 AND datetime(expiry_date, 'localtime') > datetime('now', 'localtime')"""
        )
        stats['active_subscriptions'] = (await cursor.fetchone())[0]
        
        # Истекшие подписки
        cursor = await conn.execute(
            """SELECT COUNT(*) FROM users 
               WHERE subscribed = 1 AND datetime(expiry_date, 'localtime') <= datetime('now', 'localtime')"""
        )
        stats['expired_subscriptions'] = (await cursor.fetchone())[0]
        
        # Заблокированные пользователи
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM users WHERE subscribed = 0"
        )
        stats['blocked_users'] = (await cursor.fetchone())[0]
        
        # Новые пользователи за последние 24 часа
        cursor = await conn.execute(
            """SELECT COUNT(*) FROM users 
               WHERE datetime(payment_date, 'localtime') > datetime('now', '-1 day', 'localtime')"""
        )
        stats['new_users_24h'] = (await cursor.fetchone())[0]
        
        # Новые пользователи за последние 7 дней
        cursor = await conn.execute(
            """SELECT COUNT(*) FROM users 
               WHERE datetime(payment_date, 'localtime') > datetime('now', '-7 days', 'localtime')"""
        )
        stats['new_users_7d'] = (await cursor.fetchone())[0]
        
        return stats

async def search_users_by_pattern(pattern: str, limit: int = 10) -> List[Dict]:
    """Поиск пользователей по паттерну (ID или части конфига)"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """SELECT user_id, subscribed, payment_date, expiry_date 
               FROM users 
               WHERE CAST(user_id AS TEXT) LIKE ? OR config LIKE ?
               ORDER BY payment_date DESC
               LIMIT ?""",
            (f"%{pattern}%", f"%{pattern}%", limit)
        )
        rows = await cursor.fetchall()
        
        return [
            {
                "user_id": row[0],
                "subscribed": bool(row[1]),
                "payment_date": row[2],
                "expiry_date": row[3],
                "is_active": is_subscription_active(row[3]) if row[3] else False
            }
            for row in rows
        ]
