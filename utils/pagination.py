"""
Утилита постраничной навигации для inline-клавиатур.

Использование:
    pages = paginate(items, page=0, per_page=10)
    nav = nav_row(pages, page=0, cb_prefix="creo_page")
    # nav_row вернёт список кнопок «← Назад» / «→ Вперёд» для вставки в клавиатуру
"""

from __future__ import annotations
from typing import TypeVar, Sequence

from aiogram.types import InlineKeyboardButton

T = TypeVar("T")

PER_PAGE = 8  # элементов на странице — умещается в любом списке


def paginate(items: Sequence[T], page: int, per_page: int = PER_PAGE) -> list[T]:
    """Вернуть срез items для нужной страницы (0-based)."""
    start = page * per_page
    return list(items[start: start + per_page])


def total_pages(items: Sequence, per_page: int = PER_PAGE) -> int:
    return max(1, (len(items) + per_page - 1) // per_page)


def nav_row(
    items: Sequence,
    page: int,
    cb_prefix: str,
    per_page: int = PER_PAGE,
) -> list[InlineKeyboardButton] | None:
    """
    Строка навигации ← / → для встраивания в клавиатуру.
    Возвращает None если страниц всего одна (строка не нужна).

    cb_prefix: строка вида «creo_page» → callback_data = «creo_page:0», «creo_page:1» и т.д.
    """
    total = total_pages(items, per_page)
    if total <= 1:
        return None

    row: list[InlineKeyboardButton] = []

    if page > 0:
        row.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"{cb_prefix}:{page - 1}"))

    row.append(InlineKeyboardButton(
        text=f"{page + 1} / {total}",
        callback_data="page_noop",   # счётчик — нажатие ничего не делает
    ))

    if page < total - 1:
        row.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"{cb_prefix}:{page + 1}"))

    return row
