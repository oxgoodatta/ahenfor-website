import click
from flask.cli import with_appcontext
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select

from app.extensions import db
from app.models import AdminUser
from app.models.user import MIN_PASSWORD_LENGTH


def _normalise_email(value):
    try:
        return validate_email(value, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise click.BadParameter(str(exc))


@click.command("create-admin")
@with_appcontext
@click.option("--email", prompt="Admin email")
@click.option("--name", prompt="Full name")
@click.password_option(prompt=f"Password (min {MIN_PASSWORD_LENGTH} characters)")
def create_admin(email, name, password):
    """Create an administrator account (there is no public registration)."""
    email = _normalise_email(email)
    if db.session.scalar(select(AdminUser).where(func.lower(AdminUser.email) == email)):
        raise click.ClickException(f"An admin with email {email} already exists. Use set-password instead.")
    user = AdminUser(email=email, name=name.strip()[:120] or email)
    try:
        user.set_password(password)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    db.session.add(user)
    db.session.commit()
    click.echo(f"Admin account created for {email}. Sign in at /admin/login")


@click.command("set-password")
@with_appcontext
@click.option("--email", prompt="Admin email")
@click.password_option(prompt=f"New password (min {MIN_PASSWORD_LENGTH} characters)")
def set_password(email, password):
    """Reset an administrator's password (signs out their existing sessions)."""
    email = _normalise_email(email)
    user = db.session.scalar(select(AdminUser).where(func.lower(AdminUser.email) == email))
    if user is None:
        raise click.ClickException(f"No admin with email {email}.")
    try:
        user.set_password(password)
    except ValueError as exc:
        raise click.ClickException(str(exc))
    user.active = True
    db.session.commit()
    click.echo(f"Password updated for {email}.")
