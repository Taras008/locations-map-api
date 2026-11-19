from smtplib import SMTPException

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

# Спільна політика ретраїв для задач, що шлють листи: @shared_task(**EMAIL_TASK_OPTIONS).
# Експоненційна затримка з jitter, до EMAIL_TASK_MAX_RETRIES повторів (разом до N+1 спроб).
EMAIL_TASK_OPTIONS = {
    "autoretry_for": (SMTPException, OSError),
    "retry_backoff": settings.EMAIL_TASK_RETRY_BACKOFF,
    "retry_jitter": True,
    "max_retries": settings.EMAIL_TASK_MAX_RETRIES,
}


def send_templated_email(template: str, to: list[str], context: dict) -> None:
    """
    Лист із шаблонів {template}_subject.txt, {template}.txt і {template}.html.
    Тема — один рядок (переноси прибираються, інакше SMTP-заголовок зламається).
    """
    subject = "".join(render_to_string(f"{template}_subject.txt", context).splitlines())
    message = EmailMultiAlternatives(
        subject=subject,
        body=render_to_string(f"{template}.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=to,
    )
    message.attach_alternative(render_to_string(f"{template}.html", context), "text/html")
    message.send()
