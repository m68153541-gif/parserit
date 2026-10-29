import asyncio
import logging
import os
import random
from datetime import datetime
from threading import Thread
from http.server import SimpleHTTPRequestHandler, HTTPServer

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.payments import GetSavedStarGiftsRequest
from telethon.tl.types import InputPeerSelf

# ==========================================
# НАСТРОЙКИ (ОБНОВЛЕНЫ НА ВТОРОЙ АККАУНТ)
# ==========================================
BOT_TOKEN = "9217167507:AAEzoKBaNkroGJ5ISNOWIBGhwWPR5uTgP-4" # Вставь сюда токен от @BotFather
API_ID = 32969479
API_HASH = "817c78ce17662923f8167067b4551602"
ADMIN_ID = 8513244807

# Сессия будет браться из переменной окружения на Render
# Пока для локального теста можно оставить пустой строкой, но мы сделаем через generate_session.py
SESSION_STRING = os.environ.get("TG_SESSION_STRING", "")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Клиент Telethon с использованием StringSession (для Render)
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# Хранилище сессий пользователей (для диалога)
user_states = {}

# ==========================================
# ВЕБ-СЕРВЕР ДЛЯ RENDER
# ==========================================
def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    logging.info(f"Web server started on port {port}")
    server.serve_forever()

# ==========================================
# ЛОГИКА ПАРСИНГА (ЧЕРЕЗ TELETHON)
# ==========================================
async def get_gifts_from_user(peer_id):
    """Получает список подарков у пользователя по его ID"""
    try:
        user = await client.get_entity(peer_id)
        result = await client(GetSavedStarGiftsRequest(
            peer=user,
            offset=0,
            limit=100
        ))
        return result.gifts
    except Exception as e:
        logging.error(f"Error getting gifts for {peer_id}: {e}")
        return []

async def find_gift_owners(gift_name: str, limit: int = 150):
    """
    Ищет владельцев подарка.
    Для теста возвращает случайных пользователей из ваших диалогов.
    """
    owners = []
    try:
        dialogs = await client.get_dialogs(limit=50)
        for dialog in dialogs:
            if len(owners) >= limit:
                break
            if dialog.is_user:
                gifts = await get_gifts_from_user(dialog.id)
                for gift in gifts:
                    if gift_name.lower() in gift.gift.title.lower():
                        owners.append({
                            'id': dialog.id,
                            'username': dialog.username or f"id{dialog.id}",
                            'gift_title': gift.gift.title,
                            'gift_link': f"tg://user?id={dialog.id}"
                        })
                        break
    except Exception as e:
        logging.error(f"Error in find_gift_owners: {e}")
    
    random.shuffle(owners)
    return owners[:limit]

# ==========================================
# ОБРАБОТЧИКИ БОТА
# ==========================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 На продаже", callback_data="on_sale")
    builder.button(text="🎁 Не на продаже", callback_data="not_on_sale")
    builder.adjust(2)
    await message.answer(
        "👋 Привет! Я бот для поиска NFT-подарков.\n"
        "Выберите категорию:",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "on_sale")
async def process_on_sale(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="💰 Дешевые", callback_data="cheap")
    builder.button(text="💎 Дорогие", callback_data="expensive")
    builder.button(text="⬅️ Назад", callback_data="back")
    builder.adjust(2)
    await callback.message.edit_text(
        "Выберите ценовой диапазон:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data == "not_on_sale")
async def process_not_on_sale(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="Durov's Cap", callback_data="gift_Durov Cap")
    builder.button(text="Heart", callback_data="gift_Heart")
    builder.button(text="⬅️ Назад", callback_data="back")
    builder.adjust(1)
    await callback.message.edit_text(
        "Выберите подарок:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("gift_"))
async def process_gift_selection(callback: CallbackQuery):
    gift_name = callback.data.replace("gift_", "")
    await callback.message.edit_text(f"⏳ Ищу владельцев подарка «{gift_name}»...")
    
    owners = await find_gift_owners(gift_name)
    
    if not owners:
        await callback.message.edit_text(f"❌ Владельцы подарка «{gift_name}» не найдены.")
        return
    
    text = f"🔍 Найдено {len(owners)} владельцев подарка «{gift_name}»:\n\n"
    for i, owner in enumerate(owners[:150], 1):
        text += f"{i}. @{owner['username']} — {owner['gift_title']} — [ссылка]({owner['gift_link']})\n"
        if i % 10 == 0:
            text += "\n"
            await callback.message.answer(text)
            text = ""
    
    if text:
        await callback.message.answer(text)
    await callback.answer()

@dp.callback_query(F.data == "back")
async def process_back(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="🛒 На продаже", callback_data="on_sale")
    builder.button(text="🎁 Не на продаже", callback_data="not_on_sale")
    builder.adjust(2)
    await callback.message.edit_text(
        "Выберите категорию:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

# ==========================================
# ЗАПУСК
# ==========================================
async def main():
    t = Thread(target=run_dummy_server)
    t.daemon = True
    t.start()
    
    await client.start()
    logging.info("Telethon client started")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
