"""Storage backend interface.

Every backend stores opaque objects under generated keys of the form
``{public|private}/{kind}/{yyyy}/{mm}/{uuid}{suffix}``. The ``public/`` and
``private/`` prefix is the single source of truth for visibility, so a bucket
policy (or the local media route) can expose only ``public/``.
"""
from abc import ABC, abstractmethod


class StorageError(Exception):
    """A storage operation failed (network, permissions, provider error)."""


class StorageBackend(ABC):
    name = "abstract"
    #: True when files can be streamed from disk (local backend only).
    is_local = False

    @abstractmethod
    def save(self, data, key, content_type, private=False):
        """Store ``data`` (bytes or a binary file object) under ``key``."""

    @abstractmethod
    def delete(self, key):
        """Delete ``key``. Must not raise if the object is already gone."""

    @abstractmethod
    def url(self, key, private=False, expires=300):
        """Return a URL for ``key``. Private keys get a short-lived signed URL."""

    def exists(self, key):  # pragma: no cover - optional
        raise NotImplementedError

    def path_for(self, key):  # pragma: no cover - local only
        raise NotImplementedError
