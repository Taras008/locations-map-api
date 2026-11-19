import pytest

from apps.reviews.models import Review, ReviewReaction
from apps.reviews.tests.factories import ReviewFactory, ReviewReactionFactory

pytestmark = pytest.mark.django_db


def reaction_url(review: Review) -> str:
    return f"/api/v1/reviews/{review.pk}/reaction/"


@pytest.fixture
def review():
    return ReviewFactory()


class TestVote:
    @pytest.mark.parametrize(("value", "counts"), [("like", (1, 0)), ("dislike", (0, 1))])
    def test_vote(self, auth_client, user, review, value, counts):
        response = auth_client.post(reaction_url(review), {"value": value})

        assert response.status_code == 201
        body = response.json()
        assert body["id"] == review.pk
        assert (body["likes_count"], body["dislikes_count"]) == counts
        reaction = ReviewReaction.objects.get()
        assert (reaction.user, reaction.get_value_display()) == (user, value)

    def test_counts_include_other_votes(self, auth_client, review):
        ReviewReactionFactory.create_batch(2, review=review)
        ReviewReactionFactory(review=review, value=ReviewReaction.Value.DISLIKE)

        response = auth_client.post(reaction_url(review), {"value": "like"})

        assert (response.json()["likes_count"], response.json()["dislikes_count"]) == (3, 1)

    @pytest.mark.parametrize("second", ["like", "dislike"])
    def test_second_vote_is_conflict(self, auth_client, user, review, second):
        ReviewReactionFactory(review=review, user=user, value=ReviewReaction.Value.LIKE)

        response = auth_client.post(reaction_url(review), {"value": second})

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"
        assert ReviewReaction.objects.get().value == ReviewReaction.Value.LIKE

    def test_vote_for_own_review_is_rejected(self, auth_client, user):
        review = ReviewFactory(author=user)

        response = auth_client.post(reaction_url(review), {"value": "like"})

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "business_rule"
        assert not ReviewReaction.objects.exists()

    @pytest.mark.parametrize("payload", [{}, {"value": "love"}, {"value": 1}])
    def test_invalid_value(self, auth_client, review, payload):
        response = auth_client.post(reaction_url(review), payload)

        assert response.status_code == 400
        assert "value" in response.json()["error"]["details"]

    def test_anonymous_cannot_vote(self, api_client, review):
        assert api_client.post(reaction_url(review), {"value": "like"}).status_code == 401
        assert not ReviewReaction.objects.exists()

    def test_unknown_review_is_404(self, auth_client):
        response = auth_client.post("/api/v1/reviews/999999/reaction/", {"value": "like"})

        assert response.status_code == 404

    def test_review_of_deleted_location_is_404(self, auth_client, review):
        review.location.delete()

        response = auth_client.post(reaction_url(review), {"value": "like"})

        assert response.status_code == 404
        assert not ReviewReaction.objects.exists()


class TestRemoveVote:
    def test_remove_and_vote_again(self, auth_client, user, review):
        ReviewReactionFactory(review=review, user=user, value=ReviewReaction.Value.LIKE)
        other = ReviewReactionFactory(review=review)

        assert auth_client.delete(reaction_url(review)).status_code == 204
        assert list(ReviewReaction.objects.all()) == [other]

        response = auth_client.post(reaction_url(review), {"value": "dislike"})

        assert response.status_code == 201
        assert (response.json()["likes_count"], response.json()["dislikes_count"]) == (1, 1)

    def test_remove_without_vote_is_404(self, auth_client, review):
        ReviewReactionFactory(review=review)  # чужий голос не знімається

        response = auth_client.delete(reaction_url(review))

        assert response.status_code == 404
        assert ReviewReaction.objects.count() == 1

    def test_remove_on_unknown_review_is_404(self, auth_client):
        response = auth_client.delete("/api/v1/reviews/999999/reaction/")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    def test_anonymous_cannot_remove(self, api_client, review):
        assert api_client.delete(reaction_url(review)).status_code == 401
