import os
import boto3
import logging
import multiprocessing
from django.conf import settings
from django.core.management.base import BaseCommand

# Logging Setup
LOG_FILE = os.path.join(settings.BASE_DIR, 'logs',"sync_media_r2.log")
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# AWS S3 Client for Cloudflare R2
session = boto3.session.Session()
s3 = session.client(
    "s3",
    endpoint_url=settings.R2_ENDPOINT_URL,
    aws_access_key_id=settings.R2_ACCESS_KEY_ID,
    aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY
)

# Optimized for a 5-core server: Use 4 parallel uploads
NUM_WORKERS = 10 # Keep 1 core free for other tasks

# Function to Upload a Single File
def upload_file(file_path):
    try:
        # Convert local path to S3 key (ensure media/ prefix is included)
        relative_path = os.path.relpath(file_path, settings.MEDIA_ROOT)
        s3_key = f"media/{relative_path}"

        # Skip if file already exists in Cloudflare R2
        try:
            s3.head_object(Bucket=settings.R2_BUCKET_NAME, Key=s3_key)
            logging.info(f"Skipped (already exists): {s3_key}")
            return
        except:
            pass  # Proceed if file doesn't exist

        # Upload file
        s3.upload_file(file_path, settings.R2_BUCKET_NAME, s3_key, ExtraArgs={'ACL': 'private'})
        logging.info(f"Uploaded: {s3_key}")

    except Exception as e:
        logging.error(f"Failed: {file_path} -> {e}")

class Command(BaseCommand):
    help = "Sync media files to Cloudflare R2 in the background"

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("Starting media sync to Cloudflare R2..."))

        # Collect all files in the media directory
        media_files = []
        for root, _, files in os.walk(settings.MEDIA_ROOT):
            for file in files:
                media_files.append(os.path.join(root, file))

        self.stdout.write(self.style.SUCCESS(f"Found {len(media_files)} files to upload..."))

        # Use multiprocessing (optimized for 5-core CPU)
        with multiprocessing.Pool(processes=NUM_WORKERS) as pool:
            pool.map(upload_file, media_files)

        self.stdout.write(self.style.SUCCESS("✅ Media sync completed successfully! Check logs for details."))
