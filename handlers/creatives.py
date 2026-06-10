import html
import re

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from db import queries

router = Router()

# Плейсхолдер, который пользователь пишет в шаблоне
PLACEHOLDER = "{link}"

# Формат гиперссылки в шаблоне: [текст кнопки]({link})
# При подстановке → <a href="https://t.me/...">текст кнопки</a>
HYPERLINK_RE = re.compile(r'\[([^\]]+)\]\(\{link\}\)')


class CreativeStates(StatesGroup):
    waiting_name = State()
    waiting_template = State()
    editing_template = State()


# ── Применение шаблона ────────────────────────────────────────────────

def apply_template(template: str, link_url: str) -> str:
    """
    Подставляет ссылку в шаблон. Поддерживает два формата:
      1. Гиперссылка: [текст]({link})  →  <a href="URL">текст</a>
      2. Голая ссылка: {link}          →  URL
    """
    # Сначала обрабатываем гиперссылки — они должны идти до голой замены
    result = HYPERLINK_RE.sub(
        lambda m: f'<a href="{html.escape(link_url)}">{m.group(1)}</a>',
        template
    )
    # Потом заменяем оставшиеся голые {link}
    result = result.replace(PLACEHOLDER, link_url)
    return result


def _preview(template: str) -> str:
    return apply_template(template, "https://t.me/+xxxxxx")


def _has_placeholder(template: str) -> bool:
    """Возвращает True если в шаблоне есть {link} — хоть в гиперссылке, хоть отдельно."""
    return PLACEHOLDER in template


# ── Клавиатуры ────────────────────────────────────────────────────────

def creatives_list_kb(creatives: list) -> InlineKeyboardMarkup:
    buttons = []
    for c in creatives:
        buttons.append([
            InlineKeyboardButton(text=f"✏️ {c['name']}", callback_data=f"creo_view:{c['id']}"),
            InlineKeyboardButton(text="🗑",               callback_data=f"creo_delete:{c['id']}"),
        ])
    buttons.append([InlineKeyboardButton(text="➕ Новый креатив", callback_data="creo_new")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def creative_actions_kb(creative_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"creo_edit:{creative_id}"),
            InlineKeyboardButton(text="🗑 Удалить",        callback_data=f"creo_delete:{creative_id}"),
        ],
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


# ── Текст подсказки по форматам ───────────────────────────────────────

TEMPLATE_HELP = (
    "Используй <code>{link}</code> там, где должна встать ссылка.\n\n"
    "<b>Варианты:</b>\n"
    "• Голая ссылка:\n"
    "  <code>Подписывайся 👉 {link}</code>\n\n"
    "• Гиперссылка (кликабельный текст):\n"
    "  <code>Подписывайся 👉 [нажми сюда]({link})</code>\n"
    "  <code>[🔥 Лучший канал о крипте]({link})</code>\n\n"
    "  Формат: <code>[текст]({link})</code>"
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
async def cb_creative_view(callback: CallbackQuery):
    creative_id = int(callback.data.split(":")[1])
    c = await queries.get_creative(creative_id, callback.from_user.id)
    if not c:
        return await callback.answer("Креатив не найден.", show_alert=True)

    text = (
        f"✏️ <b>{html.escape(c['name'])}</b>\n\n"
        f"<b>Шаблон:</b>\n<code>{html.escape(c['template'])}</code>\n\n"
        f"<b>Пример (с тестовой ссылкой):</b>\n{_preview(c['template'])}"
    )
    await callback.message.edit_text(
        text, parse_mode="HTML", disable_web_page_preview=True,
        reply_markup=creative_actions_kb(creative_id)
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
    name = message.text.strip()
    if len(name) > 64:
        return await message.answer(
            "❌ Название слишком длинное (макс. 64 символа). Попробуй ещё:",
            reply_markup=cancel_kb()
        )
    await state.update_data(creative_name=name)
    await message.answer(
        f"✏️ <b>Новый креатив — шаг 2/2</b>\n\n"
        f"Название: <b>{html.escape(name)}</b>\n\n"
        "Теперь введи текст шаблона:\n\n"
        + TEMPLATE_HELP,
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await state.set_state(CreativeStates.waiting_template)


@router.message(CreativeStates.waiting_template)
async def process_creative_template(message: Message, state: FSMContext):
    template = message.text.strip()

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

    await queries.save_creative(message.from_user.id, name, template)

    await message.answer(
        f"✅ Креатив <b>{html.escape(name)}</b> сохранён!\n\n"
        f"<b>Пример:</b>\n\n{_preview(template)}",
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# ── Редактирование ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("creo_edit:"))
async def cb_creative_edit(callback: CallbackQuery, state: FSMContext):
    creative_id = int(callback.data.split(":")[1])
    c = await queries.get_creative(creative_id, callback.from_user.id)
    if not c:
        return await callback.answer("Креатив не найден.", show_alert=True)

    await state.update_data(editing_creative_id=creative_id, creative_name=c["name"])
    await callback.message.edit_text(
        f"✏️ Редактирование <b>{html.escape(c['name'])}</b>\n\n"
        f"Текущий шаблон:\n<code>{html.escape(c['template'])}</code>\n\n"
        "Отправь новый текст шаблона:\n\n"
        + TEMPLATE_HELP,
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await state.set_state(CreativeStates.editing_template)
    await callback.answer()


@router.message(CreativeStates.editing_template)
async def process_edit_template(message: Message, state: FSMContext):
    template = message.text.strip()
    if not _has_placeholder(template):
        return await message.answer(
            f"❌ В шаблоне нет <code>{PLACEHOLDER}</code>.\n\n" + TEMPLATE_HELP,
            parse_mode="HTML",
            reply_markup=cancel_kb()
        )

    data = await state.get_data()
    name = data["creative_name"]
    await state.clear()

    await queries.save_creative(message.from_user.id, name, template)

    await message.answer(
        f"✅ Шаблон <b>{html.escape(name)}</b> обновлён!\n\n"
        f"<b>Пример:</b>\n\n{_preview(template)}",
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# ── Удаление ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("creo_delete:"))
async def cb_creative_delete(callback: CallbackQuery):
    creative_id = int(callback.data.split(":")[1])
    c = await queries.get_creative(creative_id, callback.from_user.id)
    if not c:
        return await callback.answer("Креатив не найден.", show_alert=True)

    await callback.message.edit_text(
        f"❓ Удалить креатив <b>{html.escape(c['name'])}</b>?",
        parse_mode="HTML",
        reply_markup=confirm_delete_creative_kb(creative_id)
    )
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

    buttons = [
        [InlineKeyboardButton(
            text=f"✏️ {c['name']}",
            callback_data=f"apply_creo:{c['id']}:{link_url}"
        )]
        for c in creatives
    ]
    buttons.append([
        InlineKeyboardButton(text="➕ Новый шаблон", callback_data="creo_new"),
        InlineKeyboardButton(text="Пропустить →",    callback_data="creo_skip"),
    ])

    await message.answer(
        "✏️ Подставить ссылку в шаблон?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("apply_creo:"))
async def cb_apply_creative(callback: CallbackQuery):
    # apply_creo:<id>:<url>  — url может содержать ":", поэтому maxsplit=2
    parts = callback.data.split(":", 2)
    creative_id = int(parts[1])
    link_url = parts[2]

    c = await queries.get_creative(creative_id, callback.from_user.id)
    if not c:
        return await callback.answer("Шаблон не найден.", show_alert=True)

    result = apply_template(c["template"], link_url)
    await callback.message.edit_text(
        f"✏️ <b>{html.escape(c['name'])}</b>\n\n"
        f"{result}\n\n"
        "<i>Скопируй и вставь в рекламный пост.</i>",
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    await callback.answer()


@router.callback_query(F.data == "creo_skip")
async def cb_creo_skip(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()
