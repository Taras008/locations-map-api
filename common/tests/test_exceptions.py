import pytest
from rest_framework.test import APIClient


def assert_error(response, status_code: int, code: str) -> dict:
    assert response.status_code == status_code
    assert response["Content-Type"].startswith("application/json")
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    return body["error"]


@pytest.mark.django_db
def test_unknown_api_url_returns_404_in_unified_format(api_client):
    error = assert_error(api_client.get("/api/v1/does-not-exist/"), 404, "not_found")
    assert error["details"] == {}


@pytest.mark.urls("common.tests.urls")
class TestExceptionHandler:
    @pytest.mark.parametrize("url", ["/http404/", "/not-found/"])
    def test_not_found(self, api_client, url):
        assert_error(api_client.get(url), 404, "not_found")

    def test_validation_error_has_field_details(self, api_client):
        error = assert_error(api_client.get("/validation/"), 400, "validation_error")
        assert error["details"] == {"name": ["Обов'язкове поле."]}

    def test_validation_error_list_goes_to_non_field_errors(self, api_client):
        error = assert_error(api_client.get("/validation-list/"), 400, "validation_error")
        assert error["details"] == {"non_field_errors": ["Помилка."]}

    def test_conflict(self, api_client):
        error = assert_error(api_client.get("/conflict/"), 409, "conflict")
        assert error["message"] == "Вже існує."

    def test_business_rule(self, api_client):
        assert_error(api_client.get("/business/"), 400, "business_rule")

    def test_protected_error_is_conflict(self, api_client):
        assert_error(api_client.get("/protected/"), 409, "conflict")

    def test_django_permission_denied(self, api_client):
        assert_error(api_client.get("/django-forbidden/"), 403, "permission_denied")

    def test_not_authenticated(self, api_client):
        assert_error(api_client.get("/unauthenticated/"), 401, "not_authenticated")

    def test_throttled_has_retry_after(self, api_client):
        error = assert_error(api_client.get("/throttled/"), 429, "throttled")
        assert error["details"] == {"retry_after": 42}

    def test_csrf_failure_in_csrf_protected_view(self):
        client = APIClient(enforce_csrf_checks=True)
        error = assert_error(client.post("/csrf-protected/", {}), 403, "csrf_failed")
        assert "reason" in error["details"]

    def test_csrf_protected_view_passes_with_token(self):
        client = APIClient(enforce_csrf_checks=True)
        client.cookies["csrftoken"] = "a" * 32
        response = client.post("/csrf-protected/", {}, HTTP_X_CSRFTOKEN="a" * 32)
        assert response.status_code == 200

    def test_django_suspicious_operation_returns_400(self):
        client = APIClient(raise_request_exception=False)
        assert_error(client.get("/django-suspicious/"), 400, "bad_request")

    def test_django_permission_denied_outside_drf_returns_403(self):
        client = APIClient(raise_request_exception=False)
        assert_error(client.get("/django-403/"), 403, "permission_denied")

    def test_unhandled_exception_returns_500_in_unified_format(self):
        client = APIClient(raise_request_exception=False)
        assert_error(client.get("/crash/"), 500, "server_error")


@pytest.mark.django_db
def test_disallowed_host_returns_400_in_unified_format(settings):
    settings.ALLOWED_HOSTS = ["api.example.com"]
    client = APIClient(raise_request_exception=False)

    assert_error(client.get("/api/v1/health/", HTTP_HOST="evil.example.com"), 400, "bad_request")
