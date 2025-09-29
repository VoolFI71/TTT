import aiosqlite
from datetime import datetime, timedelta
import aiohttp
import logging
from config import DB_PATH, PRICES
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
    'has_paid_subscription',
    'has_used_trial',
    'grant_trial_14d',
    'attach_referrer_chain',
    'get_uplines',
    'accrue_referral_commissions',
    'get_referral_overview',
    'calculate_amount_for_period'
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
        
        # Добавляем колонку для отметки использования триала (если её нет)
        try:
            await db.execute("""ALTER TABLE bot_users ADD COLUMN trial_used INTEGER DEFAULT 0""")
        except Exception:
            pass

        # Баланс реферальный
        try:
            await db.execute("""ALTER TABLE bot_users ADD COLUMN referral_balance REAL DEFAULT 0""")
        except Exception:
            pass

        # Таблица фиксации реферальных начислений
        await db.execute('''CREATE TABLE IF NOT EXISTS referral_rewards
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          payer_id INTEGER,
                          beneficiary_id INTEGER,
                          level INTEGER,
                          amount REAL,
                          created_at TEXT,
                          method TEXT)''')

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

async def add_payment(user_id: int, period_months: int, payment_method: str = 'yookassa') -> bool:
    """Добавляет платеж и обновляет подписку"""
    try:
        payment_date = datetime.now()
        
        # Определяем сумму платежа по актуальным ценам из конфигурации (в рублях)
        if period_months == 0:
            amount = 1  # Специальная подписка 7 дней
        else:
            try:
                # PRICES хранит цены в копейках
                amount = PRICES.get(str(period_months), PRICES.get('1')) // 100
            except Exception:
                amount = 0
        
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
                (user_id, amount, period_months, payment_date.strftime('%d.%m.%Y %H:%M'), payment_method)
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
            
            # Подписки по периодам (включая спец-подписку 7 дней как period=0)
            for period in [0, 1, 3, 6, 12]:
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM payments WHERE period = ?",
                    (period,)
                )
                result = await cursor.fetchone()
                if period == 0:
                    stats['subs_7d'] = result[0] if result else 0
                else:
                    stats[f'subs_{period}m'] = result[0] if result else 0
            
            return stats
    except Exception as e:
        logging.error(f"Ошибка получения статистики платежей: {e}")
        return {
            'revenue_today': 0,
            'revenue_week': 0,
            'revenue_month': 0,
            'avg_payment': 0,
            'subs_7d': 0,
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
                    # Продлеваем на точное количество дней
                    new_expiry = current_expiry + timedelta(days=days)

                    await conn.execute(
                        "UPDATE users SET expiry_date = ?, subscribed = 1, notified_expiring_2d = 0 WHERE user_id = ?",
                        (new_expiry.strftime('%d.%m.%Y %H:%M'), user_id)
                    )
                    await conn.commit()

                    # Пытаемся продлить на VPN сервере (в днях)
                    await extend_vpn_config(user_id, days)

                    logging.info(f"Подписка пользователя {user_id} продлена на {days} дней. Новое окончание: {new_expiry.strftime('%d.%m.%Y %H:%M')}")
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

async def has_used_trial(user_id: int) -> bool:
    """Проверяет, использовал ли пользователь пробный период"""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute(
                "SELECT trial_used FROM bot_users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            return bool(row and row[0])
    except Exception as e:
        logging.error(f"Ошибка has_used_trial: {e}")
        return False

async def grant_trial_14d(user_id: int) -> bool:
    """Выдаёт пробный доступ на 14 дней единожды"""
    try:
        # если нет записи в bot_users — создаём
        await add_bot_user(user_id)

        # проверяем, не использовал ли триал ранее
        if await has_used_trial(user_id):
            return False

        # выдаём подписку на 14 дней через унифицированный путь
        success = await give_user_subscription(user_id, 14)
        if not success:
            return False

        # отмечаем триал как использованный
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE bot_users SET trial_used = 1 WHERE user_id = ?",
                (user_id,)
            )
            # логируем псевдо-платёж типа trial для аналитики
            now = datetime.now().strftime('%d.%m.%Y %H:%M')
            await conn.execute(
                "INSERT INTO payments (user_id, amount, period, payment_date, payment_method) VALUES (?, ?, ?, ?, ?)",
                (user_id, 0, 0, now, 'trial')
            )
            await conn.commit()
        return True
    except Exception as e:
        logging.error(f"Ошибка grant_trial_14d: {e}", exc_info=True)
        return False

def calculate_amount_for_period(period_months: int) -> int:
    """Возвращает сумму в рублях для периода (0 => спец 7 дней = 1₽)."""
    if period_months == 0:
        return 1
    try:
        return PRICES.get(str(period_months), PRICES.get('1')) // 100
    except Exception:
        return 0

async def attach_referrer_chain(new_user_id: int, referrer_1_id: int) -> bool:
    """Привязывает пользователя к рефереру 1-й линии (если ещё не привязан)."""
    if new_user_id == referrer_1_id:
        return False
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            # Проверяем, нет ли уже привязки
            cursor = await conn.execute(
                "SELECT referrer_id FROM bot_users WHERE user_id = ?",
                (new_user_id,)
            )
            row = await cursor.fetchone()
            if row and row[0]:
                return False

            # Проверяем, что пользователь НЕ был в bot_users ранее (первый заход)
            cursor = await conn.execute(
                "SELECT first_interaction FROM bot_users WHERE user_id = ?",
                (new_user_id,)
            )
            existing_user = await cursor.fetchone()
            if existing_user:
                # Пользователь уже был в системе - не считаем рефералом
                return False

            # Убеждаемся, что оба есть в bot_users
            await add_bot_user(new_user_id)
            await add_bot_user(referrer_1_id)

            # Сохраняем прямого реферера
            await conn.execute(
                "UPDATE bot_users SET referrer_id = ? WHERE user_id = ?",
                (referrer_1_id, new_user_id)
            )
            
            logging.info(f"Привязан реферал {new_user_id} к рефереру {referrer_1_id}")

            # Фиксируем связь в таблице referrals (только 1-я линия)
            current_time = datetime.now().strftime('%d.%m.%Y %H:%M')
            await conn.execute(
                "INSERT INTO referrals (referrer_id, referred_id, referral_date) VALUES (?, ?, ?)",
                (referrer_1_id, new_user_id, current_time)
            )

            # Инкремент счётчика 1-й линии у реферера
            await conn.execute(
                "UPDATE bot_users SET total_referrals = COALESCE(total_referrals, 0) + 1 WHERE user_id = ?",
                (referrer_1_id,)
            )

            await conn.commit()
            return True
    except Exception as e:
        logging.error(f"Ошибка attach_referrer_chain: {e}")
        return False

async def get_uplines(user_id: int):
    """Возвращает кортеж (lvl1, lvl2, lvl3) для данного пользователя."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            # lvl1
            cursor = await conn.execute(
                "SELECT referrer_id FROM bot_users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            lvl1 = row[0] if row and row[0] else None
            lvl2 = None
            lvl3 = None
            if lvl1:
                cursor = await conn.execute(
                    "SELECT referrer_id FROM bot_users WHERE user_id = ?",
                    (lvl1,)
                )
                row = await cursor.fetchone()
                lvl2 = row[0] if row and row[0] else None
                if lvl2:
                    cursor = await conn.execute(
                        "SELECT referrer_id FROM bot_users WHERE user_id = ?",
                        (lvl2,)
                    )
                    row = await cursor.fetchone()
                    lvl3 = row[0] if row and row[0] else None
            return (lvl1, lvl2, lvl3)
    except Exception as e:
        logging.error(f"Ошибка get_uplines: {e}")
        return (None, None, None)

async def accrue_referral_commissions(payer_id: int, amount_rub: float, method: str = 'unknown', bot=None) -> None:
    """Начисляет вознаграждения трём уровням (35%/10%/5%) и пишет лог."""
    try:
        if amount_rub is None or amount_rub <= 0:
            return
        lvl1, lvl2, lvl3 = await get_uplines(payer_id)
        shares = [0.35, 0.10, 0.05]
        beneficiaries = [lvl1, lvl2, lvl3]
        now = datetime.now().strftime('%d.%m.%Y %H:%M')
        async with aiosqlite.connect(DB_PATH) as conn:
            for level, (beneficiary, share) in enumerate(zip(beneficiaries, shares), start=1):
                if not beneficiary:
                    continue
                if beneficiary == payer_id:
                    continue
                reward = round(amount_rub * share, 2)
                if reward <= 0:
                    continue
                await conn.execute(
                    "UPDATE bot_users SET referral_balance = COALESCE(referral_balance, 0) + ? WHERE user_id = ?",
                    (reward, beneficiary)
                )
                await conn.execute(
                    "INSERT INTO referral_rewards (payer_id, beneficiary_id, level, amount, created_at, method) VALUES (?, ?, ?, ?, ?, ?)",
                    (payer_id, beneficiary, level, reward, now, method)
                )
                
                # Отправляем уведомление рефереру
                if bot:
                    try:
                        # Получаем новый баланс
                        cursor = await conn.execute(
                            "SELECT referral_balance FROM bot_users WHERE user_id = ?",
                            (beneficiary,)
                        )
                        new_balance = (await cursor.fetchone())[0]
                        
                        # Определяем период подписки
                        period_text = "7 дней" if amount_rub == 1 else f"{int(amount_rub/99)} мес." if amount_rub >= 99 else f"{int(amount_rub/279)} мес." if amount_rub >= 279 else f"{int(amount_rub/549)} мес." if amount_rub >= 549 else f"{int(amount_rub/999)} мес."
                        
                        # Определяем процент
                        percentage = int(share * 100)
                        
                        notification_text = f"""🎁 <b>Ваше реферальное вознаграждение!</b>

Вы получили <b>{reward:.2f} ₽ ({percentage}%)</b> за покупку <b>{period_text} подписки</b> приглашённым пользователем по {level}-й линии.

💰 <b>Текущий реферальный баланс: {new_balance:.2f}₽</b>"""
                        
                        await bot.send_message(
                            chat_id=beneficiary,
                            text=notification_text
                        )
                    except Exception as e:
                        logging.error(f"Ошибка отправки уведомления рефереру {beneficiary}: {e}")
            
            await conn.commit()
    except Exception as e:
        logging.error(f"Ошибка accrue_referral_commissions: {e}", exc_info=True)

async def debug_referral_chain(user_id: int) -> dict:
    """Отладочная функция для проверки реферальной цепочки"""
    result = {
        'user_id': user_id,
        'referrer_id': None,
        'level1_refs': [],
        'level2_refs': [],
        'level3_refs': []
    }
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            # Получаем реферера пользователя
            cursor = await conn.execute(
                "SELECT referrer_id FROM bot_users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            if row and row[0]:
                result['referrer_id'] = row[0]
            
            # 1-я линия - прямые рефералы
            cursor = await conn.execute(
                "SELECT user_id FROM bot_users WHERE referrer_id = ?",
                (user_id,)
            )
            level1 = await cursor.fetchall()
            result['level1_refs'] = [row[0] for row in level1]
            
            # 2-я линия - рефералы рефералов
            if result['level1_refs']:
                cursor = await conn.execute(
                    "SELECT user_id FROM bot_users WHERE referrer_id IN ({})".format(
                        ','.join('?' * len(result['level1_refs']))
                    ),
                    result['level1_refs']
                )
                level2 = await cursor.fetchall()
                result['level2_refs'] = [row[0] for row in level2]
            
            # 3-я линия - рефералы рефералов рефералов
            if result['level2_refs']:
                cursor = await conn.execute(
                    "SELECT user_id FROM bot_users WHERE referrer_id IN ({})".format(
                        ','.join('?' * len(result['level2_refs']))
                    ),
                    result['level2_refs']
                )
                level3 = await cursor.fetchall()
                result['level3_refs'] = [row[0] for row in level3]
                
    except Exception as e:
        logging.error(f"Ошибка debug_referral_chain: {e}")
    
    return result

async def get_referral_overview(user_id: int) -> dict:
    """Возвращает сводку для партнёрской программы: баланс, сегодня, counts по 1/2/3 линиям."""
    result = {
        'balance': 0.0,
        'today_first_line': 0,
        'level1': 0,
        'level2': 0,
        'level3': 0,
    }
    try:
        # Получаем отладочную информацию
        debug_info = await debug_referral_chain(user_id)
        
        # Баланс
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute(
                "SELECT COALESCE(referral_balance, 0) FROM bot_users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            result['balance'] = round(float(row[0]) if row else 0.0, 2)
        
        # Подсчитываем рефералов по линиям
        result['level1'] = len(debug_info['level1_refs'])
        result['level2'] = len(debug_info['level2_refs'])
        result['level3'] = len(debug_info['level3_refs'])
        
        # Отладочная информация
        logging.info(f"Отладка рефералов для {user_id}:")
        logging.info(f"  Реферер: {debug_info['referrer_id']}")
        logging.info(f"  1-я линия: {debug_info['level1_refs']} (всего: {result['level1']})")
        logging.info(f"  2-я линия: {debug_info['level2_refs']} (всего: {result['level2']})")
        logging.info(f"  3-я линия: {debug_info['level3_refs']} (всего: {result['level3']})")
        
        # Рефералы за сегодня
        today = datetime.now().strftime('%d.%m.%Y')
        today_count = 0
        
        async with aiosqlite.connect(DB_PATH) as conn:
            # 1-я линия за сегодня
            if debug_info['level1_refs']:
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM bot_users WHERE user_id IN ({}) AND first_interaction LIKE ?".format(
                        ','.join('?' * len(debug_info['level1_refs']))
                    ),
                    debug_info['level1_refs'] + [f"{today}%"]
                )
                today_count += (await cursor.fetchone())[0]
            
            # 2-я линия за сегодня
            if debug_info['level2_refs']:
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM bot_users WHERE user_id IN ({}) AND first_interaction LIKE ?".format(
                        ','.join('?' * len(debug_info['level2_refs']))
                    ),
                    debug_info['level2_refs'] + [f"{today}%"]
                )
                today_count += (await cursor.fetchone())[0]
            
            # 3-я линия за сегодня
            if debug_info['level3_refs']:
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM bot_users WHERE user_id IN ({}) AND first_interaction LIKE ?".format(
                        ','.join('?' * len(debug_info['level3_refs']))
                    ),
                    debug_info['level3_refs'] + [f"{today}%"]
                )
                today_count += (await cursor.fetchone())[0]
        
        result['today_first_line'] = today_count
        
        return result
    except Exception as e:
        logging.error(f"Ошибка get_referral_overview: {e}")
        return result

async def check_referral_data(user_id: int) -> dict:
    """Проверяет данные рефералов в базе для отладки"""
    result = {
        'user_exists': False,
        'has_referrer': False,
        'referrer_id': None,
        'direct_referrals': [],
        'referrals_table': []
    }
    
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            # Проверяем, есть ли пользователь в bot_users
            cursor = await conn.execute(
                "SELECT user_id, referrer_id, first_interaction FROM bot_users WHERE user_id = ?",
                (user_id,)
            )
            user_data = await cursor.fetchone()
            if user_data:
                result['user_exists'] = True
                result['referrer_id'] = user_data[1]
                result['has_referrer'] = bool(user_data[1])
                result['first_interaction'] = user_data[2]
            
            # Проверяем прямых рефералов
            cursor = await conn.execute(
                "SELECT user_id FROM bot_users WHERE referrer_id = ?",
                (user_id,)
            )
            direct_refs = await cursor.fetchall()
            result['direct_referrals'] = [row[0] for row in direct_refs]
            
            # Проверяем таблицу referrals
            cursor = await conn.execute(
                "SELECT referrer_id, referred_id, referral_date FROM referrals WHERE referrer_id = ?",
                (user_id,)
            )
            referrals_data = await cursor.fetchall()
            result['referrals_table'] = [
                {'referrer_id': row[0], 'referred_id': row[1], 'date': row[2]} 
                for row in referrals_data
            ]
            
    except Exception as e:
        logging.error(f"Ошибка check_referral_data: {e}")
    
    return result
