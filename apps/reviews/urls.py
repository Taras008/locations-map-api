from django.urls import path

from .views import LocationReviewListCreateView, ReviewDetailView, ReviewReactionView

urlpatterns = [
    path(
        "locations/<int:location_id>/reviews/",
        LocationReviewListCreateView.as_view(),
        name="location-reviews",
    ),
    path("reviews/<int:pk>/", ReviewDetailView.as_view(), name="review-detail"),
    path("reviews/<int:pk>/reaction/", ReviewReactionView.as_view(), name="review-reaction"),
]
