.PHONY: venv deps compile migrate run check

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
