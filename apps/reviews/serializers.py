from django.conf import settings
from rest_framework import serializers

from apps.users.serializers import PublicUserSerializer

from .models import Review, ReviewReaction


class ReviewSerializer(serializers.ModelSerializer):
    location = serializers.PrimaryKeyRelatedField(read_only=True)
    # Автор завжди request.user: поле лише для читання, передане значення ігнорується.
    author = PublicUserSerializer(read_only=True)
    likes_count = serializers.IntegerField(read_only=True)
    dislikes_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Review
        fields = (
            "id",
            "location",
            "author",
            "rating",
            "comment",
            "likes_count",
            "dislikes_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")
        extra_kwargs = {"comment": {"max_length": settings.REVIEW_COMMENT_MAX_LENGTH}}


class ReactionSerializer(serializers.Serializer):
    value = serializers.ChoiceField(choices=["like", "dislike"])

    def validate_value(self, value: str) -> int:
        return ReviewReaction.Value.LIKE if value == "like" else ReviewReaction.Value.DISLIKE
