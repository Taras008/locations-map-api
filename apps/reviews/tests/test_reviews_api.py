import pytest
from rest_framework.test import APIClient

from apps.locations.models import Location
from apps.locations.tests.factories import LocationFactory
from apps.reviews.models import Review, ReviewReaction
from apps.reviews.tests.factories import ReviewFactory, ReviewReactionFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def reviews_url(location: Location) -> str:
    return f"/api/v1/locations/{location.pk}/reviews/"


def review_url(review: Review) -> str:
    return f"/api/v1/reviews/{review.pk}/"


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def location():
    return LocationFactory()


@pytest.fixture
def payload() -> dict:
    return {"rating": 5, "comment": "Чудовий краєвид"}


@pytest.fixture
def own_review(user, location):
    return ReviewFactory(author=user, location=location)


class TestList:
    def test_anonymous_reads_location_reviews(self, api_client, location):
        review = ReviewFactory(location=location)
        ReviewReactionFactory.create_batch(2, review=review)
        ReviewReactionFactory(review=review, value=ReviewReaction.Value.DISLIKE)
        ReviewFactory()  # відгук іншої локації

        response = api_client.get(reviews_url(location))

        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        item = body["results"][0]
        assert item == {
            "id": review.pk,
            "location": location.pk,
            "author": {"id": review.author.pk, "username": review.author.username},
            "rating": review.rating,
            "comment": review.comment,
            "likes_count": 2,
            "dislikes_count": 1,
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
        }

    def test_author_email_is_not_exposed(self, api_client, location):
        review = ReviewFactory(location=location)

        response = api_client.get(reviews_url(location))

        assert review.author.email not in response.content.decode()

    def test_newest_first_and_paginated(self, api_client, location):
        reviews = ReviewFactory.create_batch(3, location=location)

        response = api_client.get(reviews_url(location), {"page_size": 2})

        body = response.json()
        assert body["count"] == 3
        assert [item["id"] for item in body["results"]] == [reviews[2].pk, reviews[1].pk]

    def test_list_has_no_n_plus_one(self, api_client, location, django_assert_num_queries):
        for review in ReviewFactory.create_batch(5, location=location):
            ReviewReactionFactory.create_batch(2, review=review)
            ReviewReactionFactory(review=review, value=ReviewReaction.Value.DISLIKE)

        # локація, count, сторінка відгуків з автором і лічильниками
        with django_assert_num_queries(3):
            response = api_client.get(reviews_url(location))

        assert {(r["likes_count"], r["dislikes_count"]) for r in response.json()["results"]} == {
            (2, 1)
        }

    def test_unknown_location_is_404(self, api_client):
        response = api_client.get("/api/v1/locations/999999/reviews/")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_deleted_location_is_404(self, api_client, location):
        ReviewFactory(location=location)
        location.delete()

        response = api_client.get(reviews_url(location))

        assert response.status_code == 404


class TestCreate:
    def test_anonymous_cannot_create(self, api_client, location, payload):
        response = api_client.post(reviews_url(location), payload)

        assert response.status_code == 401
        assert not Review.objects.exists()

    def test_authenticated_user_creates_review(self, auth_client, user, location, payload):
        response = auth_client.post(reviews_url(location), payload)

        assert response.status_code == 201
        body = response.json()
        review = Review.objects.get()
        assert body["id"] == review.pk
        assert body["location"] == location.pk
        assert body["author"] == {"id": user.pk, "username": user.username}
        assert (body["rating"], body["comment"]) == (5, "Чудовий краєвид")
        assert (body["likes_count"], body["dislikes_count"]) == (0, 0)

    def test_author_and_location_cannot_be_spoofed(self, auth_client, user, location, payload):
        other_user, other_location = UserFactory(), LocationFactory()

        response = auth_client.post(
            reviews_url(location),
            {**payload, "author": other_user.pk, "location": other_location.pk},
        )

        assert response.status_code == 201
        review = Review.objects.get()
        assert (review.author, review.location) == (user, location)

    @pytest.mark.parametrize("rating", [1, 5])
    def test_boundary_ratings_are_valid(self, auth_client, location, payload, rating):
        response = auth_client.post(reviews_url(location), {**payload, "rating": rating})

        assert response.status_code == 201

    @pytest.mark.parametrize("rating", [0, 6, -1, "abc", ""])
    def test_invalid_rating(self, auth_client, location, payload, rating):
        response = auth_client.post(reviews_url(location), {**payload, "rating": rating})

        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert "rating" in error["details"]
        assert not Review.objects.exists()

    @pytest.mark.parametrize("field", ["rating", "comment"])
    def test_required_fields(self, auth_client, location, payload, field):
        del payload[field]

        response = auth_client.post(reviews_url(location), payload)

        assert response.status_code == 400
        assert field in response.json()["error"]["details"]

    def test_blank_comment(self, auth_client, location, payload):
        response = auth_client.post(reviews_url(location), {**payload, "comment": "  "})

        assert response.status_code == 400
        assert "comment" in response.json()["error"]["details"]

    def test_comment_length_limit(self, auth_client, location, payload, settings):
        limit = settings.REVIEW_COMMENT_MAX_LENGTH

        too_long = auth_client.post(
            reviews_url(location), {**payload, "comment": "a" * (limit + 1)}
        )
        exact = auth_client.post(reviews_url(location), {**payload, "comment": "a" * limit})

        assert too_long.status_code == 400
        assert "comment" in too_long.json()["error"]["details"]
        assert exact.status_code == 201

    def test_second_review_is_conflict(self, auth_client, location, payload, own_review):
        response = auth_client.post(reviews_url(location), payload)

        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "conflict"
        assert error["message"] == "Ви вже залишили відгук до цієї локації."
        assert Review.objects.count() == 1

    def test_review_of_own_location_is_rejected(self, auth_client, user, payload):
        location = LocationFactory(author=user)

        response = auth_client.post(reviews_url(location), payload)

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "business_rule"
        assert not Review.objects.exists()

    def test_deleted_location_is_404(self, auth_client, location, payload):
        location.delete()

        response = auth_client.post(reviews_url(location), payload)

        assert response.status_code == 404
        assert not Review.objects.exists()

    def test_can_review_again_after_deleting(self, auth_client, location, payload, own_review):
        assert auth_client.delete(review_url(own_review)).status_code == 204

        response = auth_client.post(reviews_url(location), payload)

        assert response.status_code == 201


class TestUpdate:
    def test_author_updates_own_review(self, auth_client, own_review):
        response = auth_client.patch(review_url(own_review), {"rating": 2, "comment": "Гірше"})

        assert response.status_code == 200
        own_review.refresh_from_db()
        assert (own_review.rating, own_review.comment) == (2, "Гірше")
        assert response.json()["likes_count"] == 0

    def test_invalid_rating_on_update(self, auth_client, own_review):
        response = auth_client.patch(review_url(own_review), {"rating": 6})

        assert response.status_code == 400

    def test_author_and_location_cannot_be_changed(self, auth_client, user, location, own_review):
        auth_client.patch(
            review_url(own_review),
            {"author": UserFactory().pk, "location": LocationFactory().pk},
        )

        own_review.refresh_from_db()
        assert (own_review.author, own_review.location) == (user, location)

    def test_other_user_cannot_update(self, auth_client):
        review = ReviewFactory()

        response = auth_client.patch(review_url(review), {"rating": 1})

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"

    def test_admin_cannot_rewrite_others_review(self, staff_client):
        review = ReviewFactory(rating=4)

        response = staff_client.patch(review_url(review), {"rating": 1})

        assert response.status_code == 403
        review.refresh_from_db()
        assert review.rating == 4

    def test_anonymous_cannot_update(self, api_client, own_review):
        assert api_client.patch(review_url(own_review), {"rating": 1}).status_code == 401

    def test_put_and_get_are_not_allowed(self, auth_client, own_review):
        assert auth_client.put(review_url(own_review), {"rating": 1}).status_code == 405
        assert auth_client.get(review_url(own_review)).status_code == 405

    def test_review_of_deleted_location_is_404(self, auth_client, own_review):
        own_review.location.delete()

        response = auth_client.patch(review_url(own_review), {"rating": 1})

        assert response.status_code == 404


class TestDelete:
    def test_author_deletes_own_review(self, auth_client, own_review):
        ReviewReactionFactory(review=own_review)

        response = auth_client.delete(review_url(own_review))

        assert response.status_code == 204
        assert not Review.objects.exists()
        assert not ReviewReaction.objects.exists()

    def test_other_user_cannot_delete(self, auth_client):
        review = ReviewFactory()

        response = auth_client.delete(review_url(review))

        assert response.status_code == 403
        assert Review.objects.filter(pk=review.pk).exists()

    def test_anonymous_cannot_delete(self, api_client, own_review):
        assert api_client.delete(review_url(own_review)).status_code == 401

    def test_admin_deletes_any_review(self, staff_client):
        review = ReviewFactory()

        response = staff_client.delete(review_url(review))

        assert response.status_code == 204
        assert not Review.objects.exists()

    def test_unknown_review_is_404(self, auth_client):
        assert auth_client.delete("/api/v1/reviews/999999/").status_code == 404

    def test_review_of_deleted_location_is_404_even_for_admin(self, staff_client, own_review):
        own_review.location.delete()

        response = staff_client.delete(review_url(own_review))

        assert response.status_code == 404
        assert Review.objects.filter(pk=own_review.pk).exists()


class TestCsrf:
    def test_session_user_needs_csrf_token(self, user, location, payload):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user)

        response = client.post(reviews_url(location), payload)

        assert response.status_code == 403
        assert not Review.objects.exists()
