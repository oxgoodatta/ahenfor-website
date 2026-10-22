"""Cloudinary storage. Requires ``pip install cloudinary``.

Public assets use delivery type ``upload``; private assets use ``authenticated``
and are delivered through signed URLs.
"""
import io

from app.storage.base import StorageBackend, StorageError


def _resource_type(key):
    # keys look like public/image/2026/10/<uuid>.jpg
    parts = key.split("/")
    kind = parts[1] if len(parts) > 1 else ""
    return {"image": "image", "video": "video"}.get(kind, "raw")


def _public_id(key):
    # Cloudinary appends the format itself for image/video resources.
    if _resource_type(key) == "raw":
        return key
    return key.rsplit(".", 1)[0]


class CloudinaryStorage(StorageBackend):
    name = "cloudinary"

    def __init__(self, config):
        try:
            import cloudinary
        except ImportError as exc:  # pragma: no cover
            raise StorageError("Install the 'cloudinary' package for MEDIA_STORAGE_PROVIDER=cloudinary") from exc
        cloudinary.config(
            cloud_name=config["CLOUDINARY_CLOUD_NAME"],
            api_key=config["CLOUDINARY_API_KEY"],
            api_secret=config["CLOUDINARY_API_SECRET"],
            secure=True,
        )

    def save(self, data, key, content_type, private=False):
        import cloudinary.uploader

        stream = io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data
        try:
            cloudinary.uploader.upload(
                stream,
                public_id=_public_id(key),
                resource_type=_resource_type(key),
                type="authenticated" if private else "upload",
                overwrite=False,
                unique_filename=False,
                use_filename=False,
            )
        except Exception as exc:  # cloudinary raises its own Error subclasses
            raise StorageError("Upload to Cloudinary failed.") from exc

    def delete(self, key):
        import cloudinary.uploader

        private = key.startswith("private/")
        try:
            cloudinary.uploader.destroy(
                _public_id(key),
                resource_type=_resource_type(key),
                type="authenticated" if private else "upload",
                invalidate=True,
            )
        except Exception as exc:
            raise StorageError("Delete from Cloudinary failed.") from exc

    def url(self, key, private=False, expires=300):
        from cloudinary.utils import cloudinary_url

        private = private or key.startswith("private/")
        fmt = None if _resource_type(key) == "raw" else key.rsplit(".", 1)[-1]
        url, _ = cloudinary_url(
            _public_id(key),
            resource_type=_resource_type(key),
            type="authenticated" if private else "upload",
            sign_url=private,
            format=fmt,
            secure=True,
        )
        return url
