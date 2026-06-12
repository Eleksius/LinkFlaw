"""
Простое персистентное FSM-хранилище на SQLite для aiogram 3.
Заменяет MemoryStorage — данные выживают перезапуски бота.
"""
import json
import logging
from typing import Any, Optional

import aiosqlite
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType

from config import DB_PATH

logger = logging.getLogger(__name__)


class SQLiteStorage(BaseStorage):
    """FSM-хранилище поверх существующей SQLite БД проекта."""

    async def _ensure_table(self, db: aiosqlite.Connection) -> None:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fsm_storage (
                key  TEXT PRIMARY KEY,
                state TEXT,
                data  TEXT NOT NULL DEFAULT '{}'
            )
        """)
        await db.commit()

    @staticmethod
    def _key(storage_key: StorageKey) -> str:
        return f"{storage_key.bot_id}:{storage_key.chat_id}:{storage_key.user_id}"

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        state_str = state.state if isinstance(state, State) else state
        async with aiosqlite.connect(DB_PATH) as db:
            await self._ensure_table(db)
            await db.execute("""
                INSERT INTO fsm_storage (key, state, data) VALUES (?, ?, '{}')
                ON CONFLICT(key) DO UPDATE SET state = excluded.state
            """, (self._key(key), state_str))
            await db.commit()

    async def get_state(self, key: StorageKey) -> Optional[str]:
        async with aiosqlite.connect(DB_PATH) as db:
            await self._ensure_table(db)
            async with db.execute(
                "SELECT state FROM fsm_storage WHERE key = ?", (self._key(key),)
            ) as cur:
                row = await cur.fetchone()
        return row[0] if row else None

    async def set_data(self, key: StorageKey, data: dict[str, Any]) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            await self._ensure_table(db)
            await db.execute("""
                INSERT INTO fsm_storage (key, state, data) VALUES (?, NULL, ?)
                ON CONFLICT(key) DO UPDATE SET data = excluded.data
            """, (self._key(key), json.dumps(data, ensure_ascii=False)))
            await db.commit()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with aiosqlite.connect(DB_PATH) as db:
            await self._ensure_table(db)
            async with db.execute(
                "SELECT data FROM fsm_storage WHERE key = ?", (self._key(key),)
            ) as cur:
                row = await cur.fetchone()
        return json.loads(row[0]) if row and row[0] else {}

    async def close(self) -> None:
        pass  # aiosqlite открывает соединения per-query, закрывать нечего
