import asyncio
import sqlite3
from io import BytesIO

from telethon import TelegramClient

import parsing


async def publish_latest_once() -> None:
    client = TelegramClient("session_name_dryrun", parsing.api_id, parsing.api_hash)

    for attempt in range(1, parsing.SESSION_LOCK_RETRIES + 1):
        try:
            await client.start()
            break
        except sqlite3.OperationalError as e:
            if "database is locked" not in str(e).lower() or attempt == parsing.SESSION_LOCK_RETRIES:
                raise
            wait_seconds = parsing.SESSION_LOCK_RETRY_DELAY * attempt
            print(
                "Сессия занята другим процессом "
                f"(попытка {attempt}/{parsing.SESSION_LOCK_RETRIES}), повтор через {wait_seconds} сек..."
            )
            await asyncio.sleep(wait_seconds)

    try:
        source_entities = [await client.get_entity(channel) for channel in parsing.SOURCE_CHANNELS]
        target = await client.get_entity(parsing.TARGET_CHANNEL)

        latest = None
        latest_source = None
        for source in source_entities:
            async for candidate in client.iter_messages(source, limit=50):
                if parsing.has_video_media(candidate):
                    continue

                candidate_text = candidate.message or (
                    candidate.media.caption if (candidate.media and hasattr(candidate.media, "caption")) else ""
                )
                if not candidate_text:
                    continue

                if latest is None:
                    latest = candidate
                    latest_source = source
                    break

                candidate_date = getattr(candidate, "date", None)
                latest_date = getattr(latest, "date", None)
                if candidate_date and latest_date and candidate_date > latest_date:
                    latest = candidate
                    latest_source = source
                break

        if latest is None or latest_source is None:
            print("PUBLISH_RESULT: Не найдено сообщений в источниках")
            return

        source_name = getattr(latest_source, "username", None) or getattr(latest_source, "title", str(latest_source.id))

        media_list = []
        grouped_message_ids = set()

        base_text = latest.message or (latest.media.caption if (latest.media and hasattr(latest.media, "caption")) else "")
        all_text = base_text

        if latest.grouped_id:
            album_messages = []
            async for message in client.iter_messages(latest_source, limit=100):
                if getattr(message, "grouped_id", None) == latest.grouped_id:
                    album_messages.append(message)

            album_messages.sort(key=lambda item: item.id)

            if any(parsing.has_video_media(message) for message in album_messages):
                print(
                    f"PUBLISH_RESULT: Последний альбом содержит видео, публикация отменена "
                    f"(source={source_name}, group_id={latest.grouped_id})"
                )
                return

            for message in album_messages:
                message_text = message.message or (
                    message.media.caption if (message.media and hasattr(message.media, "caption")) else ""
                )
                if message_text and message_text != base_text:
                    all_text = message_text

                if message.media:
                    buffer = BytesIO()
                    await client.download_media(message, file=buffer)
                    buffer.seek(0)
                    buffer.name = "photo.jpg"
                    media_list.append(buffer)

                grouped_message_ids.add(message.id)

            if len(media_list) < 2:
                print(
                    f"PUBLISH_RESULT: В последнем альбоме менее 2 фото, публикация отменена "
                    f"(source={source_name}, group_id={latest.grouped_id})"
                )
                return
        else:
            if latest.media:
                buffer = BytesIO()
                await client.download_media(latest, file=buffer)
                buffer.seek(0)
                buffer.name = "photo.jpg"
                media_list.append(buffer)

        brand = parsing.detect_brand(all_text or "") or "—"
        formatted_text = parsing.format_message(all_text, brand)
        if not formatted_text:
            print("PUBLISH_RESULT: Генерация текста не удалась (OpenAI недоступен или пустой ответ)")
            return

        if media_list:
            await client.send_file(
                target,
                file=media_list,
                caption=formatted_text,
                force_document=False,
            )
        else:
            message_obj, entities = parsing.markdown.parse(formatted_text)
            await client.send_message(target, message_obj, formatting_entities=entities)

        parsing.posted_ids = parsing.load_posted_ids()
        message_key = parsing.make_message_key(latest_source.id, latest.id)
        parsing.posted_ids.add(message_key)

        if latest.grouped_id:
            parsing.posted_ids.add(parsing.make_group_key(latest_source.id, latest.grouped_id))
            for gid in grouped_message_ids:
                parsing.posted_ids.add(parsing.make_message_key(latest_source.id, gid))

        parsing.save_posted_ids()

        print(
            f"PUBLISH_RESULT: OK | source={source_name} | "
            f"message_id={latest.id} | grouped_id={latest.grouped_id} | media_count={len(media_list)}"
        )
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(publish_latest_once())
