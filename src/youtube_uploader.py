"""آپلود ویدیو روی یوتیوب با استفاده از YouTube Data API v3."""

import logging
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
_TOKEN_FILE = os.getenv("YOUTUBE_TOKEN_FILE", "youtube_token.json")
_CLIENT_SECRETS = os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secrets.json")


def get_youtube_service():
    """سرویس احراز‌هویت‌شده YouTube برمی‌گرداند."""
    if not os.path.exists(_TOKEN_FILE):
        raise FileNotFoundError(
            f"فایل توکن یوتیوب '{_TOKEN_FILE}' پیدا نشد. "
            "اول اسکریپت youtube_auth.py را اجرا کن."
        )
    creds = Credentials.from_authorized_user_file(_TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def upload_short(
    video_path: str,
    title: str,
    description: str,
    hashtags: list[str],
    tags: list[str],
    category_id: str = "22",
    privacy: str = "public",
) -> str:
    """ویدیو رو به عنوان YouTube Short آپلود می‌کنه و لینک شورت رو برمی‌گردونه."""
    youtube = get_youtube_service()

    hashtag_text = " ".join(h if h.startswith("#") else f"#{h}" for h in hashtags)
    full_description = f"{description}\n\n{hashtag_text} #Shorts"

    all_tags = list(tags) + ["Shorts"]

    body = {
        "snippet": {
            "title": title,
            "description": full_description,
            "tags": all_tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, mimetype="video/*", resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            log.info("آپلود: %d%%", pct)

    video_id = response["id"]
    log.info("آپلود کامل شد: %s", video_id)
    return f"https://youtube.com/shorts/{video_id}"
