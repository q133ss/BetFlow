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
  - пользователю отправляется ссылка на премиум-папку из БД (`app_settings.premium_folder_link`)
- Событийный membership-контроль:
  - бот отслеживает `chat_member` и при входе в активный канал проверяет подписку в БД
  - если подписка неактивна, пользователь автоматически исключается из канала
- Авто-ревок: бот периодически проверяет истекшие подписки и удаляет пользователей из активных каналов
- Ссылка на премиум-папку редактируется в веб-админке (Home -> Premium Folder Link)

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

## 3) Команды для прод-хоста (Ubuntu + systemd)

Подключение:

```bash
ssh root@89.169.39.62
cd /var/www/html/BetFlow
```

После изменения `.env`:

```bash
sudo systemctl restart betflow
sudo systemctl status betflow
sudo journalctl -u betflow -n 100 --no-pager
```

Перезапуск Apache (только если меняли его конфиг):

```bash
sudo apache2ctl configtest
sudo systemctl reload apache2
```

Полная перезагрузка хоста:

```bash
sudo reboot
```

## .env параметры

- `TELEGRAM_BOT_TOKEN` - токен бота
- `ADMIN_TELEGRAM_ID` - Telegram user ID админа (куда бот шлет новые чеки)
- `PUBLIC_ADMIN_URL` - публичный URL панели (например, `https://domain.com`)
- `ADMIN_WEB_USERNAME` - логин админки
- `ADMIN_WEB_PASSWORD` - пароль админки
- `ADMIN_SESSION_SECRET` - длинный случайный секрет для cookie-сессии
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
