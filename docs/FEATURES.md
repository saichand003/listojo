# Listojo — Feature Flows

> How the major flows work end-to-end, with the files involved. For systems see
> `ARCHITECTURE.md`; for models see `DATA_MODEL.md`.

---

## 1. Guided Search (the USP)
Intent-based wizard that captures what a user wants and produces ranked matches +
a lead.
- **Flow:** `/search/guided/` wizard → POST → creates/updates a `Lead` +
  `LeadPreference`, saves a `SavedSearch` (for logged-in users), redirects to
  `/listings/?fmm=1&...` with "Find My Match" ranking.
- **Files:** `listings/views.py::guided_search`, `templates/listings/guided_search.html`,
  `listings/services/search.py`, `listings/services/matching.py`,
  `portal/services/lead_service.py`.
- **Ranking:** rule-based tag/criteria scoring today (`matching.py`). Event data
  for a learned ranker is logged in `UserListingEvent` (not yet wired to ML).

## 2. Search, filters & map view
- **List:** `/listings/` with category/city/price/tag filters; AJAX grid refresh.
- **Map (Airbnb-style):** toggle → sticky Google Map, list scrolls with the page,
  price pins from **real lat/lng**, "search as you move" ready. Falls back to
  city-centroid jitter only for un-geocoded rows.
- **Files:** `listings/views.py::listing_list`, `listings/services/search.py`,
  `templates/listings/listing_list.html`, `_listings_grid.html`.

## 3. Geocoding (real coordinates)
- Address → lat/lng via **Google Geocoding** on save (a `pre_save` signal), stored
  on `Listing`/`Community`. Only re-geocodes when the address changes.
- **Files:** `listings/services/geocoding.py`, `listings/signals.py`,
  `listings/management/commands/geocode_listings.py` (backfill).
- **Config:** `GOOGLE_GEOCODING_API_KEY` (server key). "Use my location" reverse-
  geocodes the browser position → served-market check → DFW fallback + waitlist.

## 4. Signup with email verification (anti-fake-account)
No `User` row is created until the email is proven.
- **Flow:** `/accounts/register/` form (first/last name, username, email, password)
  → Turnstile + rate-limit checks → pending signup held in **session** → 6-digit
  code emailed → `/accounts/register/confirm/` → correct code → **account created +
  logged in**.
- **Files:** `accounts/views.py::register / register_confirm`,
  `accounts/services/signup_otp.py`, `accounts/services/security.py`,
  `templates/accounts/register.html`, `register_confirm.html`.

## 5. Login OTP + device trust ("Confirm it's you")
Password logins step up to an email code (Google logins skip it — already verified).
- **Flow:** username+password → (rate limit + adaptive CAPTCHA) → validated →
  **not logged in yet** → email OTP → `/accounts/login/confirm/` → correct code →
  logged in. "Trust this device for 30 days" (opt-in, unchecked by default) sets a
  signed cookie that skips OTP on that browser.
- **Fallback:** "Try another way" sends the code via **Twilio SMS** to a verified phone.
- **Files:** `accounts/views.py::user_login / login_confirm`,
  `accounts/services/login_otp.py`, `templates/registration/login.html`,
  `login_confirm.html`.

## 6. Phone verification + progressive gates
Users verify a phone only at high-value moments (not at signup).
- **Where gated:** contacting a landlord (chat/inquiry), posting a listing.
  Verified phone powers the "Verified Owner" badge.
- **Fail-open:** all gates pass through when Twilio isn't configured.
- **Files:** `accounts/services/twilio_service.py`,
  `templates/includes/phone_verify_gate.html`, `accounts/views.py` (send/verify).
- **Config:** `TWILIO_ACCOUNT_SID/AUTH_TOKEN/VERIFY_SERVICE_SID` (+ `SMS_FROM` for alerts).

## 7. Google social login
- **allauth** with PKCE; auto-links to an existing same-email account and
  backfills first/last name from Google on every login.
- **Files:** `accounts/adapters.py::SocialAccountAdapter`, `listojo/settings.py`
  (allauth config), `templates/includes/google_login_button.html`.
- **Config:** `GOOGLE_OAUTH_CLIENT_ID/SECRET` + redirect URI in Google Cloud.

## 8. Bot / abuse protection
- **Turnstile CAPTCHA:** on signup; **adaptive** on login (only after 3 failed
  attempts). Fail-open without keys.
- **Rate limiting:** per-IP via DB cache — login (10/15min), signup (5/hr),
  resend (5/10min).
- **Files:** `accounts/services/security.py`, `listojo/settings.py` (CACHES).
- **Config:** `TURNSTILE_SITE_KEY/SECRET_KEY`.

## 9. Saved-search alerts (retention loop)
New listings matching a saved search are emailed (+ SMS) on a schedule.
- **Flow:** guided search saves a `SavedSearch` → scheduled command finds new
  matches since `last_alerted_at` → sends a digest via each user's channels →
  advances the watermark (each listing alerted once).
- **Files:** `listings/services/saved_search_alerts.py`,
  `listings/management/commands/send_saved_search_alerts.py`,
  `listojo/services/notifications.py::notify_user`.
- **Ops:** run `send_saved_search_alerts` on a Railway cron (e.g. daily `0 14 * * *`).

## 10. Messaging
- **In-app chat:** registered user ↔ owner about a listing (`ChatMessage`), polled.
- **Guest chat:** non-registered visitor → owner (`GuestChatMessage`).
- **Bulk outreach:** Saved Listings page → message multiple landlords (Zumper-style
  fan-out via `ChatMessage`).
- **Files:** `chatapp/views.py`, `listings/views.py::bulk_message_landlords`.

## 11. Communities (multi-unit properties)
- Owners create a `Community` → add `FloorPlan`s → add `Unit`s. Community cards
  appear in discovery with "Check Availability" / "Tour" CTAs (→ leads).
- **Files:** `listings/community_views.py`, `templates/listings/*community*`.
- **Rules:** `docs/community_product_rules.md`.

## 12. Concierge / agent CRM (portal)
- **Flow:** leads (from guided search, inquiries, tours) → auto-assigned to the
  least-loaded agent → agent builds a `Shortlist` of listings → sends to the lead
  → tracks status to won/lost.
- **Access:** superuser/agent only (`portal_login_required` / `agent_login_required`).
- **Files:** `portal/views.py`, `portal/services/{routing,lead_service,shortlist_service,dashboard}.py`.
- **Subdomains:** `adminportal.listojo.com` → `/portal/` via `SubdomainPortalMiddleware`.

## 13. Price valuation (ML)
- LightGBM model estimates a price range/confidence for a listing.
- **Files:** `listings/services/valuation.py`,
  `listings/management/commands/train_valuation_model.py` (model at
  `listings/ml/valuation_model.pkl`).
- Returns `None` gracefully if the model isn't trained.

## 14. Partner inventory import (CSV)
- Property managers supply inventory as a CSV; every supply format normalizes
  into a canonical record before anything touches the database.
- **Files:** `listings/services/partner_import.py` (adapter interface +
  `CsvAdapter` + upsert), `listings/services/media.py` (photo fetch),
  `listings/management/commands/import_partner_csv.py`.
- **Template:** `docs/partner-csv-template.csv`.

**Two row shapes, selected per row by the `community_ref` column:**

| `community_ref` | Builds | Renders as |
|---|---|---|
| set | `Community` → `FloorPlan` → `Unit` | Community chip → floor plans → unit tables |
| empty | `Listing` | Standard listing card |

Community and floor-plan columns repeat on every unit row of the same property;
the importer de-duplicates. One file can carry both shapes — an operator with
apartment communities *and* scattered single-family rentals sends one CSV.

- **Identity:** communities resolve through `partners.SourceRecordMap`
  (`organization` + the partner's own `source_id`), units on
  `(community, source_unit_id)` (defaults to `unit_number`), standalone rows on
  `(organization, source_listing_id)`. Never on address — a partner reformatting
  an address must not duplicate inventory, and a property changing managers must
  not import twice.
- **Safe deactivation:** absent from one file marks *pending*; only a second file
  that also omits it retires the row (`Listing.status='closed'`,
  `Unit.status='withdrawn'`). A file omitting more than 30% of a partner's live
  rows aborts the whole run untouched.
- **`withdrawn` vs `occupied`:** a withdrawn unit drops out of
  `available_unit_count`, `price_range` and `bedroom_types`, so it leaves the
  community card cleanly without asserting someone moved in.
- **Adding a format** (XML/JSON/MITS) means one new `PartnerAdapter` subclass —
  the import, validation and deactivation logic is format-agnostic.

---

## Notification channels (shared)
`listojo/services/notifications.py::notify_user(user, subject, email_body, sms_body)`
sends across the channels a user opted into (`UserProfile.notify_email/notify_sms`).
Email greetings resolve **full name → email → username**. All email flows go
through Resend's HTTP-API backend.

## 15. Listojo Partners portal
- Partner-facing surface at `/partners/` (and `partners.listojo.com` via
  `SubdomainPortalMiddleware`). Access requires a `partners.Membership`, not a
  staff flag; superusers see all orgs for support.
- **Pages:** Portfolio (communities, standalone rentals, last-refreshed,
  rows pending deactivation), Upload inventory (preview → publish, with a
  per-row rejection table), Upload history, and "Help me connect" (blueprint §21
  assisted onboarding).
- **Files:** `partners/views.py`, `partners/forms.py`, `partners/urls.py`,
  `templates/partners/`.

### Ownership model
`Listing.owner` used to collapse three facts. They are now separate:

| Fact | Field |
|---|---|
| Who manages it | `Community.managed_by`, `Listing.organization` |
| Who may edit it | `partners.Membership` |
| Whose feed record it is | `partners.SourceRecordMap` |

- **Nothing CASCADEs from a person or company to inventory.** `owner` and
  `managed_by` are `SET_NULL`; `ManagementAssignment.organization` is `PROTECT`.
- **Handover:** `transfer_management()` closes the open `ManagementAssignment`,
  opens a new one, repoints `managed_by`, and clears `media_rights_confirmed` —
  display rights came from the previous partner's agreement (§14).
- **Feed authority:** a partner may only import into properties they currently
  manage, so a stale cron cannot overwrite the new manager's pricing.
- Authorization helpers live in `listings/services/ownership.py`. Native
  listings stay person-owned — individual landlords really do own theirs.
