"""S3-compatible storage adapter (AWS S3, MinIO, etc.)."""

import asyncio
import logging
from functools import partial
from uuid import UUID

import boto3
from botocore.exceptions import ClientError

from app.ports.storage import StoragePort

logger = logging.getLogger(__name__)


class S3StorageAdapter(StoragePort):
    """Store book files in S3-compatible object storage."""

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
    ) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        self._bucket = bucket
        self._ensure_bucket()
        logger.info("S3Storage initialized: bucket=%s, endpoint=%s", bucket, endpoint_url)

    def _ensure_bucket(self) -> None:
        """Create the bucket if it doesn't exist."""
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)
            logger.info("Created S3 bucket: %s", self._bucket)

    async def save(self, file_id: UUID, content: bytes, extension: str) -> str:
        """Upload file to S3. Returns the object key."""
        key = f"books/{file_id}.{extension}"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            partial(
                self._client.put_object,
                Bucket=self._bucket,
                Key=key,
                Body=content,
            ),
        )
        logger.info("Uploaded to S3: %s (%d bytes)", key, len(content))
        return key

    async def read(self, path: str) -> bytes:
        """Download file from S3."""
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            partial(self._client.get_object, Bucket=self._bucket, Key=path),
        )
        content = resp["Body"].read()
        logger.debug("Downloaded from S3: %s (%d bytes)", path, len(content))
        return content

    async def delete(self, path: str) -> None:
        """Delete file from S3."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            partial(
                self._client.delete_object,
                Bucket=self._bucket,
                Key=path,
            ),
        )
        logger.info("Deleted from S3: %s", path)
