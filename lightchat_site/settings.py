import os
import secrets
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or secrets.token_urlsafe(48)
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"


def parse_allowed_hosts(value, *, debug):
    if value is None or not value.strip():
        value = "127.0.0.1,localhost,*" if debug else "127.0.0.1,localhost"
    hosts = [host.strip() for host in value.split(",") if host.strip()]
    if "*" in hosts and not debug:
        raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS cannot contain '*' when DJANGO_DEBUG is false.")
    return hosts


ALLOWED_HOSTS = parse_allowed_hosts(os.getenv("DJANGO_ALLOWED_HOSTS"), debug=DEBUG)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "lightchat.apps.LightchatConfig",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "lightchat_site.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "lightchat_site.wsgi.application"
ASGI_APPLICATION = "lightchat_site.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.getenv("LIGHTCHAT_MEDIA_ROOT", str(BASE_DIR / "media")))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "chat-home"
LOGOUT_REDIRECT_URL = "login"

LIGHTCHAT_PROVIDER_MODE = os.getenv("LIGHTCHAT_PROVIDER_MODE", "mock").strip().lower()
LIGHTCHAT_MAX_UPLOAD_BYTES = max(1024, int(os.getenv("LIGHTCHAT_MAX_UPLOAD_BYTES", "10485760")))
LITECHAT_PROXY_URL = os.getenv("LITECHAT_PROXY_URL", "")
LITECHAT_CREDENTIALS = {
    "openai": os.getenv("LITECHAT_OPENAI_CREDENTIAL", ""),
    "anthropic": os.getenv("LITECHAT_ANTHROPIC_CREDENTIAL", ""),
    "google": os.getenv("LITECHAT_GOOGLE_CREDENTIAL", ""),
}

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
X_FRAME_OPTIONS = "DENY"
