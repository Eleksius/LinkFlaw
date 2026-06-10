from datetime import datetime


def fmt_date(dt_str: str) -> str:
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return dt_str


def fmt_link_row(label: str, link: str, joins: int, created_at: str) -> str:
    return (
        f"🔗 <b>{label}</b>\n"
        f"   └ <code>{link}</code>\n"
        f"   └ 👥 Переходов: <b>{joins}</b>  |  📅 {fmt_date(created_at)}\n"
    )


def fmt_channel_option(idx: int, title: str, channel_id: int) -> str:
    return f"{idx}. <b>{title}</b> (<code>{channel_id}</code>)"
