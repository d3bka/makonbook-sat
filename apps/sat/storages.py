from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings


class PublicStorage(S3Boto3Storage):
    """Public storage for images and public files with Cloudflare R2"""
    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    custom_domain = settings.AWS_S3_CUSTOM_DOMAIN
    file_overwrite = False
    default_acl = None
    querystring_auth = False
    location = "media"

    def url(self, name, parameters=None, expire=None, http_method=None):
        clean_name = str(name).lstrip("/")
        return f"https://{settings.AWS_S3_CUSTOM_DOMAIN}/media/{clean_name}"


class PrivateStorage(S3Boto3Storage):
    """Private storage for sensitive files with signed URLs"""
    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    custom_domain = None
    file_overwrite = False
    default_acl = None
    querystring_auth = True
    location = "private"