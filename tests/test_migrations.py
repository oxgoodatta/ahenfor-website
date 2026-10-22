"""The Alembic migrations must build exactly the schema the models describe."""
import os

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import upgrade

from app import create_app
from app.config import normalise_db_url
from app.extensions import db


def test_migrations_match_models(tmp_path):
    url = normalise_db_url(os.environ.get("TEST_DATABASE_URL")) or f"sqlite:///{tmp_path / 'migrate.db'}"
    app = create_app("testing", {"SQLALCHEMY_DATABASE_URI": url, "LOCAL_MEDIA_ROOT": str(tmp_path / "m")})
    migrations_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations")
    with app.app_context():
        db.drop_all()
        with db.engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
        upgrade(directory=migrations_dir)
        with db.engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), db.metadata)
        db.drop_all()
        with db.engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
        db.engine.dispose()
    assert diff == [], f"models and migrations differ: {diff}"
