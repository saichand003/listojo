FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# psycopg2 needs libpq; gcc needed to compile it
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Install deps first (cached layer — only re-runs when requirements.txt changes)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy source
COPY . .

# Collect static files at build time
RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD python manage.py migrate --noinput && \
    gunicorn listojo.wsgi \
      --bind 0.0.0.0:$PORT \
      --workers 2 \
      --timeout 120 \
      --preload \
      --log-file -
