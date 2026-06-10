# 📢 Invite Link Bot — MVP

Telegram-бот для управления рекламными инвайт-ссылками с трекингом переходов.

## Возможности MVP

- 🔗 Создание именованных инвайт-ссылок через Telegram API
- 📊 Трекинг переходов (кто и когда вступил по какой ссылке)
- 📋 Список всех ссылок с количеством переходов
- 👥 База пользователей бота
- 📣 Рассылка сообщений всем пользователям

## Быстрый старт

### 1. Создай бота
Напиши [@BotFather](https://t.me/BotFather), команда `/newbot`.
Получи токен.

### 2. Установи зависимости

```bash
cd tgbot
pip install -r requirements.txt
```

### 3. Настрой конфиг

```bash
cp .env.example .env
# Отредактируй .env — вставь токен и свой Telegram ID
```

Узнать свой Telegram ID: напиши [@userinfobot](https://t.me/userinfobot)

### 4. Запусти бота

```bash
python bot.py
```

## Как использовать

### Подключить канал
1. Добавь бота в канал как **администратора**
2. Выдай право: **Пригласительные ссылки** (Invite Users)
3. Перешли боту в личку **любое сообщение** из этого канала

### Создать ссылку для рекламы
```
/create_link
```
→ Выбрать канал → Ввести метку (например: `Пост у @channel`)
→ Получить ссылку → Вставить в рекламный пост

### Статистика
```
/stats        — переходы по всем ссылкам
/links        — список ссылок
/users        — пользователи бота
```

### Рассылка
```
/broadcast    — отправить сообщение всем пользователям
```

## Структура проекта

```
tgbot/
├── bot.py              # Точка входа, глобальные хэндлеры
├── config.py           # Конфигурация из .env
├── requirements.txt
├── .env.example
├── db/
│   ├── models.py       # Инициализация БД (SQLite)
│   └── queries.py      # Все запросы к БД
├── handlers/
│   ├── links.py        # Создание и управление ссылками
│   ├── stats.py        # Статистика
│   └── admin.py        # Пользователи и рассылка
└── utils/
    └── formatters.py   # Форматирование текста
```

## Деплой на сервер

```bash
# Установить как systemd-сервис (Ubuntu/Debian)
sudo nano /etc/systemd/system/invitebot.service
```

```ini
[Unit]
Description=Invite Link Bot
After=network.target

[Service]
WorkingDirectory=/path/to/tgbot
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable invitebot
sudo systemctl start invitebot
```

## Что можно добавить в следующей версии

- [ ] Авто-ротация ссылок (автоматически заменять ссылки в постах)
- [ ] Лимиты на инвайт-ссылки (макс. участников, срок действия)
- [ ] Веб-дашборд со статистикой
- [ ] Интеграция с Google Sheets
- [ ] Мультитенантность (несколько команд/клиентов)
- [ ] PostgreSQL вместо SQLite
- [ ] Экспорт статистики в CSV
