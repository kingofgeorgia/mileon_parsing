# Copilot Instructions for Telegram Auto Monitoring & Relay Project

## Project Overview
This is a **Telegram-based car marketplace monitoring and content relay system** built with Python. It monitors multiple Telegram car-selling channels, filters by brand/price criteria, parses listing data, and relays/republishes matching content to other channels.

### Three Main Components:
1. **TG_Parser.py** - Live monitoring dashboard: displays filtered car listings from multiple channels in real-time with Rich table UI
2. **parsing.py** - Relay client: automatically fetches messages from source channel, filters, formats, and republishes to target channel  
3. **live_moniitoring.py** - Integrated monitoring with FastAPI web API and Telegram bot integration for notifications

## Architecture & Data Flow
```
Telegram Channels (source) 
  ↓ (GetHistoryRequest via Telethon)
Channel Messages (raw)
  ↓ (match_filters: brand + price)
Filtered Messages
  ↓ (format_message: markdown + metadata)
Target Channel / Dashboard / API
```

**Key constraint:** Each module maintains a separate `client = TelegramClient()` instance with session names (relay_client, live_monitor). Sessions persist authentication across runs.

## Critical Patterns & Conventions

### Configuration at Top of File
All settings are hardcoded at module top:
- **api_id, api_hash** (Telegram API credentials - SAME across modules)
- **SOURCE/TARGET_CHANNEL** (channel names as strings, not IDs)
- **CAR_BRANDS, CURRENCIES** (filter lists)
- **PRICE_PATTERN** (regex: `\d[\d\s]{3,}` captures price with separators)
- **UPDATE_INTERVAL** (polling interval in seconds)

### Core Filtering Function
```python
def match_filters(text: str) -> bool:
    if not text: return False
    if not any(brand.lower() in text.lower() for brand in CAR_BRANDS): return False
    if not PRICE_PATTERN.search(text): return False
    return True
```
Used in all modules. Filters are **AND conditions**: brand AND price required.

### Telethon API Usage
```python
history = await client(GetHistoryRequest(
    peer=source,
    limit=20,           # Fixed: always 20 messages
    offset_id=0,        # Always fetch from latest
    offset_date=None,
    add_offset=0,
    max_id=0,
    min_id=0,
    hash=0
))
```
**Note:** All modules use identical GetHistoryRequest params. Messages are fetched newest-first; `reversed()` in **parsing.py** to process oldest-first.

### Message Deduplication
**parsing.py** maintains `posted_ids = set()` to avoid reposting. When adding relay logic, always check message IDs against local state.

### Async Architecture
All modules use `asyncio.run()` at entry point with while loops inside async functions. Multiple channels processed sequentially per iteration (loop inside async function, not concurrent tasks).

## Developer Workflows

### Running Modules
```powershell
python parsing.py         # Start relay client (background process)
python TG_Parser.py       # Start monitoring dashboard (interactive)
python live_moniitoring.py # Start integrated monitor + API
```

### Adding New Channels
1. Add channel name to CHANNELS list: `CHANNELS = ["mileoncars", "cars_europe"]`
2. Filtering logic applies automatically via `match_filters()`
3. Source/target channels specified separately (parsing.py uses SOURCE_CHANNEL, TG_Parser uses CHANNELS)

### Modifying Filters
- Edit **CAR_BRANDS** list (case-insensitive matching with `.lower()`)
- Edit **PRICE_PATTERN** regex (captures `\d[\d\s]{3,}` + currency symbols)
- Run module; filters apply on next poll cycle

### Updating Message Format
**parsing.py** format_message():
```python
formatted = f"🚗 **{brand}**\nЦена: {price}\n{message.text}\n\n📍 Источник: @{SOURCE_CHANNEL}"
```
All modules use markdown parse_mode. Preserve emoji + bold headers.

## External Dependencies
- **telethon** - Telegram client library (async-first)
- **rich** - Terminal UI library (for Live table displays)
- **fastapi** - Web framework (live_moniitoring.py only)
- **python-telebot** - Bot framework (live_moniitoring.py notification handler)

## Common Issues & Debugging
- **Session files (.session):** Deleted cached session → run module again to re-authenticate via QR code
- **GetHistoryRequest returns empty:** Channel may be private or access revoked; verify api_id/api_hash
- **Duplicate posts:** Add message ID to `posted_ids` set before retry
- **Telethon connection timeouts:** Module auto-retries; check internet + Telegram API status

## Code Style Notes
- Russian comments throughout (документация, настройки, фильтры sections)
- Configuration sections marked with `# ================== SECTION ==================`
- All regexes use raw strings: `r"pattern"`
- Message text accessed via `.text` attribute (handles None values with `or ""`)
