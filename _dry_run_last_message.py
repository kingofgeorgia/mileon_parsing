import asyncio
import parsing
from telethon import TelegramClient


async def main():
    test_client = TelegramClient("session_name", parsing.api_id, parsing.api_hash)
    await test_client.start()
    source = await test_client.get_entity(parsing.SOURCE_CHANNEL)

    messages = await test_client.get_messages(source, limit=100)

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
        print("DRY_RUN: объявление не найдено в последних 100 сообщениях")
        await test_client.disconnect()
        return

    text = selected.message or (selected.media.caption if (selected.media and hasattr(selected.media, "caption")) else "")
    brand = next((b for b in parsing.CAR_BRANDS if b.lower() in text.lower()), "—")

    print(f"DRY_RUN: message_id={selected.id}, grouped_id={selected.grouped_id}")
    print("DRY_RUN: публикация отключена, ID не сохраняется")

    formatted = parsing.format_message(text, brand)
    if formatted:
        print("DRY_RUN_RESULT: API_OK")
        print("----- BEGIN FORMATTED TEXT -----")
        print(formatted)
        print("----- END FORMATTED TEXT -----")
    else:
        print("DRY_RUN_RESULT: API_UNAVAILABLE")

    await test_client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
