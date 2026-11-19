import pytest


@pytest.mark.django_db
@pytest.mark.parametrize("url", ["/api/schema/", "/api/docs/"])
def test_api_docs_are_available(api_client, url):
    assert api_client.get(url).status_code == 200
