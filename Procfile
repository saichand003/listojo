web: python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn listojo.wsgi --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --log-file -
