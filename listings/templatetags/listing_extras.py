from django import template

register = template.Library()

@register.filter
def split_csv(value):
    """Split a comma-separated string into a list of stripped, non-empty terms."""
    if not value:
        return []
    return [t.strip() for t in str(value).split(',') if t.strip()]

@register.filter
def dict_get(d, key):
    """Return d[key] or empty string if missing."""
    if isinstance(d, dict):
        return d.get(key, '')
    return ''

@register.filter
def category_icon(cat):
    icons = {
        'roommates':      '👥',
        'rentals':        '🔑',
        'properties':     '🏠',
        'local_services': '🔧',
        'jobs':           '💼',
        'buy_sell':       '🛒',
        'events':         '🎉',
    }
    return icons.get(cat, '📋')


@register.filter
def short_timesince(value):
    """Coarsest single unit of Django's timesince, e.g. "2 hours", "1 day".

    timesince() returns two units ("2 hours, 34 minutes"). Card chips only have
    room for one, and the template-only workarounds both render badly:
    truncatechars cuts mid-value ("2 hours, ... ago") and truncatewords appends
    its own ellipsis ("2 hours ... ago"). Splitting on the comma is exact.
    """
    if not value:
        return ''
    return str(value).split(',')[0].strip()
