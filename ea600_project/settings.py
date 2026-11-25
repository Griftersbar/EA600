import os
from datetime import timedelta
from pathlib import Path

from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = "RAILWAY_ENVIRONMENT_ID" not in os.environ
if DEBUG:
    SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or get_random_secret_key()
else:
    SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
if railway_domain:
    ALLOWED_HOSTS.append(railway_domain)
    CSRF_TRUSTED_ORIGINS = [f"https://{railway_domain}"]
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

WAGTAIL_SITE_NAME = "EA600 Guides"
WAGTAILADMIN_BASE_URL = f"https://{railway_domain}" if railway_domain else "http://localhost:8000"
WAGTAILDOCS_SERVE_METHOD = "serve_view"
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10_000

INSTALLED_APPS = [
    "whitenoise.runserver_nostatic",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "wagtail.sites",
    "wagtail.contrib.settings",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "modelcluster",
    "taggit",
    "siteapp",
    "guides",
    "partners",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "siteapp.editor_auth.EditorMFAMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "ea600_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "ea600_project.wsgi.application"
ASGI_APPLICATION = "ea600_project.asgi.application"

DATA_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", BASE_DIR))

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AXES_CLIENT_IP_CALLABLE = "siteapp.editor_auth.editor_client_ip"
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_RESET_ON_SUCCESS = True
AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT = False
AXES_LOCKOUT_CALLABLE = "siteapp.editor_auth.password_lockout"
AXES_SENSITIVE_PARAMETERS = ["username", "ip_address", "csrfmiddlewaretoken"]

OTP_TOTP_ISSUER = "EA600"
OTP_TOTP_THROTTLE_FACTOR = 2
OTP_STATIC_THROTTLE_FACTOR = 2

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"
MEDIA_URL = "/media/"
MEDIA_ROOT = DATA_DIR / "media"

PARTNER_APPLICATIONS_ENABLED = os.environ.get("PARTNER_APPLICATIONS_ENABLED") == "1"
PARTNER_PILOT_PREVIEW = os.environ.get("PARTNER_PILOT_PREVIEW") == "1"
PARTNER_RESEND_API_KEY = os.environ.get("PARTNER_RESEND_API_KEY", "")
STRIPE_TEST_SECRET_KEY = os.environ.get("STRIPE_TEST_SECRET_KEY", "")
STRIPE_TEST_WEBHOOK_SECRET = os.environ.get("STRIPE_TEST_WEBHOOK_SECRET", "")
STRIPE_TEST_MONTHLY_PRICE = os.environ.get("STRIPE_TEST_MONTHLY_PRICE", "")
STRIPE_TEST_ANNUAL_PRICE = os.environ.get("STRIPE_TEST_ANNUAL_PRICE", "")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "webmaster@localhost")
EMAIL_BACKEND = (
    "django.core.mail.backends.console.EmailBackend" if DEBUG and not EMAIL_HOST
    else "django.core.mail.backends.smtp.EmailBackend"
)
STATICFILES_DIRS = [
    ("assets", BASE_DIR / "assets"),
    ("css", BASE_DIR / "css"),
    ("js", BASE_DIR / "js"),
]
