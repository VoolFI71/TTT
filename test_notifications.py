#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для тестирования уведомлений о подписке
"""

import asyncio
import aiosqlite
from datetime import datetime, timedelta
from database import (
    init_db,
    get_all_users_expiring_in_days,
    mark_user_notified,
    get_user_data,
    check_user_payment
)
from config import DB_PATH, TOKEN
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

class NotificationTester:
    def __init__(self):
        self.bot = Bot(token=TOKEN)
    
    async def reset_notification_flags(self, user_id: int):
        """Сбрасывает флаги уведомлений для тестирования"""
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE users SET notified_3d = 0, notified_1d = 0, notified_expired = 0 WHERE user_id = ?",
                (user_id,)
            )
            await conn.commit()
            print(f"✅ Флаги уведомлений сброшены для пользователя {user_id}")
    
    async def create_test_subscription(self, user_id: int, days: int):
        """Создает тестовую подписку с указанным сроком"""
        from database import give_user_subscription
        
        # Сбрасываем флаги уведомлений
        await self.reset_notification_flags(user_id)
        
        # Создаем подписку
        success = await give_user_subscription(user_id, days)
        if success:
            print(f"✅ Тестовая подписка на {days} дней создана для {user_id}")
            return True
        else:
            print(f"❌ Ошибка создания подписки для {user_id}")
            return False
    
    async def send_test_notification(self, user_id: int, notification_type: str):
        """Отправляет тестовое уведомление"""
        try:
            # Получаем данные пользователя
            user_data = await get_user_data(user_id)
            if not user_data:
                print(f"❌ Пользователь {user_id} не найден")
                return False
            
            expiry_date, config = user_data
            
            # Создаем клавиатуру
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data='renew_sub')]
            ])
            
            # Определяем текст уведомления
            if notification_type == "3d":
                text = (
                '''
⏳ <b>Ваша подписка истекает через 3 дня</b>

<blockquote><i>Не теряйте доступ к быстрому и безопасному VPN — продлите подписку заранее.</i></blockquote>

Дата окончания: <code>{expiry_date}</code>'''
                )
            elif notification_type == "1d":
                text = (
                    f"⚠️ <b>Ваша подписка истекает завтра!</b>\n\n"
                    "<blockquote><i>Последний день доступа. Продлите подписку, чтобы не потерять защиту.</i></blockquote>\n\n"
                    f"Дата окончания: <code>{expiry_date}</code>"
                )
            elif notification_type == "expired":
                text = (
                    f"❌ <b>Ваша подписка истёкла</b>\n\n"
                    "<blockquote><i>Доступ завершён. Продлите подписку, чтобы продолжить пользоваться VPN.</i></blockquote>\n\n"
                    f"Дата окончания: <code>{expiry_date}</code>"
                )
            else:
                print(f"❌ Неизвестный тип уведомления: {notification_type}")
                return False
            
            # Отправляем уведомление
            await self.bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=keyboard
            )
            
            # Отмечаем как отправленное
            await mark_user_notified(user_id, notification_type)
            
            print(f"✅ Уведомление {notification_type} отправлено пользователю {user_id}")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка отправки уведомления: {e}")
            return False
    
    async def test_notification_system(self, user_id: int):
        """Тестирует всю систему уведомлений для пользователя"""
        print(f"\n🧪 Тестирование уведомлений для пользователя {user_id}")
        
        # Создаем подписку на 5 дней
        if not await self.create_test_subscription(user_id, 5):
            return
        
        # Ждем немного
        await asyncio.sleep(1)
        
        # Проверяем, кто должен получить уведомления
        print("\n📊 Проверка пользователей для уведомлений:")
        
        for days in [3, 1, 0]:
            users = await get_all_users_expiring_in_days(days, 10)
            print(f"   - За {days} дней: {len(users)} пользователей")
            
            for uid, expiry, payment_method in users:
                if uid == user_id:
                    print(f"     ✅ Пользователь {uid} найден в списке ({expiry}, {payment_method})")
        
        # Отправляем тестовые уведомления
        print("\n📤 Отправка тестовых уведомлений:")
        
        for notification_type in ["3d", "1d", "expired"]:
            await self.send_test_notification(user_id, notification_type)
            await asyncio.sleep(1)
    
    async def check_notification_flags(self, user_id: int):
        """Проверяет флаги уведомлений пользователя"""
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute(
                "SELECT notified_3d, notified_1d, notified_expired, notified_expiring_2d FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            
            if row:
                notified_3d, notified_1d, notified_expired, notified_expiring_2d = row
                print(f"📋 Флаги уведомлений для {user_id}:")
                print(f"   - 3 дня: {notified_3d}")
                print(f"   - 1 день: {notified_1d}")
                print(f"   - Истекла: {notified_expired}")
                print(f"   - 2 дня (старая): {notified_expiring_2d}")
            else:
                print(f"❌ Пользователь {user_id} не найден")
    
    async def simulate_expiring_subscriptions(self):
        """Симулирует истекающие подписки для тестирования"""
        print("\n🎭 Симуляция истекающих подписок...")
        
        # Получаем всех пользователей с подписками
        async with aiosqlite.connect(DB_PATH) as conn:
            cursor = await conn.execute(
                "SELECT user_id, expiry_date FROM users WHERE subscribed = 1 AND expiry_date IS NOT NULL"
            )
            users = await cursor.fetchall()
        
        if not users:
            print("❌ Нет пользователей с подписками")
            return
        
        print(f"📊 Найдено {len(users)} пользователей с подписками")
        
        # Показываем ближайшие истечения
        now = datetime.now()
        for user_id, expiry_date in users[:5]:  # Показываем первых 5
            try:
                for fmt in ['%d.%m.%Y %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                    try:
                        exp = datetime.strptime(expiry_date, fmt)
                        days_left = (exp.date() - now.date()).days
                        print(f"   - {user_id}: {expiry_date} (осталось {days_left} дней)")
                        break
                    except ValueError:
                        continue
            except:
                print(f"   - {user_id}: {expiry_date} (ошибка парсинга даты)")
    
    async def close(self):
        """Закрывает соединение с ботом"""
        await self.bot.session.close()

async def main():
    """Главная функция"""
    tester = NotificationTester()
    
    print("⏰ Тестирование системы уведомлений Shard VPN")
    print("=" * 50)
    
    try:
        await init_db()
        
        while True:
            print("\nВыберите действие:")
            print("1. Тестировать уведомления для пользователя")
            print("2. Проверить флаги уведомлений")
            print("3. Симулировать истекающие подписки")
            print("4. Сбросить флаги уведомлений")
            print("5. Создать тестовую подписку")
            print("0. Выход")
            
            choice = input("\nВведите номер: ").strip()
            
            if choice == "1":
                user_id = int(input("Введите ID пользователя: "))
                await tester.test_notification_system(user_id)
            elif choice == "2":
                user_id = int(input("Введите ID пользователя: "))
                await tester.check_notification_flags(user_id)
            elif choice == "3":
                await tester.simulate_expiring_subscriptions()
            elif choice == "4":
                user_id = int(input("Введите ID пользователя: "))
                await tester.reset_notification_flags(user_id)
            elif choice == "5":
                user_id = int(input("Введите ID пользователя: "))
                days = int(input("Введите количество дней: "))
                await tester.create_test_subscription(user_id, days)
            elif choice == "0":
                print("👋 До свидания!")
                break
            else:
                print("❌ Неверный выбор")
    
    except KeyboardInterrupt:
        print("\n👋 Тестирование прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
    finally:
        await tester.close()

if __name__ == "__main__":
    asyncio.run(main())
