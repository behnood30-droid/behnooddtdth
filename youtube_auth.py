"""اجرا کن تا ربات به یوتیوب وصل بشه (فقط یک‌بار لازمه)."""

import os

from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS = os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secrets.json")
TOKEN_FILE = os.getenv("YOUTUBE_TOKEN_FILE", "youtube_token.json")


def main() -> None:
    if not os.path.exists(CLIENT_SECRETS):
        print(
            f"❌ فایل '{CLIENT_SECRETS}' پیدا نشد.\n"
            "از Google Cloud Console > APIs & Services > Credentials\n"
            "یه OAuth 2.0 Client ID بساز (نوع Desktop) و فایل JSON رو دانلود کن."
        )
        return

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
    creds = flow.run_local_server(port=8080, open_browser=True)

    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    print(f"✅ احراز هویت موفق! توکن در '{TOKEN_FILE}' ذخیره شد.")


if __name__ == "__main__":
    main()
