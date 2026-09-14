import io
from datetime import timedelta
from typing import Optional
import urllib3
from minio import Minio
from minio.error import S3Error

from app.core.config import settings
from app.core.logging_config import logger


class StorageService:
    def __init__(self) -> None:
        endpoint = settings.MINIO_ENDPOINT_URL.replace("http://", "").replace("https://", "")
        self.bucket = settings.MINIO_BUCKET
        self._connected = False
        try:
            # Configure fast timeout for dev/testing when MinIO is offline
            http_client = urllib3.PoolManager(
                timeout=urllib3.Timeout(connect=0.5, read=2.0),
                retries=False,
            )
            self.client = Minio(
                endpoint,
                access_key=settings.MINIO_ROOT_USER,
                secret_key=settings.MINIO_ROOT_PASSWORD,
                secure=settings.MINIO_ENDPOINT_URL.startswith("https"),
                http_client=http_client,
            )
        except Exception as e:
            logger.warning(f"MinIO client initialization warning: {e}")
            self.client = None

    def ensure_bucket_exists(self) -> bool:
        if not self.client:
            return False
        if self._connected:
            return True
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
            self._connected = True
            return True
        except Exception as e:
            logger.info(f"MinIO storage offline, operating in simulated storage mode: {e}")
            self.client = None
            return False

    def upload_evidence(
        self,
        event_nonce: str,
        file_bytes: bytes,
        content_type: str = "video/mp4",
    ) -> str:
        """Upload evidence clip to MinIO and return storage_ref."""
        object_name = f"evidence/{event_nonce}.mp4"
        if not self.client or not self.ensure_bucket_exists():
            # Simulated storage ref when MinIO container is offline
            return f"minio://{self.bucket}/{object_name}"

        try:
            data_stream = io.BytesIO(file_bytes)
            self.client.put_object(
                bucket_name=self.bucket,
                object_name=object_name,
                data=data_stream,
                length=len(file_bytes),
                content_type=content_type,
            )
            return f"minio://{self.bucket}/{object_name}"
        except Exception as e:
            logger.error(f"Error uploading evidence for nonce {event_nonce}: {e}")
            return f"minio://{self.bucket}/{object_name}"

    def get_presigned_url(self, storage_ref: str, expires_hours: int = 24) -> str:
        """Generate presigned download URL for evidence clip."""
        if not storage_ref:
            return ""
        if not self.client or not self._connected:
            return storage_ref

        object_name = storage_ref.replace(f"minio://{self.bucket}/", "")
        try:
            url = self.client.presigned_get_object(
                bucket_name=self.bucket,
                object_name=object_name,
                expires=timedelta(hours=expires_hours),
            )
            return url
        except Exception as e:
            logger.warning(f"Failed to generate presigned URL for {storage_ref}: {e}")
            return storage_ref

    def get_evidence_bytes(self, storage_ref: str) -> tuple[Optional[bytes], str]:
        """Fetch raw bytes and content type for evidence clip."""
        if not storage_ref or not self.client or not self._connected:
            return None, "video/mp4"

        object_name = storage_ref.replace(f"minio://{self.bucket}/", "")
        try:
            response = self.client.get_object(self.bucket, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            content_type = "video/mp4"
            if object_name.endswith(".jpg") or object_name.endswith(".jpeg"):
                content_type = "image/jpeg"
            elif object_name.endswith(".png"):
                content_type = "image/png"
            return data, content_type
        except Exception as e:
            logger.warning(f"Failed to fetch evidence bytes for {storage_ref}: {e}")
            return None, "video/mp4"


storage_service = StorageService()
