"""
Saving a guided search, for visitors who are signed in and for those who
aren't yet.

A signed-out visitor's answers are held in the session and saved the moment
they sign in (see listings.signals), so finishing the guided search and then
signing in doesn't lose it.
"""
from __future__ import annotations

from listings.models import SavedSearch
from portal.services.lead_service import parse_budget

PENDING_KEY = 'gs_pending_search'

_FIELDS = ('category', 'city', 'bedrooms', 'max_price', 'tags', 'available_by',
           'priority', 'urgency', 'monthly_income', 'property_type', 'accommodation_type')


def answers_from_post(post) -> dict:
    """The raw guided-search answers, as strings (safe to keep in the session)."""
    return {k: (post.get(k) or '').strip() for k in _FIELDS}


def save_answers(user, answers: dict) -> SavedSearch:
    try:
        bedrooms = int(answers.get('bedrooms') or '')
    except ValueError:
        bedrooms = None
    search_type = 'buy' if answers.get('category') == 'properties' else 'rent'
    search, _ = SavedSearch.objects.update_or_create(
        user=user,
        search_type=search_type,
        defaults={
            'city': answers.get('city', ''),
            'max_budget': parse_budget(answers.get('max_price', '')),
            'bedrooms': bedrooms,
            'property_type': answers.get('property_type', ''),
            'accommodation_type': answers.get('accommodation_type', ''),
            'amenities': answers.get('tags', ''),
            'available_by': answers.get('available_by', ''),
            'priority': answers.get('priority', ''),
            'urgency': answers.get('urgency', ''),
            'monthly_income': parse_budget(answers.get('monthly_income', '')),
        },
    )
    return search


def hold_for_signin(request, answers: dict) -> None:
    request.session[PENDING_KEY] = answers


def save_pending(request, user) -> SavedSearch | None:
    """Save the answers held for a visitor who has just signed in."""
    answers = request.session.pop(PENDING_KEY, None)
    if not answers:
        return None
    return save_answers(user, answers)
