import os

BOT_TOKEN = "8620210758:AAHpPYAPUWJ0F4lCBXKVUHDnXGapdgggW8E"
ADMIN_ID = 7416327364

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SONGS_DIR = os.path.join(BASE_DIR, "songs")
DB_PATH = os.path.join(BASE_DIR, "music_bot.db")
LOG_FILE = os.path.join(BASE_DIR, "bot.log")
