# MileON Telegram Relay

Автоматический релей объявлений из Telegram-канала с фильтрацией по марке/цене, генерацией текста через OpenAI и публикацией в целевой канал.

## Что делает скрипт

- Читает новые сообщения из `SOURCE_CHANNEL`
- Отбирает только объявления с маркой + ценой
- Обрабатывает фото/альбомы (видео пропускает)
- Формирует structured payload для OpenAI
- Генерирует финальный текст по шаблону MileON Cars
- Публикует в `TARGET_CHANNEL`
- Ведёт дедупликацию через `posted_ids.json`

## Текущая конфигурация

В `parsing.py` сейчас используются:

- `SOURCE_CHANNEL = "garageneva"`
- `TARGET_CHANNEL = "mileoncars"`
- `OPENAI_MODEL = "gpt-5-mini"` (зафиксировано)
- `UPDATE_INTERVAL = 20`

## Установка

```bash
pip install telethon openai currency-converter-free
```

## Настройка ключей

Скрипт берёт OpenAI-ключ в таком порядке:

1. Переменная окружения `OPENAI_API_KEY`
2. Файл `openai_api_key.txt` в корне проекта

Пример для PowerShell (текущая сессия):

```powershell
$env:OPENAI_API_KEY="your_key_here"
```

Или создайте файл `openai_api_key.txt`:

```text
your_key_here
```

## Запуск

```bash
python parsing.py
```

## Фоновый запуск без окна (Windows)

Чтобы скрипт работал в фоне и не показывал консольное окно, используй Task Scheduler.

1. Открой PowerShell **от имени администратора**
2. Выполни:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_hidden_task.ps1
```

Что будет сделано:

- установится скрытая задача `MileON-Parsing-Hidden`
- автозапуск при старте Windows и при входе пользователя
- запуск через `pythonw.exe` (без окна)
- автоперезапуск при падении
- логи в `logs/relay_background.log`

Проверка статуса задачи:

```powershell
Get-ScheduledTask -TaskName "MileON-Parsing-Hidden" | Get-ScheduledTaskInfo
```

Удаление задачи:

```powershell
Unregister-ScheduledTask -TaskName "MileON-Parsing-Hidden" -Confirm:$false
```

Быстрое управление задачей:

```powershell
# Интерактивное меню действий (без -Action)
powershell -ExecutionPolicy Bypass -File .\scripts\task_control.ps1

# Установка задачи
powershell -ExecutionPolicy Bypass -File .\scripts\task_control.ps1 -Action install

# Удаление задачи
powershell -ExecutionPolicy Bypass -File .\scripts\task_control.ps1 -Action uninstall

# Статус
powershell -ExecutionPolicy Bypass -File .\scripts\task_control.ps1 -Action status

# Запуск
powershell -ExecutionPolicy Bypass -File .\scripts\task_control.ps1 -Action start

# Остановка
powershell -ExecutionPolicy Bypass -File .\scripts\task_control.ps1 -Action stop

# Перезапуск
powershell -ExecutionPolicy Bypass -File .\scripts\task_control.ps1 -Action restart

# Последние строки лога
powershell -ExecutionPolicy Bypass -File .\scripts\task_control.ps1 -Action logs -Tail 80

# Диагностика (задача + процессы + ошибки в логе)
powershell -ExecutionPolicy Bypass -File .\scripts\task_control.ps1 -Action doctor
```

## Логика порядка публикации

- Новые сообщения сначала собираются до первого уже опубликованного
- Затем публикуются от старых к новым
- Если на объявлении возникает ошибка (API/отправка), текущий батч останавливается,
  чтобы не нарушить порядок и не пропустить старое объявление

## Dry-run скрипты

- `_dry_run_last_message.py` — тест последнего объявления без публикации и без сохранения ID
- `_dry_run_verbose.py` — подробный тест (raw text, sanitized text, payload, ответ API)

## Формат данных для OpenAI

В API передаётся JSON с полями:

- `brand`
- `model`
- `year`
- `engine_volume`
- `power`
- `drive`
- `mileage`
- `price_local`
- `price_russia`
- `currency`
- `extras`

Правило валют:

- `price_local` всегда передаётся в `USD`
- `price_russia` всегда передаётся в `RUB`
- если исходная цена в другой валюте, перед отправкой выполняется конвертация по актуальному курсу

## Важные файлы

- `parsing.py` — основной рабочий скрипт
- `posted_ids.json` — база уже опубликованных ID
- `openai_api_key.txt` — файл ключа OpenAI (опционально)

## Примечания

- Если `OPENAI_API_KEY` не найден, публикация не выполняется
- Сессии Telegram хранятся в `.session` файлах
- Для повторной авторизации можно удалить соответствующий `.session` файл
