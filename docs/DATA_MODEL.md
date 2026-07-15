# Listojo — Data Model

> The domain models and how they relate. Read this before touching queries,
> migrations, or the admin. Auth uses Django's built-in `User`; everything hangs
> off it.

---

## Entity-relationship overview

```
                          ┌────────────────┐
                          │  User (Django) │
                          └───┬───┬───┬──┬──┘
              1:1 profile ────┘   │   │  └──── owns ──────────┐
                                  │   │                        │
        ┌─────────────────────────┘   └──────────────┐        │
        ▼                                             ▼        ▼
  ┌───────────┐   1:N images   ┌────────────┐   ┌──────────────┐
  │  Listing  │───────────────▶│ListingImage│   │  Community   │
  │           │◀── parent(self)│            │   │              │
  └──┬──┬──┬──┘                └────────────┘   └──┬────────┬──┘
     │  │  │                                        │        │ 1:N images
     │  │  └── 1:N inquiries ▶ ListingInquiry       │        ▼
     │  │  └── N:N favourites ▶ Favourite ◀ User    │   CommunityImage
     │  └──── 1:N chat ▶ ChatMessage / GuestChat     │
     │                                               │ 1:N
     │                                               ▼
     │                                          ┌──────────┐  1:N  ┌──────┐
     │                                          │ FloorPlan│──────▶│ Unit │
     │                                          └──────────┘       └──────┘
     │
     │  (CRM — portal app)
     ▼
  ┌────────┐  1:N   ┌──────────────┐   1:N   ┌───────────────┐
  │  Lead  │───────▶│  Shortlist   │────────▶│ ShortlistItem │──▶ Listing
  │        │  1:1   └──────────────┘         └───────────────┘
  │        │──────▶ LeadPreference
  └────────┘  (assigned_agent → User; listing/community → source)

  SavedSearch (User 1:N)   UserListingEvent (analytics)   CityWaitlist   GuidedSearchEvent
```

---

## Core listing models (`listings/`)

### `Listing`
The central entity — a rental, property-for-sale, or roommate post.
- `owner` → User (`related_name='listings'`)
- `parent` → self (legacy child-unit link; new communities use the Community model)
- Key fields: `title, description, price, price_unit, category, address_line,
  city, state, zip_code, status, featured, bedrooms, bathrooms, square_footage,
  latitude, longitude, geocoded_address, expires_at, source_type, tags`
- `status`: `active, draft, on_hold, closed, pending, flagged, under_contract, sold`
- Visibility: only `status='active'` and non-expired listings are public
  (`listings/services/visibility.py::active_listings`).
- `latitude/longitude` are set by the **geocoding signal on save** (real coords).

### `ListingImage` — 1:N images for a Listing (`related_name='images'`)

### `Favourite` — User ↔ Listing many-to-many (saved listings)

### `ListingInquiry` — contact-form submissions on a listing (emails the owner)

---

## Community models (`listings/`)
Models a multi-unit property (apartment complex). **This is the supported
community workflow** — not `Listing.parent`.

```
Community ──1:N──▶ FloorPlan ──1:N──▶ Unit
    └──1:N──▶ CommunityImage
```
- `Community.owner` → User (`related_name='communities'`); has `latitude/longitude`
  (geocoded), `community_type`, amenities, `status`, `featured`.
- `FloorPlan` — bedroom/bath layout under a community.
- `Unit` — a rentable unit under a floor plan; `status` includes `available`.
- `Community.price_range` / `available_unit_count` aggregate over available units.

Business rules: see `docs/community_product_rules.md`.

---

## CRM models (`portal/`) — the concierge layer

### `Lead`
A captured prospect (from guided search, inquiry, chat, or manual entry).
- `assigned_agent` → User (round-robin via `portal/services/routing.py`)
- `listing` / `community` → the source that triggered the lead
- `status`: `new → contacted → shortlist_ready → shortlist_sent → touring →
  application_in_progress → closed_won / closed_lost`

### `LeadPreference` — 1:1 with Lead; city, budget, beds, amenities, urgency, income.

### `Shortlist` — an agent-curated set of listings for a Lead (`Lead 1:N Shortlist`).

### `ShortlistItem` — a Listing inside a Shortlist (`Shortlist 1:N ShortlistItem → Listing`).

Leads are created via `portal/services/lead_service.py::create_or_update_lead`,
called from guided search, inquiries, and community tour requests.

---

## Account & messaging models

### `UserProfile` (`accounts/`) — 1:1 with User
- `phone, phone_verified, notify_email, notify_sms`
- Auto-created by a `post_save` signal on User.
- Drives SMS eligibility (`can_sms`) and notification preferences.

### `ChatMessage` (`chatapp/`) — in-app message between two registered users about a listing.
- `sender` / `recipient` → User; `listing` → Listing (nullable).

### `GuestChatMessage` (`chatapp/`) — message from a non-registered visitor to an owner.

---

## Search & analytics models (`listings/`)

### `SavedSearch` — a user's saved guided search (unique per user+search_type).
- Fields mirror guided-search inputs: `city, max_budget, bedrooms, property_type,
  amenities, available_by, priority, urgency, monthly_income`.
- `alerts_enabled` + `last_alerted_at` power the saved-search alert digest.
- `as_url_params()` rebuilds the search URL; `summary_label()` for banners.

### `UserListingEvent` — event log for ranking/analytics
- Captures impressions/clicks with `search_id, rank_position, fmm_score, label,
  listing_features_snapshot` — training data for a learned ranker (not yet live).

### `CityWaitlist` — email captures for cities not yet served (from "Use my location").

### `GuidedSearchEvent` — funnel counters (guided search start/complete).

---

## Migrations & conventions
- All models use `BigAutoField` PKs.
- Geographic coords: `DecimalField(max_digits=9, decimal_places=6)`, indexed.
- Money: `DecimalField(max_digits=10, decimal_places=2)`.
- Never edit an applied migration; add a new one (`makemigrations`).
- `latitude/longitude/geocoded_address` on Listing & Community are populated by
  the geocoding `pre_save` signal — don't set them manually.
