import asyncio
import re
from io import BytesIO
from telethon import TelegramClient, types
from telethon.extensions import markdown

# ================== НАСТРОЙКИ ==================
api_id = 34277624
api_hash = "3906edabc2198a97d68878633496809d"

SOURCE_CHANNEL = "garageneva"
TARGET_CHANNEL = "garagesale_dighomi"
UPDATE_INTERVAL = 20  # секунд

CAR_BRANDS = ["BMW", "Mercedes", "Toyota", "Audi", "Porsche"]
CURRENCIES = ["$", "€", "₽", "USD", "EUR"]
PRICE_PATTERN = re.compile(r"(\d[\d\s]{3,})\s*(" + "|".join(CURRENCIES) + ")", re.IGNORECASE)

client = TelegramClient("relay_client", api_id, api_hash)
posted_ids = set()

# ================== ФИЛЬТРЫ ==================
def match_filters(text: str) -> bool:
    if not text:
        return False
    if not any(brand.lower() in text.lower() for brand in CAR_BRANDS):
        return False
    if not PRICE_PATTERN.search(text):
        return False
    return True

def format_message(text: str, brand: str) -> str:
    return f"🚗 **{brand}**\n{text}\n\n📍 Источник: @{SOURCE_CHANNEL}"

# ================== ПАРСИНГ И ПУБЛИКАЦИЯ ==================
async def fetch_and_post():
    print("Старт скрипта...")
    await client.start()
    print("Клиент Telethon подключен.")

    source = await client.get_entity(SOURCE_CHANNEL)
    target = await client.get_entity(TARGET_CHANNEL)
    print(f"Подключение к каналам: источник={SOURCE_CHANNEL}, целевой={TARGET_CHANNEL}")

    while True:
        async for msg in client.iter_messages(source, limit=20):
            # Пропускаем уже опубликованные
            if msg.id in posted_ids:
                continue

            # Если это часть альбома - пропускаем если уже публиковали
            if msg.grouped_id and msg.grouped_id in posted_ids:
                continue

            # Берём текст из сообщения или подписи к медиа
            text = msg.message or (msg.media.caption if hasattr(msg.media, "caption") else "")
            if not text and not msg.media:
                print(f"ID={msg.id} - пустое, пропускаем")
                continue

            brand = next((b for b in CAR_BRANDS if b.lower() in text.lower()), "—")
            if text and not match_filters(text):
                print(f"ID={msg.id} - не прошло фильтры")
                continue

            print(f"ID={msg.id} - публикуем")

            # ===== Собираем медиа для альбома в памяти =====
            media_list = []
            grouped_ids = set()
            all_text = text  # Текст из первого сообщения

            if msg.grouped_id:
                # Альбом - собираем все сообщения с одинаковым grouped_id
                album_messages = []
                async for m in client.iter_messages(source, limit=100):
                    if getattr(m, "grouped_id", None) == msg.grouped_id:
                        album_messages.append(m)
                
                # Сортируем по ID (в правильном порядке)
                album_messages.sort(key=lambda x: x.id)
                
                for m in album_messages:
                    # Собираем текст из всех сообщений
                    msg_text = m.message or (m.media.caption if hasattr(m.media, "caption") else "")
                    if msg_text and msg_text != text:
                        all_text = msg_text  # Берём полный текст из альбома
                    
                    if m.media:
                        b = BytesIO()
                        await client.download_media(m, file=b)
                        b.seek(0)
                        b.name = 'photo.jpg'
                        media_list.append(b)
                    grouped_ids.add(m.id)
            else:
                # Одиночное сообщение с медиа
                if msg.media:
                    b = BytesIO()
                    await client.download_media(msg, file=b)
                    b.seek(0)
                    b.name = 'photo.jpg'
                    media_list.append(b)

            try:
                formatted_text = format_message(all_text, brand)
                if media_list:
                    # Отправка фото/альбома
                    await client.send_file(
                        target,
                        file=media_list,
                        caption=formatted_text,
                        force_document=False
                    )
                    print(f" - Опубликован альбом/фото ID={msg.id}")
                    # Помечаем все ID альбома как опубликованные
                    if msg.grouped_id:
                        posted_ids.add(msg.grouped_id)
                        for gid in grouped_ids:
                            posted_ids.add(gid)
                    else:
                        posted_ids.add(msg.id)
                else:
                    # Использует markdown форматирование встроенное в Telethon
                    message_obj, entities = markdown.parse(formatted_text)
                    await client.send_message(target, message_obj, formatting_entities=entities)
                    print(f" - Опубликован текст ID={msg.id}")
                    posted_ids.add(msg.id)

            except Exception as e:
                print(f"Ошибка при отправке: {e}")

        print(f"Ожидание {UPDATE_INTERVAL} секунд...")
        await asyncio.sleep(UPDATE_INTERVAL)

# ================== ТОЧКА ВХОДА ==================
if __name__ == "__main__":
    asyncio.run(fetch_and_post())
