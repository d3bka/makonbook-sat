import boto3
from django.core.management.base import BaseCommand
from django.conf import settings
from botocore.exceptions import ClientError

class Command(BaseCommand):
    help = 'Check if a specific file exists in Cloudflare R2'

    def add_arguments(self, parser):
        parser.add_argument('key', type=str, help='The R2 key to check (e.g., sat/question_images/Screenshot_2025-03-15_201917.png)')

    def handle(self, *args, **options):
        key = options['key']

        # Cloudflare R2 client setup
        r2_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            endpoint_url=settings.AWS_S3_ENDPOINT_URL
        )

        # Check if the file exists in R2
        try:
            response = r2_client.head_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=key)
            self.stdout.write(self.style.SUCCESS(f"File exists in R2: {key} (Size: {response['ContentLength']} bytes, Last Modified: {response['LastModified']})"))
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                self.stdout.write(self.style.ERROR(f"File does not exist in R2: {key}"))
            else:
                self.stdout.write(self.style.ERROR(f"Error checking R2 for {key}: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Unexpected error: {e}"))