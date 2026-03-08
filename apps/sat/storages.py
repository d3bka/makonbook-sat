from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings


class PublicStorage(S3Boto3Storage):
    """Public storage for images and public files with Cloudflare R2"""
    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    custom_domain = None
    file_overwrite = False
    default_acl = None  # R2 handles this
    querystring_auth = False  # Public files don't need signed URLs
    location = 'media'  # Organize files in media folder
    
    def __init__(self, **settings):
        super().__init__(**settings)
        self.signature_version = 's3v4'
        self.addressing_style = 'virtual'


class PrivateStorage(S3Boto3Storage):
    """Private storage for sensitive files with signed URLs"""
    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    custom_domain = None
    file_overwrite = False
    default_acl = None
    querystring_auth = True  # Enable signed URLs for private files
    location = 'private'  # Organize private files separately
    
    def __init__(self, **settings):
        super().__init__(**settings)
        self.signature_version = 's3v4'
        self.addressing_style = 'virtual'