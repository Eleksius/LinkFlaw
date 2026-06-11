import aiosqlite
from config import DB_PATH


# ── Users ──────────────────────────────────────────────────────────────

async def upsert_user(user_id: int, username: str, first_name: str, last_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                last_activity = CURRENT_TIMESTAMP
        """, (user_id, username, first_name, last_name))
        await db.commit()


async def get_all_users(skip_blocked: bool = True):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM users"
        if skip_blocked:
            query += " WHERE is_blocked = 0"
        async with db.execute(query) as cursor:
            return await cursor.fetchall()


async def get_user_count():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            row = await cur.fetchone()
            return row[0]


# ── Channels ───────────────────────────────────────────────────────────

async def add_channel(channel_id: int, title: str, added_by: int):
    async with aiosqlite.connect(DB_PATH) as db:
        # Канал уникален в разрезе пользователя — один канал могут добавить разные пользователи
        await db.execute("""
            INSERT INTO channels (channel_id, channel_title, added_by)
            VALUES (?, ?, ?)
            ON CONFLICT(channel_id, added_by) DO UPDATE SET
                channel_title = excluded.channel_title
        """, (channel_id, title, added_by))
        await db.commit()


async def get_channels(user_id: int):
    """Каналы конкретного пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM channels WHERE added_by = ? ORDER BY added_at DESC",
            (user_id,)
        ) as cur:
            return await cur.fetchall()


async def get_channel(channel_id: int, user_id: int):
    """Канал пользователя по channel_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM channels WHERE channel_id = ? AND added_by = ?",
            (channel_id, user_id)
        ) as cur:
            return await cur.fetchone()


async def delete_channel(channel_id: int, user_id: int):
    """Удалить канал пользователя (и деактивировать его ссылки)."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Деактивируем ссылки этого канала, созданные этим пользователем
        await db.execute(
            "UPDATE invite_links SET is_active = 0 WHERE channel_id = ? AND created_by = ?",
            (channel_id, user_id)
        )
        await db.execute(
            "DELETE FROM channels WHERE channel_id = ? AND added_by = ?",
            (channel_id, user_id)
        )
        await db.commit()


async def get_all_channels_admin():
    """Все каналы всех пользователей — только для админа."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM channels ORDER BY added_at DESC") as cur:
            return await cur.fetchall()


# ── Invite Links ───────────────────────────────────────────────────────

async def save_invite_link(channel_id: int, label: str, link: str, created_by: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO invite_links (channel_id, label, link, created_by)
            VALUES (?, ?, ?, ?)
        """, (channel_id, label, link, created_by))
        await db.commit()
        return cur.lastrowid


async def get_links_for_channel(channel_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT il.*, COUNT(lj.id) as joins_count
            FROM invite_links il
            LEFT JOIN link_joins lj ON lj.link_id = il.id
            WHERE il.channel_id = ? AND il.created_by = ? AND il.is_active = 1
            GROUP BY il.id
            ORDER BY il.created_at DESC
        """, (channel_id, user_id)) as cur:
            return await cur.fetchall()


async def get_all_links(user_id: int):
    """Все активные ссылки конкретного пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT il.*, c.channel_title, COUNT(lj.id) as joins_count
            FROM invite_links il
            LEFT JOIN channels c ON c.channel_id = il.channel_id AND c.added_by = il.created_by
            LEFT JOIN link_joins lj ON lj.link_id = il.id
            WHERE il.is_active = 1 AND il.created_by = ?
            GROUP BY il.id
            ORDER BY il.created_at DESC
        """, (user_id,)) as cur:
            return await cur.fetchall()


async def get_link_by_id(link_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM invite_links WHERE id = ?", (link_id,)) as cur:
            return await cur.fetchone()


async def deactivate_link(link_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE invite_links SET is_active = 0 WHERE id = ?", (link_id,))
        await db.commit()


# ── Joins tracking ─────────────────────────────────────────────────────

async def record_join(link: str, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id FROM invite_links WHERE link = ?", (link,)) as cur:
            row = await cur.fetchone()
        if row:
            await db.execute(
                "INSERT OR IGNORE INTO link_joins (link_id, user_id) VALUES (?, ?)",
                (row["id"], user_id)
            )
            await db.commit()


async def get_stats_by_channel(channel_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT il.label, il.link, il.created_at, COUNT(lj.id) as joins_count
            FROM invite_links il
            LEFT JOIN link_joins lj ON lj.link_id = il.id
            WHERE il.channel_id = ? AND il.created_by = ?
            GROUP BY il.id
            ORDER BY joins_count DESC
        """, (channel_id, user_id)) as cur:
            return await cur.fetchall()


async def get_my_stats(user_id: int):
    """Общая статистика пользователя по его каналам и ссылкам."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT
                COUNT(DISTINCT il.id) as total_links,
                COUNT(DISTINCT lj.id) as total_joins,
                COUNT(DISTINCT il.channel_id) as total_channels
            FROM invite_links il
            LEFT JOIN link_joins lj ON lj.link_id = il.id
            WHERE il.is_active = 1 AND il.created_by = ?
        """, (user_id,)) as cur:
            return await cur.fetchone()


async def get_total_stats():
    """Глобальная статистика бота — только для админа."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT
                COUNT(DISTINCT il.id) as total_links,
                COUNT(DISTINCT lj.id) as total_joins,
                COUNT(DISTINCT il.channel_id) as total_channels,
                COUNT(DISTINCT il.created_by) as total_users_active
            FROM invite_links il
            LEFT JOIN link_joins lj ON lj.link_id = il.id
            WHERE il.is_active = 1
        """) as cur:
            return await cur.fetchone()


# ── Creatives ──────────────────────────────────────────────────────────

async def save_creative(user_id: int, name: str, template: str, photo_file_id: str | None = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO creatives (user_id, name, template, photo_file_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, name) DO UPDATE SET
                template = excluded.template,
                photo_file_id = excluded.photo_file_id
        """, (user_id, name, template, photo_file_id))
        await db.commit()
        return cur.lastrowid


async def get_creatives(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM creatives WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        ) as cur:
            return await cur.fetchall()


async def get_creative(creative_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM creatives WHERE id = ? AND user_id = ?",
            (creative_id, user_id)
        ) as cur:
            return await cur.fetchone()


async def delete_creative(creative_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM creatives WHERE id = ? AND user_id = ?",
            (creative_id, user_id)
        )
        await db.commit()
