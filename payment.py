import uuid
import asyncio
import aiosqlite
import logging
from yookassa import Configuration, Payment
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, YOOKASSA_RETURN_URL, DB_PATH
from database import add_payment
from datetime import datetime
# Настройка ЮKассы
Configuration.configure(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)

# Глобальный набор для отслеживания активных проверок
active_checks = set()

# Глобальный список для отслеживания активных задач проверки платежей
active_payment_tasks = set()

async def cancel_all_payment_tasks():
    """Отменяет все активные задачи проверки платежей"""
    if active_payment_tasks:
        logging.info(f"Отменяем {len(active_payment_tasks)} активных задач проверки платежей")
        for task in active_payment_tasks.copy():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        active_payment_tasks.clear()

async def create_payment(period: str, user_id: int):
    """Создает платеж в ЮKассе"""
    periods = {
        'special': {'value': '1.00', 'description': '7 дней'},
        '1': {'value': '99.00', 'description': '1 месяц'},
        '3': {'value': '279.00', 'description': '3 месяца'},
        '6': {'value': '549.00', 'description': '6 месяцев'},
        '12': {'value': '999.00', 'description': '12 месяцев'}
    }
    
    if period not in periods:
        logging.error(f"Неверный период подписки: {period}")
        return None
    
    try:
        payment = Payment.create({
            "amount": {
                "value": periods[period]['value'],
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": YOOKASSA_RETURN_URL
            },
            "capture": True,
            "description": f"Shard VPN: {periods[period]['description']}",
            "metadata": {
                "user_id": str(user_id),
                "period": period
            }
        }, str(uuid.uuid4()))
        
        return {
            'confirmation_url': payment.confirmation.confirmation_url,
            'payment_id': payment.id,
            'period': period
        }
    except Exception as e:
        logging.error(f"Ошибка создания платежа: {str(e)}", exc_info=True)
        return None

async def check_payment_status(payment_data: dict, bot):
    """Автоматически проверяет статус платежа"""
    payment_id = payment_data['payment_id']
    
    # Добавляем текущую задачу в список активных
    current_task = asyncio.current_task()
    if current_task:
        active_payment_tasks.add(current_task)
    
    try:
        for _ in range(60):  # 10 минут (60 попыток * 10 секунд)
            try:
                payment = Payment.find_one(payment_id)
                
                if payment.status == "succeeded":
                    # Проверяем, была ли подписка активной ДО продления
                    was_active = False
                    try:
                        async with aiosqlite.connect(DB_PATH) as conn:
                            cursor = await conn.execute(
                                "SELECT expiry_date FROM users WHERE user_id=?",
                                (payment_data['user_id'],)
                            )
                            row_before = await cursor.fetchone()
                            if row_before and row_before[0]:
                                expiry_str = row_before[0]
                                for fmt in ('%d.%m.%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
                                    try:
                                        dt = datetime.strptime(expiry_str, fmt)
                                        was_active = datetime.now() < dt
                                        if was_active or True:
                                            break
                                    except ValueError:
                                        continue
                    except Exception:
                        was_active = False
                    # Добавляем оплату в БД
                    # Обрабатываем специальную подписку
                    if payment_data['period'] == 'special':
                        period_months = 0  # Специальная подписка
                    else:
                        period_months = int(payment_data['period'])

                    # ЮKassa платеж
                    success = await add_payment(
                        payment_data['user_id'],
                        period_months,
                        payment_method='yookassa'
                    )
                    
                    if not success:
                        logging.error("Не удалось обновить подписку в БД")
                        return False
                    
                    
                    # Удаляем сообщение с платежом
                    try:
                        await bot.delete_message(
                            chat_id=payment_data['chat_id'],
                            message_id=payment_data['message_id']
                        )
                    except Exception as e:
                        logging.warning(f"Не удалось удалить сообщение: {e}")

                    # Получаем дату окончания и форматируем её
                    async with aiosqlite.connect(DB_PATH) as conn:
                        cursor = await conn.execute(
                            "SELECT expiry_date FROM users WHERE user_id=?",
                            (payment_data['user_id'],)
                        )
                        row = await cursor.fetchone()
                        if row and row[0]:
                            try:
                                from datetime import datetime as dt
                                expiry_date = dt.strptime(row[0], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
                            except ValueError:
                                expiry_date = row[0]
                        else:
                            expiry_date = "не определена"

                    # Отправляем сообщение об успешной оплате
                    action_word = "продлена" if was_active else "активирована"
                    
                    # Определяем текст срока подписки
                    if payment_data['period'] == 'special':
                        period_text = "7 дней"
                    else:
                        period_text = f"{payment_data['period']} мес."
                    
                    await bot.send_message(
                        chat_id=payment_data['chat_id'],
                        text=f"""
<b>✅ Оплата успешно выполнена</b>

✨Ваша подписка на <b>Shard VPN</b> {action_word}!

📅Срок подписки: <b>{period_text}</b>
⏳Дата окончания: <b>{expiry_date}</b>

<blockquote><i>🔹 Нажмите «Активировать VPN», чтобы начать пользоваться.</i></blockquote>
""",
                        message_effect_id="5046509860389126442"
                    )
                    return True
                    
                elif payment.status in ("canceled", "failed"):
                    return False
                    
            except Exception as e:
                logging.error(f"Ошибка проверки платежа: {str(e)}", exc_info=True)
            
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                logging.info(f"Проверка платежа {payment_id} отменена")
                return False
        
        logging.warning(f"Платеж {payment_id} не завершился в течение 10 минут")
        return False
        
    except asyncio.CancelledError:
        logging.info(f"Проверка платежа {payment_id} отменена")
        return False
    except Exception as e:
        logging.error(f"Критическая ошибка в check_payment_status: {str(e)}", exc_info=True)
        return False
    finally:
        # Удаляем задачу из списка активных
        if current_task:
            active_payment_tasks.discard(current_task)