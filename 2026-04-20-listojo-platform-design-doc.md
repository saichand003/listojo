# Listojo Platform Design Doc
**Date:** 2026-04-20  
**Branch:** new_realestate_confined_version  
**Author:** saichand003  
**Status:** Active development — pre-launch, Irving/DFW focus

---

## What Listojo Is

Listojo is a classifieds and rental marketplace built for DFW — initially Irving/Las Colinas — that competes with Zillow and Craigslist by being free for small landlords, trusted for renters, and smarter than Facebook Marketplace. The core insight: small DFW landlords (1-5 self-managed units) can't afford Zillow's $300/month listing fees and don't trust Craigslist's spam and no-shows. Listojo is free, local, and adds trust through profiles, chat, and match scoring.

The platform covers rentals, roommates, properties for sale, local services, jobs, events, and buy/sell. Rentals and roommates are the launch wedge.

---

## Architecture Overview

**Stack:** Django 5.2, SQLite (dev) / PostgreSQL (prod), Python 3.x  
**Frontend:** Server-rendered Django templates, vanilla JS, no framework  
**Styling:** CSS custom properties, Sora + Montserrat fonts, mobile-first  
**Auth:** Django built-in auth, session-based  
**Storage:** Local `listing_images/` (dev), S3 in prod  
**Maps:** Google Maps Embed API  

```
classifieds_project/   # settings, urls, context_processors
accounts/              # user auth, profiles, agent dashboard
listings/              # core marketplace (Listing, Inquiry, Favourite, GuidedSearch)
chatapp/               # real-time messaging between users
portal/                # superuser-only admin dashboard
static/                # CSS, JS, images
templates/             # all HTML templates
```

### Key Models

| Model | App | Purpose |
|-------|-----|---------|
| `Listing` | listings | Core listing with category, price, location, status, view_count, bedrooms |
| `ListingImage` | listings | Multiple images per listing (ordered) |
| `ListingInquiry` | listings | Contact form submissions per listing |
| `Favourite` | listings | User saves a listing |
| `CityWaitlist` | listings | Email capture for cities not yet live |
| `GuidedSearchEvent` | listings | Funnel tracking: start/complete guided search |
| `ChatMessage` | chatapp | Messages between users about a listing, with `is_read` flag |
| `User` (Django built-in) | accounts | Auth, profile, is_superuser for portal access |

### Listing Status Flow

```
[User creates listing]
        ↓
    PENDING  ──→  (admin approves) ──→  ACTIVE  ──→  (admin flags) ──→  FLAGGED
        ↓                                                                    ↓
    DRAFT   ←── (admin rejects)                              (admin restores → ACTIVE
                                                              or deletes permanently)
```

---

## Features Inventory

### Marketplace (listings/)

| Feature | Status | Location |
|---------|--------|----------|
| Listing create / edit / delete | Done | `listings/views.py`, `templates/listings/create_listing.html` |
| Multiple image upload | Done | `ListingImage`, `validate_uploaded_images()` |
| Smart matching engine (FMM) | Done | `listings/views.py:_fmm_score()` |
| Category filtering + search | Done | `listings/views.py:listing_list()` |
| Guided search (multi-step intake) | Done | `listings/views.py:guided_search()`, `templates/listings/guided_search.html` |
| Google Maps embed per listing | Done | `settings.GOOGLE_MAPS_API_KEY` |
| View count tracking | Done | `Listing.view_count`, incremented on detail load (owner visits excluded) |
| Bedrooms field | Done | `Listing.bedrooms` (added 2026-04-20) |
| Favourites | Done | `Favourite` model, heart button on listing cards |
| City waitlist | Done | `CityWaitlist`, shown for non-DFW cities |
| Listing inquiry form | Done | `ListingInquiry`, email notification |
| Listing approval workflow | Done | Pending → admin review → Active or Draft |
| Featured listings | Done | `Listing.featured`, boosted in search order |
| Income qualifier (3× rent rule) | Done | `Listing.recommended_income()` shown on rental detail |
| Tags | Done | Comma-separated, shown as pills on detail page |

### User Accounts (accounts/)

| Feature | Status | Location |
|---------|--------|----------|
| Register / login / logout | Done | `accounts/views.py` |
| Unified profile page with tabs | Done | `templates/accounts/profile.html` |
| My Listings tab | Done | `accounts/views.py:my_listings()` |
| Inquiries overview | Done | `accounts/views.py:inquiries_overview()` |
| Performance page | Done | `accounts/views.py:performance()` |
| Agent dashboard | Done | `accounts/views.py:agent_dashboard()`, `templates/accounts/agent_dashboard.html` |

### Messaging (chatapp/)

| Feature | Status | Location |
|---------|--------|----------|
| Guest chat (no login required to message) | Done | `chatapp/views.py` |
| Inbox with conversation threads | Done | `chatapp/views.py:inbox()` |
| Unread message count | Done | `ChatMessage.is_read`, badge in sidebar |
| Mark as read on thread open | Done | `chatapp/views.py` |

### Admin Portal (portal/)

| Feature | Status | Location |
|---------|--------|----------|
| Superuser-only login | Done | `portal/views.py:portal_login()` |
| Dashboard with 8 KPI cards | Done | `templates/portal/dashboard.html` |
| Conversion funnel (5 steps) | Done | Views → Guided search → Intake → Contacted → Agent |
| Search intent breakdown | Done | Categories + bedroom sub-breakdown for rentals |
| Review queue (pending + flagged) | Done | Approve / Reject / Restore / Delete actions |
| Top listers table | Done | By total views, with listing count + inquiry count |
| Recent signups | Done | Last 6 users with Active/Staff badges |
| Listing quality alerts | Done | No photos, no tags, stale (14d < 3 views) |
| User management | Done | `portal/views.py:users_view()`, search, activate/deactivate |
| User detail page | Done | All listings by user with status |
| Listings management | Done | Filter by category/status, toggle featured, delete |
| Flag / Approve / Reject actions | Done | From both portal listings and dashboard review queue |

### Navigation + Shell (base.html / styles.css)

| Feature | Status | Notes |
|---------|--------|-------|
| Left sidebar (desktop) | Done | `.app-sidebar`, collapsible |
| Bottom tab bar (mobile) | Done | `.mob-nav` |
| Sidebar unread badge | Done | `sb_inquiry_count` via context processor |
| Portal dark sidebar | Done | `templates/portal/base.html`, `#0f1c35` bg |
| Sora / Montserrat fonts | Done | Google Fonts, loaded in both base templates |

---

## Data Flow: Conversion Funnel

The 5-step funnel in the portal dashboard maps to these real data points:

```
Visitors              → Listing.view_count aggregate (all listing page views)
Started guided search → GuidedSearchEvent(event_type='start') — logged on GET /search/guided/
Completed intake      → GuidedSearchEvent(event_type='complete') — logged on POST /search/guided/
Contacted a lister    → ListingInquiry.objects.values('email').distinct().count()
Connected to agent    → ChatMessage.objects.values('listing').distinct().count()
```

Each step shows a count and a % of the top-of-funnel (visitors). The bar uses a `warn` class (amber) when the step drops below 5% — matching the "Connected to agent" pattern in the mockup.

---

## Search Intent Breakdown Logic

The dashboard shows listing distribution by type. For rentals specifically, it tries to show a bedroom-level breakdown (Rentals — 1 bed, 2 bed, 3+ bed, Studios) when the `bedrooms` field has data. When no listings have bedrooms filled in, it falls back to showing Rentals as a single category. This auto-upgrades as users start filling in the bedrooms field on new listings.

Top searched area is computed as the city with the highest aggregate `view_count` across active listings.

---

## URL Map

```
/                          → Homepage (listing_list with FMM if logged in)
/listings/<pk>/            → Listing detail (increments view_count)
/listings/create/          → Create listing (login required)
/listings/<pk>/edit/       → Edit listing (owner only)
/search/guided/            → Guided search intake (multi-step)
/chat/                     → Inbox
/chat/<pk>/                → Thread for a listing
/accounts/login/           → Login
/accounts/register/        → Register
/accounts/profile/         → Unified profile (My Listings, Inquiries, Performance tabs)
/accounts/my-listings/     → My listings (redirect-friendly)
/accounts/inquiries/       → Inquiries overview
/accounts/performance/     → Performance metrics
/accounts/agent/           → Agent dashboard
/portal/                   → Portal login
/portal/dashboard/         → Admin dashboard (superuser only)
/portal/users/             → User management
/portal/users/<pk>/        → User detail
/portal/listings/          → Listings management
/portal/listings/<pk>/approve/  → Approve listing
/portal/listings/<pk>/reject/   → Reject listing
/portal/listings/<pk>/flag/     → Flag listing
/portal/listings/<pk>/delete/   → Delete listing
```

---

## Migrations History

| Migration | What |
|-----------|------|
| 0014_add_listing_status | Added `status` field with pending/active/flagged/draft |
| 0015_add_view_count | Added `view_count` PositiveIntegerField |
| 0016_add_bedrooms_guided_search_event | Added `bedrooms` to Listing + GuidedSearchEvent model |
| chatapp/0005_add_is_read | Added `is_read` to ChatMessage |

---

## What's Missing (Next Sprint)

### P0 — Launch blockers

| Item | Why it's blocking |
|------|------------------|
| `bedrooms` field on listing create form | Users can't fill it in; bedroom breakdown stays empty |
| Email notifications on inquiry | Landlords don't know someone contacted them |
| Production database (PostgreSQL) | SQLite is single-writer, not suitable for prod |
| Image storage (S3 or Cloudflare R2) | Local `listing_images/` breaks on server restart |
| `LAUNCH_ACTIVE` flag | Platform is still restricted to Irving/DFW; needs flip to go wide |

### P1 — Quality of life

| Item | Notes |
|------|-------|
| Guided search form completion → actual search results | Currently just renders the form; POST should return matched listings |
| Phone verification for listers | Trust signal for renters |
| Listing expiry / renewal | Listings auto-expire after 30 days, lister prompted to renew |
| Saved search alerts | Email when a new listing matches a saved filter |
| Mobile listing creation | Create listing flow is desktop-optimized |

### P2 — Growth features

| Item | Notes |
|------|-------|
| Landlord referral program | Give a landlord $0 but they get verified badge for referring 3 others |
| Listing boost / featured (paid) | First monetization lever; $9/week boost |
| Tenant screening integration | Stripe-based income/background check upsell |
| City expansion waitlist → launch playbook | CityWaitlist model exists; automate outreach email |
| Analytics: real visitor tracking | Replace view_count proxy with session-based visitors |

---

## Admin Credentials (dev only)

| Field | Value |
|-------|-------|
| Username | founder |
| Password | QAtest123! |
| Portal URL | http://127.0.0.1:8000/portal/ |

---

## Launch Checklist

- [ ] Add `bedrooms` to listing create/edit form
- [ ] Wire guided search POST to return filtered results
- [ ] Set up PostgreSQL + S3 for production
- [ ] Deploy to Railway / Render / Fly.io
- [ ] Flip `LAUNCH_ACTIVE` to True
- [ ] Manually seed 10-20 DFW listings
- [ ] Post in 3 DFW Facebook rental groups + r/Dallas + r/DFW
- [ ] Get 5 real landlords to post without help
- [ ] Fix whatever breaks

---

## Design Principles

**Free for landlords, always.** Monetize the trust layer, not the listing. Zillow's paywall is the wedge.

**DFW-first, city-agnostic product.** The code doesn't hard-code DFW. The go-to-market does. Expand to Austin, Houston, San Antonio on traction.

**Trust over volume.** A verified listing with photos and a real chat is worth 10 anonymous Craigslist posts. Build trust signals into every step.

**Ship and learn.** The FMM smart matching engine is a moat at 1000 listings. The launch blocker is getting the first 50. Don't build features for a scale problem you don't have yet.
