import aiosqlite
from datetime import datetime, timedelta
import aiohttp
import logging
from config import DB_PATH
from dateutil.relativedelta import relativedelta

__all__ = [
    'init_db',
    'check_user_payment',
    'add_payment',
    'get_user_data',
    'get_vpn_config',
    'get_vpn_config_days',
    'extend_vpn_config',
    'get_all_users',
    'get_user_stats',
    'delete_user',
    'extend_user_subscription',
    'get_users_by_status',
    'get_payment_stats',
    'add_bot_user',
    'give_user_subscription',
    'deactivate_user_subscription',
    'activate_user_subscription',
    'block_user',
    'unblock_user',
    'find_user_by_id',
    'generate_referral_code',
    'get_referral_code',
    'add_referral',
    'get_referral_stats',
    'get_referral_earnings',
    'get_referral_details',
    'get_all_referral_stats',
    'get_all_users_expiring_in_days',
    'mark_user_notified',
    'has_paid_subscription'
]

async def init_db():
    """Инициализация базы данных"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица пользователей VPN
        await db.execute('''CREATE TABLE IF NOT EXISTS users
                         (user_id INTEGER PRIMARY KEY,
                          subscribed BOOLEAN DEFAULT 0,
                          payment_date TEXT,
                          expiry_date TEXT,
                          config TEXT,
                          last_update TEXT)''')
        
        # Таблица всех пользователей бота
        await db.execute('''CREATE TABLE IF NOT EXISTS bot_users
                         (user_id INTEGER PRIMARY KEY,
                          username TEXT,
                          first_name TEXT,
                          last_name TEXT,
                          first_interaction TEXT,
                          last_interaction TEXT)''')
        
        # Добавляем таблицу для платежей если её нет
        await db.execute('''CREATE TABLE IF NOT EXISTS payments
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          user_id INTEGER,
                          amount REAL,
                          period INTEGER,
                          payment_date TEXT,
                          payment_method TEXT DEFAULT 'yookassa',
                          FOREIGN KEY (user_id) REFERENCES users (user_id))''')
        
        # Таблица рефералов
        await db.execute('''CREATE TABLE IF NOT EXISTS referrals
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          referrer_id INTEGER,
                          referred_id INTEGER,
                          referral_date TEXT,
                          reward_given BOOLEAN DEFAULT 0,
                          reward_amount REAL DEFAULT 0,
                          FOREIGN KEY (referrer_id) REFERENCES bot_users (user_id),
                          FOREIGN KEY (referred_id) REFERENCES bot_users (user_id))''')
        
        # Добавляем поля реферальной системы в таблицу bot_users (с проверкой существования)
        try:
            await db.execute('''ALTER TABLE bot_users ADD COLUMN referrer_id INTEGER DEFAULT NULL''')
        except Exception:
            pass  # Колонка уже существует
        
        try:
            await db.execute('''ALTER TABLE bot_users ADD COLUMN referral_code TEXT DEFAULT NULL''')
        except Exception:
            pass  # Колонка уже существует
        
        try:
            await db.execute('''ALTER TABLE bot_users ADD COLUMN total_referrals INTEGER DEFAULT 0''')
        except Exception:
            pass  # Колонка уже существует
        
        try:
            await db.execute('''ALTER TABLE bot_users ADD COLUMN referral_earnings REAL DEFAULT 0''')
        except Exception:
            pass  # Колонка уже существует
        
        await db.commit()

        # Добавляем служебные колонки при необходимости
        try:
            await db.execute("""ALTER TABLE users ADD COLUMN notified_expiring_2d INTEGER DEFAULT 0""")
        except Exception:
            pass
        
        # Добавляем колонки для уведомлений о всех подписках
        try:
            await db.execute("""ALTER TABLE users ADD COLUMN notified_3d INTEGER DEFAULT 0""")
        except Exception:
            pass
        
        try:
            await db.execute("""ALTER TABLE users ADD COLUMN notified_1d INTEGER DEFAULT 0""")
        except Exception:
            pass
        
        try:
            await db.execute("""ALTER TABLE users ADD COLUMN notified_expired INTEGER DEFAULT 0""")
        except Exception:
            pass
        
        await db.commit()

async def add_bot_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    """Добавляет пользователя в таблицу всех пользователей бота"""
    try:
        current_time = datetime.now().strftime('%d.%m.%Y %H:%M')
        
        async with aiosqlite.connect(DB_PATH) as conn:
            # Проверяем, есть ли уже такой пользователь
            cursor = await conn.execute(
                "SELECT user_id FROM bot_users WHERE user_id = ?",
                (user_id,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                # Обновляем последнее взаимодействие
                await conn.execute(
                    "UPDATE bot_users SET last_interaction = ?, username = ?, first_name = ?, last_name = ? WHERE user_id = ?",
                    (current_time, username, first_name, last_name, user_id)
                )
                logging.info(f"Обновлен пользователь бота: {user_id}")
            else:
                # Добавляем нового пользователя
                await conn.execute(
                    "INSERT INTO bot_users (user_id, username, first_name, last_name, first_interaction, last_interaction) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, username, first_name, last_name, current_time, current_time)
                )
                logging.info(f"Добавлен новый пользователь бота: {user_id} ({first_name})")
            
            await conn.commit()
            return True
    except Exception as e:
        logging.error(f"Ошибка добавления пользователя бота {user_id}: {e}")
        return False

async def check_user_payment(user_id: int) -> bool:
    """Проверяет активную подписку пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT expiry_date FROM users WHERE user_id=?",
            (user_id,)
        )
        row = await cursor.fetchone()
        
    if not row or not row[0]:
        return False
        
    try:
        # Пробуем разные форматы даты
        expiry_date_str = row[0]
        formats = ['%d.%m.%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']
        
        for fmt in formats:
            try:
                expiry_date = datetime.strptime(expiry_date_str, fmt)
                return datetime.now() < expiry_date
            except ValueError:
                continue
        
        return False
    except Exception as e:
        logging.error(f"Ошибка проверки подписки для {user_id}: {e}")
        return False

async def add_payment(user_id: int, period_months: int) -> bool:
    """Добавляет платеж и обновляет подписку"""
    try:
        payment_date = datetime.now()
        
        # Определяем сумму платежа
        prices = {1: 149, 3: 399, 6: 699, 12: 999}
        amount = prices.get(period_months, 149)
        
        # Обработка специальной подписки (7 дней за 10₽)
        if period_months == 0:  # Специальная подписка
            amount = 10
        
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute(
                "SELECT user_id FROM bot_users WHERE user_id = ?",
                (user_id,)
            )
            bot_user_exists = await cursor.fetchone()
            
            if not bot_user_exists:
                current_time = payment_date.strftime('%d.%m.%Y %H:%M')
                await conn.execute(
                    "INSERT INTO bot_users (user_id, first_interaction, last_interaction) VALUES (?, ?, ?)",
                    (user_id, current_time, current_time)
                )
                logging.info(f"Пользователь {user_id} добавлен в bot_users при оплате")
            
            # Получаем текущие данные пользователя
            cursor = await conn.execute(
                "SELECT expiry_date, config FROM users WHERE user_id=?",
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if row and row[0]:  # Если есть существующая подписка
                try:
                    formats = ['%d.%m.%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']
                    current_expiry = None
                    
                    for fmt in formats:
                        try:
                            current_expiry = datetime.strptime(row[0], fmt)
                            break
                        except ValueError:
                            continue
                    
                    if current_expiry:
                        # Продлеваем по календарным месяцам
                        if period_months == 0:  # Специальная подписка
                            expiry_date = current_expiry + timedelta(days=7)
                        else:
                            expiry_date = current_expiry + relativedelta(months=period_months)
                    else:
                        if period_months == 0:  # Специальная подписка
                            expiry_date = payment_date + timedelta(days=7)
                        else:
                            expiry_date = payment_date + relativedelta(months=period_months)
                        
                except Exception as e:
                    logging.error(f"Ошибка парсинга даты: {e}")
                    if period_months == 0:  # Специальная подписка
                        expiry_date = payment_date + timedelta(days=7)
                    else:
                        expiry_date = payment_date + relativedelta(months=period_months)
                
                # Пытаемся продлить конфиг на VPN сервере
                if period_months == 0:  # Специальная подписка
                    extend_success = await extend_vpn_config(user_id, 7)
                else:
                    # Вычисляем точное количество календарных дней для продления
                    current_date = datetime.now()
                    future_date = current_date + relativedelta(months=period_months)
                    days_difference = (future_date - current_date).days
                    extend_success = await extend_vpn_config(user_id, days_difference)
                if not extend_success:
                    logging.warning(f"Не удалось продлить конфиг для user_id={user_id}, но продолжаем")
                    
                config_id = row[1]  # Используем существующий config_id
                
            else:  # Для нового пользователя
                if period_months == 0:  # Специальная подписка
                    expiry_date = payment_date + timedelta(days=7)
                    config_id = await get_vpn_config_days(user_id, 7)
                else:
                    expiry_date = payment_date + relativedelta(months=period_months)
                    config_id = await get_vpn_config(user_id, period_months)
                if not config_id:
                    logging.error(f"Не удалось получить конфиг для user_id={user_id}")
                    return False
            
            # Обновляем данные пользователя в БД
            await conn.execute('''
                INSERT OR REPLACE INTO users 
                (user_id, subscribed, payment_date, expiry_date, config, last_update)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (
                    user_id,
                    True,
                    payment_date.strftime('%d.%m.%Y %H:%M'),
                    expiry_date.strftime('%d.%m.%Y %H:%M'),
                    config_id,
                    payment_date.strftime('%d.%m.%Y %H:%M')
                )
            )
            # Сбрасываем флаг уведомления об истечении за 2 дня
            await conn.execute(
                "UPDATE users SET notified_expiring_2d = 0 WHERE user_id = ?",
                (user_id,)
            )
            
            # Добавляем запись о платеже
            await conn.execute('''
                INSERT INTO payments (user_id, amount, period, payment_date, payment_method)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (user_id, amount, period_months, payment_date.strftime('%d.%m.%Y %H:%M'), 'yookassa')
            )
            
            await conn.commit()
            logging.info(f"Подписка успешно добавлена для пользователя {user_id} на {period_months} мес. До {expiry_date.strftime('%d.%m.%Y %H:%M')}")
            return True
            
    except Exception as e:
        logging.error(f"Ошибка в add_payment: {str(e)}", exc_info=True)
        return False

async def get_vpn_config(user_id: int, period_months: int) -> str:
    """Получает конфигурацию VPN от сервера"""
    # Вычисляем точное количество дней для календарных месяцев
    current_date = datetime.now()
    future_date = current_date + relativedelta(months=period_months)
    days_difference = (future_date - current_date).days
    
    url = "https://shardtg.ru/giveconfig"
    data = {
        "time": days_difference,  # Используем точное количество календарных дней
        "id": str(user_id),
        "server": "nl"
    }
    headers = {
        "x-api-key": "18181818"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.text()
                logging.error(f"Ошибка VPN сервера: {resp.status}")
                return None
    except Exception as e:
        logging.error(f"Ошибка получения конфига: {e}")
        return None

async def get_vpn_config_days(user_id: int, days: int) -> str:
    """Упрощенная выдача конфига на фиксированное число дней"""
    # Для коротких периодов (меньше 30 дней) используем прямое указание дней
    if days < 30:
        # Создаем специальную функцию для коротких периодов
        url = "https://shardtg.ru/giveconfig"
        data = {
            "time": days,  # Прямо указываем количество дней
            "id": str(user_id),
            "server": "nl"
        }
        headers = {
            "x-api-key": "18181818"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers) as resp:
                    if resp.status == 200:
                        return await resp.text()
                    logging.error(f"Ошибка VPN сервера для {days} дней: {resp.status}")
                    return None
        except Exception as e:
            logging.error(f"Ошибка получения конфига на {days} дней: {e}")
            return None
    else:
        # Для длинных периодов используем месяцы
        months = days // 30
        return await get_vpn_config(user_id, months)

async def get_user_data(user_id: int):
    """Получает данные пользователя из БД"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT expiry_date, config FROM users WHERE user_id=?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if row and row[0]:
            return row
        return None

async def extend_vpn_config(user_id: int, days: int) -> bool:
    """Продлевает конфигурацию VPN на сервере"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute(
                "SELECT config FROM users WHERE user_id=?",
                (user_id,)
            )
            row = await cursor.fetchone()
            if not row or not row[0]:
                logging.error(f"Не найден конфиг для user_id={user_id}")
                return False
                
            config_id = row[0].strip('"\'')  # Удаляем лишние кавычки
            
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://shardtg.ru/extendconfig",
                json={
                    "time": days, 
                    "uid": config_id,
                    "server": "nl"
                },
                headers={"x-api-key": "18181818"},
                timeout=10
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    logging.error(f"Ошибка продления: {resp.status} - {error}")
                    return False
                return True
                
    except Exception as e:
        logging.error(f"Ошибка в extend_vpn_config: {str(e)}", exc_info=True)
        return False

# Новые функции для админ панели

async def get_all_users(limit: int = 50, offset: int = 0):
    """Получает всех пользователей с пагинацией"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """SELECT user_id, subscribed, payment_date, expiry_date, config, last_update 
               FROM users ORDER BY payment_date DESC LIMIT ? OFFSET ?""",
            (limit, offset)
        )
        return await cursor.fetchall()

async def get_user_stats():
    """Получает статистику пользователей"""
    async with aiosqlite.connect(DB_PATH) as conn:
        stats = {}
        
        # Всего пользователей бота (кто запускал /start)
        cursor = await conn.execute("SELECT COUNT(*) FROM bot_users")
        stats['total_users'] = (await cursor.fetchone())[0]
        
        # Активные подписки - проверяем все пользователей программно
        cursor = await conn.execute("SELECT user_id, expiry_date FROM users WHERE subscribed = 1")
        all_subscribed = await cursor.fetchall()
        
        active_count = 0
        for user_id, expiry_date in all_subscribed:
            if expiry_date and is_subscription_active_check(expiry_date):
                active_count += 1
        
        stats['active_users'] = active_count
        
        # Новые за сегодня (кто запустил бота)
        today = datetime.now().strftime('%d.%m.%Y')
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM bot_users WHERE first_interaction LIKE ?",
            (f"{today}%",)
        )
        stats['new_today'] = (await cursor.fetchone())[0]
        
        # Новые за неделю (кто запустил бота)
        cursor = await conn.execute("SELECT user_id, first_interaction FROM bot_users")
        all_bot_users = await cursor.fetchall()
        
        week_ago = datetime.now() - timedelta(days=7)
        new_week = 0
        
        for user_id, first_interaction in all_bot_users:
            if first_interaction:
                try:
                    formats = ['%d.%m.%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']
                    for fmt in formats:
                        try:
                            interaction_date = datetime.strptime(first_interaction, fmt)
                            if interaction_date >= week_ago:
                                new_week += 1
                            break
                        except ValueError:
                            continue
                except:
                    pass
        
        stats['new_week'] = new_week
        
        return stats

def is_subscription_active_check(expiry_date_str: str) -> bool:
    """Проверяет активность подписки с поддержкой разных форматов"""
    if not expiry_date_str:
        return False
    
    try:
        formats = ['%d.%m.%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']
        for fmt in formats:
            try:
                expiry_date = datetime.strptime(expiry_date_str, fmt)
                return datetime.now() < expiry_date
            except ValueError:
                continue
        return False
    except Exception as e:
        logging.error(f"Ошибка проверки даты {expiry_date_str}: {e}")
        return False

async def get_users_by_status(status: str, limit: int = 20):
    """Получает пользователей по статусу"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT user_id, expiry_date, subscribed FROM users ORDER BY payment_date DESC"
        )
        all_users = await cursor.fetchall()
        
        result = []
        count = 0
        
        for user_id, expiry_date, subscribed in all_users:
            if count >= limit:
                break
                
            is_active = False
            if expiry_date and subscribed:
                is_active = is_subscription_active_check(expiry_date)
            
            if status == "active" and is_active:
                result.append((user_id, expiry_date))
                count += 1
            elif status == "expired" and subscribed and not is_active and expiry_date:
                result.append((user_id, expiry_date))
                count += 1
            elif status == "expiring" and is_active and expiry_date:
                # Проверяем, истекает ли в ближайшие 3 дня
                try:
                    formats = ['%d.%m.%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']
                    for fmt in formats:
                        try:
                            exp_date = datetime.strptime(expiry_date, fmt)
                            days_left = (exp_date - datetime.now()).days
                            if 0 <= days_left <= 3:
                                result.append((user_id, expiry_date))
                                count += 1
                            break
                        except ValueError:
                            continue
                except:
                    pass
        
        return result

async def get_users_expiring_in_days(days: int = 2, limit: int = 100):
    """Возвращает пользователей, у кого подписка истекает через days дней, и кто ещё не уведомлён"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute(
                "SELECT user_id, expiry_date FROM users WHERE subscribed = 1 AND expiry_date IS NOT NULL AND COALESCE(notified_expiring_2d, 0) = 0"
            )
            rows = await cursor.fetchall()

        result = []
        now = datetime.now()

        for user_id, expiry_date in rows:
            if not expiry_date:
                continue
            for fmt in ['%d.%m.%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                try:
                    exp = datetime.strptime(expiry_date, fmt)
                    delta_days = (exp.date() - now.date()).days
                    if delta_days == days:
                        result.append((user_id, exp.strftime('%d.%m.%Y %H:%M')))
                    break
                except ValueError:
                    continue
            if len(result) >= limit:
                break

        return result
    except Exception as e:
        logging.error(f"Ошибка get_users_expiring_in_days: {e}")
        return []

async def mark_user_notified_expiring(user_id: int, field: str):
    """Ставит флаг уведомления по полю (например, notified_expiring_3d)"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                f"UPDATE users SET {field} = 1 WHERE user_id = ?",
                (user_id,)
            )
            await conn.commit()
            return True
    except Exception as e:
        print(f"Ошибка mark_user_notified_expiring: {e}")
        return False

async def get_all_users_expiring_in_days(days: int, limit: int = 100):
    """Возвращает всех пользователей с подпиской, у кого подписка истекает через days дней"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            # Определяем поле для проверки уведомления
            if days == 3:
                notification_field = "COALESCE(u.notified_3d, 0) = 0"
            elif days == 1:
                notification_field = "COALESCE(u.notified_1d, 0) = 0"
            elif days == 0:
                notification_field = "COALESCE(u.notified_expired, 0) = 0"
            else:
                return []
            
            cursor = await conn.execute(
                f"""SELECT u.user_id, u.expiry_date, p.payment_method
                   FROM users u
                   LEFT JOIN payments p ON u.user_id = p.user_id
                   WHERE u.subscribed = 1 
                   AND u.expiry_date IS NOT NULL
                   AND {notification_field}""",
            )
            rows = await cursor.fetchall()

        result = []
        now = datetime.now()

        for user_id, expiry_date, payment_method in rows:
            if not expiry_date:
                continue
            for fmt in ['%d.%m.%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                try:
                    exp = datetime.strptime(expiry_date, fmt)
                    if days == 0:  # Истекла
                        if exp.date() < now.date():
                            result.append((user_id, exp.strftime('%d.%m.%Y %H:%M'), payment_method or 'unknown'))
                    else:  # Истекает через N дней
                        delta_days = (exp.date() - now.date()).days
                        if delta_days == days:
                            result.append((user_id, exp.strftime('%d.%m.%Y %H:%M'), payment_method or 'unknown'))
                    break
                except ValueError:
                    continue
            if len(result) >= limit:
                break

        return result
    except Exception as e:
        logging.error(f"Ошибка get_all_users_expiring_in_days: {e}")
        return []

async def mark_user_notified(user_id: int, notification_type: str):
    """Ставит флаг уведомления для пользователя"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            field_map = {
                '2d': 'notified_expiring_2d',
                '3d': 'notified_3d',
                '1d': 'notified_1d', 
                'expired': 'notified_expired'
            }
            field = field_map.get(notification_type)
            if field:
                await conn.execute(
                    f"UPDATE users SET {field} = 1 WHERE user_id = ?",
                    (user_id,)
                )
                await conn.commit()
                return True
        return False
    except Exception as e:
        logging.error(f"Ошибка mark_user_notified: {e}")
        return False


async def get_payment_stats():
    """Получает статистику платежей"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            stats = {}
            
            # Доход за сегодня
            today = datetime.now().strftime('%d.%m.%Y')
            cursor = await conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE payment_date LIKE ?",
                (f"{today}%",)
            )
            result = await cursor.fetchone()
            stats['revenue_today'] = result[0] if result else 0
            
            # Доход за неделю - программная проверка
            cursor = await conn.execute("SELECT amount, payment_date FROM payments")
            all_payments = await cursor.fetchall()
            
            revenue_week = 0
            revenue_month = 0
            
            if all_payments:
                week_ago = datetime.now() - timedelta(days=7)
                month_ago = datetime.now() - timedelta(days=30)
                
                for amount, payment_date in all_payments:
                    if payment_date and amount:
                        try:
                            formats = ['%d.%m.%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']
                            for fmt in formats:
                                try:
                                    pay_date = datetime.strptime(payment_date, fmt)
                                    if pay_date >= week_ago:
                                        revenue_week += amount
                                    if pay_date >= month_ago:
                                        revenue_month += amount
                                    break
                                except ValueError:
                                    continue
                        except:
                            pass
            
            stats['revenue_week'] = revenue_week
            stats['revenue_month'] = revenue_month
            
            # Средний чек
            cursor = await conn.execute("SELECT AVG(amount) FROM payments")
            avg_result = await cursor.fetchone()
            stats['avg_payment'] = round(avg_result[0], 2) if avg_result and avg_result[0] else 0
            
            # Подписки по периодам
            for period in [1, 3, 6, 12]:
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM payments WHERE period = ?",
                    (period,)
                )
                result = await cursor.fetchone()
                stats[f'subs_{period}m'] = result[0] if result else 0
            
            return stats
    except Exception as e:
        logging.error(f"Ошибка получения статистики платежей: {e}")
        return {
            'revenue_today': 0,
            'revenue_week': 0,
            'revenue_month': 0,
            'avg_payment': 0,
            'subs_1m': 0,
            'subs_3m': 0,
            'subs_6m': 0,
            'subs_12m': 0
        }

async def delete_user(user_id: int):
    """Удаляет пользователя из БД"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await conn.execute("DELETE FROM payments WHERE user_id = ?", (user_id,))
        await conn.execute("DELETE FROM bot_users WHERE user_id = ?", (user_id,))
        await conn.commit()
        return True

async def extend_user_subscription(user_id: int, days: int):
    """Продлевает подписку пользователя"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT expiry_date FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        
        if row and row[0]:
            try:
                formats = ['%d.%m.%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']
                current_expiry = None
                
                for fmt in formats:
                    try:
                        current_expiry = datetime.strptime(row[0], fmt)
                        break
                    except ValueError:
                        continue
                
                if current_expiry:
                    # Продлеваем по календарным месяцам
                    months = days // 30 if days >= 30 else 1
                    new_expiry = current_expiry + relativedelta(months=months)
                    
                    await conn.execute(
                        "UPDATE users SET expiry_date = ?, subscribed = 1, notified_expiring_2d = 0 WHERE user_id = ?",
                        (new_expiry.strftime('%d.%m.%Y %H:%M'), user_id)
                    )
                    await conn.commit()
                    
                    # Пытаемся продлить на VPN сервере
                    await extend_vpn_config(user_id, days)
                    
                    logging.info(f"Подписка пользователя {user_id} продлена на {months} месяцев. Новое окончание: {new_expiry.strftime('%d.%m.%Y %H:%M')}")
                    return True
            except Exception as e:
                logging.error(f"Ошибка продления подписки: {e}")
                return False
        return False

async def find_user_by_id(user_id: int):
    """Находит пользователя по ID"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """SELECT user_id, subscribed, payment_date, expiry_date, config, last_update 
               FROM users WHERE user_id = ?""",
            (user_id,)
        )
        return await cursor.fetchone()

async def block_user(user_id: int):
    """Блокирует пользователя"""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET subscribed = 0 WHERE user_id = ?",
            (user_id,)
        )
        await conn.commit()
        return True

async def unblock_user(user_id: int):
    """Разблокирует пользователя"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT expiry_date FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        
        if row and row[0]:
            # Проверяем, не истекла ли подписка
            try:
                formats = ['%d.%m.%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']
                expiry_date = None
                
                for fmt in formats:
                    try:
                        expiry_date = datetime.strptime(row[0], fmt)
                        break
                    except ValueError:
                        continue
                
                if expiry_date and expiry_date > datetime.now():
                    await conn.execute(
                        "UPDATE users SET subscribed = 1 WHERE user_id = ?",
                        (user_id,)
                    )
                    await conn.commit()
                    return True
            except Exception as e:
                logging.error(f"Ошибка разблокировки пользователя: {e}")
        return False

async def give_user_subscription(user_id: int, days: int):
    """Выдает подписку пользователю (создает новую запись)"""
    try:
        current_time = datetime.now()
        # Используем фиксированные дни для синхронизации с VPN сервером
        expiry_date = current_time + timedelta(days=days)
        
        # Получаем конфиг от VPN сервера
        if days < 30:
            config_id = await get_vpn_config_days(user_id, days)
        else:
            config_id = await get_vpn_config(user_id, days // 30)
        if not config_id:
            logging.error(f"Не удалось получить конфиг для user_id={user_id}")
            return False
        
        async with aiosqlite.connect(DB_PATH) as conn:
            # Создаем новую подписку
            await conn.execute('''
                INSERT OR REPLACE INTO users 
                (user_id, subscribed, payment_date, expiry_date, config, last_update, notified_expiring_2d)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    user_id,
                    True,
                    current_time.strftime('%d.%m.%Y %H:%M'),
                    expiry_date.strftime('%d.%m.%Y %H:%M'),
                    config_id,
                    current_time.strftime('%d.%m.%Y %H:%M'),
                    0
                )
            )
            
            # Добавляем запись о "платеже" (админская выдача)
            await conn.execute('''
                INSERT INTO payments (user_id, amount, period, payment_date, payment_method)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (user_id, 0, days // 30 if days >= 30 else 1, current_time.strftime('%d.%m.%Y %H:%M'), 'admin_gift')
            )
            
            await conn.commit()
            logging.info(f"Админская подписка выдана пользователю {user_id} на {days} дней. До {expiry_date.strftime('%d.%m.%Y %H:%M')}")
            return True
            
    except Exception as e:
        logging.error(f"Ошибка выдачи подписки: {str(e)}", exc_info=True)
        return False



async def deactivate_user_subscription(user_id: int):
    """Деактивирует подписку пользователя"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            # Устанавливаем дату окончания на вчера
            yesterday = datetime.now() - timedelta(days=1)
            
            await conn.execute(
                "UPDATE users SET subscribed = 0, expiry_date = ?, notified_expiring_2d = 0 WHERE user_id = ?",
                (yesterday.strftime('%d.%m.%Y %H:%M'), user_id)
            )
            await conn.commit()
            logging.info(f"Подписка пользователя {user_id} деактивирована. Дата окончания установлена на {yesterday.strftime('%d.%m.%Y %H:%M')}")
            return True
    except Exception as e:
        logging.error(f"Ошибка деактивации подписки: {e}")
        return False

async def activate_user_subscription(user_id: int):
    """Активирует подписку пользователя (если дата не истекла критично)"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute(
                "SELECT expiry_date FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if row and row[0]:
                try:
                    formats = ['%d.%m.%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']
                    expiry_date = None
                    
                    for fmt in formats:
                        try:
                            expiry_date = datetime.strptime(row[0], fmt)
                            break
                        except ValueError:
                            continue
                    
                    if expiry_date:
                        # Если подписка истекла недавно (менее 30 дней назад), активируем
                        days_expired = (datetime.now() - expiry_date).days
                        if days_expired <= 30:
                            await conn.execute(
                                "UPDATE users SET subscribed = 1 WHERE user_id = ?",
                                (user_id,)
                            )
                            await conn.commit()
                            
                            # Пытаемся активировать на VPN сервере
                            await extend_vpn_config(user_id, max(1, -days_expired))
                            
                            logging.info(f"Подписка пользователя {user_id} активирована. Истекла {days_expired} дней назад")
                            return True
                        else:
                            # Если истекла давно, продлеваем на 7 дней от текущей даты
                            new_expiry = datetime.now() + timedelta(days=7)
                            await conn.execute(
                                "UPDATE users SET subscribed = 1, expiry_date = ?, notified_expiring_2d = 0 WHERE user_id = ?",
                                (new_expiry.strftime('%d.%m.%Y %H:%M'), user_id)
                            )
                            await conn.commit()
                            
                            # Продлеваем на VPN сервере
                            await extend_vpn_config(user_id, 7)
                            
                            logging.info(f"Подписка пользователя {user_id} продлена на 7 дней. До {new_expiry.strftime('%d.%m.%Y %H:%M')}")
                            return True
                except Exception as e:
                    logging.error(f"Ошибка парсинга даты при активации: {e}")
                    return False
        return False
    except Exception as e:
        logging.error(f"Ошибка активации подписки: {e}")
        return False

# ========== РЕФЕРАЛЬНАЯ СИСТЕМА ==========

async def generate_referral_code(user_id: int) -> str:
    """Генерирует уникальный реферальный код для пользователя"""
    import hashlib
    import random
    
    # Создаем код на основе user_id + случайного числа
    code_data = f"{user_id}_{random.randint(1000, 9999)}"
    code = hashlib.md5(code_data.encode()).hexdigest()[:8].upper()
    
    async with aiosqlite.connect(DB_PATH) as conn:
        # Проверяем уникальность кода
        cursor = await conn.execute(
            "SELECT user_id FROM bot_users WHERE referral_code = ?",
            (code,)
        )
        existing = await cursor.fetchone()
        
        if existing:
            # Если код уже существует, генерируем новый
            return await generate_referral_code(user_id)
        
        # Сохраняем код для пользователя
        await conn.execute(
            "UPDATE bot_users SET referral_code = ? WHERE user_id = ?",
            (code, user_id)
        )
        await conn.commit()
        
    return code

async def get_referral_code(user_id: int) -> str:
    """Получает реферальный код пользователя или создает новый"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT referral_code FROM bot_users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        
        if row and row[0]:
            return row[0]
        else:
            return await generate_referral_code(user_id)

async def add_referral(referrer_id: int, referred_id: int) -> bool:
    """Добавляет реферала в систему"""
    try:
        current_time = datetime.now().strftime('%d.%m.%Y %H:%M')
        
        async with aiosqlite.connect(DB_PATH) as conn:
            # Проверяем, что реферал еще не был добавлен
            cursor = await conn.execute(
                "SELECT id FROM referrals WHERE referred_id = ?",
                (referred_id,)
            )
            existing = await cursor.fetchone()
            
            if existing:
                return False  # Реферал уже существует
            
            # Добавляем реферала
            await conn.execute(
                "INSERT INTO referrals (referrer_id, referred_id, referral_date) VALUES (?, ?, ?)",
                (referrer_id, referred_id, current_time)
            )
            
            # Обновляем счетчик рефералов у реферера
            await conn.execute(
                "UPDATE bot_users SET total_referrals = total_referrals + 1 WHERE user_id = ?",
                (referrer_id,)
            )
            
            # Устанавливаем реферера для нового пользователя
            await conn.execute(
                "UPDATE bot_users SET referrer_id = ? WHERE user_id = ?",
                (referrer_id, referred_id)
            )
            
            await conn.commit()
            return True
            
    except Exception as e:
        logging.error(f"Ошибка добавления реферала: {e}")
        return False

async def get_referral_stats(user_id: int) -> dict:
    """Получает статистику рефералов пользователя"""
    async with aiosqlite.connect(DB_PATH) as conn:
        # Общее количество рефералов
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = ?",
            (user_id,)
        )
        total_referrals = (await cursor.fetchone())[0]
        
        # Количество рефералов, которые оформили платную подписку (исключаем trial)
        cursor = await conn.execute(
            """SELECT COUNT(*) FROM referrals r 
               JOIN users u ON r.referred_id = u.user_id 
               JOIN payments p ON u.user_id = p.user_id
               WHERE r.referrer_id = ? AND u.subscribed = 1 AND p.payment_method != 'trial'""",
            (user_id,)
        )
        subscribed_referrals = (await cursor.fetchone())[0]
        
        # Количество рефералов без подписки (включая trial)
        cursor = await conn.execute(
            """SELECT COUNT(*) FROM referrals r 
               LEFT JOIN users u ON r.referred_id = u.user_id 
               LEFT JOIN payments p ON u.user_id = p.user_id
               WHERE r.referrer_id = ? AND (u.subscribed = 0 OR u.subscribed IS NULL OR p.payment_method = 'trial')""",
            (user_id,)
        )
        unsubscribed_referrals = (await cursor.fetchone())[0]
        
        return {
            'total_referrals': total_referrals,
            'subscribed_referrals': subscribed_referrals,
            'unsubscribed_referrals': unsubscribed_referrals
        }

async def get_referral_earnings(user_id: int) -> float:
    """Получает общий заработок пользователя с рефералов"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT COALESCE(SUM(reward_amount), 0) FROM referrals WHERE referrer_id = ? AND reward_given = 1",
            (user_id,)
        )
        result = await cursor.fetchone()
        return result[0] if result else 0.0

async def get_referral_details(user_id: int) -> list:
    """Получает детальную информацию о рефералах пользователя для админки"""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """SELECT 
                r.referred_id,
                bu.username,
                bu.first_name,
                bu.last_name,
                r.referral_date,
                CASE 
                    WHEN u.subscribed = 1 THEN 'Подписан'
                    ELSE 'Не подписан'
                END as status
               FROM referrals r
               LEFT JOIN bot_users bu ON r.referred_id = bu.user_id
               LEFT JOIN users u ON r.referred_id = u.user_id
               WHERE r.referrer_id = ?
               ORDER BY r.referral_date DESC""",
            (user_id,)
        )
        return await cursor.fetchall()

async def get_all_referral_stats() -> dict:
    """Получает общую статистику рефералов для админки"""
    async with aiosqlite.connect(DB_PATH) as conn:
        # Общее количество рефералов
        cursor = await conn.execute("SELECT COUNT(*) FROM referrals")
        total_referrals = (await cursor.fetchone())[0]
        
        # Количество рефералов с платной подпиской (исключаем trial)
        cursor = await conn.execute(
            """SELECT COUNT(*) FROM referrals r 
               JOIN users u ON r.referred_id = u.user_id 
               JOIN payments p ON u.user_id = p.user_id
               WHERE u.subscribed = 1 AND p.payment_method != 'trial'"""
        )
        subscribed_referrals = (await cursor.fetchone())[0]
        
        # Количество рефералов без подписки (включая trial)
        cursor = await conn.execute(
            """SELECT COUNT(*) FROM referrals r 
               LEFT JOIN users u ON r.referred_id = u.user_id 
               LEFT JOIN payments p ON u.user_id = p.user_id
               WHERE u.subscribed = 0 OR u.subscribed IS NULL OR p.payment_method = 'trial'"""
        )
        unsubscribed_referrals = (await cursor.fetchone())[0]
        
        # Топ рефереров
        cursor = await conn.execute(
            """SELECT 
                r.referrer_id,
                bu.username,
                bu.first_name,
                COUNT(r.referred_id) as total_refs,
                COUNT(CASE WHEN u.subscribed = 1 AND p.payment_method != 'trial' THEN 1 END) as subscribed_refs
               FROM referrals r
               LEFT JOIN bot_users bu ON r.referrer_id = bu.user_id
               LEFT JOIN users u ON r.referred_id = u.user_id
               LEFT JOIN payments p ON u.user_id = p.user_id
               GROUP BY r.referrer_id
               ORDER BY total_refs DESC
               LIMIT 10"""
        )
        top_referrers = await cursor.fetchall()
        
        return {
            'total_referrals': total_referrals,
            'subscribed_referrals': subscribed_referrals,
            'unsubscribed_referrals': unsubscribed_referrals,
            'top_referrers': top_referrers
        }

async def has_paid_subscription(user_id: int) -> bool:
    """Проверяет, была ли у пользователя когда-либо платная подписка"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute(
                "SELECT 1 FROM payments WHERE user_id = ? AND payment_method != 'trial' LIMIT 1",
                (user_id,)
            )
            result = await cursor.fetchone()
            return result is not None
    except Exception as e:
        logging.error(f"Ошибка has_paid_subscription: {e}")
        return False
