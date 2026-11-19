from rest_framework import serializers

from apps.locations.models import Location

from .models import LocationSubscription


class SubscribedLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ("id", "name")
        read_only_fields = fields


class SubscriptionSerializer(serializers.ModelSerializer):
    location = SubscribedLocationSerializer(read_only=True)

    class Meta:
        model = LocationSubscription
        fields = ("location", "created_at")
        read_only_fields = fields
