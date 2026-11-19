from django.contrib import admin

from .models import Review, ReviewReaction


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "location", "author", "rating", "created_at")
    list_filter = ("rating",)
    list_select_related = ("location", "author")
    search_fields = ("comment", "location__name", "author__username")
    raw_id_fields = ("location", "author")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(ReviewReaction)
class ReviewReactionAdmin(admin.ModelAdmin):
    list_display = ("id", "review", "user", "value", "created_at")
    list_filter = ("value",)
    list_select_related = ("review__location", "review__author", "user")
    raw_id_fields = ("review", "user")
    readonly_fields = ("created_at",)
