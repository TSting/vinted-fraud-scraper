FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# System build tools voor C/C++ extensions (madoka)
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080
ENV PORT=8080

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "--timeout", "600", "--bind", ":8080", "app:app"]