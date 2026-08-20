# Listojo — Architecture & Operations Guide

> Onboarding doc for engineers supporting Listojo. Covers system architecture,
> every third-party vendor and what to configure there, all environment
> variables, and common operational runbooks.

---

## 1. What Listojo is

A Django real-estate marketplace for the Dallas–Fort Worth (DFW) metro:
rentals, homes for sale, and multi-unit communities. Core differentiators are
**Guided Search** (intent-based lead capture) and a built-in **concierge/agent
CRM** (leads → shortlists → agents).

**Stack:** Django 5 · PostgreSQL · Gunicorn · WhiteNoise · Docker on Railway ·
Cloudflare R2 (media) · LightGBM (price valuation).

---

## 2. System architecture

```
                                   ┌─────────────────────────┐
                          DNS      │      Namecheap          │
                    (listojo.com)  │  nameservers + records  │
                                   └───────────┬─────────────┘
                                               │  A/CNAME → Railway
                                               │  MX/TXT/DKIM → Resend (email auth)
                                               ▼
  ┌──────────┐   HTTPS    ┌──────────────────────────────────────────────┐
  │ Browser  │──────────▶ │                 RAILWAY                        │
  │ (user)   │            │  ┌────────────────────────────────────────┐   │
  └──────────┘            │  │  listojo service (Docker / Gunicorn)   │   │
       │                  │  │  Django app  ── WhiteNoise (static)    │   │
       │                  │  └───────┬───────────────┬────────────────┘   │
       │                  │          │               │                    │
       │                  │          ▼               ▼                    │
       │                  │  ┌───────────────┐  ┌──────────────┐          │
       │                  │  │  Postgres     │  │ DB cache tbl │          │
       │                  │  │  (managed)    │  │ (rate limits)│          │
       │                  │  └───────────────┘  └──────────────┘          │
       │                  │  ┌────────────────────────────────────────┐   │
       │                  │  │  listojo-cron (optional 2nd service)   │   │
       │                  │  │  send_saved_search_alerts (scheduled)  │   │
       │                  │  └────────────────────────────────────────┘   │
       │                  └───────────────────┬────────────────────────────┘
       │                                      │  outbound HTTPS (443)
       │  static assets / user media          │
       ▼                                      ▼
  ┌───────────────┐        ┌──────────────────────────────────────────────┐
  │ Cloudflare R2 │        │            THIRD-PARTY APIs                    │
  │ (listing imgs)│        │  • Resend        — transactional email (HTTP) │
  └───────────────┘        │  • Google Maps   — map JS (browser)           │
                           │  • Google Geocode— address → lat/lng (server) │
                           │  • Google OAuth  — social login               │
                           │  • Cloudflare    — Turnstile CAPTCHA          │
                           │    Turnstile                                  │
                           │  • Twilio        — phone OTP + SMS (optional) │
                           └──────────────────────────────────────────────┘

  Source control + CI:  GitHub (branch: New-MVP-PartnerPortal) ──▶ Railway auto-deploy
```

### Request lifecycle (typical page)
1. Browser → `https://listojo.com` → Cloudflare/Namecheap DNS → Railway
2. Gunicorn → Django → Postgres (data), R2 (media URLs), WhiteNoise (CSS/JS)
3. Browser-side: Google Maps JS draws the map; Turnstile runs on auth forms
4. Server-side (as needed): Geocoding, Resend email, Twilio SMS, OAuth

---

## 3. Django apps (code layout)

| App | Responsibility |
|-----|----------------|
| `listings` | Listings, communities/floor-plans/units, search, ML valuation, geocoding, saved-search alerts |
| `accounts` | Auth, signup + email verification, login OTP, device trust, profile, Twilio, security (rate-limit/CAPTCHA) |
| `portal` | Concierge/admin CRM — Lead → Shortlist → Agent routing (superuser/agent only) |
| `partners` | Partner organizations, memberships, management assignments, feed provenance, and the Listojo Partners portal |
| `chatapp` | In-app + guest messaging |
| `listojo` | Project config: `settings.py`, `context_processors.py`, `email_backends.py`, middleware |

Key service modules:
- `listings/services/` — `search`, `matching`, `valuation`, `geocoding`, `saved_search_alerts`, `visibility`
- `accounts/services/` — `login_otp`, `signup_otp`, `twilio_service`, `security`
- `listojo/email_backends.py` — **Resend HTTP-API backend** (bypasses blocked SMTP ports)

---

## 4. Third-party vendors — what to configure at each

> Golden rule: **all credentials live in Railway env vars, never in code.**
> `.env` is git-ignored and only for local dev.

### 4.1 Railway — hosting & deploy
- **What it runs:** the `listojo` Docker service (Gunicorn) + managed **Postgres**.
- **Configure:**
  - **Settings → Source:** GitHub repo, branch = `New-MVP-PartnerPortal`.
  - **Variables:** all env vars (see §5).
  - **Networking:** custom domains `listojo.com`, `adminportal.listojo.com`.
  - Deploys auto-trigger on push. Dockerfile `CMD` runs `migrate` +
    `createcachetable` + `seed_downtowns` + `assign_downtowns` + Gunicorn.
  - **The Dockerfile `CMD` is the start command — the Procfile is NOT used**
    (railway.json selects the DOCKERFILE builder). Editing the Procfile alone
    has no effect on deploys.
- **Optional 2nd service `listojo-cron`:** same repo, **Cron Schedule**
  `0 14 * * *`, **Start Command** `python manage.py send_saved_search_alerts`.
  Needs the same env vars (DB + Resend).

### 4.2 Namecheap — domain & DNS
- **What:** registrar + DNS for `listojo.com` (Namecheap BasicDNS).
- **Configure (Advanced DNS → Host Records):**
  - `A`/`CNAME` records pointing the domain to Railway (from Railway's DNS panel).
  - **Resend email-auth records** (see 4.4): MX + SPF + DKIM.
  - Existing `www → https://listojo.com` redirect.

### 4.3 Google Cloud — Maps, Geocoding, OAuth
One Cloud project holds three products. **APIs & Services → Credentials.**
- **Browser Maps key** (`GOOGLE_MAPS_API_KEY`): Maps JavaScript API enabled;
  **HTTP-referrer** restricted to `https://listojo.com/*`, `https://www.listojo.com/*`, `http://127.0.0.1:8000/*`.
- **Server Geocoding key** (`GOOGLE_GEOCODING_API_KEY`): Geocoding API enabled;
  **API-restricted to Geocoding only**, **no** referrer restriction (server calls
  have no referrer). Must be a *separate* key from the browser one.
- **OAuth client** (`GOOGLE_OAUTH_CLIENT_ID/SECRET`): Web application; Authorized
  redirect URIs `https://listojo.com/accounts/google/login/callback/` and the
  `127.0.0.1:8000` equivalent. Consent screen must be Published (or add testers).
- **Billing:** must be **active on the project** or Maps shows a "for development
  only" watermark and Geocoding returns `REQUEST_DENIED`.

### 4.4 Resend — transactional email
- **What:** all outbound email (OTP, saved-search alerts, inquiry notifications).
  Sent via the **HTTP API** (`ResendEmailBackend`) because Railway blocks SMTP ports.
- **Configure:**
  - **API Keys →** create key → `EMAIL_HOST_PASSWORD` / `RESEND_API_KEY`.
  - **Domains → Add `listojo.com`** → copy the MX/SPF/DKIM records into Namecheap
    (4.2). Until verified, Resend only delivers to your Resend account email.
  - After verified, `DEFAULT_FROM_EMAIL=Listojo <noreply@listojo.com>`.
  - `EMAIL_BACKEND=listojo.email_backends.ResendEmailBackend`.

### 4.5 Cloudflare Turnstile — bot/CAPTCHA
- **What:** CAPTCHA on signup + adaptive CAPTCHA on login (after failed attempts).
  Fail-open: disabled cleanly when keys are absent.
- **Configure:** dash.cloudflare.com → **Turnstile → Add site** (`listojo.com`) →
  copy Site Key + Secret Key → `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`.

### 4.6 Cloudflare R2 — media storage
- **What:** stores listing/community/floor-plan images (Django `STORAGES` → S3-compat).
- **Configure:** R2 bucket + API token → set `R2_*` vars (see §5). Static files are
  served by WhiteNoise from the container, **not** R2 — R2 is user-uploaded media only.

### 4.7 Twilio — phone OTP + SMS (optional)
- **What:** SMS fallback for login OTP + phone verification (progressive gates).
  Fail-open: SMS features no-op until configured.
- **Configure:** Console → Account SID + Auth Token; **Verify → create Service**
  (`VA...`) for OTP; buy a phone number for `TWILIO_SMS_FROM` (SMS alerts only —
  Verify OTP doesn't need a number). Set `TWILIO_*` vars.

### 4.8 GitHub — source & CI
- Repo hosts the code; Railway watches the `New-MVP-PartnerPortal` branch and
  auto-deploys on push. Keep secrets out of commits.
  (Verified 2026-08-18 against the live site: `dangerously-allow-revamp` is
  stale and several commits behind. Re-check here if a deploy ever appears to
  ship nothing.)

---

## 5. Environment variables reference

Set on **Railway → `listojo` service → Variables** (and locally in `.env`).

### Core / Django
| Var | Example | Notes |
|-----|---------|-------|
| `DJANGO_SECRET_KEY` | (50+ random chars) | **Must be strong in prod.** |
| `DJANGO_DEBUG` | `false` | `false` in prod (enables all hardening). |
| `DJANGO_ALLOWED_HOSTS` | `listojo.com,www.listojo.com,adminportal.listojo.com` | |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://listojo.com,https://adminportal.listojo.com` | |
| `DATABASE_URL` | (Railway Postgres ref) | Auto-provided by Railway Postgres. |
| `SITE_URL` | `https://listojo.com` | Used in email links. |

### Email (Resend)
| Var | Value |
|-----|-------|
| `EMAIL_BACKEND` | `listojo.email_backends.ResendEmailBackend` |
| `RESEND_API_KEY` / `EMAIL_HOST_PASSWORD` | `re_...` |
| `DEFAULT_FROM_EMAIL` | `Listojo <noreply@listojo.com>` |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_USE_TLS` / `EMAIL_TIMEOUT` | SMTP fallback values (unused by HTTP backend) |

### Google
| Var | Notes |
|-----|-------|
| `GOOGLE_MAPS_API_KEY` | Browser key (referrer-restricted). |
| `GOOGLE_GEOCODING_API_KEY` | Server key (API-restricted, no referrer). |
| `GOOGLE_PLACES_API_KEY` | Server key with **Places API (New)** enabled — nearby grocery chains. Falls back to the geocoding key, then the browser key. |
| `GOOGLE_ROUTES_API_KEY` | Server key with **Routes API** enabled — drive times. Falls back through the Places, geocoding and browser keys. |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | Social login. |

### Neighborhood data
All three are optional. An absent key disables its feature cleanly: nothing is
stored and the card hides itself, rather than erroring.

| Var | Notes |
|-----|-------|
| `WALKSCORE_API_KEY` | walkscore.com/professional/api — walk / transit / bike scores. |
| `GREATSCHOOLS_API_KEY` | greatschools.org/api. **Note:** the 1-10 rating and themed ratings shown on the school card need the Enterprise Data License, not the self-serve NearbySchools plans. |
| `GOOGLE_PLACES_API_KEY` | See Google above — used by `fetch_groceries`. |

Nearest-downtown needs no key at all: it is local maths over the curated
`Downtown` table (`seed_downtowns`, then `assign_downtowns`).

Transit and the Commute Score need no key either, and make no API call at any
point. Stations, lines and service frequency come from agency **GTFS** feeds —
static zips published under an open licence — imported by `import_gtfs` into
`TransitAgency` / `TransitRoute` / `TransitStation`. `fetch_transit` then matches
listings against that table with local maths and computes the score.

Every stop with weekday service is imported (~9,200 rows for DART + CapMetro).
The card shows rail and bus in separate sections, each listing the nearest stops
by distance — one row per route, so the two poles of an intersection do not
appear twice.

Service frequency is **not** part of the score or the card. Only distance and
mode are. Trip counts are still computed at import, but solely to drop stops
with no weekday service at all; `trips_per_weekday` and `TransitRoute.is_frequent`
are retained as admin-visible reference and affect nothing that renders. The feed URL
lives on `TransitAgency` and is editable in admin, so a moved feed is not a
deploy. Seeded agencies: DART (which also carries the TRE, putting Fort Worth on
the map) and CapMetro.

The **Commute Score** replaces Walk Score's Transit Score on the listing page.
The `transit_score` column is still fetched and stored — it is licensed data we
already pay for, and dropping the fetch would make it expensive to restore — it
is simply no longer rendered. See `Listing.walk_score_rows`.

### Bot protection (Turnstile)
| Var | Notes |
|-----|-------|
| `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` | Fail-open if unset. |

### Media (Cloudflare R2)
| Var | Notes |
|-----|-------|
| `R2_BUCKET_NAME` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_ENDPOINT_URL` / `R2_PUBLIC_DOMAIN` | S3-compatible media storage. |

### Twilio (optional)
| Var | Notes |
|-----|-------|
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | Account creds. |
| `TWILIO_VERIFY_SERVICE_SID` | `VA...` for OTP. |
| `TWILIO_SMS_FROM` | `+1...` for SMS alerts. |

### Other
| Var | Notes |
|-----|-------|
| `LAUNCH_ACTIVE` | Launch/waitlist gating flag. |

**Feature toggles are automatic:** each integration checks whether its keys are
present and **fails open** (feature hidden/skipped) when they're not. So the app
runs with any subset configured.

---

## 6. Deployment

- **Trigger:** push to `New-MVP-PartnerPortal` → Railway rebuilds the Docker image.
- **On boot** (Dockerfile `CMD`): `migrate --noinput` → `createcachetable` →
  `seed_downtowns` → `assign_downtowns --missing-only` → Gunicorn (2 workers,
  preload, 120s timeout). The two proximity commands are free (no API calls)
  and idempotent; their failure is caught so it cannot stop the web server.
- **Not on boot, by design:** `fetch_groceries`, `fetch_schools` and
  `fetch_drive_times` cost money per API call and would bill on every deploy and
  restart. `import_gtfs` is free but downloads 8-15 MB per agency, which is not
  something to repeat on every container restart. Run them manually in the
  Railway console, or add a cron service like `listojo-cron` above.

  Order matters across the whole proximity pipeline:

  ```
  geocode_listings
    → assign_downtowns → fetch_groceries → import_gtfs → fetch_transit
    → fetch_drive_times
    → fetch_transit --score-only
  ```

  `fetch_drive_times` only fills in times for places the earlier commands have
  already matched. The trailing `--score-only` pass exists because the downtown
  drive is one of the Commute Score's three components, and `fetch_drive_times`
  is what produces it — scoring before that runs leaves the component at zero.

  Cadence: `import_gtfs` quarterly (agencies republish every few weeks, but the
  station list barely moves), then `fetch_transit`. No `--force` needed: a
  listing whose match predates the newest import counts as stale automatically,
  so re-running the pair is always sufficient.
- **Static:** collected at build time, served by WhiteNoise.
- **Rollback:** Railway → Deployments → redeploy a previous successful build.

### Local dev
```bash
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver          # http://127.0.0.1:8000
```
Email prints to the console locally (console backend) unless SMTP/Resend vars are set.

---

## 7. Runbooks

| Task | How |
|------|-----|
| **Add/change a secret** | Railway → `listojo` → Variables → save → auto-redeploys. |
| **Rotate a leaked key** | Revoke at the vendor, issue a new one, update the Railway var, redeploy. |
| **Test email delivery** | `python manage.py send_test_email you@x.com` (Railway Console). |
| **Backfill geocoding** | `python manage.py geocode_listings` |
| **Send alerts manually** | `python manage.py send_saved_search_alerts` |
| **Import partner CSV** | `python manage.py import_partner_csv <org-slug> file.csv` (add `--dry-run` first) |
| **Hand a property to a new PM** | `partners.models.transfer_management(community, to_organization=org)` |
| **Check prod security** | `python manage.py check --deploy` |
| **DB shell** | Railway → Postgres → Connect. |

---

## 8. Security posture (summary)

- HTTPS + HSTS(1yr, preload), Secure+HttpOnly cookies, nosniff, X-Frame DENY.
- Django ORM (no raw SQL), auto-escaping, CSRF on — SQLi/XSS/CSRF covered.
- Auth: signup email verification, login OTP (email + Twilio SMS fallback),
  opt-in 30-day device trust, per-IP rate limiting (login/signup/resend),
  adaptive Turnstile, PKCE OAuth.
- Admin/portal: `is_superuser`-gated custom decorator.
- **Known follow-ups:** OTP on admin login; rate-limit `bulk_message_landlords`,
  inquiry, and guest chat; add a Content-Security-Policy header.

See the security review notes for the prioritized list.
