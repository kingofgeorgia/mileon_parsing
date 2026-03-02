import asyncio
import json
import parsing
from telethon import TelegramClient

SYSTEM_INSTRUCTION = (
    "Ты маркетолог MileON Cars. Оформи автомобиль по фирменному MileON Cars шаблону на русском языке. "
    "Строго соблюдай структуру: 1) заголовок с маркой и моделью, 2) блок характеристик, 3) блок преимуществ, "
    "4) блок цены с добавкой +5% и округлением до 1000, 5) контакты и автоканал, 6) финальный продающий абзац. "
    "Если второй цены нет (price_russia = null), не пиши вторую цену. "
    "Используй только данные из JSON, null-поля пропускай."
)


async def main():
    print("STEP 1: Подключение к Telegram (только чтение, без постинга)")
    client = TelegramClient("session_name", parsing.api_id, parsing.api_hash)
    await client.start()
    source = await client.get_entity(parsing.SOURCE_CHANNEL)

    print("STEP 2: Получение последнего объявления")
    messages = await client.get_messages(source, limit=100)
    selected = None
    for msg in messages:
        text = msg.message or (msg.media.caption if (msg.media and hasattr(msg.media, "caption")) else "")
        if msg.media and text:
            selected = msg
            break

    if not selected:
        for msg in messages:
            text = msg.message or (msg.media.caption if (msg.media and hasattr(msg.media, "caption")) else "")
            if text:
                selected = msg
                break

    if not selected:
        print("RESULT: Объявление не найдено")
        await client.disconnect()
        return

    raw_text = selected.message or (selected.media.caption if (selected.media and hasattr(selected.media, "caption")) else "")
    print(f"- message_id={selected.id}")
    print(f"- grouped_id={selected.grouped_id}")

    print("STEP 3: Очистка текста перед API")
    safe_text = parsing.sanitize_text_for_ai(raw_text)
    parsing_text = safe_text if safe_text else raw_text
    info = parsing.parse_car_info(parsing_text)
    payload = parsing.build_ai_payload(info, safe_text)

    print("\n--- RAW TEXT (fragment) ---")
    print(raw_text[:1200])
    print("--- END RAW TEXT ---\n")

    print("--- SANITIZED TEXT (to API) ---")
    print(safe_text[:1200])
    print("--- END SANITIZED TEXT ---\n")

    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    print("STEP 4: Payload, который отправляется в API")
    print(payload_json)

    print("STEP 5: Запрос в OpenAI (без публикации, без сохранения ID)")
    if not parsing.openai_client:
        print("RESULT: OPENAI_API_KEY не задан")
        await client.disconnect()
        return

    try:
        response = parsing.openai_client.responses.create(
            model=parsing.OPENAI_MODEL,
            instructions=SYSTEM_INSTRUCTION,
            input=json.dumps(payload, ensure_ascii=False),
            max_output_tokens=1800,
        )

        response_dump = response.model_dump()
        print("\nSTEP 6: Сырой ответ API (ключевые поля)")
        print(json.dumps({
            "id": response_dump.get("id"),
            "status": response_dump.get("status"),
            "model": response_dump.get("model"),
            "output": response_dump.get("output"),
        }, ensure_ascii=False, indent=2))

        print("\nSTEP 7: Итоговый текст, который вернула модель")
        output_text = getattr(response, "output_text", None)
        if output_text:
            print(output_text)
        else:
            print("Пустой output_text")

    except Exception as e:
        print(f"RESULT: Ошибка API: {e}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
