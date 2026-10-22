from urllib.parse import urlsplit

from wtforms.validators import ValidationError


class HttpUrl:
    """Accept only absolute http(s) URLs (blocks javascript: and data: links)."""

    def __init__(self, message=None):
        self.message = message or "Enter a full web address starting with https://"

    def __call__(self, form, field):
        value = (field.data or "").strip()
        if not value:
            return
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.netloc or " " in value:
            raise ValidationError(self.message)
        field.data = value


class Digits:
    """Phone-like value: digits, spaces, +, -, parentheses."""

    def __init__(self, message=None):
        self.message = message or "Enter a valid phone number."

    def __call__(self, form, field):
        value = (field.data or "").strip()
        if value and (not all(c.isdigit() or c in " +-()" for c in value) or sum(c.isdigit() for c in value) < 7):
            raise ValidationError(self.message)
