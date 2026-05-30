"""
AI-powered features for Listojo.

All Claude API calls use claude-haiku-4-5 (fast, cheap — ~$0.001/call).
Set ANTHROPIC_API_KEY in your .env to enable; features degrade gracefully when absent.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ── Spam / quality patterns (no API) ─────────────────────────────────────────

_SPAM_PATTERNS = [
    r'wire\s*transfer', r'western\s*union', r'money\s*gram',
    r'google\s*hangouts', r'whatsapp\s*only', r'text\s*only',
    r'send\s*(gift\s*card|itunes)', r'overseas.*listed',
    r'i\s*(am|\'m)\s*not\s*in\s*(town|state|country|us)',
    r'military\s*deployment', r'keys?\s*by\s*mail', r'no\s*viewing\s*required',
]
_SPAM_RE = [re.compile(p, re.IGNORECASE) for p in _SPAM_PATTERNS]


def detect_spam(title: str, description: str) -> list[str]:
    """Rule-based spam detector. Returns warning strings (empty = clean)."""
    blob = f"{title} {description}"
    hits = []
    for pattern in _SPAM_RE:
        if pattern.search(blob):
            readable = pattern.pattern.replace(r'\s*', ' ').replace(r'\'', "'")
            hits.append(f"Possible spam indicator detected in your listing text.")
            break
    return hits


def check_listing_quality(
    *,
    title: str,
    description: str,
    price: float | None,
    category: str,
    image_count: int = 0,
) -> list[str]:
    """
    Rules-based quality checker — no API call, free at runtime.
    Returns up to 5 improvement suggestions shown to the landlord.
    """
    issues: list[str] = []

    if len(description.strip()) < 80:
        issues.append(
            "Description is too short — add details about the space, neighbourhood, "
            "and what makes it special. Aim for at least 80 words."
        )
    if image_count == 0:
        issues.append("No photos yet — listings with photos get 3× more inquiries.")
    elif image_count < 3:
        issues.append("Add more photos (aim for 3+) — more images means more interest.")

    if price is not None and category in ('rentals', 'roommates') and float(price) < 50:
        issues.append(
            "Price looks unusually low for a rental — double-check it's monthly rent, not per-year."
        )
    if price is not None and category == 'properties' and float(price) < 10_000:
        issues.append(
            "Sale price looks very low — verify this is a sale price, not monthly rent."
        )
    if title and title == title.upper() and len(title) > 5:
        issues.append("Title is ALL-CAPS — mixed-case titles look more professional.")

    issues.extend(detect_spam(title, description))
    return issues[:5]


# ── Claude API helpers ────────────────────────────────────────────────────────

def _get_client():
    """Lazy-init Anthropic client. Raises ValueError when key is absent."""
    try:
        import anthropic
    except ImportError:
        raise ValueError("anthropic package not installed — run: pip install anthropic")
    from django.conf import settings
    api_key = getattr(settings, 'ANTHROPIC_API_KEY', '') or ''
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not configured")
    return anthropic.Anthropic(api_key=api_key)


# ── Feature 1: AI listing description writer ──────────────────────────────────

def generate_listing_description(
    *,
    title: str = '',
    category: str = '',
    bedrooms: int | None = None,
    bathrooms: float | None = None,
    price: float | None = None,
    price_unit: str = 'mo',
    tags: str = '',
    city: str = '',
    property_type: str = '',
    accommodation_type: str = '',
    square_footage: int | None = None,
) -> str:
    """
    Generate a professional listing description using Claude Haiku.
    ~$0.001 per call. Raises ValueError/APIError on failure.
    """
    client = _get_client()

    # Build property summary for the prompt
    details: list[str] = []
    if bedrooms:
        details.append(f"{bedrooms} bedroom{'s' if bedrooms != 1 else ''}")
    if bathrooms:
        details.append(f"{bathrooms} bath{'s' if bathrooms != 1.0 else ''}")
    if square_footage:
        details.append(f"{square_footage:,} sq ft")
    if price:
        unit_label = {'mo': '/month', 'wk': '/week', 'day': '/day', 'hr': '/hour'}.get(price_unit, '')
        details.append(f"${int(price):,}{unit_label}")
    if city:
        details.append(f"in {city}")
    tag_list = [t.strip() for t in tags.split(',') if t.strip()][:6]
    if tag_list:
        details.append(f"amenities: {', '.join(tag_list)}")

    type_label = {
        'rentals': 'rental', 'roommates': 'room for rent',
        'properties': 'property for sale', 'local_services': 'service',
        'jobs': 'job', 'buy_sell': 'item for sale', 'events': 'event',
    }.get(category, 'listing')
    if accommodation_type == 'whole':
        type_label = 'whole-property rental'
    elif accommodation_type == 'room':
        type_label = 'private room rental'
    prop_overrides = {
        'apartment': 'apartment', 'condo': 'condo', 'house': 'house',
        'townhouse': 'townhouse', 'basement': 'basement suite',
        'loft': 'loft', 'studio': 'studio apartment',
    }
    if property_type in prop_overrides:
        type_label = prop_overrides[property_type]

    details_str = ', '.join(details) if details else 'details not provided'

    prompt = (
        f'Write a professional, warm, and compelling description for a {type_label} '
        f'titled "{title}".\n\n'
        f'Property details: {details_str}\n\n'
        'Requirements:\n'
        '- 3–4 sentences, 80–120 words total\n'
        '- Highlight the key features naturally\n'
        '- Friendly, welcoming tone\n'
        '- Plain paragraph text — no markdown, no bullet points\n'
        '- Do NOT repeat the title word for word\n'
        '- End with a call to action (e.g. "Schedule a tour today!")\n\n'
        'Write the description only — nothing else.'
    )

    response = client.messages.create(
        model='claude-haiku-4-5',
        max_tokens=300,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return response.content[0].text.strip()


# ── Feature 2: Natural language search parser ─────────────────────────────────

_NL_SYSTEM = (
    'You are a search query parser for a real estate listing platform. '
    'Extract structured filters from natural language. '
    'Respond with valid JSON only — no explanation, no markdown fences.'
)

def parse_natural_language_search(query: str) -> dict[str, Any]:
    """
    Convert a free-text search query to structured URL filter parameters.
    Returns a dict with zero or more of: category, city, bedrooms, max_price,
    min_price, tags, accommodation_type, property_type.
    Returns {} on failure so callers can fall back gracefully.
    """
    client = _get_client()

    prompt = (
        f'Parse this search query into structured filters:\n\nQuery: "{query}"\n\n'
        'Return a JSON object with these optional keys (omit keys not mentioned):\n'
        '- "category": "rentals" | "properties" | "roommates" | "buy_sell" | "local_services" | "jobs" | "events"\n'
        '- "city": city name string\n'
        '- "bedrooms": integer\n'
        '- "max_price": integer (monthly price, numbers only)\n'
        '- "min_price": integer\n'
        '- "tags": comma-separated amenities e.g. "pet-friendly, parking, furnished"\n'
        '- "accommodation_type": "whole" | "room"\n'
        '- "property_type": "apartment" | "condo" | "house" | "townhouse" | "basement" | "loft" | "studio"\n\n'
        'Examples:\n'
        '- "2BR pet-friendly near Uptown under $1800" → {"category":"rentals","bedrooms":2,"max_price":1800,"tags":"pet-friendly"}\n'
        '- "3 bed house for sale Dallas" → {"category":"properties","bedrooms":3,"property_type":"house","city":"Dallas"}\n\n'
        'JSON only:'
    )

    try:
        response = client.messages.create(
            model='claude-haiku-4-5',
            max_tokens=200,
            system=_NL_SYSTEM,
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip accidental markdown fences
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw.strip())
        return json.loads(raw)
    except Exception as exc:
        logger.warning("parse_natural_language_search failed: %s", exc)
        return {}


# ── Feature 3: AI match explanation ──────────────────────────────────────────

def generate_ai_match_explanation(
    listing,
    *,
    max_price: float | None = None,
    bedrooms: int | None = None,
    tags: list[str] | None = None,
    score: int = 0,
) -> str:
    """
    Generate a plain-English match explanation using Claude Haiku.
    Only called when a user with saved search preferences views a listing.
    ~$0.001 per call.
    """
    client = _get_client()

    tags = tags or []
    listing_details: list[str] = []
    if listing.price:
        listing_details.append(f"${int(listing.price):,}/{listing.price_unit or 'mo'}")
    if listing.bedrooms:
        listing_details.append(f"{listing.bedrooms}BR")
    if listing.city:
        listing_details.append(listing.city)
    listing_tags = [t.strip() for t in (listing.tags or '').split(',') if t.strip()][:5]
    if listing_tags:
        listing_details.append(', '.join(listing_tags))

    user_prefs: list[str] = []
    if max_price:
        user_prefs.append(f"budget ≤${int(max_price):,}/mo")
    if bedrooms:
        user_prefs.append(f"{bedrooms}BR")
    if tags:
        user_prefs.append(f"wants {', '.join(tags[:3])}")

    prompt = (
        f"A renter's preferences: {', '.join(user_prefs) or 'general search'}.\n"
        f"This listing scores {score}% match. Details: {', '.join(listing_details)}.\n\n"
        "Write ONE sentence (max 25 words) explaining why this listing fits their needs. "
        "Be specific and friendly. Start with 'This fits because' or 'Great match —'. "
        "Plain text only."
    )

    try:
        response = client.messages.create(
            model='claude-haiku-4-5',
            max_tokens=80,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        logger.warning("generate_ai_match_explanation failed: %s", exc)
        return ''
