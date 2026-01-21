import asyncio
import re
from io import BytesIO
from telethon import TelegramClient, types
from telethon.extensions import markdown
from openai import OpenAI

# ================== НАСТРОЙКИ ==================
api_id = 34277624
api_hash = "3906edabc2198a97d68878633496809d"

SOURCE_CHANNEL = "garageneva"
TARGET_CHANNEL = "garagesale_dighomi"
UPDATE_INTERVAL = 20  # секунд

# OpenAI API
OPENAI_API_KEY = "your-openai-api-key-here"  # Replace with your actual API key
openai_client = OpenAI(api_key=OPENAI_API_KEY)

CAR_BRANDS = ["BMW", "Mercedes", "Toyota", "Audi", "Porsche", "Volkswagen", "Honda", "Ford", "Chevrolet", "Tesla", "Lexus", "Jaguar", "Land Rover", "Range Rover", "Volvo", "Nissan", "Mazda", "Subaru", "Hyundai", "Kia"]
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

# ================== ПАРСИНГ ПАРАМЕТРОВ АВТОМОБИЛЯ ==================
def parse_car_info(text: str) -> dict:
    """Парсит текст и извлекает параметры автомобиля"""
    info = {
        'brand': '—',
        'model': '—',
        'year': '—',
        'condition': '—',
        'drive': '—',
        'mileage': '—',
        'price': '—',
        'price_num': 0,
        'exchange_rate': '—'
    }
    if not text:
        return info
    
    # Ищем первую строку, которая содержит марку автомобиля
    first_line = text.split('\n')[0]
    car_line = first_line
    
    # Если марка не в первой строке, ищем её во всех строках
    if not any(brand.lower() in first_line.lower() for brand in CAR_BRANDS):
        for line in text.split('\n'):
            if any(brand.lower() in line.lower() for brand in CAR_BRANDS):
                car_line = line
                break
    
    # Ищем год в начале строки
    year_match = re.search(r'^(\d{4})\s+', car_line)
    if year_match:
        info['year'] = year_match.group(1)
        # Убираем год из строки для дальнейшего парсинга
        remaining_text = car_line[year_match.end():]
    else:
        # Если год не в начале, ищем его везде в тексте
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', text)
        if year_match:
            info['year'] = year_match.group(1)
        remaining_text = car_line
    
    # Ищем марку и всё после неё - это марка + модель
    for brand in CAR_BRANDS:
        if brand.lower() in remaining_text.lower():
            info['brand'] = brand
            # Находим позицию марки и берём все после неё
            brand_pos = remaining_text.lower().find(brand.lower())
            after_brand = remaining_text[brand_pos + len(brand):].strip()
            
            # Всё, что осталось после марки - это модель
            if after_brand:
                info['model'] = after_brand
            break
    
    # Состояние (отличное, хорошее, удовлетворительное и т.д.)
    condition_match = re.search(r'(?:состояние|condition)[\s:]*([^\n,]+)', text, re.IGNORECASE)
    if condition_match:
        info['condition'] = condition_match.group(1).strip()
    
    # Привод (передний, задний, полный)
    if 'передний' in text.lower() or 'front' in text.lower() or 'fwd' in text.lower():
        info['drive'] = 'Передний'
    elif 'задний' in text.lower() or 'rear' in text.lower() or 'rwd' in text.lower():
        info['drive'] = 'Задний'
    elif 'полный' in text.lower() or 'all' in text.lower() or 'awd' in text.lower() or '4wd' in text.lower():
        info['drive'] = 'Полный'
    
    # Пробег (цифры + км/mi)
    mileage_match = re.search(r'(\d+(?:[.,]\d+)*)\s*(?:км|km|mi|miles|миль)', text, re.IGNORECASE)
    if mileage_match:
        info['mileage'] = mileage_match.group(0).replace('.', '').replace(',', '')
    
    # Цена - ищем строку которая содержит цену (например "Цена: 50000 $")
    # Сначала ищем все строки с ценой
    price_lines = re.finditer(r'(?:цена|price)[\s:]*([^\n]+)', text, re.IGNORECASE)
    price_found = False
    currency = ''
    
    for price_line_match in price_lines:
        price_line = price_line_match.group(0)
        
        # Если есть МСК или Москва в этой строке - приоритет высокий
        if 'мск' in price_line.lower() or 'москва' in price_line.lower():
            price_value_match = re.search(r'(\d[\d\.]*)\s*([€$₽]|USD|EUR)?', price_line, re.IGNORECASE)
            if price_value_match:
                price_value = price_value_match.group(1).replace('.', '').replace(' ', '')  # Убираем точки и пробелы
                currency = price_value_match.group(2) if price_value_match.group(2) else ''
                try:
                    original_price = int(price_value)
                    new_price = int(original_price * 1.05)
                    # Округляем до целого числа в сотнях тысяч
                    new_price = round(new_price / 100000) * 100000
                    info['price'] = f"{new_price} {currency}".strip()
                    info['price_num'] = original_price
                except:
                    info['price'] = f"{price_value} {currency}".strip()
                price_found = True
                break
    
    # Если МСК/Москва не найдена, берём первую найденную цену
    if not price_found:
        price_line_match = re.search(r'(?:цена|price)[\s:]*([^\n]+)', text, re.IGNORECASE)
        if price_line_match:
            price_line = price_line_match.group(1).strip()
            # Извлекаем из этой строки число + валюту
            price_match = re.search(r'(\d[\d\.]*)\s*([€$₽]|USD|EUR)?', price_line, re.IGNORECASE)
            if price_match:
                price_value = price_match.group(1).replace('.', '').replace(' ', '')  # Убираем точки и пробелы
                currency = price_match.group(2) if price_match.group(2) else ''
                try:
                    original_price = int(price_value)
                    new_price = int(original_price * 1.05)
                    # Округляем до целого числа в сотнях тысяч
                    new_price = round(new_price / 100000) * 100000
                    info['price'] = f"{new_price} {currency}".strip()
                    info['price_num'] = original_price
                except:
                    info['price'] = f"{price_value} {currency}".strip()
                price_found = True
    
    # Если всё ещё не найдена цена, используем общий поиск
    if not price_found:
        price_match = PRICE_PATTERN.search(text)
        if price_match:
            price_value = price_match.group(0).replace('.', '').replace(' ', '')  # Убираем точки и пробелы
            price_currency_match = re.search(r'([€$₽]|USD|EUR)', price_value)
            if price_currency_match:
                currency = price_currency_match.group(0)
                price_num_str = re.search(r'(\d+)', price_value.replace(currency, ''))
                if price_num_str:
                    try:
                        original_price = int(price_num_str.group(1))
                        new_price = int(original_price * 1.05)
                        # Округляем до целого числа в сотнях тысяч
                        new_price = round(new_price / 100000) * 100000
                        info['price'] = f"{new_price} {currency}"
                        info['price_num'] = original_price
                    except:
                        info['price'] = price_value
            else:
                info['price'] = price_value
    
    # Ищем курс (например "79₽/USDT" или "79 ₽/USDT")
    exchange_rate_match = re.search(r'(\d+(?:[.,]\d+)?)\s*₽\s*/\s*(?:USDT|USD)', text, re.IGNORECASE)
    if exchange_rate_match:
        info['exchange_rate'] = exchange_rate_match.group(1)
    
    return info

def get_car_tagline(text: str) -> str:
    """Извлекает ключевое преимущество/особенность (новый, рестайлинг, AMG, люксовый и т.д.)"""
    # Ищем важные маркеры
    if 'amg' in text.lower():
        return "мощная версия AMG"
    if 'f sport' in text.lower() or 'f-sport' in text.lower():
        return "спортивный F Sport"
    if 'рестайлинг' in text.lower() or 'restyling' in text.lower():
        return "обновленный рестайлинг"
    if 'новый' in text.lower() or 'new' in text.lower() or '2025' in text or '2024' in text:
        return "новый и свежий"
    if 'люкс' in text.lower() or 'люксовый' in text.lower() or 'премиум' in text.lower():
        return "люксовый комфорт"
    if 'спорт' in text.lower() or 'sport' in text.lower():
        return "спортивная мощь"
    if 'дизель' in text.lower():
        return "мощь экономичного дизеля"
    if 'электро' in text.lower() or 'electric' in text.lower():
        return "чистая электроэнергия"
    if 'гибрид' in text.lower() or 'hybrid' in text.lower():
        return "гибридная экономичность"
    
    return "премиальный комфорт"

def get_car_description(brand: str, model: str, text: str) -> str:
    """Генерирует краткое описание второй строки с 1-2 ключевыми преимуществами"""
    # Определяем преимущества на основе текста
    advantages = []
    
    # Комфорт и люкс
    if any(word in text.lower() for word in ['люкс', 'премиум', 'кожа', 'панорам', 'люкс']):
        advantages.append("комфорт премиум-класса")
    
    # Технологии и инновации
    if any(word in text.lower() for word in ['технолог', 'инновац', 'ai', 'автопилот', 'электро']):
        advantages.append("передовые технологии")
    
    # Статус и престиж
    if any(word in text.lower() for word in ['флагман', 'топ', 'премиум', 'люкс', 'амг']):
        advantages.append("статусный автомобиль")
    
    # Мощность и динамика
    if any(word in text.lower() for word in ['мощ', 'динамик', 'спорт', 'л.с', 'hp', '367', '450']):
        advantages.append("динамичная мощность")
    
    # Надежность
    if any(word in text.lower() for word in ['надежн', 'долговечн', 'toyota', 'honda']):
        advantages.append("надежность на годы")
    
    # Экономичность
    if any(word in text.lower() for word in ['дизель', 'гибрид', 'эконом', 'расход']):
        advantages.append("экономичный расход")
    
    # Семейный транспорт
    if any(word in text.lower() for word in ['семей', 'suv', 'внедорож', 'детский']):
        advantages.append("идеален для семьи")
    
    # Выбираем 1-2 лучших преимущества
    if not advantages:
        advantages.append("надежное качество")
    
    if len(advantages) > 2:
        advantages = advantages[:2]
    
    advantage_text = " и ".join(advantages)
    
    return f"Для тех, кто ценит {advantage_text}"

def generate_text_with_chatgpt(info: dict, original_text: str) -> str:
    """Генерирует маркетинговый текст через ChatGPT API"""
    try:
        prompt = f"""Ты специалист по продаже автомобилей. Напиши привлекательное описание для объявления о продаже автомобиля.

Параметры автомобиля:
- Марка и модель: {info['brand']} {info['model']}
- Год выпуска: {info['year']}
- Привод: {info['drive']}
- Пробег: {info['mileage']}
- Цена: {info['price']}

Требования:
1. Первая строка: 🔥 **{info['brand']} {info['model']}** 🔥
2. Вторая строка: 🚘 Краткое описание автомобиля (1-2 преимущества)
3. Затем: ⚙️ Характеристики с параметрами
4. Затем: Комплектация и преимущества (4-5 пунктов)
5. Затем: Цена и информация о расходах
6. В конце: Контакты и каналы

Стиль: профессиональный, привлекательный, ориентированный на мотивацию покупателя
Используй эмодзи для выделения информации
Текст должен быть на русском языке"""
        
        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "Ты профессиональный писатель объявлений о продаже автомобилей. Пишешь убедительные, красиво оформленные тексты с использованием эмодзи."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.7,
            max_tokens=800
        )
        
        return response.choices[0].message.content
    except Exception as e:
        print(f"Ошибка при запросе к ChatGPT: {e}")
        return None

def format_message(text: str, brand: str) -> str:
    """Форматирует сообщение с использованием ChatGPT или стандартного шаблона"""
    info = parse_car_info(text)
    
    # Пытаемся получить текст от ChatGPT
    generated_text = generate_text_with_chatgpt(info, text)
    
    if generated_text:
        # Если ChatGPT вернул текст, добавляем контакты и источник
        message = generated_text + "\n\n"
    else:
        # Если ChatGPT недоступен, используем стандартный шаблон
        message = f"🔥 **{info['brand']} {info['model']}** 🔥\n\n"
        message += f"🚘 {get_car_description(info['brand'], info['model'], text)}\n\n"
        message += f"⚙️ Характеристики:\n"
        message += f"🗓 Год выпуска: {info['year']}\n"
        
        engine_info = ""
        engine_match = re.search(r'(\d+\.?\d*)\s*л[\s\.]*([^,\n]+)', text, re.IGNORECASE)
        if engine_match:
            engine_info = f"{engine_match.group(1)} л {engine_match.group(2)}"
            message += f"🚀 Двигатель: {engine_info}\n"
        
        message += f"🛞 Привод: {info['drive']}\n"
        message += f"📊 Пробег: {info['mileage']}\n"
        
        if info['condition'] != '—':
            message += f"🛠 Состояние: {info['condition']}\n"
        
        message += f"\n✨ Комплектация и преимущества:\n"
        message += f"✔️ Премиальный транспорт\n"
        message += f"✔️ Комфорт и надёжность\n"
        message += f"✔️ Привод: {info['drive']}\n"
        message += f"✔️ Идеально для семьи и бизнеса\n"
        message += f"✔️ Высокий уровень комфорта и безопасности\n\n"
        
        message += f"💰 Цена под ключ: {info['price']}\n"
        message += f"📌 В стоимость включены все расходы\n\n"
    
    # Добавляем контакты (всегда одинаковые)
    message += f"📞 Контакты для связи:\n"
    message += f"📱 +995 577 11 57 57\n"
    message += f"📲 Telegram: @kingofgeorgia\n"
    message += f"📷 Instagram: instagram.com/king.of.georgia\n\n"
    
    message += f"📲 Автоканал с новыми поступлениями:\n"
    message += f"🎧 Telegram: t.me/mileoncars\n"
    message += f"🎥 Instagram: instagram.com/mileoncars\n\n"
    
    message += f"🔁 Нужна другая комплектация или модель?\n"
    message += f"Подберём оптимальный вариант под ваш бюджет и задачи.\n\n"
    
    message += f"📍 Источник: @{SOURCE_CHANNEL}"
    
    return message

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

            # Проверяем наличие видео - пропускаем посты с видео
            if msg.media:
                media_type = msg.media.__class__.__name__
                if 'Video' in media_type or 'VideoNote' in media_type:
                    print(f"ID={msg.id} - видео, пропускаем")
                    continue

            # Берём текст из сообщения или подписи к медиа
            text = msg.message or (msg.media.caption if hasattr(msg.media, "caption") else "")
            if not msg.media:
                print(f"ID={msg.id} - нет медиа, пропускаем")
                continue

            brand = next((b for b in CAR_BRANDS if b.lower() in (text or "").lower()), "—")
            if text and not match_filters(text):
                print(f"ID={msg.id} - не прошло фильтры")
                continue

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
                    # Пропускаем видео в альбоме
                    if m.media:
                        media_type = m.media.__class__.__name__
                        if 'Video' in media_type or 'VideoNote' in media_type:
                            continue
                    
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
                
                # Если в альбоме менее 2 фото - пропускаем
                if len(media_list) < 2:
                    print(f"ID={msg.id} - менее 2 фотографий в альбоме, пропускаем")
                    continue
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
