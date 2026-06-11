from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, MessageOriginChannel
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from db import queries
from utils.formatters import fmt_link_row
from handlers.keyboards import channel_select_kb, channels_manage_kb, confirm_delete_channel_kb
from handlers.creatives import ask_apply_creative

router = Router()


class CreateLinkStates(StatesGroup):
    waiting_channel = State()
    waiting_label = State()


# ── Общий обработчик отмены для всех FSM ─────────────────────────────

@router.callback_query(F.data == "cancel_action")
async def cb_cancel_action(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    from handlers.keyboards import main_kb, admin_main_kb
    user_id = callback.from_user.id
    is_adm = user_id in __import__("config").ADMIN_IDS
    try:
        await callback.message.edit_text("❌ Действие отменено.", reply_markup=admin_main_kb() if is_adm else main_kb())
    except Exception:
        await callback.message.delete()
        await callback.message.answer("❌ Действие отменено.", reply_markup=admin_main_kb() if is_adm else main_kb())
    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery):
    from handlers.keyboards import main_kb, admin_main_kb
    user_id = callback.from_user.id
    is_adm = user_id in __import__("config").ADMIN_IDS
    try:
        await callback.message.edit_text(
            "🏠 Главное меню", reply_markup=admin_main_kb() if is_adm else main_kb()
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer("🏠 Главное меню", reply_markup=admin_main_kb() if is_adm else main_kb())
    await callback.answer()


# ── Хелпер: показать список каналов ──────────────────────────────────

async def show_channels(target: Message | CallbackQuery, user_id: int):
    channels = await queries.get_channels(user_id)
    text = "📢 <b>Мои каналы</b>\n\n"
    if not channels:
        text += (
            "У тебя пока нет добавленных каналов.\n\n"
            "<b>Как добавить:</b>\n"
            "1. Добавь бота в канал как <b>администратора</b>\n"
            "2. Дай право <b>Пригласительные ссылки</b>\n"
            "3. Перешли сюда любое сообщение из этого канала"
        )
        msg = target if isinstance(target, Message) else target.message
        await msg.answer(text, parse_mode="HTML")
        return

    text += "Нажми на канал чтобы посмотреть ссылки, или 🗑 чтобы удалить."
    kb = channels_manage_kb(channels)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


# ── Мои каналы ────────────────────────────────────────────────────────

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
    await callback.message.edit_text(
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
    user_id = callback.from_user.id
    channel = await queries.get_channel(channel_id, user_id)
    if not channel:
        return await callback.answer("Канал не найден.", show_alert=True)

    await callback.message.edit_text(
        f"❓ Удалить канал <b>{channel['channel_title']}</b>?\n\n"
        "Все ссылки этого канала будут деактивированы.",
        parse_mode="HTML",
        reply_markup=confirm_delete_channel_kb(channel_id)
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
            parse_mode="HTML"
        )

    # Попробуем показать иллюстрацию к экрану создания ссылки
    import os
    from aiogram.types import FSInputFile
    img_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "images", "create_link.png"))
    if os.path.isfile(img_path):
        photo = FSInputFile(img_path)
        await message.answer_photo(
            photo=photo,
            caption="📢 Выбери канал для создания ссылки:",
            reply_markup=channel_select_kb(channels),
            parse_mode="HTML"
        )
    else:
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

    from handlers.keyboards import cancel_kb
    await callback.message.edit_text(
        f"📢 Канал: <b>{channel['channel_title']}</b>\n\n"
        "✏️ Введи метку для ссылки\n"
        "<i>Например: Реклама у @durov, Баннер апрель</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
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
            f"🔗 <code>{link_url}</code>",
            parse_mode="HTML"
        )
        await ask_apply_creative(message, message.from_user.id, link_url)
    except Exception as e:
        await message.answer(
            f"❌ Не удалось создать ссылку.\n"
            f"Убедись, что бот является администратором канала с правом «Пригласительные ссылки».\n\n"
            f"Ошибка: <code>{e}</code>",
            parse_mode="HTML"
        )


# ── Мои ссылки + статистика (объединено) ─────────────────────────────

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

    # Формируем подробный текст со статистикой и клавиатуру
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 Подставить в креатив", callback_data="links_apply_creo")]])

    # Попробуем показать иллюстрацию к экрану со ссылками — если есть, отправим фото с клавиатурой, затем текст без клавиатуры
    import os
    from aiogram.types import FSInputFile
    img_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "images", "my_links.png"))
    if os.path.isfile(img_path):
        # Сначала проверим, доступна ли Pillow
        try:
            import PIL  # type: ignore
            pil_available = True
        except Exception:
            pil_available = False

        if pil_available:
            try:
                from PIL import Image, ImageDraw, ImageFont
                import textwrap
                import tempfile
                from uuid import uuid4

                base = Image.open(img_path).convert("RGB")
                # Параметры шрифта
                try:
                    font = ImageFont.truetype("arial.ttf", 18)
                except Exception:
                    font = ImageFont.load_default()

                # Подготовим текстовую часть и обернём по ширине
                max_chars = 60
                wrapped = textwrap.wrap(text, width=max_chars)
                line_h = font.getsize("A")[1] + 6
                padding = 16
                text_height = line_h * len(wrapped) + padding

                new_w = base.width
                new_h = base.height + text_height
                new_img = Image.new("RGB", (new_w, new_h), (255, 255, 255))
                new_img.paste(base, (0, 0))
                draw = ImageDraw.Draw(new_img)

                y = base.height + padding // 2
                x = padding // 2
                fill = (20, 20, 20)
                for line in wrapped:
                    draw.text((x, y), line, font=font, fill=fill)
                    y += line_h

                tmp_path = os.path.join(tempfile.gettempdir(), f"links_{user_id}_{uuid4().hex}.png")
                new_img.save(tmp_path, format="PNG")

                photo = FSInputFile(tmp_path)
                await message.answer_photo(photo=photo, caption="📊 <b>Мои ссылки</b>", parse_mode="HTML", reply_markup=kb)
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            except Exception:
                # Если что-то пошло не так при рендеринге — падаём к более простому варианту ниже
                pil_available = False

        if not pil_available:
            # Отправляем фото с укороченным caption, чтобы это было одно сообщение
            cap = text if len(text) <= 1024 else text[:1020] + "..."
            photo = FSInputFile(img_path)
            await message.answer_photo(photo=photo, caption=cap, parse_mode="HTML", reply_markup=kb)
    else:
        # Если картинки нет — отправляем текст с клавиатурой
        await message.answer(text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=kb)


# ── Авто-регистрация канала при пересылке ────────────────────────────

@router.message(F.forward_origin.type == "channel")
async def forward_from_channel(message: Message, bot: Bot):
    origin: MessageOriginChannel = message.forward_origin
    chat = origin.chat

    user_id = message.from_user.id

    # Проверяем, является ли пользователь администратором этого канала
    try:
        member = await bot.get_chat_member(chat_id=chat.id, user_id=user_id)
        if member.status not in ("administrator", "creator"):
            return await message.answer(
                f"❌ Ты не являешься администратором канала <b>{chat.title}</b>.\n\n"
                "Добавить канал могут только его администраторы.",
                parse_mode="HTML"
            )
    except TelegramForbiddenError:
        return await message.answer(
            f"❌ Бот не добавлен в канал <b>{chat.title}</b> или не имеет доступа.\n\n"
            "Сначала добавь бота в канал как <b>администратора</b> "
            "с правом <b>Пригласительные ссылки</b>.",
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        return await message.answer(
            f"❌ Не удалось проверить права в канале <b>{chat.title}</b>.\n\n"
            f"Убедись, что бот добавлен в канал как администратор.\n\n"
            f"<code>{e}</code>",
            parse_mode="HTML"
        )

    await queries.add_channel(chat.id, chat.title, user_id)
    await message.answer(
        f"✅ Канал <b>{chat.title}</b> добавлен!\n\n"
        "Убедись, что бот добавлен в этот канал как администратор "
        "с правом <b>Пригласительные ссылки</b>.",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "links_apply_creo")
async def cb_links_apply_creo(callback: CallbackQuery):
    user_id = callback.from_user.id
    links = await queries.get_links(user_id)
    if not links:
        await callback.answer("У тебя нет ссылок.", show_alert=True)
        return

    buttons = []
    for l in links:
        label = l["label"] or l["link"]
        display = label if len(label) < 40 else label[:37] + "..."
        buttons.append([InlineKeyboardButton(text=f"🔗 {display}", callback_data=f"link_apply_creo:{l['id']}")])

    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="back_channels")])
    try:
        await callback.message.edit_text("Выбери ссылку для подстановки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception:
        await callback.message.delete()
        await callback.message.answer("Выбери ссылку для подстановки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("link_apply_creo:"))
async def cb_link_apply_creo(callback: CallbackQuery):
    link_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    l = await queries.get_link(link_id, user_id)
    if not l:
        return await callback.answer("Ссылка не найдена.", show_alert=True)

    link_url = l["link"]
    # Вызов существующей функции, которая предложит шаблоны
    await ask_apply_creative(callback.message, user_id, link_url)
    await callback.answer()
