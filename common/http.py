from django.conf import settings
from django.http import HttpRequest


def get_client_ip(request: HttpRequest) -> str:
    """
    IP клієнта з урахуванням settings.NUM_PROXIES — кількості довірених проксі перед застосунком.

    X-Forwarded-For дописує кожен проксі, але першу частину заголовка задає сам клієнт,
    тож йому довіряємо лише на глибину NUM_PROXIES, рахуючи з кінця. 0 — проксі немає,
    заголовок ігнорується повністю (інакше його можна підробити й обійти throttling).
    """
    remote_addr = request.META.get("REMOTE_ADDR", "")
    num_proxies = settings.NUM_PROXIES
    if num_proxies <= 0:
        return remote_addr

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    addrs = [addr.strip() for addr in forwarded.split(",") if addr.strip()]
    if not addrs:
        return remote_addr
    return addrs[-min(num_proxies, len(addrs))]
