#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для тестирования реферальной системы и уведомлений
"""

import asyncio
import aiosqlite
from datetime import datetime, timedelta
from database import (
    init_db,
    get_referral_stats,
    get_all_referral_stats,
    get_all_users_expiring_in_days,
    mark_user_notified,
    add_bot_user,
    give_user_subscription,
    add_referral,
    get_user_data,
    check_user_payment
)
from config import DB_PATH

class SystemTester:
    def __init__(self):
        self.test_users = []
    
    async def setup_test_users(self):
        """Создает тестовых пользователей"""
        print("🔧 Создание тестовых пользователей...")
        
        # Создаем тестовых пользователей
        test_user_ids = [999001, 999002, 999003, 999004, 999005]
        
        for user_id in test_user_ids:
            await add_bot_user(
                user_id=user_id,
                username=f"test_user_{user_id}",
                first_name=f"Test{user_id}",
                last_name="User"
            )
            self.test_users.append(user_id)
            print(f"✅ Создан тестовый пользователь: {user_id}")
    
    async def test_referral_system(self):
        """Тестирует реферальную систему"""
        print("\n🔗 Тестирование реферальной системы...")
        
        if len(self.test_users) < 3:
            print("❌ Недостаточно тестовых пользователей")
            return
        
        referrer_id = self.test_users[0]
        referred_id = self.test_users[1]
        
        # Добавляем реферала
        success = await add_referral(referrer_id, referred_id)
        if success:
            print(f"✅ Реферал добавлен: {referred_id} -> {referrer_id}")
        else:
            print(f"❌ Ошибка добавления реферала")
        
        # Проверяем статистику реферера
        stats = await get_referral_stats(referrer_id)
        print(f"📊 Статистика реферера {referrer_id}:")
        print(f"   - Всего рефералов: {stats['total_referrals']}")
        print(f"   - С подпиской: {stats['subscribed_referrals']}")
        print(f"   - Без подписки: {stats['unsubscribed_referrals']}")
        
        # Проверяем общую статистику
        all_stats = await get_all_referral_stats()
        print(f"\n📈 Общая статистика рефералов:")
        print(f"   - Всего рефералов: {all_stats['total_referrals']}")
        print(f"   - С подпиской: {all_stats['subscribed_referrals']}")
        print(f"   - Без подписки: {all_stats['unsubscribed_referrals']}")
        
        if all_stats['top_referrers']:
            print(f"   - Топ рефереры: {len(all_stats['top_referrers'])}")
    
    
    async def test_notifications(self):
        """Тестирует систему уведомлений"""
        print("\n⏰ Тестирование системы уведомлений...")
        
        # Проверяем пользователей за 3 дня
        users_3d = await get_all_users_expiring_in_days(3, 10)
        print(f"📅 Пользователи за 3 дня до истечения: {len(users_3d)}")
        for user_id, expiry, payment_method in users_3d[:3]:
            print(f"   - {user_id}: {expiry} ({payment_method})")
        
        # Проверяем пользователей за 1 день
        users_1d = await get_all_users_expiring_in_days(1, 10)
        print(f"📅 Пользователи за 1 день до истечения: {len(users_1d)}")
        for user_id, expiry, payment_method in users_1d[:3]:
            print(f"   - {user_id}: {expiry} ({payment_method})")
        
        # Проверяем истекших пользователей
        users_expired = await get_all_users_expiring_in_days(0, 10)
        print(f"📅 Истекшие пользователи: {len(users_expired)}")
        for user_id, expiry, payment_method in users_expired[:3]:
            print(f"   - {user_id}: {expiry} ({payment_method})")
    
    async def create_test_subscriptions(self):
        """Создает тестовые подписки с разными сроками"""
        print("\n🔧 Создание тестовых подписок...")
        
        if len(self.test_users) < 3:
            print("❌ Недостаточно тестовых пользователей")
            return
        
        # Создаем подписки с разными сроками для тестирования
        test_cases = [
            (self.test_users[0], 1),  # 1 день
            (self.test_users[1], 3),  # 3 дня
            (self.test_users[2], 7),  # 7 дней
        ]
        
        for user_id, days in test_cases:
            success = await give_user_subscription(user_id, days)
            if success:
                print(f"✅ Подписка на {days} дней создана для {user_id}")
            else:
                print(f"❌ Ошибка создания подписки для {user_id}")
    
    async def check_database_state(self):
        """Проверяет состояние базы данных"""
        print("\n🗄️ Проверка состояния базы данных...")
        
        async with aiosqlite.connect(DB_PATH) as conn:
            # Проверяем пользователей бота
            cursor = await conn.execute("SELECT COUNT(*) FROM bot_users")
            bot_users_count = (await cursor.fetchone())[0]
            print(f"👥 Пользователей бота: {bot_users_count}")
            
            # Проверяем VPN пользователей
            cursor = await conn.execute("SELECT COUNT(*) FROM users")
            vpn_users_count = (await cursor.fetchone())[0]
            print(f"🌐 VPN пользователей: {vpn_users_count}")
            
            # Проверяем активные подписки
            cursor = await conn.execute("SELECT COUNT(*) FROM users WHERE subscribed = 1")
            active_subs = (await cursor.fetchone())[0]
            print(f"✅ Активных подписок: {active_subs}")
            
            # Проверяем платежи
            cursor = await conn.execute("SELECT COUNT(*) FROM payments")
            payments_count = (await cursor.fetchone())[0]
            print(f"💳 Платежей: {payments_count}")
            
            # Проверяем рефералов
            cursor = await conn.execute("SELECT COUNT(*) FROM referrals")
            referrals_count = (await cursor.fetchone())[0]
            print(f"🔗 Рефералов: {referrals_count}")
    
    async def cleanup_test_data(self):
        """Очищает тестовые данные"""
        print("\n🧹 Очистка тестовых данных...")
        
        async with aiosqlite.connect(DB_PATH) as conn:
            for user_id in self.test_users:
                await conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                await conn.execute("DELETE FROM payments WHERE user_id = ?", (user_id,))
                await conn.execute("DELETE FROM bot_users WHERE user_id = ?", (user_id,))
                await conn.execute("DELETE FROM referrals WHERE referrer_id = ? OR referred_id = ?", (user_id, user_id))
            
            await conn.commit()
            print(f"✅ Тестовые данные очищены для {len(self.test_users)} пользователей")
    
    async def run_all_tests(self):
        """Запускает все тесты"""
        print("🚀 Запуск тестирования системы...")
        
        await init_db()
        await self.setup_test_users()
        await self.check_database_state()
        await self.test_referral_system()
        await self.create_test_subscriptions()
        await self.test_notifications()
        
        print("\n✅ Тестирование завершено!")
        
        # Спрашиваем, нужно ли очистить тестовые данные
        cleanup = input("\n🧹 Очистить тестовые данные? (y/n): ").lower().strip()
        if cleanup == 'y':
            await self.cleanup_test_data()

async def main():
    """Главная функция"""
    tester = SystemTester()
    
    print("🔧 Система тестирования Shard VPN")
    print("=" * 50)
    
    while True:
        print("\nВыберите действие:")
        print("1. Запустить все тесты")
        print("2. Тестировать только реферальную систему")
        print("3. Тестировать только уведомления")
        print("4. Проверить состояние базы данных")
        print("5. Очистить тестовые данные")
        print("0. Выход")
        
        choice = input("\nВведите номер: ").strip()
        
        if choice == "1":
            await tester.run_all_tests()
        elif choice == "2":
            await init_db()
            await tester.setup_test_users()
            await tester.test_referral_system()
        elif choice == "3":
            await init_db()
            await tester.test_notifications()
        elif choice == "4":
            await init_db()
            await tester.check_database_state()
        elif choice == "5":
            await init_db()
            await tester.cleanup_test_data()
        elif choice == "0":
            print("👋 До свидания!")
            break
        else:
            print("❌ Неверный выбор")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Тестирование прервано пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
