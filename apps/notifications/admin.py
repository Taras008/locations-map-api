from django.contrib import admin

from .models import LocationSubscription


@admin.register(LocationSubscription)
class LocationSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "location", "created_at")
    list_select_related = ("user", "location")
    search_fields = ("user__username", "location__name")
    raw_id_fields = ("user", "location")
    readonly_fields = ("created_at",)
