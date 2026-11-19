from rest_framework.permissions import SAFE_METHODS, BasePermission


def is_admin(user) -> bool:
    return bool(user and user.is_authenticated and user.is_staff)


class IsAdminOrReadOnly(BasePermission):
    """Читання — всім, запис — тільки адміністратору (is_staff)."""

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or is_admin(request.user)


class IsOwnerOrAdminOrReadOnly(BasePermission):
    """
    Читання — всім; створення — автентифікованим; зміна й видалення — власнику або адміністратору.
    Власник визначається атрибутом view.owner_field (за замовчуванням "author").
    """

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS or bool(
            request.user and request.user.is_authenticated
        )

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS or is_admin(request.user):
            return True
        owner_field = getattr(view, "owner_field", "author")
        return getattr(obj, f"{owner_field}_id") == request.user.pk
