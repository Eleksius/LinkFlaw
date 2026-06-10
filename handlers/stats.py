from aiogram import Router, F
from aiogram.types import Message

from config import ADMIN_IDS
from db import queries

router = Router()


@router.message(F.text == "🛡 Стата бота")
async def cmd_bot_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("⛔ Нет доступа.")

    total = await queries.get_total_stats()
    user_count = await queries.get_user_count()

    text = (
        "🛡 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей: <b>{user_count}</b>\n"
        f"👤 Активных (есть ссылки): <b>{total['total_users_active']}</b>\n"
        f"📢 Каналов подключено: <b>{total['total_channels']}</b>\n"
        f"🔗 Активных ссылок: <b>{total['total_links']}</b>\n"
        f"📥 Всего переходов: <b>{total['total_joins']}</b>"
    )

    await message.answer(text, parse_mode="HTML")
