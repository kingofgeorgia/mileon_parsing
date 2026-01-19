# Telegram Auto Monitoring & Relay System

A Python-based Telegram monitoring and content relay system that automatically filters and republishes car listings across channels based on specified criteria.

## Features

- **Real-time Monitoring**: Live dashboard displaying filtered car listings from multiple Telegram channels
- **Automatic Filtering**: Smart filtering by car brand and price range
- **Content Relay**: Automatically fetch, format, and republish matched listings to target channels
- **Multiple Channels**: Monitor and relay from multiple source channels simultaneously
- **Web API Integration**: FastAPI-based REST API for programmatic access
- **Bot Notifications**: Telegram bot integration for real-time alerts
- **Session Persistence**: Maintains authentication sessions across runs

## Project Structure

### Components

1. **parsing.py** - Relay Client
   - Automatically fetches messages from source channels
   - Filters content by brand and price criteria
   - Formats and republishes to target channels
   - Maintains deduplication with message ID tracking

## Installation

### Prerequisites
- Python 3.8+
- Telegram account with API credentials
- OpenAI API key (optional, for advanced features)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/kingofgeorgia/mileon_parsing.git
cd mileon_parsing
```

2. Install dependencies:
```bash
pip install telethon rich fastapi python-telebot openai
```

3. Configure your API credentials in any module:
```python
api_id = YOUR_API_ID
api_hash = "YOUR_API_HASH"
```

Get your Telegram API credentials at [https://my.telegram.org/apps](https://my.telegram.org/apps)

## Configuration

Edit the configuration section at the top of each module:

```python
# Telegram API
api_id = 34277624
api_hash = "3906edabc2198a97d68878633496809d"

# Channels
SOURCE_CHANNEL = "mileoncars"
TARGET_CHANNEL = "garagesale_dighomi"

# Filtering
CAR_BRANDS = ["BMW", "Mercedes", "Toyota", "Audi", "Porsche"]
CURRENCIES = ["$", "€", "₽", "USD", "EUR"]

# Polling
UPDATE_INTERVAL = 20  # seconds
```

### Filter Configuration

- **CAR_BRANDS**: List of car brands to monitor (case-insensitive)
- **CURRENCIES**: Accepted currency symbols for price detection
- **PRICE_PATTERN**: Regex for price extraction (default: `\d[\d\s]{3,}`)

## Usage

### Run Relay Client
```bash
python parsing.py
```
Continuously monitors source channels and relays matching listings.

## Architecture

```
Telegram Channels (source)
  ↓ (GetHistoryRequest via Telethon)
Channel Messages (raw)
  ↓ (match_filters: brand + price)
Filtered Messages
  ↓ (format_message: markdown + metadata)
Target Channel / Dashboard / API / Notifications
```

### Data Flow

1. **Fetch**: Retrieve latest messages from source channels
2. **Filter**: Match against brand and price criteria (AND condition)
3. **Format**: Convert to markdown with metadata and emoji
4. **Relay**: Post to target channel or dashboard
5. **Deduplicate**: Track message IDs to prevent reposts

## Filtering Logic

Messages must match **both** conditions to be included:
- Contains one of the specified car brands
- Contains a price in the specified currency format

```python
def match_filters(text: str) -> bool:
    if not text:
        return False
    if not any(brand.lower() in text.lower() for brand in CAR_BRANDS):
        return False
    if not PRICE_PATTERN.search(text):
        return False
    return True
```

## Dependencies

```
telethon>=1.0        # Telegram client library
openai>=0.27         # OpenAI integration
```

## Session Management

Each module creates persistent session files:
- `relay_client.session` - Parsing client session
- `session_name.session` - Live monitor session

Sessions preserve authentication. Delete to force re-authentication on next run.

## Troubleshooting

### Session Authentication Issues
Delete the `.session` file and restart the module to re-authenticate via QR code.

### Empty Message History
- Verify channel is public/accessible
- Check API credentials (api_id, api_hash)
- Ensure account has channel access permissions

### Duplicate Posts
The relay client tracks posted message IDs in `posted_ids` set. Clear this to reprocess.

### Telethon Connection Timeouts
The module auto-retries. Check internet connection and Telegram API status.

### Filter Not Working
- Verify CAR_BRANDS contains correct brand names
- Check PRICE_PATTERN regex matches message prices
- Ensure filters use AND logic (both brand AND price required)

## Code Style

- Russian comments throughout (documentation sections)
- Configuration marked with section headers
- Raw strings for regex patterns: `r"pattern"`
- Message text safely accessed via `.text` attribute

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/improvement`)
3. Commit your changes (`git commit -am 'Add improvement'`)
4. Push to the branch (`git push origin feature/improvement`)
5. Open a Pull Request

## License

This project is provided as-is for personal use.

## Support

For issues and questions, open an issue on [GitHub](https://github.com/kingofgeorgia/mileon_parsing/issues).
