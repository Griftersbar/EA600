from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice


def sign_in_verified(client, editor):
    """Start the session that an editor receives after both sign-in steps."""
    device, _ = TOTPDevice.objects.get_or_create(user=editor, name="Test authenticator")
    client.force_login(editor, backend="django.contrib.auth.backends.ModelBackend")
    session = client.session
    session[DEVICE_ID_SESSION_KEY] = device.persistent_id
    session.save()
