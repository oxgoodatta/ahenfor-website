"""Sample content for development and demos.

Every record created here is flagged ``is_sample=True`` and the public site shows
a "sample content" notice while any sample record is published. No awards,
testimonials, client names or statistics are created: those must be real.

    flask seed-demo          # add sample content
    flask seed-demo --clear  # remove all sample content and its images
"""
import io
import random
from datetime import date, timedelta

import click
from flask.cli import with_appcontext
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models import (
    ContentPost,
    PhaseStatus,
    PostKind,
    ProgressUpdate,
    Project,
    ProjectPhase,
    ProjectStatus,
    PublicationStatus,
    Service,
)
from app.models.base import utcnow
from app.services import media_service, project_service
from app.services.media_service import UploadBatch

PALETTES = [((14, 31, 58), (194, 154, 75)), ((40, 46, 56), (214, 205, 190)),
            ((26, 49, 89), (239, 235, 228)), ((88, 82, 72), (247, 245, 241))]


def placeholder_image(label, seed, size=(1600, 1067)):
    rnd = random.Random(seed)
    bg, fg = rnd.choice(PALETTES)
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    w, h = size
    grid = tuple(min(255, c + 18) for c in bg)
    for x in range(0, w, 40):
        draw.line([(x, 0), (x, h)], fill=grid, width=1)
    for y in range(0, h, 40):
        draw.line([(0, y), (w, y)], fill=grid, width=1)
    ground = int(h * 0.78)
    draw.line([(0, ground), (w, ground)], fill=fg, width=3)
    x = int(w * 0.08)
    while x < w * 0.9:
        bw = rnd.randint(120, 260)
        bh = rnd.randint(int(h * 0.2), int(h * 0.6))
        draw.rectangle([x, ground - bh, x + bw, ground], outline=fg, width=3)
        for fy in range(ground - bh + 30, ground - 20, 46):
            draw.line([(x + 14, fy), (x + bw - 14, fy)], fill=fg, width=1)
        x += bw + rnd.randint(30, 90)
    crane_x = int(w * rnd.uniform(0.55, 0.8))
    draw.line([(crane_x, ground), (crane_x, int(h * 0.12))], fill=fg, width=5)
    draw.line([(crane_x - 260, int(h * 0.14)), (crane_x + 140, int(h * 0.14))], fill=fg, width=5)
    font = ImageFont.load_default(size=34)
    small = ImageFont.load_default(size=22)
    draw.rectangle([0, 0, w, 64], fill=fg)
    draw.text((28, 14), "SAMPLE IMAGE  ·  replace with a real project photograph", fill=bg, font=small)
    draw.text((40, h - 80), label.upper(), fill=fg, font=font)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82)
    buf.seek(0)
    return FileStorage(stream=buf, filename=f"sample-{seed}.jpg", content_type="image/jpeg")


SERVICES = [
    ("Building Construction", "Commercial, residential and institutional buildings delivered from foundations to finishes."),
    ("Civil and Structural Engineering", "Structural design coordination, reinforced concrete and steel works."),
    ("Roads and Infrastructure", "Roads, drainage, culverts and site infrastructure."),
    ("Renovation and Rehabilitation", "Upgrading, repairing and extending existing structures safely."),
    ("Project Management", "Programme, cost and quality control across every phase of delivery."),
    ("Engineering Consultancy", "Feasibility, technical advice and site supervision."),
]

PROJECTS = [
    ("Takoradi Commercial Complex", "Takoradi, Western Region", "Commercial Buildings", ProjectStatus.ONGOING, 45),
    ("Kumasi Office Block", "Kumasi, Ashanti Region", "Commercial Buildings", ProjectStatus.COMPLETED, 100),
    ("Tema Industrial Warehouse", "Tema, Greater Accra", "Industrial", ProjectStatus.ONGOING, 70),
    ("Cape Coast School Extension", "Cape Coast, Central Region", "Institutional", ProjectStatus.UPCOMING, None),
    ("Ho Access Road Upgrade", "Ho, Volta Region", "Roads and Infrastructure", ProjectStatus.ON_HOLD, 20),
]

UPDATES = {
    "Excavation and Foundation": ["Site excavation", "Reinforcement installation", "Concrete foundation completed"],
    "Structural Works": ["Ground-floor columns", "First-floor slab", "Upper-floor structural work"],
}


@click.command("seed-demo")
@with_appcontext
@click.option("--clear", is_flag=True, help="Remove all sample content instead of adding it.")
def seed_demo(clear):
    """Create (or remove) clearly flagged sample content for development."""
    if clear:
        _clear()
        return
    if db.session.scalar(select(Project.id).where(Project.is_sample.is_(True)).limit(1)):
        raise click.ClickException("Sample content already exists. Run `flask seed-demo --clear` first.")

    with UploadBatch() as batch:
        for i, (name, short) in enumerate(SERVICES):
            db.session.add(Service(
                name=name, slug=_slug(Service, name), short_description=short,
                description=short + "\n\nProposed service description. Confirm with the company before launch.",
                position=i, is_sample=True, publication_status=PublicationStatus.PUBLISHED, published_at=utcnow(),
            ))

        today = date.today()
        for n, (name, location, category, status, pct) in enumerate(PROJECTS):
            cover = batch.store(placeholder_image(name, n), alt_text=f"Sample image for {name}")
            project = Project(
                name=name, slug=_slug(Project, name), location=location, category=category, status=status,
                short_description=f"Sample project for development. {category} works in {location.split(',')[0]}.",
                description="This is sample content created by `flask seed-demo`. Replace it with real, "
                            "approved project information before launch.",
                cover_image=cover, progress_percent=pct, is_sample=True,
                start_date=today - timedelta(days=300 - n * 40) if status != ProjectStatus.UPCOMING else None,
                estimated_completion_date=today + timedelta(days=200 + n * 30),
                is_featured=n < 3, featured_order=n,
                publication_status=PublicationStatus.PUBLISHED, published_at=utcnow(),
            )
            if status == ProjectStatus.COMPLETED:
                project.actual_completion_date = today - timedelta(days=20)
            db.session.add(project)
            db.session.flush()
            if status == ProjectStatus.UPCOMING:
                continue
            project_service.add_default_phases(project)
            db.session.flush()
            for phase in project.phases:
                titles = UPDATES.get(phase.title)
                if phase.position <= 1:
                    phase.status = PhaseStatus.COMPLETED
                elif phase.position == 2:
                    phase.status = PhaseStatus.IN_PROGRESS
                if status == ProjectStatus.COMPLETED:
                    phase.status = PhaseStatus.COMPLETED
                if not titles:
                    continue
                for k, title in enumerate(titles):
                    update = ProgressUpdate(
                        phase=phase, title=title,
                        update_date=today - timedelta(days=(6 - phase.position) * 40 - k * 12),
                        body="Sample progress note. Replace with the site team's real update.",
                        publication_status=PublicationStatus.PUBLISHED, published_at=utcnow(),
                    )
                    db.session.add(update)
                    entries = [
                        (batch.store(placeholder_image(f"{name} - {title}", n * 100 + phase.position * 10 + k * 3 + j),
                                     alt_text=f"Sample image: {title}"), "", "")
                        for j in range(3)
                    ]
                    project_service.apply_update_media(update, entries)

        now = utcnow()
        posts = [
            ("Site safety open day", PostKind.EVENT, now + timedelta(days=21), "Head office"),
            ("Industry engineering forum", PostKind.EVENT, now - timedelta(days=60), "Accra"),
            ("Website launch", PostKind.NEWS, None, None),
        ]
        for i, (title, kind, starts, venue) in enumerate(posts):
            db.session.add(ContentPost(
                title=title, slug=_slug(ContentPost, title), kind=kind, starts_at=starts, venue=venue,
                summary="Sample news/event item created for development. Replace before launch.",
                body="This is sample content.",
                cover_image=batch.store(placeholder_image(title, 900 + i), alt_text=f"Sample image for {title}"),
                is_sample=True, publication_status=PublicationStatus.PUBLISHED, published_at=now - timedelta(days=1),
            ))
        db.session.commit()
    click.echo("Sample content created. Every item is marked as sample; remove it with `flask seed-demo --clear`.")


def _slug(model, value):
    from app.utils.helpers import unique_slug

    return unique_slug(model, value)


def _clear():
    from app.models import MediaAsset

    media_ids = set()
    for project in db.session.scalars(select(Project).where(Project.is_sample.is_(True))):
        media_ids.update(i for i in (project.cover_image_id, project.cover_video_id) if i)
        for phase in project.phases:
            for update in phase.updates:
                media_ids.update(m.media_id for m in update.media_items)
        db.session.delete(project)
    for post in db.session.scalars(select(ContentPost).where(ContentPost.is_sample.is_(True))):
        media_ids.update(i for i in (post.cover_image_id, post.video_id) if i)
        db.session.delete(post)
    for service in db.session.scalars(select(Service).where(Service.is_sample.is_(True))):
        if service.image_id:
            media_ids.add(service.image_id)
        db.session.delete(service)
    db.session.commit()
    removed = 0
    for asset_id in media_ids:
        asset = db.session.get(MediaAsset, asset_id)
        if asset is None:
            continue
        try:
            media_service.purge(asset)
            removed += 1
        except media_service.MediaInUseError:
            pass  # reused by real content - keep it
    click.echo(f"Sample content removed ({removed} sample files deleted).")
