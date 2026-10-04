from uuid import uuid4

from app.core.config import Settings


class S3MediaStorage:
    def __init__(self, settings: Settings):
        self._settings = settings

    def put(self, key: str, content: bytes, content_type: str) -> None:
        import boto3

        client = boto3.client("s3", endpoint_url=str(self._settings.s3_endpoint), region_name="us-east-1")
        client.put_object(Bucket=self._settings.s3_bucket, Key=key, Body=content, ContentType=content_type)


def media_key(filename: str) -> str:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"media/{uuid4()}.{suffix}"
