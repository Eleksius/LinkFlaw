import asyncio

from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from db import queries
from config import is_admin
from handlers.keyboards import broadcast_confirm_kb

router = Router()


class BroadcastStates(StatesGroup):
    waiting_message = State()
    confirm = State()


# ── /users — только для админа ────────────────────────────────────────

@router.message(Command("users"))
async def cmd_users(message: Message):
    if not is_admin(message.from_user.id):
        return

    users = await queries.get_all_users()
    count = len(users)

    if not users:
        return await message.answer("👥 Пользователей пока нет.")

    text = f"👥 <b>Пользователи бота</b> ({count})\n\n"
    for u in users[:50]:
        name = u["first_name"] or ""
        if u["last_name"]:
            name += f" {u['last_name']}"
        username_part = f" @{u['username']}" if u["username"] else ""
        text += f"• <a href='tg://user?id={u['user_id']}'>{name}</a>{username_part} — <code>{u['user_id']}</code>\n"

    if count > 50:
        text += f"\n... и ещё {count - 50} пользователей"

    await message.answer(text, parse_mode="HTML")


# ── Рассылка: кнопка + команда ───────────────────────────────────────

@router.message(F.text == "📣 Рассылка")
@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    user_count = await queries.get_user_count()
    await message.answer(
        f"📣 <b>Рассылка</b>\n\n"
        f"Получателей: <b>{user_count}</b>\n\n"
        "Отправь сообщение для рассылки (текст, фото, видео — любой тип).\n"
        "Или /cancel для отмены.",
        parse_mode="HTML"
    )
    await state.set_state(BroadcastStates.waiting_message)


@router.message(Command("cancel"), BroadcastStates.waiting_message)
@router.message(Command("cancel"), BroadcastStates.confirm)
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Отменено.")


@router.message(BroadcastStates.waiting_message)
async def process_broadcast_message(message: Message, state: FSMContext):
    await state.update_data(message_id=message.message_id, from_chat=message.chat.id)
    await message.answer(
        "👆 Это сообщение получат все пользователи.\n\n"
        "Подтверди отправку:",
        reply_markup=broadcast_confirm_kb()
    )
    await state.set_state(BroadcastStates.confirm)


@router.callback_query(F.data == "broadcast_cancel", BroadcastStates.confirm)
async def cb_broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.")
    await callback.answer()


@router.callback_query(F.data == "broadcast_confirm", BroadcastStates.confirm)
async def cb_broadcast_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()

    users = await queries.get_all_users(skip_blocked=True)
    success, failed = 0, 0

    await callback.message.edit_text(f"⏳ Отправляю... 0/{len(users)}")

    for i, user in enumerate(users):
        try:
            await bot.copy_message(
                chat_id=user["user_id"],
                from_chat_id=data["from_chat"],
                message_id=data["message_id"]
            )
            success += 1
        except Exception:
            failed += 1

        if (i + 1) % 20 == 0:
            try:
                await callback.message.edit_text(f"⏳ Отправляю... {i+1}/{len(users)}")
            except Exception:
                pass

        await asyncio.sleep(0.05)

    await callback.message.edit_text(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"📤 Отправлено: {success}\n"
        f"❌ Не доставлено: {failed}",
        parse_mode="HTML"
    )
    await callback.answer()
