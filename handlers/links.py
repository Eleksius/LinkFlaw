from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from db import queries
from utils.formatters import fmt_link_row
from handlers.keyboards import channel_select_kb, channels_manage_kb, confirm_delete_channel_kb
from handlers.creatives import ask_apply_creative

router = Router()


class CreateLinkStates(StatesGroup):
    waiting_channel = State()
    waiting_label = State()


# ── Хелпер: показать список каналов пользователя ──────────────────────

async def show_channels(target: Message | CallbackQuery, user_id: int):
    channels = await queries.get_channels(user_id)
    text = "📢 <b>Мои каналы</b>\n\n"
    if not channels:
        text += (
            "У тебя пока нет добавленных каналов.\n\n"
            "Чтобы добавить канал:\n"
            "1. Добавь бота в канал как <b>администратора</b>\n"
            "2. Дай право <b>Пригласительные ссылки</b>\n"
            "3. Перешли сюда любое сообщение из этого канала"
        )
        msg = target if isinstance(target, Message) else target.message
        await msg.answer(text, parse_mode="HTML")
        return

    text += "Нажми 🗑 Удалить рядом с каналом, чтобы его отключить."
    kb = channels_manage_kb(channels)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


# ── Кнопка "📢 Мои каналы" и команда /channels ────────────────────────

@router.message(F.text == "📢 Мои каналы")
@router.message(Command("channels"))
async def cmd_channels(message: Message):
    await show_channels(message, message.from_user.id)


# ── Просмотр ссылок канала ────────────────────────────────────────────

@router.callback_query(F.data.startswith("ch_info:"))
async def cb_channel_info(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    channel = await queries.get_channel(channel_id, user_id)
    if not channel:
        return await callback.answer("Канал не найден.", show_alert=True)

    links = await queries.get_links_for_channel(channel_id, user_id)
    text = f"📢 <b>{channel['channel_title']}</b>\n\n"
    if not links:
        text += "Ссылок пока нет. Создай через «🔗 Создать ссылку»."
    else:
        text += f"🔗 Ссылок: <b>{len(links)}</b>\n\n"
        for lnk in links:
            text += fmt_link_row(lnk["label"], lnk["link"], lnk["joins_count"], lnk["created_at"])

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ К каналам", callback_data="back_channels")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML",
                                     disable_web_page_preview=True, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "back_channels")
async def cb_back_channels(callback: CallbackQuery):
    await show_channels(callback, callback.from_user.id)
    await callback.answer()


# ── Удаление канала ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ch_delete:"))
async def cb_channel_delete(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    channel = await queries.get_channel(channel_id, user_id)
    if not channel:
        return await callback.answer("Канал не найден.", show_alert=True)

    kb = confirm_delete_channel_kb(channel_id)
    await callback.message.edit_text(
        f"❓ Удалить канал <b>{channel['channel_title']}</b>?\n\n"
        "Все ссылки этого канала будут деактивированы.",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ch_delete_confirm:"))
async def cb_channel_delete_confirm(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    channel = await queries.get_channel(channel_id, user_id)
    if not channel:
        return await callback.answer("Канал не найден.", show_alert=True)

    title = channel["channel_title"]
    await queries.delete_channel(channel_id, user_id)
    await callback.answer(f"✅ Канал «{title}» удалён.", show_alert=True)
    await show_channels(callback, user_id)


@router.callback_query(F.data == "ch_delete_cancel")
async def cb_channel_delete_cancel(callback: CallbackQuery):
    await show_channels(callback, callback.from_user.id)
    await callback.answer()


# ── Создать ссылку: кнопка + команда ──────────────────────────────────

@router.message(F.text == "🔗 Создать ссылку")
@router.message(Command("create_link"))
async def cmd_create_link(message: Message, state: FSMContext):
    channels = await queries.get_channels(message.from_user.id)
    if not channels:
        return await message.answer(
            "❌ У тебя нет добавленных каналов.\n\n"
            "Сначала добавь бота в канал как администратора, "
            "затем перешли сюда любое сообщение из этого канала.",
            parse_mode="HTML"
        )

    await message.answer(
        "📢 Выбери канал для создания ссылки:",
        reply_markup=channel_select_kb(channels)
    )
    await state.set_state(CreateLinkStates.waiting_channel)


@router.callback_query(F.data.startswith("select_channel:"), CreateLinkStates.waiting_channel)
async def cb_select_channel(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split(":")[1])
    channel = await queries.get_channel(channel_id, callback.from_user.id)
    if not channel:
        return await callback.answer("Канал не найден.", show_alert=True)

    await state.update_data(channel_id=channel_id, channel_title=channel["channel_title"])
    await callback.message.edit_text(
        f"✅ Канал: <b>{channel['channel_title']}</b>\n\n"
        "✏️ Введи метку для ссылки\n"
        "<i>Например: Реклама у @durov, Баннер апрель</i>",
        parse_mode="HTML"
    )
    await state.set_state(CreateLinkStates.waiting_label)
    await callback.answer()


@router.message(CreateLinkStates.waiting_label)
async def process_label(message: Message, state: FSMContext, bot: Bot):
    label = message.text.strip()
    if len(label) > 100:
        return await message.answer("❌ Слишком длинная метка (макс. 100 символов). Попробуй ещё раз:")

    data = await state.get_data()
    channel_id = data["channel_id"]
    channel_title = data["channel_title"]
    await state.clear()

    try:
        link_obj = await bot.create_chat_invite_link(
            chat_id=channel_id,
            name=label,
            creates_join_request=False
        )
        link_url = link_obj.invite_link
        await queries.save_invite_link(
            channel_id=channel_id,
            label=label,
            link=link_url,
            created_by=message.from_user.id
        )
        await message.answer(
            f"✅ Ссылка создана!\n\n"
            f"📢 Канал: <b>{channel_title}</b>\n"
            f"🏷 Метка: <b>{label}</b>\n\n"
            f"🔗 Ссылка:\n<code>{link_url}</code>",
            parse_mode="HTML"
        )
        # Предложить подставить в шаблон
        await ask_apply_creative(message, message.from_user.id, link_url)
    except Exception as e:
        await message.answer(
            f"❌ Не удалось создать ссылку.\n"
            f"Убедись, что бот является администратором канала с правом «Пригласительные ссылки».\n\n"
            f"Ошибка: <code>{e}</code>",
            parse_mode="HTML"
        )


# ── Список ссылок: кнопка + команда ──────────────────────────────────

@router.message(F.text == "📋 Мои ссылки")
@router.message(Command("links"))
async def cmd_links(message: Message):
    user_id = message.from_user.id
    links = await queries.get_all_links(user_id)

    if not links:
        return await message.answer(
            "📭 У тебя пока нет активных ссылок.\n"
            "Создай первую через «🔗 Создать ссылку»."
        )

    by_channel: dict[str, list] = {}
    for lnk in links:
        title = lnk["channel_title"] or str(lnk["channel_id"])
        by_channel.setdefault(title, []).append(lnk)

    text = "🔗 <b>Мои активные ссылки</b>\n\n"
    for channel_title, channel_links in by_channel.items():
        text += f"📢 <b>{channel_title}</b>\n"
        for lnk in channel_links:
            text += fmt_link_row(lnk["label"], lnk["link"], lnk["joins_count"], lnk["created_at"])
        text += "\n"

    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


# ── Авто-регистрация канала при пересылке сообщения ───────────────────

@router.message(F.forward_from_chat)
async def forward_from_channel(message: Message):
    chat = message.forward_from_chat
    if chat.type not in ("channel", "supergroup"):
        return await message.answer("❌ Это не канал. Перешли сообщение из канала.")

    await queries.add_channel(chat.id, chat.title, message.from_user.id)
    await message.answer(
        f"✅ Канал <b>{chat.title}</b> добавлен!\n\n"
        "Убедись, что бот добавлен в этот канал как администратор "
        "с правом <b>Пригласительные ссылки</b>.",
        parse_mode="HTML"
    )
