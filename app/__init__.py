"""Application factory."""
import logging
import os
from datetime import datetime

from flask import Flask, g, jsonify, render_template, request, url_for
from flask_wtf.csrf import CSRFError
from sqlalchemy import event
from sqlalchemy.engine import Engine
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import CONFIGS
from app.extensions import csrf, db, limiter, login_manager, migrate


@event.listens_for(Engine, "connect")
def _sqlite_foreign_keys(dbapi_connection, connection_record):  # pragma: no cover - driver specific
    """SQLite settings for a small production site.

    foreign_keys: enforce relationships (media can't be deleted while in use).
    WAL + busy_timeout: readers never block the writer, and several Gunicorn
    workers wait briefly instead of failing with "database is locked".
    """
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def create_app(config_name=None, overrides=None):
    config_name = config_name or os.environ.get("FLASK_CONFIG", "production")
    if config_name not in CONFIGS:
        raise RuntimeError(f"Unknown FLASK_CONFIG {config_name!r}. Use development or production.")
    config_class = CONFIGS[config_name]

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    if overrides:
        app.config.update(overrides)
    app.config["CONFIG_NAME"] = config_name
    os.makedirs(app.instance_path, exist_ok=True)

    _configure_logging(app)
    config_class.validate(app)

    if app.config.get("PROXY_FIX_HOPS"):
        hops = app.config["PROXY_FIX_HOPS"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops, x_prefix=hops)

    db.init_app(app)
    is_sqlite = (app.config["SQLALCHEMY_DATABASE_URI"] or "").startswith("sqlite")
    migrate.init_app(app, db, render_as_batch=is_sqlite, compare_type=True)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from app import models  # noqa: F401  (register models with SQLAlchemy)
    from app.services.email_service import init_email
    from app.storage import build_storage

    app.extensions["media_storage"] = build_storage(app)
    init_email(app)

    from app.admin import bp as admin_bp
    from app.public import bp as public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    from app.cli import register_cli

    register_cli(app)
    _register_template_helpers(app)
    _register_error_handlers(app)
    _register_security_headers(app)
    return app


def _configure_logging(app):
    if not app.debug and not app.testing:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _register_template_helpers(app):
    from app.services import settings_service
    from app.services.content_service import has_published_samples, public_services
    from app.utils.helpers import format_date, paragraphs
    from app.utils.icons import service_icon
    from app.utils.logo import prepare_logo

    static_root = app.static_folder

    def asset(path):
        """Static URL with a modification-time cache buster."""
        try:
            version = int(os.path.getmtime(os.path.join(static_root, path)))
        except OSError:
            version = 0
        return url_for("static", filename=path, v=version)

    def logo_url():
        if os.path.exists(os.path.join(static_root, "images", "logo.svg")):
            return asset("images/logo.svg")
        prepared = prepare_logo(static_root, app.instance_path)
        if prepared:
            return url_for("public.brand_logo", v=prepared[1])
        return None

    def hero_target_url(key):
        target = settings_service.HERO_TARGETS.get(key) or settings_service.HERO_TARGETS["projects"]
        return url_for(target[1])

    def canonical_url():
        return app.config["SITE_URL"] + request.path

    def organization_jsonld():
        """schema.org Organization built only from configured (verified) details."""
        ctx = settings_service.site()
        data = {"@context": "https://schema.org", "@type": "Organization",
                "name": app.config["SITE_NAME"], "url": app.config["SITE_URL"]}
        if ctx.contact_phone:
            data["telephone"] = ctx.contact_phone
        if ctx.contact_email:
            data["email"] = ctx.contact_email
        if ctx.contact_address:
            data["address"] = ctx.contact_address
        links = [url for _, url in ctx.social_links]
        if links:
            data["sameAs"] = links
        logo = logo_url()
        if logo:
            data["logo"] = app.config["SITE_URL"] + logo.split("?")[0]
        return data

    def show_sample_banner():
        if "sample_banner" not in g:
            g.sample_banner = has_published_samples()
        return g.sample_banner

    app.jinja_env.filters["paragraphs"] = paragraphs
    app.jinja_env.filters["date"] = format_date
    app.jinja_env.filters["datetime"] = lambda v: format_date(v, "%-d %B %Y, %H:%M")
    app.jinja_env.filters["short_date"] = lambda v: format_date(v, "%-d %b %Y")
    app.jinja_env.globals.update(
        static_asset=asset,
        logo_url=logo_url,
        hero_target_url=hero_target_url,
        canonical_url=canonical_url,
        show_sample_banner=show_sample_banner,
        service_icon=service_icon,
        organization_jsonld=organization_jsonld,
        footer_service_links=lambda: public_services(limit=6),
        current_year=lambda: datetime.now().year,
    )

    @app.context_processor
    def inject_site():
        return {"site": settings_service.site(), "site_name": app.config["SITE_NAME"]}


def _wants_json():
    return request.accept_mimetypes.best == "application/json" or request.headers.get("X-Requested-With") == "fetch"


def _register_error_handlers(app):
    def render_error(code, title, message):
        if _wants_json():
            return jsonify({"ok": False, "error": message}), code
        template = f"errors/{code}.html" if code in (403, 404, 413, 500) else "errors/generic.html"
        return render_template(template, code=code, title=title, message=message), code

    @app.errorhandler(400)
    def bad_request(e):
        return render_error(400, "Bad request", "The request could not be processed.")

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        return render_error(400, "Session expired",
                            "Your form session expired or was invalid. Please go back, reload the page and try again.")

    @app.errorhandler(403)
    def forbidden(e):
        return render_error(403, "Access denied", "You do not have permission to view this page.")

    @app.errorhandler(404)
    def not_found(e):
        return render_error(404, "Page not found", "The page you were looking for could not be found.")

    @app.errorhandler(405)
    def method_not_allowed(e):
        return render_error(405, "Not allowed", "That action is not allowed here.")

    @app.errorhandler(413)
    def too_large(e):
        mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        return render_error(413, "Upload too large", f"The upload exceeds the {mb} MB limit.")

    @app.errorhandler(429)
    def rate_limited(e):
        return render_error(429, "Too many requests", "Too many attempts. Please wait a few minutes and try again.")

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        return render_error(500, "Something went wrong", "An unexpected error occurred. Please try again shortly.")


CSP = (
    "default-src 'self'; "
    "img-src 'self' data: https:; "
    "media-src 'self' https:; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "object-src 'none'"
)


def _register_security_headers(app):
    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", CSP)
        if not app.debug and app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.blueprint == "admin" or request.path.startswith("/admin"):
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response
