from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)


# ── Reply-клавиатура (нижнее меню) — одна для всех ────────────────────

def main_kb() -> ReplyKeyboardMarkup:
    """Основное меню — одинаковое для всех пользователей."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔗 Создать ссылку"), KeyboardButton(text="📋 Мои ссылки")],
            [KeyboardButton(text="📊 Моя статистика"), KeyboardButton(text="📢 Мои каналы")],
            [KeyboardButton(text="✏️ Мои креативы")],
        ],
        resize_keyboard=True,
    )


def admin_main_kb() -> ReplyKeyboardMarkup:
    """Меню с дополнительной кнопкой статистики бота для админа."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔗 Создать ссылку"), KeyboardButton(text="📋 Мои ссылки")],
            [KeyboardButton(text="📊 Моя статистика"), KeyboardButton(text="📢 Мои каналы")],
            [KeyboardButton(text="✏️ Мои креативы"),   KeyboardButton(text="🛡 Стата бота")],
            [KeyboardButton(text="📣 Рассылка")],
        ],
        resize_keyboard=True,
    )


# ── Inline-клавиатуры ─────────────────────────────────────────────────

def channels_manage_kb(channels: list) -> InlineKeyboardMarkup:
    """Список каналов пользователя с кнопкой удаления."""
    buttons = []
    for ch in channels:
        buttons.append([
            InlineKeyboardButton(
                text=f"📢 {ch['channel_title']}",
                callback_data=f"ch_info:{ch['channel_id']}"
            ),
            InlineKeyboardButton(
                text="🗑 Удалить",
                callback_data=f"ch_delete:{ch['channel_id']}"
            ),
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def channel_select_kb(channels: list) -> InlineKeyboardMarkup:
    """Выбор канала для создания ссылки."""
    buttons = [
        [InlineKeyboardButton(
            text=f"📢 {ch['channel_title']}",
            callback_data=f"select_channel:{ch['channel_id']}"
        )]
        for ch in channels
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_delete_channel_kb(channel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"ch_delete_confirm:{channel_id}"),
            InlineKeyboardButton(text="❌ Отмена",      callback_data="ch_delete_cancel"),
        ]
    ])


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_confirm"),
            InlineKeyboardButton(text="❌ Отменить",  callback_data="broadcast_cancel"),
        ]
    ])
