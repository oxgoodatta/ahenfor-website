import click
from flask.cli import with_appcontext

from app.cli.create_admin import create_admin, set_password
from app.cli.seed import seed_demo


def register_cli(app):
    app.cli.add_command(create_admin)
    app.cli.add_command(set_password)
    app.cli.add_command(seed_demo)
    app.cli.add_command(check_config)


@click.command("check-config")
@with_appcontext
def check_config():
    """Print the active configuration summary (no secrets)."""
    from flask import current_app

    cfg = current_app.config
    db_url = cfg["SQLALCHEMY_DATABASE_URI"] or ""
    click.echo(f"Config:        {cfg['CONFIG_NAME']}")
    click.echo(f"Database:      {db_url.split('://')[0]}")
    click.echo(f"Media storage: {cfg['MEDIA_STORAGE_PROVIDER']}")
    click.echo(f"Mail backend:  {cfg['MAIL_BACKEND']}")
    click.echo(f"Rate limits:   {cfg['RATELIMIT_STORAGE_URI'].split('://')[0]}")
    click.echo(f"Site URL:      {cfg['SITE_URL']}")
