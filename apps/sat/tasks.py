import os
import boto3
import subprocess
from celery import shared_task
from django.conf import settings
from .models import Video

@shared_task
def convert_video_to_hls(video_id):
    """ Converts an uploaded MP4 video to HLS (.m3u8) and uploads to Cloudflare R2 """
    video = Video.objects.get(id=video_id)

    # Mark as converting
    video.conversion_status = "converting"
    video.save()

    try:
        # Local paths
        local_mp4_path = video.video_file.path
        local_hls_path = local_mp4_path.replace(".mp4", ".m3u8")
        local_ts_path = local_mp4_path.replace(".mp4", "_%03d.ts")

        # Convert to HLS using FFmpeg
        ffmpeg_cmd = [
            "ffmpeg", "-i", local_mp4_path, "-codec:", "copy",
            "-start_number", "0", "-hls_time", "10", "-hls_list_size", "0",
            "-f", "hls", local_hls_path
        ]
        subprocess.run(ffmpeg_cmd, check=True)

        # Upload HLS files to Cloudflare R2
        s3_client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        # Upload `.m3u8` file
        s3_client.upload_file(local_hls_path, settings.AWS_STORAGE_BUCKET_NAME, f"videos/hls/{os.path.basename(local_hls_path)}")

        # Upload `.ts` files
        for ts_file in os.listdir(os.path.dirname(local_hls_path)):
            if ts_file.endswith(".ts"):
                s3_client.upload_file(os.path.join(os.path.dirname(local_hls_path), ts_file),
                                      settings.AWS_STORAGE_BUCKET_NAME, f"videos/hls/{ts_file}")

        # Save HLS URL
        video.hls_url = f"{settings.AWS_S3_ENDPOINT_URL}/{settings.AWS_STORAGE_BUCKET_NAME}/videos/hls/{os.path.basename(local_hls_path)}"
        video.conversion_status = "completed"
        video.save()

        # Remove local files
        os.remove(local_mp4_path)
        os.remove(local_hls_path)

    except Exception as e:
        video.conversion_status = "failed"
        video.save()
        print(f"Error converting video {video.title}: {e}")
