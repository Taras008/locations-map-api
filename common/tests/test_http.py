import pytest
from django.test import RequestFactory

from common.http import get_client_ip


@pytest.fixture
def make_request():
    def make(remote_addr="10.0.0.1", xff=None):
        extra = {"REMOTE_ADDR": remote_addr}
        if xff is not None:
            extra["HTTP_X_FORWARDED_FOR"] = xff
        return RequestFactory().get("/", **extra)

    return make


@pytest.mark.parametrize(
    ("num_proxies", "xff", "expected"),
    [
        (0, None, "10.0.0.1"),
        (0, "6.6.6.6", "10.0.0.1"),  # без довірених проксі заголовок ігнорується
        (1, None, "10.0.0.1"),
        (1, "", "10.0.0.1"),
        (1, "1.1.1.1", "1.1.1.1"),
        (1, "6.6.6.6, 1.1.1.1", "1.1.1.1"),  # підроблена частина клієнта відкидається
        (2, "6.6.6.6, 1.1.1.1, 172.16.0.2", "1.1.1.1"),
        (3, "1.1.1.1, 172.16.0.2", "1.1.1.1"),  # проксі менше, ніж налаштовано
    ],
)
def test_get_client_ip(settings, make_request, num_proxies, xff, expected):
    settings.NUM_PROXIES = num_proxies

    assert get_client_ip(make_request(xff=xff)) == expected
