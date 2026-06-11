import html
import re

from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from db import queries

router = Router()

# Плейсхолдер, который пользователь пишет в шаблоне
PLACEHOLDER = "{link}"

# Формат гиперссылки в шаблоне: [текст кнопки]({link})
HYPERLINK_RE = re.compile(r'\[([^\]]+)\]\(\{link\}\)')


class CreativeStates(StatesGroup):
    waiting_name = State()
    waiting_template = State()   # ждём текст (и опционально фото)
    editing_template = State()   # то же при редактировании


# ── Применение шаблона ────────────────────────────────────────────────

def apply_template(template: str, link_url: str) -> str:
    result = HYPERLINK_RE.sub(
        lambda m: f'<a href="{html.escape(link_url)}">{m.group(1)}</a>',
        template
    )
    result = result.replace(PLACEHOLDER, link_url)
    return result


def _preview(template: str) -> str:
    return apply_template(template, "https://t.me/+xxxxxx")


def _has_placeholder(template: str) -> bool:
    return PLACEHOLDER in template


def _extract_text_and_photo(message: Message):
    """Возвращает (text, photo_file_id) из сообщения — с фото или без."""
    if message.photo:
        text = (message.caption or "").strip()
        photo_file_id = message.photo[-1].file_id  # берём наибольшее разрешение
        return text, photo_file_id
    else:
        return (message.text or "").strip(), None


# ── Клавиатуры ────────────────────────────────────────────────────────

def creatives_list_kb(creatives: list) -> InlineKeyboardMarkup:
    buttons = []
    for c in creatives:
        icon = "🖼" if c["photo_file_id"] else "✏️"
        buttons.append([
            InlineKeyboardButton(text=f"{icon} {c['name']}", callback_data=f"creo_view:{c['id']}"),
            InlineKeyboardButton(text="🗑",                   callback_data=f"creo_delete:{c['id']}"),
        ])
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
    "• Гиперссылка (кликабельный текст):\n"
    "  <code>Подписывайся 👉 [нажми сюда]({link})</code>\n"
    "  <code>[🔥 Лучший канал о крипте]({link})</code>\n\n"
    "  Формат: <code>[текст]({link})</code>\n\n"
    "📸 <b>Хочешь добавить фото?</b> Отправь фото с подписью, где есть <code>{link}</code>."
)


# ── Хелпер: показать список ───────────────────────────────────────────

async def show_creatives_list(target: Message | CallbackQuery, user_id: int):
    creatives = await queries.get_creatives(user_id)
    if not creatives:
        text = (
            "✏️ <b>Мои креативы</b>\n\n"
            "У тебя пока нет шаблонов.\n\n"
            + TEMPLATE_HELP
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать первый креатив", callback_data="creo_new")]
        ])
    else:
        text = f"✏️ <b>Мои креативы</b> ({len(creatives)})\n\nВыбери для просмотра или 🗑 для удаления:"
        kb = creatives_list_kb(creatives)

    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


# ── Список: кнопка + команда ──────────────────────────────────────────

@router.message(F.text == "✏️ Мои креативы")
@router.message(Command("creatives"))
async def cmd_creatives(message: Message):
    await show_creatives_list(message, message.from_user.id)


@router.callback_query(F.data == "creo_list")
async def cb_creatives_list(callback: CallbackQuery):
    await show_creatives_list(callback, callback.from_user.id)
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
            reply_markup=kb
        )
    else:
        await callback.message.edit_text(
            caption, parse_mode="HTML", disable_web_page_preview=True, reply_markup=kb
        )
    await callback.answer()


# ── Создание ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "creo_new")
async def cb_creative_new(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✏️ <b>Новый креатив — шаг 1/2</b>\n\n"
        "Введи название шаблона:\n"
        "<i>Например: Пост у блогера, Баннер апрель</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
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
            reply_markup=cancel_kb()
        )
    await state.update_data(creative_name=name)
    await message.answer(
        f"✏️ <b>Новый креатив — шаг 2/2</b>\n\n"
        f"Название: <b>{html.escape(name)}</b>\n\n"
        "Теперь отправь текст шаблона (или фото с подписью):\n\n"
        + TEMPLATE_HELP,
        parse_mode="HTML",
        reply_markup=cancel_kb()
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
            reply_markup=cancel_kb()
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
        await message.answer_photo(
            photo=photo_file_id,
            caption=preview_text,
            parse_mode="HTML"
        )
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
    # Если сейчас есть фото — удаляем сообщение и отправляем текстом
    # (edit_text не работает на photo-сообщениях)
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
            reply_markup=cancel_kb()
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
        await message.answer_photo(
            photo=photo_file_id,
            caption=preview_text,
            parse_mode="HTML"
        )
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

async def ask_apply_creative(message: Message, user_id: int, link_url: str):
    creatives = await queries.get_creatives(user_id)
    if not creatives:
        return

    buttons = []
    for c in creatives:
        icon = "🖼" if c["photo_file_id"] else "✏️"
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {c['name']}",
            callback_data=f"apply_creo:{c['id']}:{link_url}"
        )])
    buttons.append([
        InlineKeyboardButton(text="➕ Новый шаблон", callback_data="creo_new"),
        InlineKeyboardButton(text="Пропустить →",    callback_data="creo_skip"),
    ])

    await message.answer(
        "✏️ Подставить ссылку в шаблон?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("apply_creo:"))
async def cb_apply_creative(callback: CallbackQuery, bot: Bot):
    # apply_creo:<id>:<url>  — url может содержать ":", поэтому maxsplit=2
    parts = callback.data.split(":", 2)
    creative_id = int(parts[1])
    link_url = parts[2]

    c = await queries.get_creative(creative_id, callback.from_user.id)
    if not c:
        return await callback.answer("Шаблон не найден.", show_alert=True)

    # Генерируем результат и сначала отправляем заголовок
    result = apply_template(c["template"], link_url)
    header = f"✏️ <b>{html.escape(c['name'])}</b>\n\n<i>Вот твой креатив.</i>"

    # Удаляем сообщение с кнопками (если возможно)
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Сначала шлём заголовок, затем чистый креатив (без лишнего текста)
    await bot.send_message(callback.from_user.id, header, parse_mode="HTML")

    if c["photo_file_id"]:
        await bot.send_photo(
            chat_id=callback.from_user.id,
            photo=c["photo_file_id"],
            caption=result,
            parse_mode="HTML",
        )
    else:
        await bot.send_message(callback.from_user.id, result, parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()


@router.callback_query(F.data == "creo_skip")
async def cb_creo_skip(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()


@router.callback_query(F.data.startswith("creo_apply_choose:"))
async def cb_creo_apply_choose(callback: CallbackQuery):
    # Показываем список ссылок пользователя для выбора
    creative_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    # Проверим, что шаблон существует
    c = await queries.get_creative(creative_id, user_id)
    if not c:
        return await callback.answer("Креатив не найден.", show_alert=True)

    links = await queries.get_links(user_id)
    if not links:
        await callback.answer("У тебя нет ссылок.", show_alert=True)
        return

    buttons = []
    for l in links:
        # Показываем метку и домен/сокращённый URL
        label = l["label"] or l["link"]
        display = label if len(label) < 40 else label[:37] + "..."
        buttons.append([InlineKeyboardButton(text=f"🔗 {display}", callback_data=f"creo_apply_with_link:{creative_id}:{l['id']}")])

    buttons.append([
        InlineKeyboardButton(text="◀️ Назад", callback_data=f"creo_view:{creative_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="creo_list"),
    ])

    try:
        await callback.message.edit_text(
            "Выбери ссылку для подстановки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML"
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer("Выбери ссылку для подстановки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("creo_apply_with_link:"))
async def cb_creo_apply_with_link(callback: CallbackQuery, bot: Bot):
    # creo_apply_with_link:<creative_id>:<link_id>
    parts = callback.data.split(":")
    creative_id = int(parts[1])
    link_id = int(parts[2])
    user_id = callback.from_user.id

    c = await queries.get_creative(creative_id, user_id)
    if not c:
        return await callback.answer("Креатив не найден.", show_alert=True)

    l = await queries.get_link(link_id, user_id)
    if not l:
        return await callback.answer("Ссылка не найдена.", show_alert=True)

    link_url = l["link"]
    result = apply_template(c["template"], link_url)
    header = f"✏️ <b>{html.escape(c['name'])}</b>\n\n<i>Вот твой креатив.</i>"

    try:
        await callback.message.delete()
    except Exception:
        pass

    await bot.send_message(user_id, header, parse_mode="HTML")
    if c["photo_file_id"]:
        await bot.send_photo(
            chat_id=user_id,
            photo=c["photo_file_id"],
            caption=result,
            parse_mode="HTML",
        )
    else:
        await bot.send_message(user_id, result, parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()
