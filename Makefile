.PHONY: venv deps compile migrate run check messages translations

venv:
	python3 -m venv .venv

deps:
	. .venv/bin/activate && python -m pip install --upgrade pip && python -m pip install -r requirements.txt

compile:
	. .venv/bin/activate && python -m compileall .

migrate:
	. .venv/bin/activate && python manage.py migrate

run:
	. .venv/bin/activate && python manage.py runserver

check:
	. .venv/bin/activate && python manage.py check

# Spanish catalog. Both need GNU gettext (macOS: brew install gettext).
# `messages` re-extracts strings into locale/es/LC_MESSAGES/django.po after
# template changes; `translations` compiles it to the .mo Django reads.
messages:
	. .venv/bin/activate && python manage.py makemessages -l es --ignore=.venv --ignore=staticfiles

translations:
	. .venv/bin/activate && python manage.py compilemessages -l es --ignore=.venv
