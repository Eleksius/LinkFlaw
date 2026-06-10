from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from db import queries

router = Router()

PLACEHOLDER = "{link}"


class CreativeStates(StatesGroup):
    waiting_name = State()
    waiting_template = State()
    editing_template = State()


# ── Хелперы ───────────────────────────────────────────────────────────

def creatives_list_kb(creatives: list) -> InlineKeyboardMarkup:
    buttons = []
    for c in creatives:
        buttons.append([
            InlineKeyboardButton(
                text=f"✏️ {c['name']}",
                callback_data=f"creo_view:{c['id']}"
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=f"creo_delete:{c['id']}"
            ),
        ])
    buttons.append([
        InlineKeyboardButton(text="➕ Новый креатив", callback_data="creo_new")
    ])
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
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Удалить", callback_data=f"creo_delete_confirm:{creative_id}"),
            InlineKeyboardButton(text="❌ Отмена",  callback_data=f"creo_view:{creative_id}"),
        ]
    ])


async def show_creatives_list(target: Message | CallbackQuery, user_id: int):
    creatives = await queries.get_creatives(user_id)
    if not creatives:
        text = (
            "✏️ <b>Мои креативы</b>\n\n"
            "У тебя пока нет шаблонов.\n\n"
            "Шаблон — это текст рекламного поста с плейсхолдером <code>{link}</code>, "
            "который заменится на реальную ссылку.\n\n"
            "<b>Пример:</b>\n"
            "<i>Подписывайся на лучший канал! 👉 {link}</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать первый креатив", callback_data="creo_new")]
        ])
    else:
        text = f"✏️ <b>Мои креативы</b> ({len(creatives)})\n\nВыбери для просмотра или нажми 🗑 для удаления:"
        kb = creatives_list_kb(creatives)

    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


# ── Список креативов: кнопка + команда ────────────────────────────────

@router.message(F.text == "✏️ Мои креативы")
@router.message(Command("creatives"))
async def cmd_creatives(message: Message):
    await show_creatives_list(message, message.from_user.id)


@router.callback_query(F.data == "creo_list")
async def cb_creatives_list(callback: CallbackQuery):
    await show_creatives_list(callback, callback.from_user.id)
    await callback.answer()


# ── Просмотр конкретного креатива ─────────────────────────────────────

@router.callback_query(F.data.startswith("creo_view:"))
async def cb_creative_view(callback: CallbackQuery):
    creative_id = int(callback.data.split(":")[1])
    c = await queries.get_creative(creative_id, callback.from_user.id)
    if not c:
        return await callback.answer("Креатив не найден.", show_alert=True)

    preview = c["template"].replace(PLACEHOLDER, "https://t.me/+xxxxxx")
    text = (
        f"✏️ <b>{c['name']}</b>\n\n"
        f"<b>Шаблон:</b>\n<code>{c['template']}</code>\n\n"
        f"<b>Пример:</b>\n{preview}"
    )
    await callback.message.edit_text(
        text, parse_mode="HTML",
        reply_markup=creative_actions_kb(creative_id),
        disable_web_page_preview=True
    )
    await callback.answer()


# ── Создание нового креатива ──────────────────────────────────────────

@router.callback_query(F.data == "creo_new")
async def cb_creative_new(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✏️ <b>Новый креатив</b>\n\n"
        "Введи название для этого шаблона:\n"
        "<i>Например: Пост у блогера, Баннер ВК, Кнопка в посте</i>",
        parse_mode="HTML"
    )
    await state.set_state(CreativeStates.waiting_name)
    await callback.answer()


@router.message(CreativeStates.waiting_name)
async def process_creative_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) > 64:
        return await message.answer("❌ Название слишком длинное (макс. 64 символа). Попробуй ещё:")
    await state.update_data(creative_name=name)
    await message.answer(
        f"✅ Название: <b>{name}</b>\n\n"
        "Теперь введи текст шаблона.\n"
        f"Используй <code>{PLACEHOLDER}</code> — туда подставится ссылка.\n\n"
        "<b>Пример:</b>\n"
        "<code>Подписывайся! 👉 {link}\n\nЛучший канал о криптe 🔥</code>",
        parse_mode="HTML"
    )
    await state.set_state(CreativeStates.waiting_template)


@router.message(CreativeStates.waiting_template)
async def process_creative_template(message: Message, state: FSMContext):
    template = message.text.strip()

    if PLACEHOLDER not in template:
        return await message.answer(
            f"❌ В шаблоне нет <code>{PLACEHOLDER}</code> — без него некуда подставлять ссылку.\n\n"
            "Добавь его в текст и отправь ещё раз:",
            parse_mode="HTML"
        )

    data = await state.get_data()
    name = data["creative_name"]
    await state.clear()

    await queries.save_creative(message.from_user.id, name, template)

    preview = template.replace(PLACEHOLDER, "https://t.me/+xxxxxx")
    await message.answer(
        f"✅ Креатив <b>{name}</b> сохранён!\n\n"
        f"<b>Пример с подставленной ссылкой:</b>\n\n"
        f"{preview}",
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# ── Редактирование шаблона ────────────────────────────────────────────

@router.callback_query(F.data.startswith("creo_edit:"))
async def cb_creative_edit(callback: CallbackQuery, state: FSMContext):
    creative_id = int(callback.data.split(":")[1])
    c = await queries.get_creative(creative_id, callback.from_user.id)
    if not c:
        return await callback.answer("Креатив не найден.", show_alert=True)

    await state.update_data(editing_creative_id=creative_id, creative_name=c["name"])
    await callback.message.edit_text(
        f"✏️ Редактирование <b>{c['name']}</b>\n\n"
        f"Текущий шаблон:\n<code>{c['template']}</code>\n\n"
        f"Отправь новый текст (не забудь <code>{PLACEHOLDER}</code>):",
        parse_mode="HTML"
    )
    await state.set_state(CreativeStates.editing_template)
    await callback.answer()


@router.message(CreativeStates.editing_template)
async def process_edit_template(message: Message, state: FSMContext):
    template = message.text.strip()
    if PLACEHOLDER not in template:
        return await message.answer(
            f"❌ В шаблоне нет <code>{PLACEHOLDER}</code>.\n\nПопробуй ещё раз:",
            parse_mode="HTML"
        )

    data = await state.get_data()
    creative_id = data["editing_creative_id"]
    name = data["creative_name"]
    await state.clear()

    await queries.save_creative(message.from_user.id, name, template)

    preview = template.replace(PLACEHOLDER, "https://t.me/+xxxxxx")
    await message.answer(
        f"✅ Шаблон <b>{name}</b> обновлён!\n\n"
        f"<b>Пример:</b>\n\n{preview}",
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# ── Удаление креатива ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("creo_delete:"))
async def cb_creative_delete(callback: CallbackQuery):
    creative_id = int(callback.data.split(":")[1])
    c = await queries.get_creative(creative_id, callback.from_user.id)
    if not c:
        return await callback.answer("Креатив не найден.", show_alert=True)

    await callback.message.edit_text(
        f"❓ Удалить креатив <b>{c['name']}</b>?",
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
    await callback.answer(f"✅ Удалён.", show_alert=True)
    await show_creatives_list(callback, callback.from_user.id)


# ── Публичная функция: применить шаблон к ссылке ──────────────────────
# Используется из links.py после создания ссылки

def apply_template(template: str, link_url: str) -> str:
    return template.replace(PLACEHOLDER, link_url)


async def ask_apply_creative(message: Message, user_id: int, link_url: str):
    """После создания ссылки предложить выбрать креатив для подстановки."""
    creatives = await queries.get_creatives(user_id)
    if not creatives:
        return  # нет шаблонов — ничего не предлагаем

    buttons = [
        [InlineKeyboardButton(
            text=f"✏️ {c['name']}",
            callback_data=f"apply_creo:{c['id']}:{link_url}"
        )]
        for c in creatives
    ]
    buttons.append([
        InlineKeyboardButton(text="➕ Создать новый шаблон", callback_data="creo_new"),
        InlineKeyboardButton(text="Пропустить →",            callback_data="creo_skip"),
    ])

    await message.answer(
        "✏️ Хочешь подставить ссылку в шаблон?\nВыбери креатив:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("apply_creo:"))
async def cb_apply_creative(callback: CallbackQuery):
    # apply_creo:<creative_id>:<link_url>
    # link_url может содержать ":", поэтому split максимум на 3 части
    parts = callback.data.split(":", 2)
    creative_id = int(parts[1])
    link_url = parts[2]

    c = await queries.get_creative(creative_id, callback.from_user.id)
    if not c:
        return await callback.answer("Шаблон не найден.", show_alert=True)

    result = apply_template(c["template"], link_url)
    await callback.message.edit_text(
        f"✅ <b>{c['name']}</b> — готовый текст:\n\n"
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
