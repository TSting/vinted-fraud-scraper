FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Alleen essentiële build tools installeren als het echt nodig is
# We slaan apt-get update over als we geen extra packages nodig hebben
# maar voor sommige python libraries (Pillow etc) is zlib-dev handig.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Pip upgraden
RUN python -m pip install --no-cache-dir --upgrade pip

# Dependencies kopiëren en installeren met de nieuwe 'Safe requirements'
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Applicatie kopiëren
COPY . .

# Poort en start-commando
EXPOSE 8080
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "--timeout", "600", "--bind", ":8080", "app:app"]