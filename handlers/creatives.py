import html
import re
import logging

from aiogram import Router, Bot, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from db import queries
from utils.image_sender import send_with_photo
from utils.pagination import paginate, nav_row, total_pages, PER_PAGE

logger = logging.getLogger(__name__)
router = Router()

# Плейсхолдер, который пользователь пишет в шаблоне
PLACEHOLDER = "{link}"

# Формат гиперссылки в шаблоне: [текст кнопки]({link})
HYPERLINK_RE = re.compile(r'\[([^\]]+)\]\(\{link\}\)')


class CreativeStates(StatesGroup):
    waiting_name = State()
    waiting_template = State()
    editing_template = State()
    applying_link = State()   # ожидание выбора креатива для подстановки ссылки


# ── Применение шаблона ────────────────────────────────────────────────

async def _send_creative_result(
    bot: Bot,
    user_id: int,
    c,           # aiosqlite.Row креатива
    link_url: str,
) -> None:
    """Отправить готовый креатив с заголовком."""
    result = apply_template(c["template"], link_url)
    header = f"✏️ <b>{html.escape(c['name'])}</b>\n\n<i>Вот твой готовый креатив:</i>"

    await bot.send_message(user_id, header, parse_mode="HTML")

    if c["photo_file_id"]:
        await bot.send_photo(
            chat_id=user_id,
            photo=c["photo_file_id"],
            caption=result,
            parse_mode="HTML",
        )
    else:
        await bot.send_message(
            user_id, result,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )


def apply_template(template: str, link_url: str) -> str:
    """Подставляет ссылку в шаблон: [текст]({link}) → HTML-гиперссылка, {link} → голый URL."""
    result = HYPERLINK_RE.sub(
        lambda m: f'<a href="{html.escape(link_url)}">{m.group(1)}</a>',
        template,
    )
    return result.replace(PLACEHOLDER, link_url)


def _preview(template: str) -> str:
    return apply_template(template, "https://t.me/+xxxxxx")


def _has_placeholder(template: str) -> bool:
    return PLACEHOLDER in template


def _extract_text_and_photo(message: Message):
    """Возвращает (text, photo_file_id) из сообщения — с фото или без."""
    if message.photo:
        return (message.caption or "").strip(), message.photo[-1].file_id
    return (message.text or "").strip(), None


# ── Клавиатуры ────────────────────────────────────────────────────────

def creatives_list_kb(creatives: list, page: int = 0) -> InlineKeyboardMarkup:
    page_items = paginate(creatives, page)
    buttons = []
    for c in page_items:
        icon = "🖼" if c["photo_file_id"] else "✏️"
        buttons.append([
            InlineKeyboardButton(text=f"{icon} {c['name']}", callback_data=f"creo_view:{c['id']}"),
            InlineKeyboardButton(text="🗑",                   callback_data=f"creo_delete:{c['id']}"),
        ])

    nav = nav_row(creatives, page, cb_prefix="creo_page")
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(text="➕ Новый креатив", callback_data="creo_new")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def creative_actions_kb(creative_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"creo_edit:{creative_id}"),
            InlineKeyboardButton(text="🗑 Удалить",        callback_data=f"creo_delete:{creative_id}"),
        ],
        [InlineKeyboardButton(text="🔗 Подставить ссылку", callback_data=f"creo_apply_choose:{creative_id}")],
        [InlineKeyboardButton(text="◀️ К списку", callback_data="creo_list")],
    ])


def confirm_delete_creative_kb(creative_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Удалить", callback_data=f"creo_delete_confirm:{creative_id}"),
        InlineKeyboardButton(text="❌ Отмена",  callback_data=f"creo_view:{creative_id}"),
    ]])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creo")]
    ])


# ── Текст подсказки ───────────────────────────────────────────────────

TEMPLATE_HELP = (
    "Используй <code>{link}</code> там, где должна встать ссылка.\n\n"
    "<b>Варианты:</b>\n"
    "• Голая ссылка:\n"
    "  <code>Подписывайся 👉 {link}</code>\n\n"
    "• Кликабельный текст:\n"
    "  <code>[нажми сюда]({link})</code>\n"
    "  <code>[🔥 Лучший канал о крипте]({link})</code>\n\n"
    "  Формат: <code>[текст]({link})</code>\n\n"
    "📸 <b>Хочешь добавить фото?</b> Отправь фото с подписью, где есть <code>{link}</code>."
)


# ── Хелпер: показать список ───────────────────────────────────────────

async def show_creatives_list(target: Message | CallbackQuery, user_id: int, page: int = 0):
    creatives = await queries.get_creatives(user_id)

    if not creatives:
        text = (
            "✏️ <b>Мои креативы</b>\n\n"
            "У тебя пока нет шаблонов.\n\n"
            + TEMPLATE_HELP
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать первый креатив", callback_data="creo_new")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ])
    else:
        pages = total_pages(creatives)
        page = max(0, min(page, pages - 1))  # защита от выхода за границы
        text = (
            f"✏️ <b>Мои креативы</b> ({len(creatives)})\n\n"
            f"Выбери для просмотра или 🗑 для удаления:"
            + (f"\n<i>Страница {page + 1} из {pages}</i>" if pages > 1 else "")
        )
        kb = creatives_list_kb(creatives, page)

    # Удаляем старое сообщение при возврате через callback
    if isinstance(target, CallbackQuery):
        try:
            await target.message.delete()
        except Exception:
            pass

    msg = target if isinstance(target, Message) else target.message
    await send_with_photo(msg, "my_creo.png", text, reply_markup=kb, parse_mode="HTML")


# ── Список: кнопка + команда ──────────────────────────────────────────

@router.message(F.text == "✏️ Мои креативы")
@router.message(Command("creatives"))
async def cmd_creatives(message: Message):
    await show_creatives_list(message, message.from_user.id)


@router.callback_query(F.data == "creo_list")
async def cb_creatives_list(callback: CallbackQuery):
    await show_creatives_list(callback, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data.startswith("creo_page:"))
async def cb_creo_page(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])
    await show_creatives_list(callback, callback.from_user.id, page)
    await callback.answer()


# ── Просмотр ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("creo_view:"))
async def cb_creative_view(callback: CallbackQuery, bot: Bot):
    creative_id = int(callback.data.split(":")[1])
    c = await queries.get_creative(creative_id, callback.from_user.id)
    if not c:
        return await callback.answer("Креатив не найден.", show_alert=True)

    caption = (
        f"✏️ <b>{html.escape(c['name'])}</b>\n\n"
        f"<b>Шаблон:</b>\n<code>{html.escape(c['template'])}</code>\n\n"
        f"<b>Пример (с тестовой ссылкой):</b>\n{_preview(c['template'])}"
    )
    kb = creative_actions_kb(creative_id)

    if c["photo_file_id"]:
        await callback.message.delete()
        await bot.send_photo(
            chat_id=callback.from_user.id,
            photo=c["photo_file_id"],
            caption=caption,
            parse_mode="HTML",
            reply_markup=kb,
        )
    else:
        try:
            await callback.message.edit_text(
                caption, parse_mode="HTML", disable_web_page_preview=True, reply_markup=kb
            )
        except Exception:
            await callback.message.delete()
            await callback.message.answer(
                caption, parse_mode="HTML", disable_web_page_preview=True, reply_markup=kb
            )
    await callback.answer()


# ── Создание ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "creo_new")
async def cb_creative_new(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_text(
            "✏️ <b>Новый креатив — шаг 1/2</b>\n\n"
            "Введи название шаблона:\n"
            "<i>Например: Пост у блогера, Баннер апрель</i>",
            parse_mode="HTML",
            reply_markup=cancel_kb(),
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer(
            "✏️ <b>Новый креатив — шаг 1/2</b>\n\n"
            "Введи название шаблона:\n"
            "<i>Например: Пост у блогера, Баннер апрель</i>",
            parse_mode="HTML",
            reply_markup=cancel_kb(),
        )
    await state.set_state(CreativeStates.waiting_name)
    await callback.answer()


@router.message(CreativeStates.waiting_name)
async def process_creative_name(message: Message, state: FSMContext):
    name = message.text.strip() if message.text else ""
    if not name:
        return await message.answer("❌ Введи текстовое название:", reply_markup=cancel_kb())
    if len(name) > 64:
        return await message.answer(
            "❌ Название слишком длинное (макс. 64 символа). Попробуй ещё:",
            reply_markup=cancel_kb(),
        )
    await state.update_data(creative_name=name)
    await message.answer(
        f"✏️ <b>Новый креатив — шаг 2/2</b>\n\n"
        f"Название: <b>{html.escape(name)}</b>\n\n"
        "Теперь отправь текст шаблона (или фото с подписью):\n\n"
        + TEMPLATE_HELP,
        parse_mode="HTML",
        reply_markup=cancel_kb(),
    )
    await state.set_state(CreativeStates.waiting_template)


@router.message(CreativeStates.waiting_template, F.text | F.photo)
async def process_creative_template(message: Message, state: FSMContext):
    template, photo_file_id = _extract_text_and_photo(message)

    if not _has_placeholder(template):
        return await message.answer(
            f"❌ В шаблоне нет <code>{PLACEHOLDER}</code> — некуда подставлять ссылку.\n\n"
            + TEMPLATE_HELP,
            parse_mode="HTML",
            reply_markup=cancel_kb(),
        )

    data = await state.get_data()
    name = data["creative_name"]
    await state.clear()

    await queries.save_creative(message.from_user.id, name, template, photo_file_id)

    preview_text = (
        f"✅ Креатив <b>{html.escape(name)}</b> сохранён!\n\n"
        f"<b>Пример:</b>\n\n{_preview(template)}"
    )
    if photo_file_id:
        await message.answer_photo(photo=photo_file_id, caption=preview_text, parse_mode="HTML")
    else:
        await message.answer(preview_text, parse_mode="HTML", disable_web_page_preview=True)


# ── Редактирование ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("creo_edit:"))
async def cb_creative_edit(callback: CallbackQuery, state: FSMContext):
    creative_id = int(callback.data.split(":")[1])
    c = await queries.get_creative(creative_id, callback.from_user.id)
    if not c:
        return await callback.answer("Креатив не найден.", show_alert=True)

    await state.update_data(editing_creative_id=creative_id, creative_name=c["name"])
    text = (
        f"✏️ Редактирование <b>{html.escape(c['name'])}</b>\n\n"
        f"Текущий шаблон:\n<code>{html.escape(c['template'])}</code>\n\n"
        "Отправь новый текст или фото с подписью:\n\n"
        + TEMPLATE_HELP
    )
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=cancel_kb())
    except Exception:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode="HTML", reply_markup=cancel_kb())

    await state.set_state(CreativeStates.editing_template)
    await callback.answer()


@router.message(CreativeStates.editing_template, F.text | F.photo)
async def process_edit_template(message: Message, state: FSMContext):
    template, photo_file_id = _extract_text_and_photo(message)

    if not _has_placeholder(template):
        return await message.answer(
            f"❌ В шаблоне нет <code>{PLACEHOLDER}</code>.\n\n" + TEMPLATE_HELP,
            parse_mode="HTML",
            reply_markup=cancel_kb(),
        )

    data = await state.get_data()
    name = data["creative_name"]
    await state.clear()

    await queries.save_creative(message.from_user.id, name, template, photo_file_id)

    preview_text = (
        f"✅ Шаблон <b>{html.escape(name)}</b> обновлён!\n\n"
        f"<b>Пример:</b>\n\n{_preview(template)}"
    )
    if photo_file_id:
        await message.answer_photo(photo=photo_file_id, caption=preview_text, parse_mode="HTML")
    else:
        await message.answer(preview_text, parse_mode="HTML", disable_web_page_preview=True)


# ── Удаление ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("creo_delete:"))
async def cb_creative_delete(callback: CallbackQuery):
    creative_id = int(callback.data.split(":")[1])
    c = await queries.get_creative(creative_id, callback.from_user.id)
    if not c:
        return await callback.answer("Креатив не найден.", show_alert=True)

    text = f"❓ Удалить креатив <b>{html.escape(c['name'])}</b>?"
    kb = confirm_delete_creative_kb(creative_id)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.delete()
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("creo_delete_confirm:"))
async def cb_creative_delete_confirm(callback: CallbackQuery):
    creative_id = int(callback.data.split(":")[1])
    c = await queries.get_creative(creative_id, callback.from_user.id)
    if not c:
        return await callback.answer("Уже удалён.", show_alert=True)

    await queries.delete_creative(creative_id, callback.from_user.id)
    await callback.answer("✅ Удалён.", show_alert=True)
    await show_creatives_list(callback, callback.from_user.id)


# ── Отмена внутри FSM креативов ───────────────────────────────────────

@router.callback_query(F.data == "cancel_creo")
async def cb_cancel_creo(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_creatives_list(callback, callback.from_user.id)
    await callback.answer()


# ── Подстановка в шаблон после создания ссылки ───────────────────────

async def ask_apply_creative(message: Message, user_id: int, link_url: str, state: FSMContext):
    creatives = await queries.get_creatives(user_id)
    if not creatives:
        return

    # Сохраняем URL в FSMContext — не кладём его в callback_data (лимит 64 байта)
    await state.set_state(CreativeStates.applying_link)
    await state.update_data(pending_link_url=link_url)

    buttons = []
    for c in creatives:
        icon = "🖼" if c["photo_file_id"] else "✏️"
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {c['name']}",
            callback_data=f"apply_creo:{c['id']}",
        )])
    buttons.append([
        InlineKeyboardButton(text="➕ Новый шаблон", callback_data="creo_new"),
        InlineKeyboardButton(text="Пропустить →",    callback_data="creo_skip"),
    ])

    await message.answer(
        "✏️ <b>Подставить ссылку в шаблон?</b>\n\nВыбери креатив:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("apply_creo:"), CreativeStates.applying_link)
async def cb_apply_creative(callback: CallbackQuery, bot: Bot, state: FSMContext):
    creative_id = int(callback.data.split(":")[1])

    data = await state.get_data()
    link_url = data.get("pending_link_url")
    if not link_url:
        await state.clear()
        return await callback.answer("Сессия истекла. Создай ссылку заново.", show_alert=True)

    c = await queries.get_creative(creative_id, callback.from_user.id)
    if not c:
        return await callback.answer("Шаблон не найден.", show_alert=True)

    await state.clear()

    try:
        await callback.message.delete()
    except Exception:
        pass

    await _send_creative_result(bot, callback.from_user.id, c, link_url)
    await callback.answer()


@router.callback_query(F.data == "creo_skip")
async def cb_creo_skip(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("creo_apply_choose:"))
async def cb_creo_apply_choose(callback: CallbackQuery):
    creative_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    c = await queries.get_creative(creative_id, user_id)
    if not c:
        return await callback.answer("Креатив не найден.", show_alert=True)

    links = await queries.get_links(user_id)
    if not links:
        await callback.answer("У тебя нет ссылок.", show_alert=True)
        return

    await _show_creo_link_picker(callback, creative_id, links, page=0)
    await callback.answer()


def _creo_link_picker_kb(creative_id: int, links: list, page: int) -> InlineKeyboardMarkup:
    page_items = paginate(links, page)
    buttons = []
    for lnk in page_items:
        label = lnk["label"] or lnk["link"]
        display = label if len(label) < 40 else label[:37] + "…"
        buttons.append([InlineKeyboardButton(
            text=f"🔗 {display}",
            callback_data=f"creo_apply_with_link:{creative_id}:{lnk['id']}",
        )])

    nav = nav_row(links, page, cb_prefix=f"creo_link_page:{creative_id}")
    if nav:
        buttons.append(nav)

    buttons.append([
        InlineKeyboardButton(text="◀️ Назад",  callback_data=f"creo_view:{creative_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="creo_list"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _show_creo_link_picker(
    callback: CallbackQuery, creative_id: int, links: list, page: int
) -> None:
    kb = _creo_link_picker_kb(creative_id, links, page)
    try:
        await callback.message.edit_text("Выбери ссылку для подстановки:", reply_markup=kb)
    except Exception:
        await callback.message.delete()
        await callback.message.answer("Выбери ссылку для подстановки:", reply_markup=kb)


@router.callback_query(F.data.startswith("creo_link_page:"))
async def cb_creo_link_page(callback: CallbackQuery):
    # creo_link_page:<creative_id>:<page>
    parts = callback.data.split(":")
    creative_id = int(parts[1])
    page = int(parts[2])
    user_id = callback.from_user.id

    links = await queries.get_links(user_id)
    if not links:
        return await callback.answer("У тебя нет ссылок.", show_alert=True)

    try:
        await callback.message.edit_reply_markup(
            reply_markup=_creo_link_picker_kb(creative_id, links, page)
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("creo_apply_with_link:"))
async def cb_creo_apply_with_link(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    creative_id = int(parts[1])
    link_id = int(parts[2])
    user_id = callback.from_user.id

    c = await queries.get_creative(creative_id, user_id)
    if not c:
        return await callback.answer("Креатив не найден.", show_alert=True)

    lnk = await queries.get_link(link_id, user_id)
    if not lnk:
        return await callback.answer("Ссылка не найдена.", show_alert=True)

    try:
        await callback.message.delete()
    except Exception:
        pass

    await _send_creative_result(bot, user_id, c, lnk["link"])
    await callback.answer()
