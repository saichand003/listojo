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
def price_drop_pct(current_price, original_price):
    """Return the percentage drop from original_price to current_price as an integer."""
    try:
        orig = float(original_price)
        curr = float(current_price)
        if orig > 0:
            return int(round((orig - curr) / orig * 100))
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return 0


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
