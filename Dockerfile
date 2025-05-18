FROM python:3.8-slim

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p qr_codes data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Tashkent

# Run the bot
CMD ["python", "src.py"]