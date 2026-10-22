"""Amazon S3 and S3-compatible storage (Cloudflare R2, DigitalOcean Spaces, MinIO).

Bucket setup: allow public GET on the ``public/`` prefix only (bucket policy or a
public custom domain) and keep ``private/`` private. Private objects are served
with short-lived presigned URLs.
"""
import io
from urllib.parse import quote

from app.storage.base import StorageBackend, StorageError


class S3Storage(StorageBackend):
    name = "s3"

    def __init__(self, config):
        try:
            import boto3
            from botocore.config import Config as BotoConfig
        except ImportError as exc:  # pragma: no cover
            raise StorageError("boto3 is required for MEDIA_STORAGE_PROVIDER=s3") from exc

        self.bucket = config["AWS_S3_BUCKET"]
        self.region = config.get("AWS_REGION")
        self.endpoint = config.get("S3_ENDPOINT_URL")
        self.client = boto3.client(
            "s3",
            region_name=self.region,
            endpoint_url=self.endpoint,
            aws_access_key_id=config.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=config.get("AWS_SECRET_ACCESS_KEY"),
            config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 3}),
        )
        base = config.get("MEDIA_PUBLIC_BASE_URL")
        if not base:
            if self.endpoint:
                base = f"{self.endpoint.rstrip('/')}/{self.bucket}"
            else:
                region = self.region or "us-east-1"
                base = f"https://{self.bucket}.s3.{region}.amazonaws.com"
        self.public_base = base.rstrip("/")

    def save(self, data, key, content_type, private=False):
        from botocore.exceptions import BotoCoreError, ClientError

        stream = io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data
        extra = {
            "ContentType": content_type,
            "CacheControl": "private, no-store" if private else "public, max-age=31536000, immutable",
        }
        try:
            self.client.upload_fileobj(stream, self.bucket, key, ExtraArgs=extra)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Upload to object storage failed.") from exc

    def delete(self, key):
        from botocore.exceptions import BotoCoreError, ClientError

        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("Delete from object storage failed.") from exc

    def exists(self, key):
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def url(self, key, private=False, expires=300):
        if private or not key.startswith("public/"):
            return self.client.generate_presigned_url(
                "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires
            )
        return f"{self.public_base}/{quote(key)}"
