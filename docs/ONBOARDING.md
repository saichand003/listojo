# Listojo — Developer Onboarding (Day 1)

> Get the app running locally and understand the workflow. Assumes macOS/Linux.
> Pair this with `ARCHITECTURE.md` (systems) and `DATA_MODEL.md` (domain).

---

## 1. Prerequisites
- **Python 3.12+** (repo tested on 3.14)
- **Git**, and access to the GitHub repo
- (Optional) access to Railway, Google Cloud, Resend, Cloudflare — only needed
  for touching prod or testing live integrations

---

## 2. Clone & set up the environment
```bash
git clone <repo-url> listojo
cd listojo

# Create/activate a virtualenv (the project uses .venv)
python3 -m venv .venv
source .venv/bin/activate          # do this in every new terminal

pip install -r requirements.txt
```

## 3. Configure local secrets
Create a `.env` in the repo root (git-ignored). Minimum to boot:
```
DJANGO_DEBUG=true
DJANGO_SECRET_KEY=local-dev-key-does-not-matter
```
Add integration keys only if you're testing that feature (all fail-open):
```
GOOGLE_MAPS_API_KEY=...            # map rendering
GOOGLE_GEOCODING_API_KEY=...       # address → coords
# Email prints to the console locally unless you set Resend/SMTP vars
```
> Ask the lead for a copy of the dev `.env`. **Never commit `.env`.**

## 4. Database & run
Locally the app uses **SQLite** (no Postgres needed). Prod uses Postgres via
`DATABASE_URL` — the setting auto-switches.
```bash
python manage.py migrate
python manage.py createcachetable          # for rate-limit cache
python manage.py createsuperuser           # for /admin and the portal
python manage.py runserver                 # http://127.0.0.1:8000
```

## 5. Sanity checks
```bash
python manage.py check          # config sanity
python manage.py test           # test suite
```
Open:
- `http://127.0.0.1:8000/` — home
- `http://127.0.0.1:8000/listings/` — listings + map
- `http://127.0.0.1:8000/accounts/register/` — signup (email code prints to your terminal)
- `http://127.0.0.1:8000/admin/` — Django admin

---

## 6. How email/OTP works locally
With the **console email backend** (default when SMTP/Resend vars are unset),
every email — signup verification, login OTP, alerts — **prints to your
`runserver` terminal** instead of sending. Look for:
```
Your verification code is: 123456
```
Copy that into the confirm screen. This lets you test the full auth flow with no
email vendor configured.

---

## 7. Project layout (where things live)
```
listojo/            project config: settings, context_processors, email_backends, middleware
accounts/           auth, signup+verification, OTP, profile, twilio, security
  services/         login_otp, signup_otp, twilio_service, security
listings/           listings, communities, search, valuation, geocoding, alerts
  services/         search, matching, valuation, geocoding, saved_search_alerts, visibility
  management/commands/   geocode_listings, send_saved_search_alerts, fetch_walk_scores, ...
portal/             concierge/admin CRM (Lead→Shortlist→Agent)
chatapp/            in-app + guest messaging
templates/          all HTML
static/             CSS/JS/images
docs/               these docs
```

## 8. Everyday commands
| Task | Command |
|------|---------|
| Run server | `python manage.py runserver` |
| Make migrations | `python manage.py makemigrations` |
| Apply migrations | `python manage.py migrate` |
| Shell | `python manage.py shell` |
| Tests | `python manage.py test` |
| Prod-config check | `python manage.py check --deploy` |
| Test email | `python manage.py send_test_email you@x.com` |
| Geocode backfill | `python manage.py geocode_listings` |

## 9. Git & deploy workflow
- Work on a feature branch; open a PR against **`dangerously-allow-revamp`**.
- Merging/pushing to `dangerously-allow-revamp` **auto-deploys** via Railway.
- Migrations run automatically on deploy (Dockerfile `CMD`).
- Keep secrets out of commits; put them in Railway env vars.

## 10. Golden rules
1. **Secrets in env vars, never in code.** `.env` local-only, always git-ignored.
2. **Integrations fail open** — the app runs with any subset of keys configured.
3. **Don't edit applied migrations** — add new ones.
4. **Don't set `latitude/longitude` by hand** — the geocoding signal does it.
5. When stuck on a vendor, check `ARCHITECTURE.md` §4 for what to configure where.
