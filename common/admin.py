from django.contrib import admin, messages


class SoftDeleteAdminMixin:
    """
    Адмінка для SoftDeleteModel: показує й видалені записи, замість стандартної
    "Delete selected" (фізичне видалення) — дії м'якого видалення й відновлення.
    """

    list_filter = ("is_deleted",)
    actions = ("soft_delete_selected", "restore_selected")

    def get_queryset(self, request):
        queryset = self.model.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        return queryset.order_by(*ordering) if ordering else queryset

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    @admin.action(description="М'яко видалити вибрані", permissions=["delete"])
    def soft_delete_selected(self, request, queryset):
        count, _ = queryset.delete()
        self.message_user(request, f"Видалено: {count}.", messages.SUCCESS)

    @admin.action(description="Відновити вибрані", permissions=["change"])
    def restore_selected(self, request, queryset):
        count = queryset.restore()
        self.message_user(request, f"Відновлено: {count}.", messages.SUCCESS)
