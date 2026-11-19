from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect

# DRF SessionAuthentication перевіряє CSRF лише для залогінених, тому view, де користувач
# ще анонімний (login, register, password reset), треба захищати явно.
# Обгортати саме dispatch: csrf_protect(View.as_view()) не працює — as_view() позначає
# view як csrf_exempt, wraps() копіює цей прапорець і перевірка пропускається.
csrf_protect_view = method_decorator(csrf_protect, name="dispatch")
