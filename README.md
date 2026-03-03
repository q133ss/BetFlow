# BotChain Telegram Bot (Polling + Web Admin)

Python-бот с оплатой по чеку и отдельной веб-админкой (логин/пароль).

## Что реализовано

- `/start` с welcome-текстом и кнопкой `subscribe`
- `/subscribe` и кнопка `subscribe` с инструкцией по оплате + кнопка `Cancel`
- Прием чека (фото/документ), создание транзакции `pending`
- Уведомление админа в бот на русском + кнопка `Открыть приложение`
- Отдельная веб-админка `/admin` с логином `/admin/login`
- В админке:
  - управление каналами/чатами для membership-операций (через БД)
  - список пользователей
  - история диалога пользователя
  - список платежей
  - подтверждение/отклонение платежа
  - кнопка выдачи подписки пользователю
  - кнопка отмены подписки пользователя
- При подтверждении:
  - выдается подписка на 30 дней
  - пользователю отправляется ссылка `PREMIUM_FOLDER_LINK`
- Авто-ревок: бот периодически проверяет истекшие подписки и удаляет (ban) пользователей из активных каналов в БД (`managed_chats`)

## 1) Локальный запуск через venv (Windows PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# заполните .env
python -m botchain.main
```

Бот работает через **long polling**.

## 2) Запуск через Docker

```powershell
Copy-Item .env.example .env
# заполните .env
mkdir data -ErrorAction SilentlyContinue
docker compose up -d --build
```

Проверка API:

```powershell
curl http://localhost:8080/health
```

## .env параметры

- `TELEGRAM_BOT_TOKEN` - токен бота
- `ADMIN_TELEGRAM_ID` - Telegram user ID админа (куда бот шлет новые чеки)
- `PUBLIC_ADMIN_URL` - публичный URL панели (например, `https://domain.com`)
- `ADMIN_WEB_USERNAME` - логин админки
- `ADMIN_WEB_PASSWORD` - пароль админки
- `ADMIN_SESSION_SECRET` - длинный случайный секрет для cookie-сессии
- `PREMIUM_FOLDER_LINK` - ссылка, которая отправится после подтверждения оплаты
- `MANAGED_CHAT_IDS` - опциональный сид для первичного заполнения `managed_chats` (после этого каналами управляйте в админке)
- `SUBSCRIPTION_SWEEP_SECONDS` - интервал проверки истекших подписок в секундах (минимум 30)
- `DB_PATH` - путь к SQLite (по умолчанию `./botchain.db`)
- `API_HOST` - хост API (по умолчанию `0.0.0.0`)
- `API_PORT` - порт API (по умолчанию `8080`)

## Файлы

- `botchain/main.py` - запуск polling-бота + FastAPI
- `botchain/bot.py` - Telegram handlers
- `botchain/admin_web.py` - backend админки + login/password auth
- `botchain/db.py` - SQLite и бизнес-логика подписок/платежей
- `botchain/static/login.html` - страница входа
- `botchain/static/admin.html` - интерфейс админки
