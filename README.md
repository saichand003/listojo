# Listojo (Rich UI Marketplace MVP)

A Django + SQLite marketplace app inspired by local discovery apps like Sulekha.

Brand/domain: **listojo.com**

## Rich UI features included

- Modern card-based responsive layout.
- Homepage hero with KPI counters.
- Multi-filter search (keyword, category, city, sort).
- Category chips for quick exploration.
- Listing cards with image thumbnails and featured badges.
- Improved detail page layout (content + inquiry sidebar).
- Dark mode toggle with local preference persistence.
- Toast-style success messages.

## Product features

- User registration/login/logout.
- Post listings with category, location, contact phone, optional image and optional price.
- Featured listings.
- Inquiry form on listing detail.
- Direct user-to-user chat.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Or:

```bash
./run_local.sh
```

## Routes

- `/` Marketplace homepage
- `/post/` Create listing
- `/listing/<id>/` Listing detail + inquiry
- `/chat/` Chat inbox
- `/accounts/register/` Register
- `/accounts/login/` Login


## How to compile the latest code

Use one of the following:

### Option A: direct command
```bash
source .venv/bin/activate
python -m compileall .
```

### Option B: Makefile shortcut
```bash
make compile
```

This validates Python syntax by byte-compiling all project files.


## If you still see the old UI

1. Stop and restart the dev server.
2. Hard refresh your browser (`Cmd+Shift+R` on macOS).
3. Verify the footer shows `UI version: 2026-04-10-1`.
4. If needed, clear cached static files and restart:

```bash
find . -type d -name "__pycache__" -prune -exec rm -rf {} +
python manage.py runserver
```


## Security

See `SECURITY.md` for production hardening, encryption, and intrusion-resistance checklist.


## If you don't see latest changes in browser

Yes — after pulling new code you usually need to do a quick refresh workflow:

```bash
git pull
source .venv/bin/activate
python manage.py migrate
python manage.py runserver
```

Then in browser:
1. Hard refresh (`Cmd+Shift+R` on macOS / `Ctrl+F5` on Windows).
2. Open DevTools → Network → check **Disable cache** and reload once.
3. Confirm footer shows the latest `UI version` value.

If still stale, stop server and restart it from the same terminal where `.venv` is active.


## Test on your phone

### Option 1: Same Wi-Fi (fastest)
1. Connect laptop and phone to the same Wi-Fi.
2. Start Django on all interfaces:
   ```bash
   source .venv/bin/activate
   python manage.py runserver 0.0.0.0:8000
   ```
3. Find your laptop IP (macOS):
   ```bash
   ipconfig getifaddr en0
   ```
4. On phone browser open:
   ```
   http://<YOUR_LAPTOP_IP>:8000
   ```

If host validation blocks access, set env var before running:
```bash
export DJANGO_ALLOWED_HOSTS='127.0.0.1,localhost,<YOUR_LAPTOP_IP>'
python manage.py runserver 0.0.0.0:8000
```

### Option 2: Public tunnel (works outside Wi-Fi)
Use Cloudflare Tunnel or ngrok to expose local port 8000 securely for temporary testing.
