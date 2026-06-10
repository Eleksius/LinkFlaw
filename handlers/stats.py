from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from db import queries
from utils.formatters import fmt_link_row
from config import ADMIN_IDS

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ── Моя статистика — для всех пользователей ──────────────────────────

@router.message(F.text == "📊 Моя статистика")
@router.message(Command("stats"))
async def cmd_stats(message: Message):
    user_id = message.from_user.id
    total = await queries.get_my_stats(user_id)
    channels = await queries.get_channels(user_id)

    text = (
        "📊 <b>Моя статистика</b>\n\n"
        f"📢 Каналов: <b>{total['total_channels']}</b>\n"
        f"🔗 Активных ссылок: <b>{total['total_links']}</b>\n"
        f"📥 Всего переходов: <b>{total['total_joins']}</b>\n\n"
    )

    if channels:
        text += "━━━━━━━━━━━━━━━━━━━━\n"
        for ch in channels:
            stats = await queries.get_stats_by_channel(ch["channel_id"], user_id)
            if not stats:
                continue
            text += f"\n📢 <b>{ch['channel_title']}</b>\n"
            for row in stats:
                text += fmt_link_row(row["label"], row["link"], row["joins_count"], row["created_at"])

    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


# ── Стата бота — только для админа ───────────────────────────────────

@router.message(F.text == "🛡 Стата бота")
async def cmd_bot_stats(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Нет доступа.")

    total = await queries.get_total_stats()
    user_count = await queries.get_user_count()

    text = (
        "🛡 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей в боте: <b>{user_count}</b>\n"
        f"👤 Активных (с ссылками): <b>{total['total_users_active']}</b>\n"
        f"📢 Каналов подключено: <b>{total['total_channels']}</b>\n"
        f"🔗 Активных ссылок: <b>{total['total_links']}</b>\n"
        f"📥 Всего переходов: <b>{total['total_joins']}</b>\n"
    )

    await message.answer(text, parse_mode="HTML")
