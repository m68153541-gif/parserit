import asyncio
import logging
import os
import random
from threading import Thread
from http.server import SimpleHTTPRequestHandler, HTTPServer

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.payments import GetSavedStarGiftsRequest
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch

# ==========================================
# НАСТРОЙКИ
# ==========================================
BOT_TOKEN = "9217167507:AAEzoKBaNkroGJ5ISNOWIBGhwWPR5uTgP-4"
API_ID = 32969479
API_HASH = "817c78ce17662923f8167067b4551602"
ADMIN_ID = 8513244807

SESSION_STRING = os.environ.get("TG_SESSION_STRING", "")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

# Хранилище для пагинации
user_pagination = {}

# СПИСОК ПУБЛИЧНЫХ ЧАТОВ ДЛЯ СКАНИРОВАНИЯ (ДОБАВЛЯЙТЕ СВОИ)
# Это могут быть чаты NFT-трейдеров, коллекционеров и т.д.
PUBLIC_CHATS = [
    "nft_traders_chat",  # Пример (замените на реальные)
    "gifts_market_chat",
    "telegram_gifts_chat",
]

# Список популярных подарков
POPULAR_GIFTS = [
    "Durov's Cap", "Heart", "Bear", "Bunny", "Cake", "Cup", "Diamond",
    "Flower", "Gift Box", "Horse", "Ice Cream", "Moon", "Panda", "Rose",
    "Star", "Teddy Bear", "Unicorn", "Wine", "Crown", "Ring", "Rocket",
    "Balloon", "Chocolate", "Clover", "Crystal", "Dice", "Duck", "Elephant",
    "Fire", "Fish", "Ghost", "Guitar", "Hammer", "Joker", "King", "Lion",
    "Mask", "Medal", "Microphone", "Monkey", "Owl", "Penguin", "Pizza",
    "Rainbow", "Sword", "Tiger", "Trophy", "Watermelon", "Whale", "Wizard"
]

# ==========================================
# ВЕБ-СЕРВЕР ДЛЯ RENDER
# ==========================================
def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    logging.info(f"Web server started on port {port}")
    server.serve_forever()

# ==========================================
# ЛОГИКА ПАРСИНГА
# ==========================================
async def get_gifts_from_user(peer_id):
    try:
        input_peer = await client.get_input_entity(peer_id)
        result = await client(GetSavedStarGiftsRequest(
            peer=input_peer,
            offset=0,
            limit=100
        ))
        return result.gifts
    except Exception as e:
        return []

async def find_gift_owners(gift_name: str, limit: int = 150):
    owners = []
    logging.info(f"Searching for {gift_name} in public chats...")
    
    # Собираем участников из публичных чатов
    all_participants = []
    for chat_username in PUBLIC_CHATS:
        try:
            chat = await client.get_entity(chat_username)
            participants = await client(GetParticipantsRequest(
                channel=chat,
                filter=ChannelParticipantsSearch(''),
                offset=0,
                limit=100,  # Берем первых 100 участников
                hash=0
            ))
            if participants and participants.users:
                all_participants.extend(participants.users)
                logging.info(f"Found {len(participants.users)} participants in {chat_username}")
        except Exception as e:
            logging.error(f"Error getting participants from {chat_username}: {e}")
    
    # Убираем дубликаты
    unique_participants = {u.id: u for u in all_participants}.values()
    logging.info(f"Total unique participants: {len(unique_participants)}")
    
    # Проверяем подарки у каждого
    for user in unique_participants:
        if len(owners) >= limit:
            break
        try:
            gifts = await get_gifts_from_user(user.id)
            for gift in gifts:
                if gift_name.lower() in gift.gift.title.lower():
                    owners.append({
                        'id': user.id,
                        'username': user.username or f"id{user.id}",
                        'gift_title': gift.gift.title,
                        'gift_link': f"tg://user?id={user.id}"
                    })
                    break
        except Exception as e:
            continue
    
    logging.info(f"Found {len(owners)} owners for {gift_name}")
    random.shuffle(owners)
    return owners[:limit]

# ==========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ ПАГИНАЦИИ
# ==========================================
def get_owners_page_keyboard(user_id: int, page: int, total_pages: int):
    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.button(text="⬅️ Назад", callback_data=f"page_{user_id}_{page-1}")
    if page < total_pages - 1:
        builder.button(text="Вперед ➡️", callback_data=f"page_{user_id}_{page+1}")
    builder.button(text="🏠 В меню", callback_data="back")
    builder.adjust(2, 1)
    return builder.as_markup()

def format_owners_page(owners: list, page: int, per_page: int = 10):
    start = page * per_page
    end = start + per_page
    page_owners = owners[start:end]
    
    text = f"🔍 Владельцы подарка «{owners[0]['gift_title']}» (стр. {page+1}):\n\n"
    for i, owner in enumerate(page_owners, start=start+1):
        text += f"{i}. @{owner['username']} — [ссылка]({owner['gift_link']})\n"
    return text

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
    for gift in POPULAR_GIFTS[:10]:
        builder.button(text=gift, callback_data=f"gift_{gift}")
    builder.button(text="Ещё ➡️", callback_data="gifts_page_1")
    builder.button(text="⬅️ Назад", callback_data="back")
    builder.adjust(2, 2, 2, 2, 2, 1, 1)
    await callback.message.edit_text(
        "Выберите подарок (стр. 1):",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("gifts_page_"))
async def process_gifts_page(callback: CallbackQuery):
    page = int(callback.data.split("_")[2])
    start = page * 10
    end = start + 10
    page_gifts = POPULAR_GIFTS[start:end]
    
    builder = InlineKeyboardBuilder()
    for gift in page_gifts:
        builder.button(text=gift, callback_data=f"gift_{gift}")
    
    if page > 0:
        builder.button(text="⬅️ Назад", callback_data=f"gifts_page_{page-1}")
    if end < len(POPULAR_GIFTS):
        builder.button(text="Ещё ➡️", callback_data=f"gifts_page_{page+1}")
    builder.button(text="🏠 В меню", callback_data="back")
    
    builder.adjust(2, 2, 2, 2, 2, 1, 1, 1)
    await callback.message.edit_text(
        f"Выберите подарок (стр. {page+1}):",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("gift_"))
async def process_gift_selection(callback: CallbackQuery):
    gift_name = callback.data.replace("gift_", "")
    await callback.message.edit_text(f"⏳ Ищу владельцев подарка «{gift_name}» в публичных чатах...\nЭто может занять до 30 секунд.")
    
    owners = await find_gift_owners(gift_name)
    
    if not owners:
        await callback.message.edit_text(
            f"❌ Владельцы подарка «{gift_name}» не найдены.\n"
            f"Возможно, в указанных чатах нет людей с этим подарком.\n"
            f"Добавьте больше чатов в список PUBLIC_CHATS в коде."
        )
        return
    
    user_pagination[callback.from_user.id] = {
        'gift': gift_name,
        'owners': owners,
        'page': 0
    }
    
    total_pages = (len(owners) + 9) // 10
    text = format_owners_page(owners, 0)
    keyboard = get_owners_page_keyboard(callback.from_user.id, 0, total_pages)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.startswith("page_"))
async def process_page(callback: CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[1])
    page = int(parts[2])
    
    if user_id != callback.from_user.id or user_id not in user_pagination:
        await callback.answer("Ошибка: данные устарели. Начните заново.")
        return
    
    data = user_pagination[user_id]
    total_pages = (len(data['owners']) + 9) // 10
    
    text = format_owners_page(data['owners'], page)
    keyboard = get_owners_page_keyboard(user_id, page, total_pages)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
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
