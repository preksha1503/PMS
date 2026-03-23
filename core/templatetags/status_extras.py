from django import template

register = template.Library()


def _normalize_status(value: str) -> str:
    normalized = (value or "").strip().lower()
    if "plan" in normalized:
        return "planning"
    if "complete" in normalized:
        return "completed"
    if "hold" in normalized:
        return "on_hold"
    if "progress" in normalized:
        return "in_progress"
    if "pending" in normalized:
        return "pending"
    return "pending"


@register.filter
def status_key(value: str) -> str:
    return _normalize_status(value)


@register.filter
def status_label(value: str) -> str:
    key = _normalize_status(value)
    return {
        "planning": "Planning",
        "pending": "Pending",
        "in_progress": "In Progress",
        "completed": "Completed",
        "on_hold": "On Hold",
    }.get(key, "Pending")


@register.filter
def status_pill_class(value: str) -> str:
    key = _normalize_status(value)
    return {
        "planning": "status-planning",
        "pending": "status-pending",
        "in_progress": "status-in-progress",
        "completed": "status-completed",
        "on_hold": "status-on-hold",
    }.get(key, "status-pending")

