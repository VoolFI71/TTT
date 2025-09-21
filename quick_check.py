#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Быстрая проверка системы
"""

import asyncio
from database import (
    init_db,
    get_referral_stats,
    get_all_referral_stats,
    get_all_users_expiring_in_days,
)

async def quick_check():
    """Быстрая проверка всех систем"""
    print("🔍 Быстрая проверка системы Shard VPN")
    print("=" * 40)
    
    await init_db()
    
    # Проверяем реферальную систему
    print("\n🔗 Реферальная система:")
    all_stats = await get_all_referral_stats()
    print(f"   - Всего рефералов: {all_stats['total_referrals']}")
    print(f"   - С подпиской: {all_stats['subscribed_referrals']}")
    print(f"   - Без подписки: {all_stats['unsubscribed_referrals']}")
    
    # Проверяем уведомления
    print("\n⏰ Уведомления:")
    for days in [3, 1, 0]:
        users = await get_all_users_expiring_in_days(days, 5)
        print(f"   - За {days} дней: {len(users)} пользователей")
        for user_id, expiry, payment_method in users[:2]:
            print(f"     * {user_id}: {expiry} ({payment_method})")
    
    # Проверяем триальные подписки
    print("\n🎁 Триальные подписки:")
    trial_users = await get_trial_users(5)
    print(f"   - Всего триальных: {len(trial_users)}")
    for user_id, expiry, payment_date, username, first_name in trial_users[:3]:
        print(f"     * {user_id} ({first_name}): {expiry}")

if __name__ == "__main__":
    asyncio.run(quick_check())
