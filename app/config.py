"""Environment-based configuration.

Values are read from the process environment (and a local .env file).
Each environment has its own class; ProductionConfig refuses to start when
mandatory settings are missing.

Database: SQLite by default (instance/ahenfor.db), which suits a single
Hostinger VPS. Set DATABASE_URL to use PostgreSQL instead.
"""
import logging
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

MB = 1024 * 1024
log = logging.getLogger(__name__)


class ConfigurationError(RuntimeError):
    """Raised at startup when production configuration is unsafe or incomplete."""


def env(name, default=None):
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def env_bool(name, default=False):
    value = env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_int(name, default):
    try:
        return int(env(name, default))
    except (TypeError, ValueError):
        return default


def normalise_db_url(url):
    """Use the psycopg 3 driver for PostgreSQL URLs (Render/Heroku give postgres://)."""
    if not url:
        return url
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DEFAULT_SQLITE_PATH = BASE_DIR / "instance" / "ahenfor.db"
DEFAULT_SQLITE_URI = "sqlite:///" + DEFAULT_SQLITE_PATH.as_posix()


class Config:
    SITE_NAME = "Ahenfor Engineering and Construction Limited"
    SITE_SHORT_NAME = "Ahenfor"
    SITE_URL = (env("SITE_URL", "http://localhost:5000") or "").rstrip("/")

    SECRET_KEY = env("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = normalise_db_url(env("DATABASE_URL")) or DEFAULT_SQLITE_URI
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Media
    MEDIA_STORAGE_PROVIDER = (env("MEDIA_STORAGE_PROVIDER", "local") or "local").lower()
    LOCAL_MEDIA_ROOT = env("LOCAL_MEDIA_ROOT", str(BASE_DIR / "instance" / "uploads"))
    MAX_IMAGE_BYTES = env_int("MAX_IMAGE_MB", 10) * MB
    MAX_VIDEO_BYTES = env_int("MAX_VIDEO_MB", 100) * MB
    MAX_DOCUMENT_BYTES = env_int("MAX_DOCUMENT_MB", 15) * MB
    MAX_CONTENT_LENGTH = env_int("MAX_REQUEST_MB", 150) * MB
    MAX_FORM_MEMORY_SIZE = 2 * MB

    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
    AWS_S3_BUCKET = env("AWS_S3_BUCKET")
    AWS_REGION = env("AWS_REGION")
    S3_ENDPOINT_URL = env("S3_ENDPOINT_URL")
    MEDIA_PUBLIC_BASE_URL = (env("MEDIA_PUBLIC_BASE_URL") or "").rstrip("/") or None

    CLOUDINARY_CLOUD_NAME = env("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = env("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = env("CLOUDINARY_API_SECRET")

    # Email
    MAIL_BACKEND = (env("MAIL_BACKEND", "console") or "console").lower()
    MAIL_SERVER = env("MAIL_SERVER")
    MAIL_PORT = env_int("MAIL_PORT", 587)
    MAIL_USE_TLS = env_bool("MAIL_USE_TLS", True)
    MAIL_USE_SSL = env_bool("MAIL_USE_SSL", False)
    MAIL_USERNAME = env("MAIL_USERNAME")
    MAIL_PASSWORD = env("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = env("MAIL_DEFAULT_SENDER")
    MAIL_TIMEOUT = 15
    INQUIRY_NOTIFY_EMAIL = env("INQUIRY_NOTIFY_EMAIL")

    # Sessions and security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_NAME = "ahenfor_session"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=env_int("SESSION_HOURS", 8))
    REMEMBER_COOKIE_DURATION = timedelta(seconds=0)
    WTF_CSRF_TIME_LIMIT = None  # token lives as long as the session
    RATELIMIT_STORAGE_URI = env("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True
    LOGIN_RATE_LIMIT = "5 per minute;20 per hour"
    FORM_RATE_LIMIT = "10 per hour"
    PROXY_FIX_HOPS = env_int("PROXY_FIX_HOPS", 0)
    TRUSTED_HOSTS = [h.strip() for h in (env("ALLOWED_HOSTS") or "").split(",") if h.strip()] or None

    ADMIN_PER_PAGE = 20
    PUBLIC_PER_PAGE = 12
    SEND_FILE_MAX_AGE_DEFAULT = 0

    @classmethod
    def validate(cls, app):
        """Hook for environment-specific startup checks."""


class DevelopmentConfig(Config):
    DEBUG = env_bool("FLASK_DEBUG", True)
    SECRET_KEY = Config.SECRET_KEY or "dev-only-insecure-secret-key"


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "testing-secret-key-not-for-production"
    SQLALCHEMY_DATABASE_URI = normalise_db_url(env("TEST_DATABASE_URL")) or "sqlite://"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    MEDIA_STORAGE_PROVIDER = "local"
    MAIL_BACKEND = "memory"
    SITE_URL = "http://localhost"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    SEND_FILE_MAX_AGE_DEFAULT = 60 * 60 * 24 * 365  # static URLs are cache-busted

    @classmethod
    def validate(cls, app):
        cfg = app.config
        problems = []
        key = cfg.get("SECRET_KEY") or ""
        if len(key) < 32 or key == "replace-with-a-secure-secret" or key.startswith("dev-"):
            problems.append("SECRET_KEY must be a random value of at least 32 characters "
                            '(python -c "import secrets; print(secrets.token_hex(32))").')
        provider = cfg.get("MEDIA_STORAGE_PROVIDER")
        if provider == "s3" and not cfg.get("AWS_S3_BUCKET"):
            problems.append("AWS_S3_BUCKET is required when MEDIA_STORAGE_PROVIDER=s3.")
        if provider == "cloudinary" and not all(
            cfg.get(k) for k in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
        ):
            problems.append("CLOUDINARY_* settings are required when MEDIA_STORAGE_PROVIDER=cloudinary.")
        if cfg.get("MAIL_BACKEND") == "smtp" and not cfg.get("MAIL_SERVER"):
            problems.append("MAIL_SERVER is required when MAIL_BACKEND=smtp.")
        if problems:
            raise ConfigurationError(
                "Production configuration is incomplete:\n  - " + "\n  - ".join(problems)
                + "\n(For local development set FLASK_CONFIG=development in .env)"
            )
        if (cfg.get("SQLALCHEMY_DATABASE_URI") or "").startswith("sqlite"):
            log.info("Using SQLite. Back up instance/ahenfor.db regularly (deploy/backup.sh).")
        if provider == "local":
            log.info("Using local media storage at %s. Include it in backups.", cfg.get("LOCAL_MEDIA_ROOT"))
        if cfg.get("RATELIMIT_STORAGE_URI", "").startswith("memory://"):
            log.warning(
                "RATELIMIT_STORAGE_URI is memory:// - login limits are per worker process. "
                "Use Redis when running several Gunicorn workers."
            )
        if cfg.get("MAIL_BACKEND") == "console":
            log.warning("MAIL_BACKEND=console - inquiry notification emails will NOT be sent.")


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
