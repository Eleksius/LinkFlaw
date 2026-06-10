import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import Message, ChatMemberUpdated, BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from aiogram.filters import CommandStart, ChatMemberUpdatedFilter, JOIN_TRANSITION
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, ADMIN_IDS
from db.models import init_db, migrate_db
from db import queries
from handlers import links, stats, admin, creatives

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

dp.include_router(links.router)
dp.include_router(stats.router)
dp.include_router(admin.router)
dp.include_router(creatives.router)


@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    await queries.upsert_user(
        user.id, user.username or "", user.first_name or "", user.last_name or ""
    )
    from handlers.keyboards import main_kb, admin_main_kb
    is_adm = user.id in ADMIN_IDS
    await message.answer(
        "👋 Привет! Я помогаю создавать рекламные инвайт-ссылки и отслеживать переходы.\n\n"
        "<b>Как начать:</b>\n"
        "1. Добавь бота в свой канал как <b>администратора</b>\n"
        "2. Дай право <b>Пригласительные ссылки</b>\n"
        "3. Перешли сюда любое сообщение из этого канала\n"
        "4. Создавай ссылки через кнопку <b>🔗 Создать ссылку</b>",
        parse_mode="HTML",
        reply_markup=admin_main_kb() if is_adm else main_kb()
    )


@dp.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def on_new_member(event: ChatMemberUpdated):
    if event.invite_link and event.invite_link.invite_link:
        await queries.record_join(
            link=event.invite_link.invite_link,
            user_id=event.new_chat_member.user.id
        )
        logger.info(f"Join via {event.invite_link.invite_link} by {event.new_chat_member.user.id}")


async def set_bot_commands():
    user_commands = [
        BotCommand(command="start",       description="Главное меню"),
        BotCommand(command="create_link", description="Создать инвайт-ссылку"),
        BotCommand(command="links",       description="Мои ссылки и статистика"),
        BotCommand(command="channels",    description="Мои каналы"),
        BotCommand(command="creatives",   description="Мои шаблоны (креативы)"),
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

    admin_commands = user_commands + [
        BotCommand(command="users",     description="Пользователи бота"),
        BotCommand(command="broadcast", description="Рассылка"),
    ]
    for admin_id in ADMIN_IDS:
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception:
            pass


async def main():
    await init_db()
    await migrate_db()
    await set_bot_commands()
    logger.info("Bot started!")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "chat_member"])


if __name__ == "__main__":
    asyncio.run(main())
