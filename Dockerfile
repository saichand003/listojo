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

# NOTE: railway.json selects the DOCKERFILE builder, so THIS is the start
# command Railway runs. The Procfile is not used — keep it in sync if you like,
# but any change that must take effect on deploy belongs here.
#
# seed_downtowns / assign_downtowns are free (no API calls) and idempotent, so
# they run on every boot. fetch_groceries and fetch_schools are deliberately NOT
# here: they cost money per call and would bill on every deploy and restart.
# Their failure is caught so a seeding bug can never stop the web server.
CMD python manage.py migrate --noinput && \
    python manage.py createcachetable && \
    (python manage.py seed_downtowns && \
     python manage.py assign_downtowns --missing-only || \
     echo "WARN: downtown seed/assign failed - starting web anyway") && \
    gunicorn listojo.wsgi \
      --bind 0.0.0.0:$PORT \
      --workers 2 \
      --timeout 120 \
      --preload \
      --log-file -
