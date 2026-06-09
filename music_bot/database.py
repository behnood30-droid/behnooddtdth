import aiosqlite
from config import DB_PATH


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS songs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                artist      TEXT NOT NULL,
                description TEXT,
                file_id     TEXT NOT NULL,
                file_path   TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                title    TEXT NOT NULL,
                link     TEXT NOT NULL
            )
        """)
        await db.commit()


async def add_song(
    title: str,
    artist: str,
    description: str | None,
    file_id: str,
    file_path: str | None,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO songs (title, artist, description, file_id, file_path) VALUES (?, ?, ?, ?, ?)",
            (title, artist, description, file_id, file_path),
        )
        await db.commit()
        return cursor.lastrowid


async def get_song(song_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM songs WHERE id = ?", (song_id,)) as cur:
            return await cur.fetchone()


async def get_all_songs():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM songs ORDER BY created_at DESC") as cur:
            return await cur.fetchall()


async def delete_song(song_id: int) -> str | None:
    """Delete song and return its file_path, or None if not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM songs WHERE id = ?", (song_id,)) as cur:
            song = await cur.fetchone()
        if not song:
            return None
        await db.execute("DELETE FROM songs WHERE id = ?", (song_id,))
        await db.commit()
        return song["file_path"]


async def add_channel(username: str, title: str, link: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO channels (username, title, link) VALUES (?, ?, ?)",
                (username, title, link),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def get_channels():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channels ORDER BY id") as cur:
            return await cur.fetchall()


async def remove_channel(username: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM channels WHERE username = ?", (username,))
        await db.commit()
        return cursor.rowcount > 0
