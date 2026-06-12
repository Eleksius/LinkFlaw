import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []
DB_PATH = os.getenv("DB_PATH", "bot.db")

# Для будущего расширения (PostgreSQL, Redis и т.д.)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DB_PATH}")


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
