"""
اجرا کن تا ربات به یوتیوب وصل بشه (فقط یک‌بار لازمه).

روی سرور (VPS):
  1. در ترمینال لوکال خودت این دستور رو بزن:
       ssh -L 8080:localhost:8080 root@IP_سرور_تو
  2. در همون پنجره SSH:
       python youtube_auth.py
  3. لینکی که چاپ می‌شه رو در مرورگر لوکالت باز کن
  4. تأیید کن — تموم!
"""

import os
import sys

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS = os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secrets.json")
TOKEN_FILE = os.getenv("YOUTUBE_TOKEN_FILE", "youtube_token.json")
PORT = int(os.getenv("YOUTUBE_AUTH_PORT", "8080"))


def main() -> None:
    if not os.path.exists(CLIENT_SECRETS):
        print(
            f"❌ فایل '{CLIENT_SECRETS}' پیدا نشد.\n\n"
            "مراحل:\n"
            "  1. console.cloud.google.com رو باز کن\n"
            "  2. APIs & Services → Credentials\n"
            "  3. + Create Credentials → OAuth client ID → Desktop app\n"
            "  4. فایل JSON رو دانلود کن و اسمش رو 'client_secrets.json' بذار\n"
            "  5. این فایل رو آپلود کن کنار bot.py روی سرور"
        )
        sys.exit(1)

    print("=" * 60)
    print("🔐 احراز هویت یوتیوب")
    print("=" * 60)
    print(f"\n📡 سرور روی پورت {PORT} منتظره...\n")
    print("⚠️  اگه روی سرور (VPS) هستی:")
    print(f"    در ترمینال لوکال بزن:")
    print(f"    ssh -L {PORT}:localhost:{PORT} root@IP_سرورت\n")
    print("    بعد این اسکریپت رو اجرا کن.")
    print("    لینکی که چاپ می‌شه رو در مرورگر لوکالت باز کن.\n")
    print("-" * 60)

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
    creds = flow.run_local_server(
        port=PORT,
        open_browser=False,
        success_message="✅ تأیید شد! این پنجره رو ببند و به ترمینال برگرد.",
    )

    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    print(f"\n✅ احراز هویت موفق!")
    print(f"📄 توکن در '{TOKEN_FILE}' ذخیره شد.")
    print("🚀 حالا می‌تونی ربات رو با  python bot.py  اجرا کنی.\n")


if __name__ == "__main__":
    main()
