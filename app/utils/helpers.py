"""
Shared helpers registered as Jinja2 filters and globals.
"""
from datetime import date as _date


def format_gnf(amount):
    """Format integer as GNF currency string."""
    if amount is None:
        return 'GNF 0'
    return f'GNF {int(amount):,}'


def format_date(value):
    """Format date/string as '15 Jan 2026'."""
    if not value:
        return '—'
    try:
        if isinstance(value, str):
            value = _date.fromisoformat(value)
        return value.strftime('%d %b %Y')
    except Exception:
        return str(value)


def status_badge(status):
    """Return Bootstrap badge colour for a status string."""
    mapping = {
        'active':      'success',
        'inactive':    'secondary',
        'deprecated':  'warning',
        'open':        'danger',
        'in_progress': 'warning',
        'resolved':    'success',
        'pending':     'warning',
        'paid':        'success',
        'suspended':   'danger',
    }
    colour = mapping.get(status, 'secondary')
    label = status.replace('_', ' ').title()
    return f'<span class="badge bg-{colour}">{label}</span>'


def register_helpers(app):
    """Register filters and globals on the Flask app."""
    from datetime import datetime
    app.jinja_env.filters['gnf'] = format_gnf
    app.jinja_env.filters['fmtdate'] = format_date
    app.jinja_env.filters['status_badge'] = status_badge
    app.jinja_env.globals['status_badge'] = status_badge
    app.jinja_env.globals['now'] = datetime.now
