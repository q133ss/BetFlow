START_TEMPLATE = """Welcome to BotChain!

To get access, follow these 3 steps:
1. Send /subscribe
2. Send a payment receipt screenshot or file
3. Wait for payment verification by the admin

User: {first_name}"""

SUBSCRIBE_TEXT = """Great, let's start your subscription.

You have 5 hours to send your receipt. ⏳

Price: 200€ for 30 days.

Payment method:
TRC20 USDT
TMPiXpboFH3YCrJKSVUDjkWyaKe6WcdAXy

After payment, send your receipt screenshot or file in this chat.
After payment verification, you will receive your subscription."""

RECEIPT_ACCEPTED_TEXT = """Receipt received.

After payment verification, you will receive your subscription.
We will notify you as soon as the admin makes a decision. ⏳"""

APPROVED_TEMPLATE = """Payment approved. ✅
Your 30-day subscription is now active.

Premium link:
{premium_link}"""

REJECTED_TEMPLATE = """Payment was rejected. ❌
Reason: {reason}

Send /subscribe and upload a new receipt."""

CANCELED_BY_ADMIN_TEMPLATE = """Your subscription was canceled by an admin.
Reason: {reason}

If this is unexpected, please contact support."""

ASSIGNED_BY_ADMIN_TEMPLATE = """Subscription granted by admin. ✅
Your access has been extended by {days} day(s).

Premium link:
{premium_link}"""

SUBSCRIPTION_EXPIRING_TEMPLATE = """Напоминание: подписка закончится через {days} дн.
Продлите ее заранее, чтобы не потерять доступ.

Отправьте /subscribe для продления."""

SUBSCRIPTION_EXPIRED_TEMPLATE = """Ваша подписка закончилась.
Доступ к премиум-каналам отключен.

Отправьте /subscribe для продления доступа."""

ADMIN_SUBSCRIPTION_EXPIRED_TEMPLATE = """Авто-истечение обработано.

Пользователь: {full_name}
Username: {username}
User ID: {user_id}
Подписка истекла: {subscription_end_at}

Авто-исключен из чатов: {removed}
Ошибки исключения: {failed}"""
