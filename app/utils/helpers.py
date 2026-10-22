import re
import unicodedata
from urllib.parse import urlsplit

from markupsafe import Markup, escape
from sqlalchemy import select

from app.extensions import db

SLUG_RE = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


def slugify(value, max_length=200):
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value[:max_length].strip("-") or "item"


def unique_slug(model, value, exclude_id=None, max_length=200):
    """Return ``value`` slugified and made unique for ``model.slug``."""
    base = slugify(value, max_length=max_length - 6)
    candidate, n = base, 2
    while True:
        stmt = select(model.id).where(model.slug == candidate)
        if exclude_id is not None:
            stmt = stmt.where(model.id != exclude_id)
        if db.session.scalar(stmt) is None:
            return candidate
        candidate = f"{base}-{n}"
        n += 1


def is_safe_redirect(target):
    """Only allow same-site relative paths (prevents open redirects)."""
    if not target or not isinstance(target, str):
        return False
    if "\\" in target or any(ord(c) < 32 for c in target):
        return False
    parts = urlsplit(target)
    return not parts.scheme and not parts.netloc and target.startswith("/") and not target.startswith("//")


def paragraphs(text):
    """Escape plain text and turn blank-line separated blocks into <p> elements."""
    if not text:
        return Markup("")
    blocks = re.split(r"\n\s*\n", str(text).replace("\r\n", "\n").strip())
    html = "".join(
        "<p>" + str(escape(b.strip())).replace("\n", Markup("<br>")) + "</p>" for b in blocks if b.strip()
    )
    return Markup(html)


def format_date(value, fmt="%-d %B %Y"):
    if not value:
        return ""
    try:
        return value.strftime(fmt)
    except ValueError:  # pragma: no cover - platforms without %-d
        return value.strftime(fmt.replace("%-d", "%d"))
