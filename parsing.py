import asyncio
import json
import os
import re
import sqlite3
import sys
import traceback
from pathlib import Path
from io import BytesIO
from telethon import TelegramClient, types
from telethon.extensions import markdown
from openai import OpenAI
from currency_converter_free import CurrencyConverter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ================== НАСТРОЙКИ ==================
api_id = 34277624
api_hash = "3906edabc2198a97d68878633496809d"

SOURCE_CHANNELS = ["garageneva","@antonbuyavtochina"]
TARGET_CHANNEL = "mileoncars"
UPDATE_INTERVAL = 300  # секунд
SESSION_LOCK_RETRIES = 6
SESSION_LOCK_RETRY_DELAY = 3  # секунд

# OpenAI API
OPENAI_API_KEY_FILE = Path("openai_api_key.txt")


def load_openai_api_key() -> str:
    env_key = os.getenv("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key

    if OPENAI_API_KEY_FILE.exists():
        try:
            file_key = OPENAI_API_KEY_FILE.read_text(encoding="utf-8").strip()
            if file_key:
                return file_key
            print(f"Файл ключа найден, но пустой: {OPENAI_API_KEY_FILE}")
        except Exception as e:
            print(f"Не удалось прочитать {OPENAI_API_KEY_FILE}: {e}")

    print(
        "OPENAI_API_KEY не найден ни в переменной окружения OPENAI_API_KEY, "
        f"ни в файле {OPENAI_API_KEY_FILE}"
    )

    return ""


OPENAI_API_KEY = load_openai_api_key()
OPENAI_MODEL = "gpt-5-mini"
OPENAI_MAX_COMPLETION_TOKENS = 3200
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

SYSTEM_PROMPT = (
"Ты — маркетолог компании MileON Cars. Формируй объявления строго по фирменному мастер-шаблону MileON Cars. "
    "Никаких отклонений от структуры. Никаких служебных комментариев. Только готовое объявление.\n"

    "СТРУКТУРА ОБЯЗАТЕЛЬНА:\n"

    "Заголовок:\n"
    "Формат: 🔥 **Марка Модель** — сильный продающий подзаголовок! 🔥\n"
    "- Марка и модель всегда жирным.\n"
    "- Год никогда не указывать в заголовке.\n"
    "- Если в extras передан флаг (страна), ставь его перед маркой и моделью.\n"
    "- Подзаголовок — одна сильная маркетинговая формулировка.\n"
    "- Не указывай название блока.\n\n\n"

    "Краткое позиционирование:\n"
    "- Одна строка с описанием целевой аудитории и статуса автомобиля.\n\n"
    "- Не указывай название блока.\n"

    "Блок характеристик:\n"
    "Формат строго:\n"
    "⚙️ **Характеристики:**\n"
    "🗓 Год выпуска:\n"
    "📍 Локация: (указать страну, флаг которое передан в extras)\n"
    "📊 Пробег:\n"
    "🚗 Двигатель:\n"
    "⚡️ Мощность:\n"
    "⚙️ Коробка передач:\n"
    "🛞 Привод:\n"
    "🏆 Комплектация:\n"
    "- Порядок строк фиксированный.\n"
    "- Если engine_volume или power пустые — определить типовой двигатель и мощность по марке, модели и году.\n"
    "- Если drive пустой — определить типовой привод по модели.\n"
    "- Не придумывай новые модели автомобилей и комплектации.\n"
    "- Не указывай название блока.\n"
    "- Если пробег 0 — писать: 0 км (новый автомобиль).\n\n\n"

    "Блок преимуществ:\n"
    "Формат:\n"
    "✨ **Преимущества:**\n"
    "- 5–8 конкретных пунктов.\n"
    "- Комфорт, безопасность, технологии, интерьер, ассистенты, мультимедиа.\n"
    "- Если extras пустой — использовать типовые сильные стороны модели.\n"
    "- Не указывай название блока.\n"
    "- Без воды.\n\n"

    "Блок цены:\n"
    "- Всегда увеличить price_local и price_russia на 5%.\n"
    "- Округлить до ближайшей тысячи в большую сторону.\n"
    "- Никогда не писать про добавление 5%.\n"
    "- Не указывай название блока.\n"
    "- Разделяй сотни, тысячи и миллионы пробелом.\n"
    "- Формат строго:\n"
    "💰 **Цена в USD: ХХХХХХХ $**\n"
    "💰 **Цена в RUB: ХХХХХХХ ₽**\n\n\n"


    "Блок контактов (строго таким форматом):\n"
    "**Контакты:**\n"
    "📱**+995 577 11 57 57**\n"
    "📱 **[Telegram](https://t.me/kingofgeorgia)**\n"
    "📸 **[Instagram](https://www.instagram.com/king.of.georgia/)**\n\n"

    "Финальная строка:\n"
    "🔁 Интересующий автомобиль уже забрали? Не беда!\n"
    "Мы подберём аналогичный вариант под ваш вкус и бюджет.\n\n"
    
    "🚘 **[MileON Cars](http://t.me/mileoncars)** — привозим автомобили из Китая, Европы и США с полной прозрачностью сделки и гарантией результата.\n\n"
    "- Не указывай название блока.\n"

    
    "СТИЛЬ:\n"
    "- Премиальный, уверенный, продающий.\n"
    "- Без лишнего текста.\n"
    "- Без технических пояснений.\n"
    "- Строго соблюдать структуру."
)

CAR_BRANDS_FILE = Path("car_brands.json")


def load_brand_config() -> tuple[list[str], list[tuple[str, str]]]:
    """Загружает бренды и алиасы. Возвращает (список брендов, список (alias, brand))."""
    default_brands = [
        "Toyota", "Volkswagen", "Ford", "Honda", "Nissan", "Hyundai", "Kia", "Chevrolet", "Mercedes-Benz", "BMW",
        "Audi", "Lexus", "Subaru", "Mazda", "Peugeot", "Renault", "Skoda", "Fiat", "Volvo", "Suzuki",
        "Mitsubishi", "Jeep", "Dodge", "GMC", "Cadillac", "Buick", "Chrysler", "Ram", "Tesla", "Porsche",
        "Jaguar", "Land Rover", "Range Rover", "Mini", "Alfa Romeo", "Maserati", "Ferrari", "Lamborghini", "Bentley", "Rolls-Royce",
        "Aston Martin", "McLaren", "Lotus", "Genesis", "Infiniti", "Acura", "Lincoln", "Saab", "Opel", "Vauxhall",
        "Citroen", "SEAT", "Cupra", "Dacia", "Smart", "Maybach", "Polestar", "Rivian", "Lucid", "BYD",
        "Geely", "Chery", "Haval", "Great Wall", "GWM", "NIO", "XPeng", "Li Auto", "Zeekr", "MG",
        "Roewe", "Wuling", "Baojun", "Dongfeng", "FAW", "JAC", "Jetour", "Omoda", "Jaecoo", "Proton",
        "Perodua", "Tata", "Mahindra", "Maruti Suzuki", "Isuzu", "Daihatsu", "SsangYong", "Koenigsegg", "Pagani", "Rimac",
        "Bugatti", "Alpina", "Scion", "Daewoo", "Lancia", "DS Automobiles", "Abarth", "Brilliance", "Hongqi", "UAZ"
    ]

    if not CAR_BRANDS_FILE.exists():
        fallback_aliases = sorted(
            [(brand.lower(), brand) for brand in default_brands],
            key=lambda x: len(x[0]),
            reverse=True,
        )
        return default_brands, fallback_aliases

    try:
        raw_items = json.loads(CAR_BRANDS_FILE.read_text(encoding="utf-8"))
        brands: list[str] = []
        alias_to_brand: dict[str, str] = {}

        for item in raw_items:
            brand = (item.get("brand") or "").strip()
            if not brand:
                continue

            brands.append(brand)
            aliases = item.get("aliases") or []
            for alias in [brand, *aliases]:
                alias_value = str(alias).strip().lower()
                if alias_value and alias_value not in alias_to_brand:
                    alias_to_brand[alias_value] = brand

        if not brands:
            raise ValueError("Файл брендов пустой")

        ordered_aliases = sorted(alias_to_brand.items(), key=lambda x: len(x[0]), reverse=True)
        return brands, ordered_aliases
    except Exception as e:
        print(f"Не удалось загрузить {CAR_BRANDS_FILE}: {e}")
        fallback_aliases = sorted(
            [(brand.lower(), brand) for brand in default_brands],
            key=lambda x: len(x[0]),
            reverse=True,
        )
        return default_brands, fallback_aliases


CAR_BRANDS, BRAND_ALIASES = load_brand_config()


def detect_brand(text: str) -> str | None:
    if not text:
        return None

    text_lower = text.lower()
    for alias, brand in BRAND_ALIASES:
        if alias in text_lower:
            return brand

    return None


def contains_brand(text: str) -> bool:
    return detect_brand(text) is not None


CURRENCIES = ["$", "€", "₽", "USD", "EUR"]
PRICE_PATTERN = re.compile(r"(\d[\d\s]{3,})\s*(" + "|".join(CURRENCIES) + ")", re.IGNORECASE)

_currency_converter: CurrencyConverter | None = None

client = TelegramClient("session_name", api_id, api_hash)
posted_ids = set()
POSTED_IDS_FILE = Path("posted_ids.json")


def load_posted_ids() -> set:
    if not POSTED_IDS_FILE.exists():
        return set()

    try:
        data = json.loads(POSTED_IDS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {str(x) for x in data if str(x).strip()}
    except Exception as e:
        print(f"Не удалось загрузить {POSTED_IDS_FILE}: {e}")

    return set()


def save_posted_ids() -> None:
    try:
        POSTED_IDS_FILE.write_text(
            json.dumps(sorted(posted_ids), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"Не удалось сохранить {POSTED_IDS_FILE}: {e}")

# ================== ФИЛЬТРЫ ==================
def match_filters(text: str) -> bool:
    if not text:
        return False
    if not contains_brand(text):
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
    if not contains_brand(first_line):
        for line in text.split('\n'):
            if contains_brand(line):
                car_line = line
                break
    
    # Модельный год: MY2025 / MY 2026 / MY-2026
    model_year_match = re.search(r'\bMY\s*[-:/]?\s*(20\d{2})\b', text, re.IGNORECASE)
    if model_year_match:
        info['year'] = model_year_match.group(1)

    # Ищем год в начале строки
    year_match = re.search(r'^(\d{4})\s+', car_line)
    if year_match:
        # Если не нашли модельный год, используем обычный год из заголовка
        if info['year'] == '—':
            info['year'] = year_match.group(1)
        # Убираем год из строки для дальнейшего парсинга
        remaining_text = car_line[year_match.end():]
    else:
        # Если год не в начале, ищем его везде в тексте
        if info['year'] == '—':
            year_match = re.search(r'\b(19\d{2}|20\d{2})\b', text)
            if year_match:
                info['year'] = year_match.group(1)
        remaining_text = car_line
    
    # Ищем марку и всё после неё - это марка + модель
    matched_brand = detect_brand(remaining_text)
    if matched_brand:
        info['brand'] = matched_brand
        # Находим первую подходящую строку-алиас и берём всё после неё как модель
        remaining_lower = remaining_text.lower()
        for alias, brand in BRAND_ALIASES:
            if brand == matched_brand and alias in remaining_lower:
                alias_pos = remaining_lower.find(alias)
                after_brand = remaining_text[alias_pos + len(alias):].strip()
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
    
    text_lower = text.lower()

    # Пробег: если новое авто/без пробега — принудительно 0 км
    is_zero_mileage = any(
        marker in text_lower
        for marker in ["без пробега", "новое авто", "новый авто", "новый автомобиль", "new car", "brand new"]
    )
    if is_zero_mileage:
        info['mileage'] = "0 км"
    else:
        mileage_match = re.search(
            r'(\d[\d\s.,\u00A0\u202F]*)\s*(км|km|mi|miles|миль)\b',
            text,
            re.IGNORECASE
        )
        if mileage_match:
            mileage_value = re.sub(r'[\s.,\u00A0\u202F]+', '', mileage_match.group(1))
            mileage_unit = mileage_match.group(2)
            info['mileage'] = f"{mileage_value} {mileage_unit}"

    def currency_rank(currency_value: str) -> int:
        normalized = currency_value.upper()
        if normalized in ('$', 'USD'):
            return 0
        if normalized in ('₽', 'RUB'):
            return 1
        if normalized in ('€', 'EUR'):
            return 2
        return 3

    price_candidates: list[tuple[int, str, int, int]] = []
    for line_index, line in enumerate(text.splitlines()):
        line_lower = line.lower()
        location_rank = 0 if ('мск' in line_lower or 'москва' in line_lower) else 1
        for price_match in re.finditer(r'(\d[\d\s.,\u00A0\u202F]*)\s*([€$₽]|USD|EUR|RUB)', line, re.IGNORECASE):
            amount_raw = re.sub(r'[\s.,\u00A0\u202F]+', '', price_match.group(1))
            if not amount_raw.isdigit():
                continue
            price_candidates.append((int(amount_raw), price_match.group(2), location_rank, line_index))

    if price_candidates:
        has_usd_price = any(currency_rank(currency) == 0 for _, currency, _, _ in price_candidates)
        if has_usd_price:
            filtered_candidates = [c for c in price_candidates if currency_rank(c[1]) == 0]
        else:
            filtered_candidates = [c for c in price_candidates if currency_rank(c[1]) in (1, 2)]
            if not filtered_candidates:
                filtered_candidates = price_candidates

        filtered_candidates.sort(key=lambda c: (c[2], currency_rank(c[1]), c[3]))
        original_price, currency, _, _ = filtered_candidates[0]
        new_price = int(original_price * 1.05)
        new_price = round(new_price / 1000) * 1000
        info['price'] = f"{new_price} {currency}".strip()
        info['price_num'] = original_price
        print(f"[PARSE] Выбрана цена: {original_price} {currency} -> {new_price} {currency}")
    
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


def sanitize_text_for_ai(text: str) -> str:
    """Удаляет из исходного текста телефоны, ссылки, @username и упоминания источника."""
    if not text:
        return ""

    contact_or_source_line = re.compile(
        r"(?i)(контакт|тел\.?|телефон|phone|whatsapp|ватсап|viber|instagram|инстаграм|"
        r"telegram|телеграм|t\.me|http[s]?://|www\.|источник|source|канал|channel|"
        r"youtube|tiktok|autopapa|myauto|facebook|x\.com|twitter)"
    )

    sanitized_lines = []
    for raw_line in text.splitlines():
        line = re.sub(r"https?://\S+|www\.\S+|t\.me/\S+", "", raw_line, flags=re.IGNORECASE)
        line = re.sub(r"instagram\.com/\S+", "", line, flags=re.IGNORECASE)
        line = re.sub(r"(?:autopapa|myauto)\.ge/\S*", "", line, flags=re.IGNORECASE)
        line = re.sub(r"@[A-Za-z0-9_]{3,}", "", line)
        line = re.sub(r"(?<!\d)(?:\+?\d[\d\s\-\(\)]{7,}\d)", "", line)

        if contact_or_source_line.search(line):
            continue

        line = re.sub(r"\s{2,}", " ", line).strip()
        if line:
            sanitized_lines.append(line)

    return "\n".join(sanitized_lines)


def extract_engine_power(text: str) -> str | None:
    if not text:
        return None

    horsepower_match = re.search(
        r'(\d{2,4})\s*(?:л\.?\s*/?\s*с\.?|лс|hp|h\.p\.)\b',
        text,
        re.IGNORECASE,
    )
    if not horsepower_match:
        return None

    horsepower = horsepower_match.group(1)
    return f"{horsepower} л.с."


def extract_engine_volume(text: str) -> str | None:
    if not text:
        return None

    volume_match = re.search(
        r'\b(\d{1,2}(?:[\.,]\d{1,2})?)\s*л(?!\s*/?\s*с\b)',
        text,
        re.IGNORECASE,
    )
    if not volume_match:
        return None

    volume = volume_match.group(1).replace(',', '.')
    return f"{volume} л"


def extract_currency(price_value: str) -> str | None:
    if not price_value:
        return None

    match = re.search(r'([€$₽]|USD|EUR|RUB)', price_value, re.IGNORECASE)
    return match.group(1).upper() if match else None


def normalize_currency_code(currency_value: str | None) -> str | None:
    if not currency_value:
        return None

    normalized = currency_value.strip().upper()
    mapping = {
        "$": "USD",
        "USD": "USD",
        "€": "EUR",
        "EUR": "EUR",
        "₽": "RUB",
        "RUB": "RUB",
    }
    return mapping.get(normalized)


def get_currency_converter() -> CurrencyConverter | None:
    global _currency_converter

    if _currency_converter is not None:
        return _currency_converter

    try:
        _currency_converter = CurrencyConverter()
    except Exception as e:
        print(f"[FX] Не удалось инициализировать CurrencyConverter: {e}")
        _currency_converter = None

    return _currency_converter


def extract_price_amount(price_value: str | None) -> float | None:
    if not price_value:
        return None

    match = re.search(r'(\d[\d\s.,\u00A0\u202F]*)', price_value)
    if not match:
        return None

    amount_raw = re.sub(r'[\s.,\u00A0\u202F]+', '', match.group(1))
    if not amount_raw.isdigit():
        return None

    return float(amount_raw)


def fetch_live_exchange_rates_to_rub() -> dict[str, float] | None:
    converter = get_currency_converter()
    if not converter:
        return None

    try:
        rates = {
            "USD": float(converter.convert(1.0, "USD", "RUB")),
            "EUR": float(converter.convert(1.0, "EUR", "RUB")),
            "RUB": 1.0,
        }
        print(
            "[FX] Актуальные курсы (к RUB): "
            f"USD={rates['USD']:.6f}, EUR={rates['EUR']:.6f}, RUB={rates['RUB']:.6f}"
        )
        return rates
    except Exception as e:
        print(f"[FX] Не удалось получить актуальные курсы: {e}")
        return None


def convert_price_to_rub(
    price_value: str | None,
    currency_value: str | None,
    rates_to_rub: dict[str, float] | None = None,
) -> int | None:
    amount = extract_price_amount(price_value)
    source_currency = normalize_currency_code(currency_value)

    if amount is None or not source_currency:
        return None

    if source_currency == "RUB":
        return int(round(amount))

    if rates_to_rub and source_currency in rates_to_rub:
        try:
            converted = amount * float(rates_to_rub[source_currency])
            return int(round(converted))
        except Exception as e:
            print(
                f"[FX] Ошибка пересчета через актуальные курсы: amount={amount}, "
                f"from={source_currency}, error={e}"
            )

    converter = get_currency_converter()
    if not converter:
        return None

    try:
        converted = converter.convert(amount, source_currency, "RUB")
        return int(round(converted))
    except Exception as e:
        print(
            f"[FX] Не удалось конвертировать цену в RUB: amount={amount}, "
            f"from={source_currency}, error={e}"
        )
        return None


def convert_price_to_usd(
    price_value: str | None,
    currency_value: str | None,
    rates_to_rub: dict[str, float] | None = None,
) -> int | None:
    amount = extract_price_amount(price_value)
    source_currency = normalize_currency_code(currency_value)

    if amount is None or not source_currency:
        return None

    if source_currency == "USD":
        return int(round(amount))

    if rates_to_rub and "USD" in rates_to_rub:
        try:
            if source_currency == "RUB":
                converted = amount / float(rates_to_rub["USD"])
                return int(round(converted))

            if source_currency in rates_to_rub:
                amount_in_rub = amount * float(rates_to_rub[source_currency])
                converted = amount_in_rub / float(rates_to_rub["USD"])
                return int(round(converted))
        except Exception as e:
            print(
                f"[FX] Ошибка пересчета через актуальные курсы в USD: amount={amount}, "
                f"from={source_currency}, error={e}"
            )

    converter = get_currency_converter()
    if not converter:
        return None

    try:
        converted = converter.convert(amount, source_currency, "USD")
        return int(round(converted))
    except Exception as e:
        print(
            f"[FX] Не удалось конвертировать цену в USD: amount={amount}, "
            f"from={source_currency}, error={e}"
        )
        return None


def format_price_value(amount: int | None, currency_code: str) -> str | None:
    if amount is None:
        return None

    return f"{amount} {currency_code}"


def extract_flag_emoji(text: str) -> str | None:
    if not text:
        return None

    # Флаг страны = 2 regional indicator символа
    match = re.search(r'[\U0001F1E6-\U0001F1FF]{2}', text)
    return match.group(0) if match else None


def extract_country_flag(text: str) -> str | None:
    if not text:
        return None

    # Если в тексте уже есть эмодзи флага — используем его
    explicit_flag = extract_flag_emoji(text)
    if explicit_flag:
        return explicit_flag

    country_to_flag = [
        (r'\b(япония|japan|япон)\b', '🇯🇵'),
        (r'\b(корея|korea|коре[йя]ск)\b', '🇰🇷'),
        (r'\b(китай|china|китая|кита[йя]ск)\b', '🇨🇳'),
        (r'\b(сша|usa|united states|америк)\b', '🇺🇸'),
        (r'\b(германи[яи]|germany|немец)\b', '🇩🇪'),
        (r'\b(оаэ|uae|dubai|дубай|emirates)\b', '🇦🇪'),
        (r'\b(грузи[яи]|georgia)\b', '🇬🇪'),
        (r'\b(великобритани[яи]|uk|united kingdom|англи[яи]|britain)\b', '🇬🇧'),
        (r'\b(итал[ияии]|italy)\b', '🇮🇹'),
        (r'\b(франци[яи]|france)\b', '🇫🇷'),
        (r'\b(росси[яи]|russia|рф)\b', '🇷🇺'),
        (r'\b(канад[аеы]|canada)\b', '🇨🇦'),
    ]

    for pattern, flag in country_to_flag:
        if re.search(pattern, text, re.IGNORECASE):
            return flag

    return None


def normalize_text_field(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text or text == "—":
        return None

    return text


def resolve_brand_model_for_payload(info: dict, sanitized_text: str) -> tuple[str, str]:
    brand = normalize_text_field(info.get("brand"))
    model = normalize_text_field(info.get("model"))

    if not brand:
        brand = detect_brand(sanitized_text)

    if not model and brand and sanitized_text:
        for line in sanitized_text.splitlines():
            line_value = line.strip()
            if not line_value:
                continue

            line_lower = line_value.lower()
            for alias, alias_brand in BRAND_ALIASES:
                if alias_brand != brand:
                    continue

                alias_pos = line_lower.find(alias)
                if alias_pos < 0:
                    continue

                after_brand = line_value[alias_pos + len(alias):]
                after_brand = re.sub(r'^[\s\-–—:|,/]+', '', after_brand)
                after_brand = re.sub(r'\b(19\d{2}|20\d{2})\b', ' ', after_brand)
                after_brand = re.sub(
                    r'\d[\d\s.,\u00A0\u202F]*\s*([€$₽]|USD|EUR|RUB)\b.*$',
                    '',
                    after_brand,
                    flags=re.IGNORECASE,
                )
                after_brand = re.split(r'[\n|•;,@()]', after_brand)[0]
                after_brand = re.sub(r'\s{2,}', ' ', after_brand).strip()

                if after_brand:
                    model = after_brand
                    break

            if model:
                break

    if not brand and sanitized_text:
        first_line = next((line.strip() for line in sanitized_text.splitlines() if line.strip()), "")
        brand_match = re.match(r'([A-Za-zА-Яа-я0-9\-]+)', first_line)
        if brand_match:
            brand = brand_match.group(1)

    if not model and sanitized_text:
        first_line = next((line.strip() for line in sanitized_text.splitlines() if line.strip()), "")
        tokens = re.findall(r'[A-Za-zА-Яа-я0-9\-/]+', first_line)
        tokens = [token for token in tokens if not re.fullmatch(r'(19|20)\d{2}', token)]

        if brand and tokens and tokens[0].lower() == brand.lower():
            tokens = tokens[1:]

        if tokens:
            model = " ".join(tokens[:3])

    if (not brand or not model) and sanitized_text:
        for line in sanitized_text.splitlines():
            line_value = line.strip()
            if not line_value:
                continue

            candidate_tokens = re.findall(r'[A-Za-zА-Яа-я0-9\-/]+', line_value)
            candidate_tokens = [
                token for token in candidate_tokens
                if not re.fullmatch(r'(19|20)\d{2}', token)
            ]

            if not candidate_tokens:
                continue

            if not brand:
                brand = candidate_tokens[0]

            if not model:
                model_tokens = candidate_tokens[1:4] if len(candidate_tokens) > 1 else []
                if model_tokens:
                    model = " ".join(model_tokens)
            if brand and model:
                break

    if not brand:
        brand = ""
    if not model:
        model = ""

    return brand, model


def build_ai_payload(info: dict, sanitized_text: str) -> dict:
    flag_emoji = extract_country_flag(sanitized_text)
    resolved_brand, resolved_model = resolve_brand_model_for_payload(info, sanitized_text)
    source_price = None if info.get("price") in (None, "—") else info.get("price")
    source_currency = extract_currency(info.get("price", ""))
    exchange_rates = fetch_live_exchange_rates_to_rub()
    price_usd_amount = convert_price_to_usd(source_price, source_currency, exchange_rates)
    price_rub_amount = convert_price_to_rub(source_price, source_currency, exchange_rates)
    price_local = format_price_value(price_usd_amount, "USD")
    price_russia = format_price_value(price_rub_amount, "RUB")

    print(
        "[FX] Нормализация цены для OpenAI: "
        f"source={source_price} ({source_currency}), "
        f"price_local={price_local}, price_russia={price_russia}"
    )

    return {
        "brand": resolved_brand,
        "model": resolved_model,
        "year": int(info["year"]) if str(info.get("year", "")).isdigit() else None,
        "engine_volume": extract_engine_volume(sanitized_text),
        "power": extract_engine_power(sanitized_text),
        "drive": None if info.get("drive") in (None, "—") else info.get("drive"),
        "mileage": None if info.get("mileage") in (None, "—") else info.get("mileage"),
        "price_local": price_local,
        "price_russia": price_russia,
        "currency": "USD",
        "extras": flag_emoji
    }


def generate_text_with_chatgpt(info: dict, original_text: str) -> str | None:
    """Генерирует маркетинговый текст через ChatGPT API"""
    if not openai_client:
        print("Ошибка API: OPENAI_API_KEY не задан")
        return None

    try:
        payload = build_ai_payload(info, original_text)
        payload_json = json.dumps(payload, ensure_ascii=False)

        print("\n[OPENAI] ===== REQUEST =====")
        print(f"[OPENAI] model={OPENAI_MODEL}")
        print(f"[OPENAI] system_prompt={SYSTEM_PROMPT}")
        print(f"[OPENAI] user_payload={payload_json}")
        print("[OPENAI] ====================\n")

        def request_generation(max_tokens: int, attempt_label: str) -> tuple[str | None, str | None]:
            response = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": payload_json
                    }
                ],
                max_completion_tokens=max_tokens
            )

            content = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason

            print(f"\n[OPENAI] ===== RESPONSE ({attempt_label}) =====")
            print(f"[OPENAI] model={response.model}")
            print(f"[OPENAI] max_completion_tokens={max_tokens}")
            print(f"[OPENAI] finish_reason={finish_reason}")
            print(f"[OPENAI] content={content}")
            print("[OPENAI] =====================\n")

            return content, finish_reason

        content, _ = request_generation(
            max_tokens=OPENAI_MAX_COMPLETION_TOKENS,
            attempt_label="attempt=1"
        )

        if isinstance(content, str) and content.strip():
            return content

        print("Ошибка API: модель вернула пустой ответ")
        return None
    except Exception as e:
        print(f"Ошибка при запросе к ChatGPT: {e}")
        return None

def format_message(text: str, brand: str) -> str | None:
    """Форматирует сообщение через ChatGPT. Если API недоступен — возвращает None."""
    safe_text = sanitize_text_for_ai(text)
    parsing_text = safe_text if safe_text else text
    info = parse_car_info(parsing_text)
    
    # Пытаемся получить текст от ChatGPT
    generated_text = generate_text_with_chatgpt(info, safe_text)

    if not generated_text:
        return None

    return generated_text.strip()


def wait_before_exit() -> None:
    """Ожидание ввода перед закрытием в интерактивном терминале."""
    if sys.stdin.isatty():
        try:
            input("Нажмите Enter для закрытия...")
        except Exception:
            pass


def has_video_media(message) -> bool:
    """Проверяет, содержит ли сообщение видео (включая document с video-атрибутами)."""
    if not message or not getattr(message, "media", None):
        return False

    media = message.media
    media_type = media.__class__.__name__
    if 'Video' in media_type or 'VideoNote' in media_type:
        return True

    document = getattr(media, "document", None)
    if not document:
        return False

    mime_type = (getattr(document, "mime_type", "") or "").lower()
    if mime_type.startswith("video/"):
        return True

    for attr in getattr(document, "attributes", []) or []:
        if isinstance(attr, types.DocumentAttributeVideo):
            return True

    return False


def make_message_key(source_id: int, message_id: int) -> str:
    return f"{source_id}:m:{message_id}"


def make_group_key(source_id: int, grouped_id: int) -> str:
    return f"{source_id}:g:{grouped_id}"


def migrate_legacy_posted_ids(primary_source_id: int) -> bool:
    """Переводит старые числовые ID в формат ключей с привязкой к source_id."""
    global posted_ids

    legacy_ids = [value for value in posted_ids if ":" not in value and value.isdigit()]
    if not legacy_ids:
        return False

    migrated_keys = set(posted_ids)
    for legacy_id in legacy_ids:
        numeric_id = int(legacy_id)
        migrated_keys.add(make_message_key(primary_source_id, numeric_id))
        migrated_keys.add(make_group_key(primary_source_id, numeric_id))
        migrated_keys.discard(legacy_id)

    posted_ids = migrated_keys
    return True

# ================== ПАРСИНГ И ПУБЛИКАЦИЯ ==================
async def fetch_and_post():
    global posted_ids

    print("Старт скрипта...")
    posted_ids = load_posted_ids()
    print(f"Загружено обработанных ID: {len(posted_ids)}")

    for attempt in range(1, SESSION_LOCK_RETRIES + 1):
        try:
            await client.start()
            break
        except sqlite3.OperationalError as e:
            if "database is locked" not in str(e).lower() or attempt == SESSION_LOCK_RETRIES:
                raise

            wait_seconds = SESSION_LOCK_RETRY_DELAY * attempt
            print(
                "Файл Telethon-сессии занят другим процессом "
                f"(попытка {attempt}/{SESSION_LOCK_RETRIES}). "
                f"Повтор через {wait_seconds} сек..."
            )
            await asyncio.sleep(wait_seconds)

    print("Клиент Telethon подключен.")

    source_entities = [await client.get_entity(channel) for channel in SOURCE_CHANNELS]
    primary_source = source_entities[0]
    if migrate_legacy_posted_ids(primary_source.id):
        save_posted_ids()
        print("Старые posted_ids мигрированы в формат с привязкой к source_id")

    target = await client.get_entity(TARGET_CHANNEL)
    source_names = ", ".join(SOURCE_CHANNELS)
    print(f"Подключение к каналам: источники={source_names}, целевой={TARGET_CHANNEL}")

    while True:
        reached_known_in_any_source = False
        found_count = 0
        published_count = 0
        failed_count = 0
        failed_api_count = 0
        failed_send_count = 0
        last_send_error = ""
        skipped_video_count = 0
        per_source_stats = {}
        stop_batch_on_failure = False

        for source in source_entities:
            if stop_batch_on_failure:
                break

            source_name = getattr(source, "username", None) or getattr(source, "title", str(source.id))
            per_source_stats[source.id] = {
                "name": source_name,
                "found": 0,
                "published": 0,
                "skipped_video": 0,
                "failed": 0,
            }
            pending_messages = []
            pending_group_ids = set()
            reached_known_message = False

            async for msg in client.iter_messages(source, limit=None):
                message_key = make_message_key(source.id, msg.id)
                group_key = make_group_key(source.id, msg.grouped_id) if msg.grouped_id else None

                # Пропускаем уже опубликованные
                if message_key in posted_ids:
                    reached_known_message = True
                    print(f"[{source_name}] ID={msg.id} - уже опубликовано, останавливаем проход")
                    break

                # Если это часть альбома - пропускаем если уже публиковали
                if group_key and group_key in posted_ids:
                    reached_known_message = True
                    print(f"[{source_name}] GROUP_ID={msg.grouped_id} - альбом уже опубликован, останавливаем проход")
                    break

                # Добавляем только одно сообщение на альбом
                if msg.grouped_id:
                    if msg.grouped_id in pending_group_ids:
                        continue
                    pending_group_ids.add(msg.grouped_id)

                pending_messages.append(msg)

            if reached_known_message:
                reached_known_in_any_source = True

            # Публикуем в порядке исходного канала: от старых к новым
            pending_messages.reverse()
            found_count += len(pending_messages)
            per_source_stats[source.id]["found"] += len(pending_messages)

            for msg in pending_messages:
                if stop_batch_on_failure:
                    break

                # Дополнительная защита от дублей в рамках текущего прохода
                message_key = make_message_key(source.id, msg.id)
                group_key = make_group_key(source.id, msg.grouped_id) if msg.grouped_id else None
                if message_key in posted_ids:
                    continue
                if group_key and group_key in posted_ids:
                    continue

                # Если в объявлении есть видео — полностью пропускаем
                if has_video_media(msg):
                    print(f"[{source_name}] ID={msg.id} - видео, пропускаем объявление")
                    skipped_video_count += 1
                    per_source_stats[source.id]["skipped_video"] += 1
                    continue

                # Берём текст из сообщения или подписи к медиа
                text = msg.message or (msg.media.caption if hasattr(msg.media, "caption") else "")
                if not msg.media:
                    print(f"[{source_name}] ID={msg.id} - нет медиа, пропускаем")
                    continue

                brand = detect_brand(text or "") or "—"
                if text and not match_filters(text):
                    print(f"[{source_name}] ID={msg.id} - не прошло фильтры")
                    continue

                # ===== Собираем медиа для альбома в памяти =====
                media_list = []
                grouped_message_ids = set()
                all_text = text  # Текст из первого сообщения

                if msg.grouped_id:
                    # Альбом - собираем все сообщения с одинаковым grouped_id
                    album_messages = []
                    async for m in client.iter_messages(source, limit=100):
                        if getattr(m, "grouped_id", None) == msg.grouped_id:
                            album_messages.append(m)

                    # Сортируем по ID (в правильном порядке)
                    album_messages.sort(key=lambda x: x.id)

                    # Если в альбоме есть хотя бы одно видео — пропускаем весь альбом
                    if any(has_video_media(m) for m in album_messages):
                        print(f"[{source_name}] ID={msg.id} - альбом содержит видео, пропускаем объявление")
                        skipped_video_count += 1
                        per_source_stats[source.id]["skipped_video"] += 1
                        continue

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
                        grouped_message_ids.add(m.id)

                    # Если в альбоме менее 2 фото - пропускаем
                    if len(media_list) < 2:
                        print(f"[{source_name}] ID={msg.id} - менее 2 фотографий в альбоме, пропускаем")
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
                    if not formatted_text:
                        print(f"[{source_name}] ID={msg.id} - API недоступен, публикация пропущена")
                        failed_count += 1
                        failed_api_count += 1
                        per_source_stats[source.id]["failed"] += 1
                        continue

                    if media_list:
                        # Отправка фото/альбома
                        await client.send_file(
                            target,
                            file=media_list,
                            caption=formatted_text,
                            force_document=False
                        )
                        print(f"[{source_name}] - Опубликован альбом/фото ID={msg.id}")
                        # Помечаем все ID альбома как опубликованные
                        if msg.grouped_id:
                            posted_ids.add(make_group_key(source.id, msg.grouped_id))
                            for gid in grouped_message_ids:
                                posted_ids.add(make_message_key(source.id, gid))
                        else:
                            posted_ids.add(message_key)
                        save_posted_ids()
                        published_count += 1
                        per_source_stats[source.id]["published"] += 1
                    else:
                        # Использует markdown форматирование встроенное в Telethon
                        message_obj, entities = markdown.parse(formatted_text)
                        await client.send_message(target, message_obj, formatting_entities=entities)
                        print(f"[{source_name}] - Опубликован текст ID={msg.id}")
                        posted_ids.add(message_key)
                        save_posted_ids()
                        published_count += 1
                        per_source_stats[source.id]["published"] += 1

                except Exception as e:
                    error_type = type(e).__name__
                    print(
                        f"[{source_name}] Ошибка публикации ID={msg.id}, "
                        f"GROUP_ID={msg.grouped_id}, тип={error_type}: {e}"
                    )
                    print(f"[{source_name}] Трейсбек ошибки публикации:")
                    traceback.print_exc()
                    failed_count += 1
                    failed_send_count += 1
                    last_send_error = str(e)
                    per_source_stats[source.id]["failed"] += 1
                    continue

        if stop_batch_on_failure:
            print("Публикация батча остановлена из-за ошибки, чтобы не нарушить порядок объявлений")

        if not reached_known_in_any_source:
            print("Уже обработанных сообщений в проходе по всем источникам не найдено")

        print(
            f"Итог прохода: найдено новых={found_count}, "
            f"опубликовано={published_count}, пропущено_из-за_видео={skipped_video_count}, "
            f"ошибок_публикации={failed_count}"
        )

        if failed_count:
            print(
                f"Причины ошибок: api_генерация={failed_api_count}, "
                f"telegram_отправка={failed_send_count}"
            )
            if last_send_error:
                print(f"Последняя ошибка отправки: {last_send_error}")

        if per_source_stats:
            print("Статистика по источникам:")
            for source_stat in per_source_stats.values():
                print(
                    f" - [{source_stat['name']}] найдено={source_stat['found']}, "
                    f"опубликовано={source_stat['published']}, "
                    f"пропущено_из-за_видео={source_stat['skipped_video']}, "
                    f"ошибок_публикации={source_stat['failed']}"
                )

        if found_count == 0:
            print("Уведомление: новых сообщений не найдено")

        print(f"Ожидание {UPDATE_INTERVAL} секунд...")
        await asyncio.sleep(UPDATE_INTERVAL)

# ================== ТОЧКА ВХОДА ==================
if __name__ == "__main__":
    try:
        asyncio.run(fetch_and_post())
    except KeyboardInterrupt:
        print("Остановка по запросу пользователя (Ctrl+C)")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        traceback.print_exc()
    finally:
        wait_before_exit()
