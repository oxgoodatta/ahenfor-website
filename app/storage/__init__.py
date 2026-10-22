from flask import current_app

from app.storage.base import StorageBackend, StorageError  # noqa: F401


def build_storage(app):
    provider = app.config["MEDIA_STORAGE_PROVIDER"]
    if provider == "local":
        from app.storage.local import LocalStorage

        return LocalStorage(app.config["LOCAL_MEDIA_ROOT"])
    if provider == "s3":
        from app.storage.s3 import S3Storage

        return S3Storage(app.config)
    if provider == "cloudinary":
        from app.storage.cloudinary_backend import CloudinaryStorage

        return CloudinaryStorage(app.config)
    raise RuntimeError(f"Unknown MEDIA_STORAGE_PROVIDER: {provider!r}")


def get_storage():
    return current_app.extensions["media_storage"]
