import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from dotenv import load_dotenv
import os
load_dotenv()
# Токен бота
TOKEN = os.getenv('BOT_TOKEN')

# ID супергруппы с админами (где будут создаваться темы)
ADMIN_GROUP_ID = int(os.getenv('ADMIN_GROUP_ID'))

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Словарь: user_id -> message_thread_id
user_threads = {}


# Приветственное сообщение при /start
@dp.message(F.text == "/start")
async def start_message(message: Message):
    welcome_text = (
        "👋 Добро пожаловать в *Shard VPN Support Bot*!\n\n"
        "📩 Оставьте здесь свою заявку или вопрос.\n"
        "✅ Наши специалисты свяжутся с вами в ближайшее время."
    )
    await message.answer(welcome_text, parse_mode="Markdown")


# Обработка сообщений от пользователей
@dp.message(F.chat.type == "private")
async def user_message(message: Message):
    user_id = message.from_user.id

    # Проверяем, есть ли уже тема для пользователя
    if user_id not in user_threads:
        topic = await bot.create_forum_topic(
            chat_id=ADMIN_GROUP_ID,
            name=f"Заявка от {message.from_user.full_name} ({user_id})"
        )
        user_threads[user_id] = topic.message_thread_id

    thread_id = user_threads[user_id]

    # Пересылаем разные типы сообщений
    if message.text:
        await bot.send_message(ADMIN_GROUP_ID, message.text, message_thread_id=thread_id)
    elif message.photo:
        await bot.send_photo(ADMIN_GROUP_ID, message.photo[-1].file_id, caption=message.caption or "", message_thread_id=thread_id)
    elif message.document:
        await bot.send_document(ADMIN_GROUP_ID, message.document.file_id, caption=message.caption or "", message_thread_id=thread_id)
    elif message.video:
        await bot.send_video(ADMIN_GROUP_ID, message.video.file_id, caption=message.caption or "", message_thread_id=thread_id)
    elif message.voice:
        await bot.send_voice(ADMIN_GROUP_ID, message.voice.file_id, caption=message.caption or "", message_thread_id=thread_id)
    elif message.sticker:
        await bot.send_sticker(ADMIN_GROUP_ID, message.sticker.file_id, message_thread_id=thread_id)


# Ответы админов
@dp.message(F.chat.id == ADMIN_GROUP_ID)
async def admin_message(message: Message):
    if message.message_thread_id:
        for user_id, thread_id in user_threads.items():
            if thread_id == message.message_thread_id:
                if message.text:
                    await bot.send_message(user_id, message.text)
                elif message.photo:
                    await bot.send_photo(user_id, message.photo[-1].file_id, caption=message.caption or "")
                elif message.document:
                    await bot.send_document(user_id, message.document.file_id, caption=message.caption or "")
                elif message.video:
                    await bot.send_video(user_id, message.video.file_id, caption=message.caption or "")
                elif message.voice:
                    await bot.send_voice(user_id, message.voice.file_id, caption=message.caption or "")
                elif message.sticker:
                    await bot.send_sticker(user_id, message.sticker.file_id)
                break


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
