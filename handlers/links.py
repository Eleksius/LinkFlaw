import os
import logging

from aiogram import Router, Bot, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    MessageOriginChannel,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from config import is_admin
from db import queries
from utils.formatters import fmt_link_row
from utils.image_sender import send_with_photo
from utils.pagination import paginate, nav_row, total_pages
from handlers.keyboards import (
    channel_select_kb, channels_manage_kb,
    confirm_delete_channel_kb, cancel_kb,
    main_kb, admin_main_kb,
)
from handlers.creatives import ask_apply_creative

logger = logging.getLogger(__name__)
router = Router()


class CreateLinkStates(StatesGroup):
    waiting_channel = State()
    waiting_label = State()



# ── Отмена / Главное меню ─────────────────────────────────────────────

@router.callback_query(F.data == "cancel_action")
async def cb_cancel_action(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = admin_main_kb() if is_admin(callback.from_user.id) else main_kb()
    try:
        await callback.message.edit_text("❌ Действие отменено.", reply_markup=kb)
    except Exception:
        await callback.message.delete()
        await callback.message.answer("❌ Действие отменено.", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = admin_main_kb() if is_admin(callback.from_user.id) else main_kb()
    try:
        await callback.message.edit_text("🏠 Главное меню", reply_markup=kb)
    except Exception:
        await callback.message.delete()
        await callback.message.answer("🏠 Главное меню", reply_markup=kb)
    await callback.answer()


# ── Пагинация: нажатие на счётчик страниц («1 / 3») ──────────────────

@router.callback_query(F.data == "page_noop")
async def cb_page_noop(callback: CallbackQuery):
    await callback.answer()


async def show_channels(target: Message | CallbackQuery, user_id: int):
    channels = await queries.get_channels(user_id)

    if not channels:
        text = (
            "📢 <b>Мои каналы</b>\n\n"
            "У тебя пока нет добавленных каналов.\n\n"
            "<b>Как добавить:</b>\n"
            "1. Добавь бота в канал как <b>администратора</b>\n"
            "2. Дай право <b>Пригласительные ссылки</b>\n"
            "3. Перешли сюда любое сообщение из этого канала"
        )
        msg = target if isinstance(target, Message) else target.message
        await send_with_photo(msg, "my_channels.png", text, parse_mode="HTML")
        return

    text = (
        "📢 <b>Мои каналы</b>\n\n"
        f"Подключено каналов: <b>{len(channels)}</b>\n\n"
        "Нажми на канал, чтобы посмотреть ссылки, или 🗑 чтобы удалить."
    )
    kb = channels_manage_kb(channels)

    if isinstance(target, Message):
        await send_with_photo(target, "my_channels.png", text, reply_markup=kb, parse_mode="HTML")
    else:
        # При возврате назад — удаляем старое сообщение и шлём новое (чтобы поддержать фото)
        try:
            await target.message.delete()
        except Exception:
            pass
        await send_with_photo(target.message, "my_channels.png", text, reply_markup=kb, parse_mode="HTML")


@router.message(F.text == "📢 Мои каналы")
@router.message(Command("channels"))
async def cmd_channels(message: Message):
    await show_channels(message, message.from_user.id)


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

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ К каналам", callback_data="back_channels")]
    ])
    try:
        await callback.message.edit_text(
            text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=kb
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer(
            text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=kb
        )
    await callback.answer()


@router.callback_query(F.data == "back_channels")
async def cb_back_channels(callback: CallbackQuery):
    await show_channels(callback, callback.from_user.id)
    await callback.answer()


# ── Удаление канала ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("ch_delete:"))
async def cb_channel_delete(callback: CallbackQuery):
    channel_id = int(callback.data.split(":")[1])
    channel = await queries.get_channel(channel_id, callback.from_user.id)
    if not channel:
        return await callback.answer("Канал не найден.", show_alert=True)

    try:
        await callback.message.edit_text(
            f"❓ Удалить канал <b>{channel['channel_title']}</b>?\n\n"
            "Все ссылки этого канала будут деактивированы.",
            parse_mode="HTML",
            reply_markup=confirm_delete_channel_kb(channel_id),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer(
            f"❓ Удалить канал <b>{channel['channel_title']}</b>?\n\n"
            "Все ссылки этого канала будут деактивированы.",
            parse_mode="HTML",
            reply_markup=confirm_delete_channel_kb(channel_id),
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


# ── Создать ссылку ────────────────────────────────────────────────────

@router.message(F.text == "🔗 Создать ссылку")
@router.message(Command("create_link"))
async def cmd_create_link(message: Message, state: FSMContext):
    channels = await queries.get_channels(message.from_user.id)
    if not channels:
        return await message.answer(
            "❌ У тебя нет добавленных каналов.\n\n"
            "Сначала добавь бота в канал как администратора, "
            "затем перешли сюда любое сообщение из этого канала.",
            parse_mode="HTML",
        )

    await send_with_photo(
        message,
        "create_link.png",
        "📢 Выбери канал для создания ссылки:",
        reply_markup=channel_select_kb(channels),
        parse_mode="HTML",
    )
    await state.set_state(CreateLinkStates.waiting_channel)


@router.callback_query(F.data.startswith("select_channel:"), CreateLinkStates.waiting_channel)
async def cb_select_channel(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split(":")[1])
    channel = await queries.get_channel(channel_id, callback.from_user.id)
    if not channel:
        return await callback.answer("Канал не найден.", show_alert=True)

    await state.update_data(channel_id=channel_id, channel_title=channel["channel_title"])
    try:
        await callback.message.edit_text(
            f"📢 Канал: <b>{channel['channel_title']}</b>\n\n"
            "✏️ Введи метку для ссылки\n"
            "<i>Например: Реклама у @durov, Баннер апрель</i>",
            parse_mode="HTML",
            reply_markup=cancel_kb(),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer(
            f"📢 Канал: <b>{channel['channel_title']}</b>\n\n"
            "✏️ Введи метку для ссылки\n"
            "<i>Например: Реклама у @durov, Баннер апрель</i>",
            parse_mode="HTML",
            reply_markup=cancel_kb(),
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
    # Не очищаем state здесь — ask_apply_creative запишет в него pending_link_url

    try:
        link_obj = await bot.create_chat_invite_link(
            chat_id=channel_id,
            name=label,
            creates_join_request=False,
        )
        link_url = link_obj.invite_link
        link_id = await queries.save_invite_link(
            channel_id=channel_id,
            label=label,
            link=link_url,
            created_by=message.from_user.id,
        )
        await message.answer(
            f"✅ Ссылка создана!\n\n"
            f"📢 Канал: <b>{channel_title}</b>\n"
            f"🏷 Метка: <b>{label}</b>\n\n"
            f"🔗 <code>{link_url}</code>\n\n"
            f"📥 Переходов: <b>0</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📊 Обновить статистику", callback_data=f"link_stat:{link_id}"),
            ]]),
        )
        await ask_apply_creative(message, message.from_user.id, link_url, state)
    except Exception as e:
        await state.clear()
        await message.answer(
            f"❌ Не удалось создать ссылку.\n"
            f"Убедись, что бот является администратором канала с правом «Пригласительные ссылки».\n\n"
            f"Ошибка: <code>{e}</code>",
            parse_mode="HTML",
        )


# ── Мои ссылки + статистика ───────────────────────────────────────────

@router.message(F.text == "📊 Мои ссылки")
@router.message(Command("links"))
@router.message(Command("stats"))
async def cmd_links_stats(message: Message):
    user_id = message.from_user.id
    total = await queries.get_my_stats(user_id)
    channels = await queries.get_channels(user_id)

    if not channels:
        return await message.answer(
            "📭 У тебя пока нет каналов и ссылок.\n"
            "Добавь канал и создай первую ссылку!"
        )

    text = (
        "📊 <b>Мои ссылки</b>\n\n"
        f"📢 Каналов: <b>{total['total_channels']}</b>  "
        f"🔗 Ссылок: <b>{total['total_links']}</b>  "
        f"📥 Переходов: <b>{total['total_joins']}</b>\n"
    )

    has_links = False
    for ch in channels:
        links = await queries.get_stats_by_channel(ch["channel_id"], user_id)
        if not links:
            continue
        has_links = True
        text += f"\n━━━━━━━━━━━━━━━━━━━━\n📢 <b>{ch['channel_title']}</b>\n"
        for lnk in links:
            text += fmt_link_row(lnk["label"], lnk["link"], lnk["joins_count"], lnk["created_at"])

    if not has_links:
        text += "\nСсылок пока нет. Создай через «🔗 Создать ссылку»."

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Подставить в креатив", callback_data="links_apply_creo")]
    ])

    await send_with_photo(message, "my_links.png", text, reply_markup=kb, parse_mode="HTML")


# ── Авто-регистрация канала при пересылке ────────────────────────────

@router.message(F.forward_origin.type == "channel")
async def forward_from_channel(message: Message, bot: Bot):
    origin: MessageOriginChannel = message.forward_origin
    chat = origin.chat
    user_id = message.from_user.id

    try:
        member = await bot.get_chat_member(chat_id=chat.id, user_id=user_id)
        if member.status not in ("administrator", "creator"):
            return await message.answer(
                f"❌ Ты не являешься администратором канала <b>{chat.title}</b>.\n\n"
                "Добавить канал могут только его администраторы.",
                parse_mode="HTML",
            )
    except TelegramForbiddenError:
        return await message.answer(
            f"❌ Бот не добавлен в канал <b>{chat.title}</b> или не имеет доступа.\n\n"
            "Сначала добавь бота в канал как <b>администратора</b> "
            "с правом <b>Пригласительные ссылки</b>.",
            parse_mode="HTML",
        )
    except TelegramBadRequest as e:
        return await message.answer(
            f"❌ Не удалось проверить права в канале <b>{chat.title}</b>.\n\n"
            f"Убедись, что бот добавлен в канал как администратор.\n\n"
            f"<code>{e}</code>",
            parse_mode="HTML",
        )

    # Проверяем, что у бота есть право создавать инвайт-ссылки
    try:
        bot_member = await bot.get_chat_member(chat_id=chat.id, user_id=(await bot.get_me()).id)
        can_invite = getattr(bot_member, "can_invite_users", None)
        if can_invite is False:
            return await message.answer(
                f"❌ Бот добавлен в канал <b>{chat.title}</b>, но у него нет права "
                "<b>Пригласительные ссылки</b>.\n\n"
                "Зайди в настройки канала → Администраторы → бот → включи это право.",
                parse_mode="HTML",
            )
    except Exception:
        pass  # Если не удалось проверить — не блокируем, ошибка всплывёт при создании ссылки

    await queries.add_channel(chat.id, chat.title, user_id)
    await message.answer(
        f"✅ Канал <b>{chat.title}</b> добавлен!",
        parse_mode="HTML",
    )


# ── Подстановка ссылки в креатив ──────────────────────────────────────

def _links_apply_kb(links: list, page: int, cancel_cb: str = "back_channels") -> InlineKeyboardMarkup:
    """Клавиатура выбора ссылки для подстановки — с пагинацией."""
    page_items = paginate(links, page)
    buttons = []
    for lnk in page_items:
        label = lnk["label"] or lnk["link"]
        display = label if len(label) < 40 else label[:37] + "…"
        buttons.append([InlineKeyboardButton(
            text=f"🔗 {display}", callback_data=f"link_apply_creo:{lnk['id']}"
        )])

    nav = nav_row(links, page, cb_prefix="links_apply_page")
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data=cancel_cb)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "links_apply_creo")
async def cb_links_apply_creo(callback: CallbackQuery):
    user_id = callback.from_user.id
    links = await queries.get_links(user_id)
    if not links:
        await callback.answer("У тебя нет ссылок.", show_alert=True)
        return

    try:
        await callback.message.edit_text(
            "Выбери ссылку для подстановки в креатив:",
            reply_markup=_links_apply_kb(links, page=0),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer(
            "Выбери ссылку для подстановки в креатив:",
            reply_markup=_links_apply_kb(links, page=0),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("links_apply_page:"))
async def cb_links_apply_page(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    links = await queries.get_links(user_id)
    if not links:
        return await callback.answer("У тебя нет ссылок.", show_alert=True)

    try:
        await callback.message.edit_reply_markup(reply_markup=_links_apply_kb(links, page))
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("link_apply_creo:"))
async def cb_link_apply_creo(callback: CallbackQuery, state: FSMContext):
    link_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    lnk = await queries.get_link(link_id, user_id)
    if not lnk:
        return await callback.answer("Ссылка не найдена.", show_alert=True)

    await ask_apply_creative(callback.message, user_id, lnk["link"], state)
    await callback.answer()


# ── Быстрая статистика ссылки ─────────────────────────────────────────

@router.callback_query(F.data.startswith("link_stat:"))
async def cb_link_stat(callback: CallbackQuery):
    link_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    row = await queries.get_link_stats(link_id, user_id)
    if not row:
        return await callback.answer("Ссылка не найдена.", show_alert=True)

    text = (
        f"✅ Ссылка создана!\n\n"
        f"📢 Канал: <b>{row['channel_title'] or '—'}</b>\n"
        f"🏷 Метка: <b>{row['label']}</b>\n\n"
        f"🔗 <code>{row['link']}</code>\n\n"
        f"📥 Переходов: <b>{row['joins_count']}</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📊 Обновить статистику", callback_data=f"link_stat:{link_id}"),
    ]])

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass  # текст не изменился — Telegram вернёт ошибку, игнорируем

    await callback.answer("Обновлено ✓")
