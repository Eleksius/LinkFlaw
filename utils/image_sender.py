"""
Утилита для отправки изображений с текстом в Telegram.
Убирает дублирование кода из handlers/links.py и handlers/creatives.py.
"""

import os
import logging
from typing import Union

from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def images_path(filename: str) -> str:
    return os.path.join(_BASE_DIR, "images", filename)


async def send_with_photo(
    target: Union[Message, CallbackQuery],
    image_filename: str,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str = "HTML",
    edit_if_possible: bool = False,
) -> None:
    """
    Отправляет фото с подписью. Если фото не найдено — отправляет текст.

    При edit_if_possible=True пытается отредактировать сообщение (только текстовое).
    """
    msg: Message = target if isinstance(target, Message) else target.message

    img_path = images_path(image_filename)
    kwargs = dict(reply_markup=reply_markup, parse_mode=parse_mode)

    if os.path.isfile(img_path):
        photo = FSInputFile(img_path)
        # caption у Telegram ограничен 1024 символами
        safe_caption = caption if len(caption) <= 1024 else caption[:1020] + "…"
        await msg.answer_photo(photo=photo, caption=safe_caption, **kwargs)
    else:
        if edit_if_possible and isinstance(target, CallbackQuery):
            try:
                await msg.edit_text(caption, disable_web_page_preview=True, **kwargs)
                return
            except Exception:
                pass
        await msg.answer(caption, disable_web_page_preview=True, **kwargs)
