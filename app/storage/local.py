"""Filesystem storage for development (and, explicitly opted in, a backed-up VPS disk).

Local uploads are NOT durable on platforms with ephemeral disks (Render, Heroku).
"""
import io
import os
from pathlib import Path

from flask import url_for

from app.storage.base import StorageBackend, StorageError


class LocalStorage(StorageBackend):
    name = "local"
    is_local = True

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key):
        if not key or "\\" in key or key.startswith("/"):
            raise StorageError("Invalid storage key.")
        path = (self.root / key).resolve()
        if os.path.commonpath([str(path), str(self.root)]) != str(self.root) or path == self.root:
            raise StorageError("Invalid storage key.")
        return path

    def save(self, data, key, content_type, private=False):
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        stream = io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data
        try:
            with open(tmp, "wb") as fh:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
            os.replace(tmp, path)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise StorageError(f"Could not write file: {exc.strerror}") from exc

    def delete(self, key):
        try:
            self.path_for(key).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError(f"Could not delete file: {exc.strerror}") from exc

    def exists(self, key):
        return self.path_for(key).is_file()

    def url(self, key, private=False, expires=300):
        if private or not key.startswith("public/"):
            raise StorageError("Private local files are served through authenticated admin routes.")
        return url_for("public.media_file", key=key)
