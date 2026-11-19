from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


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
