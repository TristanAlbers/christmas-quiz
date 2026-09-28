from django import template

register = template.Library()


@register.filter
def elapsed_hhmmss(value):
    """Format authoritative elapsed milliseconds as fixed HH:MM:SS."""
    try:
        total_seconds = max(0, int(value) // 1000)
    except (TypeError, ValueError):
        total_seconds = 0
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
