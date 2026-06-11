import os
import aiosqlite
from config import DB_PATH


def _ensure_db_dir():
    """Создаёт директорию для файла БД, если её нет."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL,
    channel_title TEXT,
    added_by INTEGER NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(channel_id, added_by)
);

CREATE TABLE IF NOT EXISTS invite_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    link TEXT UNIQUE NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER DEFAULT 1,
    FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
);

CREATE TABLE IF NOT EXISTS link_joins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (link_id) REFERENCES invite_links(id)
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_blocked INTEGER DEFAULT 0
);
"""

async def init_db():
    _ensure_db_dir()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES)
        await db.commit()

# Миграция — добавляем таблицу креативов если её нет
ADD_CREATIVES_TABLE = """
CREATE TABLE IF NOT EXISTS creatives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    template TEXT NOT NULL,
    photo_file_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, name)
);
"""

# Миграция — добавляем колонку photo_file_id к существующей таблице creatives
ADD_PHOTO_COLUMN = """
ALTER TABLE creatives ADD COLUMN photo_file_id TEXT;
"""

async def migrate_db():
    """Применяет новые миграции к существующей БД."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(ADD_CREATIVES_TABLE)

        # Добавляем photo_file_id если колонки ещё нет
        async with db.execute("PRAGMA table_info(creatives)") as cur:
            columns = [row[1] for row in await cur.fetchall()]
        if "photo_file_id" not in columns:
            await db.execute(ADD_PHOTO_COLUMN)

        await db.commit()
