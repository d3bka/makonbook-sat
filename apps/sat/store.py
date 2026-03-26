from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings

class PublicStorage(S3Boto3Storage):
    location = "media"
    default_acl = "public-read"
    file_overwrite = False
    custom_domain = None
    querystring_auth = False

class PrivateStorage(S3Boto3Storage):
    """ Private storage for videos (Only accessible via signed URLs) """
    location = "videos"
    default_acl = "private"  # Videos are private
    file_overwrite = False
    custom_domain = None  # No direct URL access
