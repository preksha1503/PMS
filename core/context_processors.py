from .models import Notification


def unread_notifications(request):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return {"unread_notifications": 0}
    return {
        "unread_notifications": Notification.objects.filter(user=user, is_read=False).count(),
    }

