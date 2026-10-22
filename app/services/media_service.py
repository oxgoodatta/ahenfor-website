"""Validated uploads, storage keys, image variants and reference-safe deletion.

Usage in a route::

    with UploadBatch() as batch:
        asset = batch.store(form.cover_image_file.data, profile="image")
        project.cover_image = asset
        db.session.commit()

If anything inside the block raises (validation, storage or database error) the
session is rolled back and every object already written to storage is deleted,
so no broken references or orphaned files are left behind.
"""
import io
import logging
import os
import uuid
from dataclasses import dataclass

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import or_, select

from app.extensions import db
from app.models import (
    Award,
    ContentPost,
    HeroConfig,
    Inquiry,
    MediaAsset,
    MediaKind,
    ProgressUpdate,
    ProgressUpdateMedia,
    Project,
    Service,
    SiteSetting,
    Testimonial,
)
from app.models.base import utcnow
from app.storage import StorageError, get_storage

log = logging.getLogger(__name__)

# Decompression-bomb guard: ~60 megapixels is far above any camera we expect.
Image.MAX_IMAGE_PIXELS = 60_000_000

MAIN_MAX_EDGE = 2400
THUMB_MAX_EDGE = 800

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
PIL_FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}
VIDEO_TYPES = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"}
DOCUMENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".dwg": "image/vnd.dwg",
}

# Which extensions each upload slot accepts.
PROFILES = {
    "image": IMAGE_EXTENSIONS,
    "video": set(VIDEO_TYPES),
    "document": {".pdf"},
    "attachment": IMAGE_EXTENSIONS | {".pdf", ".docx", ".dwg"},
}

PROFILE_HINTS = {
    "image": "JPG, PNG or WebP",
    "video": "MP4, WebM or MOV",
    "document": "PDF",
    "attachment": "PDF, DOCX, DWG, JPG or PNG",
}


class MediaValidationError(ValueError):
    """The uploaded file was rejected. The message is safe to show the admin."""


class MediaInUseError(Exception):
    def __init__(self, references):
        self.references = references
        super().__init__("This file is still used by: " + "; ".join(references))


@dataclass
class _Prepared:
    kind: MediaKind
    mime: str
    suffix: str
    main: bytes | None
    thumb: bytes | None
    stream: object
    size: int
    width: int | None = None
    height: int | None = None


def accept_attr(profile):
    """Value for an <input type=file accept=...> attribute."""
    return ",".join(sorted(PROFILES[profile]))


def _size_of(stream):
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    return size


def _limit_for(kind):
    cfg = current_app.config
    return {
        MediaKind.IMAGE: cfg["MAX_IMAGE_BYTES"],
        MediaKind.VIDEO: cfg["MAX_VIDEO_BYTES"],
        MediaKind.DOCUMENT: cfg["MAX_DOCUMENT_BYTES"],
    }[kind]


def _encode(img, fmt):
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.save(buf, "JPEG", quality=85, optimize=True, progressive=True)
    else:
        img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _resized(img, max_edge):
    if max(img.size) <= max_edge:
        return img.copy()
    copy = img.copy()
    copy.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    return copy


def _prepare_image(stream, size, make_thumb=True):
    try:
        with Image.open(stream) as probe:
            fmt = probe.format
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, ValueError):
        raise MediaValidationError("The file is not a valid image.")
    if fmt not in PIL_FORMATS:
        raise MediaValidationError("Unsupported image format. Use JPG, PNG or WebP.")
    stream.seek(0)
    try:
        img = Image.open(stream)
        img.load()
        img = ImageOps.exif_transpose(img)  # apply camera rotation, then drop EXIF (GPS etc.)
    except (OSError, Image.DecompressionBombError, ValueError):
        raise MediaValidationError("The image could not be processed.")
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    out_fmt = "PNG" if has_alpha else "JPEG"
    img = img.convert("RGBA" if has_alpha else "RGB")
    main_img = _resized(img, MAIN_MAX_EDGE)
    main = _encode(main_img, out_fmt)
    thumb = _encode(_resized(img, THUMB_MAX_EDGE), out_fmt) if make_thumb else None
    return _Prepared(
        kind=MediaKind.IMAGE,
        mime="image/png" if out_fmt == "PNG" else "image/jpeg",
        suffix=".png" if out_fmt == "PNG" else ".jpg",
        main=main,
        thumb=thumb,
        stream=None,
        size=len(main),
        width=main_img.width,
        height=main_img.height,
    )


def _sniff(stream, n=16):
    head = stream.read(n)
    stream.seek(0)
    return head


def _prepare(file_storage, profile, private):
    if profile not in PROFILES:
        raise ValueError(f"Unknown upload profile {profile!r}")
    filename = (file_storage.filename or "").strip()
    suffix = os.path.splitext(filename)[1].lower()
    if suffix not in PROFILES[profile]:
        raise MediaValidationError(f"File type not allowed. Accepted: {PROFILE_HINTS[profile]}.")

    stream = file_storage.stream
    size = _size_of(stream)
    if size == 0:
        raise MediaValidationError("The file is empty.")

    if suffix in IMAGE_EXTENSIONS:
        kind = MediaKind.IMAGE
    elif suffix in VIDEO_TYPES:
        kind = MediaKind.VIDEO
    else:
        kind = MediaKind.DOCUMENT
    limit = _limit_for(kind)
    if size > limit:
        raise MediaValidationError(f"The file is too large. Maximum size is {limit // (1024 * 1024)} MB.")

    if kind == MediaKind.IMAGE:
        return _prepare_image(stream, size, make_thumb=not private)

    head = _sniff(stream)
    if kind == MediaKind.VIDEO:
        valid = head[4:8] == b"ftyp" if suffix in (".mp4", ".mov") else head[:4] == b"\x1a\x45\xdf\xa3"
        if not valid:
            raise MediaValidationError("The file is not a valid video.")
        return _Prepared(kind, VIDEO_TYPES[suffix], suffix, None, None, stream, size)

    signatures = {".pdf": b"%PDF-", ".docx": b"PK\x03\x04", ".dwg": b"AC10"}
    if not head.startswith(signatures[suffix]):
        raise MediaValidationError("The document content does not match its file type.")
    return _Prepared(kind, DOCUMENT_TYPES[suffix], suffix, None, None, stream, size)


def _new_key(kind, suffix, private):
    now = utcnow()
    scope = "private" if private else "public"
    return f"{scope}/{kind.value}/{now:%Y}/{now:%m}/{uuid.uuid4().hex}{suffix}"


def _safe_display_name(filename):
    name = os.path.basename((filename or "").replace("\\", "/")).strip()
    name = "".join(ch for ch in name if ch.isprintable())
    return name[:200] or None


class UploadBatch:
    """Unit of work for uploads. See module docstring."""

    def __init__(self):
        self.stored_keys = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            db.session.rollback()
            self.cleanup()
        return False

    def cleanup(self):
        storage = get_storage()
        for key in self.stored_keys:
            try:
                storage.delete(key)
            except StorageError:
                log.exception("Could not remove orphaned upload %s", key)
        self.stored_keys = []

    def store(self, file_storage, profile="image", private=False, alt_text="", caption="", user=None):
        if not file_storage or not getattr(file_storage, "filename", ""):
            raise MediaValidationError("No file was selected.")
        prepared = _prepare(file_storage, profile, private)
        storage = get_storage()
        key = _new_key(prepared.kind, prepared.suffix, private)
        thumb_key = None
        try:
            storage.save(prepared.main if prepared.main is not None else prepared.stream,
                         key, prepared.mime, private=private)
            self.stored_keys.append(key)
            if prepared.thumb is not None:
                thumb_key = key.rsplit(".", 1)[0] + "_thumb" + prepared.suffix
                storage.save(prepared.thumb, thumb_key, prepared.mime, private=private)
                self.stored_keys.append(thumb_key)
        except StorageError as exc:
            raise MediaValidationError(
                "The file could not be saved to media storage. Please try again."
            ) from exc

        asset = MediaAsset(
            kind=prepared.kind,
            storage_provider=storage.name,
            storage_key=key,
            thumb_key=thumb_key,
            mime_type=prepared.mime,
            size_bytes=prepared.size,
            width=prepared.width,
            height=prepared.height,
            original_filename=_safe_display_name(file_storage.filename),
            alt_text=(alt_text or "")[:255],
            caption=(caption or "")[:300],
            is_private=private,
            uploaded_by_id=getattr(user, "id", None),
        )
        db.session.add(asset)
        db.session.flush()
        return asset


# ---------------------------------------------------------------------------
# Selecting existing media
# ---------------------------------------------------------------------------

def get_selectable(asset_id, kind):
    """Return a public, non-archived asset of ``kind`` or raise MediaValidationError."""
    try:
        asset_id = int(asset_id)
    except (TypeError, ValueError):
        raise MediaValidationError("Invalid media selection.")
    asset = db.session.get(MediaAsset, asset_id)
    if asset is None or asset.is_private or asset.kind != kind:
        raise MediaValidationError("The selected media item is not available.")
    return asset


def resolve_media_field(batch, file_storage, selected_id, kind, profile=None, user=None, alt_text=""):
    """Resolve a media form slot: a new upload wins, else the selected library id, else None.

    An archived asset that is *already* selected stays valid (archiving hides it
    from the picker without breaking existing pages).
    """
    if file_storage and getattr(file_storage, "filename", ""):
        return batch.store(file_storage, profile=profile or kind.value, user=user, alt_text=alt_text)
    if selected_id not in (None, "", "0"):
        return get_selectable(selected_id, kind)
    return None


# ---------------------------------------------------------------------------
# References and deletion
# ---------------------------------------------------------------------------

def references(asset):
    """Human-readable list of every record that uses ``asset``."""
    aid = asset.id
    refs = []

    def add(rows, label):
        refs.extend(label(r) for r in rows)

    session = db.session
    add(session.scalars(select(Project).where(or_(Project.cover_image_id == aid, Project.cover_video_id == aid))),
        lambda p: f"Project cover: {p.name}")
    add(session.scalars(select(ProgressUpdateMedia).where(ProgressUpdateMedia.media_id == aid)),
        lambda m: f"Progress photo: {m.update.project.name} / {m.update.title}")
    add(session.scalars(select(ProgressUpdate).where(ProgressUpdate.video_id == aid)),
        lambda u: f"Progress video: {u.project.name} / {u.title}")
    add(session.scalars(select(ContentPost).where(or_(ContentPost.cover_image_id == aid, ContentPost.video_id == aid))),
        lambda p: f"News/event: {p.title}")
    add(session.scalars(select(Service).where(Service.image_id == aid)), lambda s: f"Service: {s.name}")
    add(session.scalars(select(Award).where(or_(Award.image_id == aid, Award.document_id == aid))),
        lambda a: f"Award: {a.title}")
    add(session.scalars(select(Testimonial).where(Testimonial.portrait_id == aid)),
        lambda t: f"Testimonial: {t.client_name}")
    add(session.scalars(select(HeroConfig).where(
        or_(HeroConfig.image_id == aid, HeroConfig.video_id == aid, HeroConfig.poster_id == aid))),
        lambda h: f"Homepage hero ({h.state})")
    add(session.scalars(select(Inquiry).where(Inquiry.attachment_id == aid)),
        lambda i: f"Inquiry attachment from {i.full_name}")

    from app.services.settings_service import MEDIA_SETTING_KEYS

    add(session.scalars(select(SiteSetting).where(SiteSetting.key.in_(MEDIA_SETTING_KEYS),
                                                  SiteSetting.value == str(aid))),
        lambda s: f"Site setting: {s.key.replace('_', ' ')}")
    return refs


def purge(asset):
    """Permanently delete an unreferenced asset (database row first, then storage)."""
    refs = references(asset)
    if refs:
        raise MediaInUseError(refs)
    keys = [k for k in (asset.storage_key, asset.thumb_key) if k]
    db.session.delete(asset)
    db.session.commit()
    storage = get_storage()
    for key in keys:
        try:
            storage.delete(key)
        except StorageError:
            # The DB row is gone, so nothing references the file; log for cleanup.
            log.exception("Stored object %s could not be deleted", key)
