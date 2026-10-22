"""Email delivery abstraction.

Backends:
  console - development default. Logs the message; reports NOT delivered.
  smtp    - real delivery via SMTP (STARTTLS or SSL).
  memory  - tests; keeps messages in ``outbox``.

``send()`` returns True only when the backend confirms the message was accepted.
"""
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from flask import current_app, render_template

log = logging.getLogger(__name__)


@dataclass
class OutgoingEmail:
    to: list
    subject: str
    text: str
    html: str | None = None
    reply_to: str | None = None


class ConsoleBackend:
    name = "console"

    def send(self, message):
        log.warning(
            "MAIL_BACKEND=console: email NOT sent. To=%s Subject=%r", ", ".join(message.to), message.subject
        )
        return False


class MemoryBackend:
    name = "memory"

    def __init__(self):
        self.outbox = []

    def send(self, message):
        self.outbox.append(message)
        return True


class SMTPBackend:
    name = "smtp"

    def __init__(self, config):
        self.config = config

    def send(self, message):
        cfg = self.config
        sender = cfg.get("MAIL_DEFAULT_SENDER") or cfg.get("MAIL_USERNAME")
        if not sender:
            log.error("MAIL_DEFAULT_SENDER is not configured; email not sent.")
            return False
        msg = EmailMessage()
        msg["Subject"] = message.subject
        msg["From"] = formataddr((cfg.get("SITE_SHORT_NAME", "Website"), sender))
        msg["To"] = ", ".join(message.to)
        msg["Message-ID"] = make_msgid()
        if message.reply_to:
            msg["Reply-To"] = message.reply_to
        msg.set_content(message.text)
        if message.html:
            msg.add_alternative(message.html, subtype="html")
        try:
            context = ssl.create_default_context()
            if cfg.get("MAIL_USE_SSL"):
                server = smtplib.SMTP_SSL(cfg["MAIL_SERVER"], cfg["MAIL_PORT"],
                                          timeout=cfg.get("MAIL_TIMEOUT", 15), context=context)
            else:
                server = smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=cfg.get("MAIL_TIMEOUT", 15))
            with server:
                if cfg.get("MAIL_USE_TLS") and not cfg.get("MAIL_USE_SSL"):
                    server.starttls(context=context)
                if cfg.get("MAIL_USERNAME"):
                    server.login(cfg["MAIL_USERNAME"], cfg.get("MAIL_PASSWORD") or "")
                refused = server.send_message(msg)
            if refused:
                log.error("SMTP server refused recipients: %s", list(refused))
                return False
            return True
        except (smtplib.SMTPException, OSError) as exc:
            log.error("Email delivery failed: %s", exc.__class__.__name__)
            return False


def init_email(app):
    backend = app.config.get("MAIL_BACKEND", "console")
    if backend == "smtp":
        instance = SMTPBackend(app.config)
    elif backend == "memory":
        instance = MemoryBackend()
    else:
        instance = ConsoleBackend()
    app.extensions["email_backend"] = instance
    return instance


def backend():
    return current_app.extensions["email_backend"]


def send(message):
    if not message.to:
        log.warning("Email with subject %r has no recipients; not sent.", message.subject)
        return False
    return backend().send(message)


def send_inquiry_notification(inquiry, recipient):
    """Notify the company about a new inquiry. Returns True if delivered."""
    if not recipient:
        log.warning("No inquiry notification address configured (Settings > Contact details).")
        return False
    subject_kind = "Quote request" if inquiry.kind.value == "quote" else "Contact message"
    context = {"inquiry": inquiry}
    message = OutgoingEmail(
        to=[recipient],
        subject=f"[Website] {subject_kind} from {inquiry.full_name}",
        text=render_template("emails/inquiry_notification.txt", **context),
        html=render_template("emails/inquiry_notification.html", **context),
        reply_to=inquiry.email,
    )
    return send(message)
