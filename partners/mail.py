import json
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail import send_mail


def email_ready():
    return bool(settings.DEBUG or settings.PARTNER_RESEND_API_KEY or settings.EMAIL_HOST)


def send_partner_mail(subject, body, recipient):
    if not settings.PARTNER_RESEND_API_KEY:
        return send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient])

    request = Request("https://api.resend.com/emails", data=json.dumps({
        "from": settings.DEFAULT_FROM_EMAIL, "to": [recipient], "subject": subject, "text": body,
    }).encode(), headers={
        "Authorization": f"Bearer {settings.PARTNER_RESEND_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "EA600 Business Listings",
    })
    with urlopen(request, timeout=settings.EMAIL_TIMEOUT):
        return 1
