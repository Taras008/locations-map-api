from django.contrib import admin

from common.admin import SoftDeleteAdminMixin

from .models import Category, Location


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Location)
class LocationAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("name", "category", "author", "created_at", "is_deleted")
    list_filter = ("is_deleted", "category")
    list_select_related = ("category", "author")
    search_fields = ("name", "description", "address")
    raw_id_fields = ("author",)
    readonly_fields = ("created_at", "updated_at", "is_deleted", "deleted_at")
    ordering = ("-created_at",)
