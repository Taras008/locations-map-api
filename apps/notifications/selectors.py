from django.db.models import QuerySet

from apps.users.models import User

from .models import LocationSubscription


def get_user_subscriptions(user: User) -> QuerySet[LocationSubscription]:
    # JOIN на локацію не проходить через Location.objects, тож видалені відсікаємо явно.
    return (
        LocationSubscription.objects.filter(user=user, location__is_deleted=False)
        .select_related("location")
        .order_by("-created_at", "-id")
    )
