from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings

class PublicStorage(S3Boto3Storage):
    """ Public storage for images & assets (Question Images, Profile Pics, etc.) """
    location = "media"
    default_acl = "public-read"  # Make images public
    file_overwrite = False
    custom_domain = None

class PrivateStorage(S3Boto3Storage):
    """ Private storage for videos (Only accessible via signed URLs) """
    location = "videos"
    default_acl = "private"  # Videos are private
    file_overwrite = False
    custom_domain = None  # No direct URL access
