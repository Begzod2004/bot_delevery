# Telegram Bot for Supplier Management

This bot helps manage supplier information and generate QR codes for products.

## Features

- Supplier registration with detailed information
- QR code generation for products
- Export data to Excel
- Admin panel for management
- Multi-language support (Russian/Uzbek)

## Requirements

- Python 3.8+
- SQLite3
- Required Python packages (see requirements.txt)

## Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd <repository-name>
```

2. Create virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Create .env file:

```
BOT_TOKEN=your_bot_token
ADMIN_IDS=admin_id1,admin_id2
```

## Running the Bot

1. Activate virtual environment:

```bash
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

2. Run the bot:

```bash
python src.py
```

## Deployment

### Using systemd (Linux)

1. Create service file:

```bash
sudo nano /etc/systemd/system/supplier-bot.service
```

2. Add service configuration:

```ini
[Unit]
Description=Supplier Management Telegram Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/bot
Environment=PATH=/path/to/bot/venv/bin
ExecStart=/path/to/bot/venv/bin/python src.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3. Enable and start service:

```bash
sudo systemctl enable supplier-bot
sudo systemctl start supplier-bot
```

### Using Docker

1. Create Dockerfile:

```dockerfile
FROM python:3.8-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "src.py"]
```

2. Build and run:

```bash
docker build -t supplier-bot .
docker run -d --name supplier-bot supplier-bot
```

## Monitoring

- Check logs: `tail -f bot.log`
- Monitor service: `systemctl status supplier-bot`

## Backup

Regular backups of the database and QR codes are recommended:

```bash
# Backup database
cp suppliers.db backup/suppliers_$(date +%Y%m%d).db

# Backup QR codes
cp -r qr_codes backup/qr_codes_$(date +%Y%m%d)
```

## Security

- Keep .env file secure and never commit it to version control
- Regularly update dependencies
- Monitor bot logs for suspicious activity
- Use strong passwords and API tokens
