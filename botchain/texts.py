from __future__ import annotations

from typing import Any

BOT_MESSAGE_PREFIX = "bot_message."

BOT_MESSAGE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "key": "start_template",
        "title": "Start message",
        "description": "Sent after /start.",
        "placeholders": ["first_name"],
        "value": """Welcome to BotChain!\n\nTo get access, follow these 3 steps:\n1. Send /subscribe\n2. Send a payment receipt screenshot or file\n3. Wait for payment verification by the admin\n\nUser: {first_name}""",
    },
    {
        "key": "start_button_text",
        "title": "Start button",
        "description": "Button under /start message.",
        "placeholders": [],
        "value": "Subscribe",
    },
    {
        "key": "subscribe_text",
        "title": "Subscribe instructions",
        "description": "Sent after /subscribe or subscribe button.",
        "placeholders": [],
        "value": """Great, let's start your subscription.\n\nYou have 5 hours to send your receipt. ⏳\n\nPrice: 200€ for 30 days.\n\nPayment method:\nTRC20 USDT\nTMPiXpboFH3YCrJKSVUDjkWyaKe6WcdAXy\n\nAfter payment, send your receipt screenshot or file in this chat.\nAfter payment verification, you will receive your subscription.""",
    },
    {
        "key": "cancel_button_text",
        "title": "Cancel button",
        "description": "Button for active receipt flow.",
        "placeholders": [],
        "value": "Cancel",
    },
    {
        "key": "receipt_accepted_text",
        "title": "Receipt accepted",
        "description": "Sent when receipt is accepted and queued for review.",
        "placeholders": [],
        "value": """Receipt received.\n\nAfter payment verification, you will receive your subscription.\nWe will notify you as soon as the admin makes a decision. ⏳""",
    },
    {
        "key": "approved_template",
        "title": "Payment approved",
        "description": "Sent after payment approval.",
        "placeholders": ["premium_link"],
        "value": """Payment approved. ✅\nYour 30-day subscription is now active.\n\nPremium link:\n{premium_link}""",
    },
    {
        "key": "rejected_template",
        "title": "Payment rejected",
        "description": "Sent after payment rejection.",
        "placeholders": ["reason"],
        "value": """Payment was rejected. ❌\nReason: {reason}\n\nSend /subscribe and upload a new receipt.""",
    },
    {
        "key": "canceled_by_admin_template",
        "title": "Subscription canceled by admin",
        "description": "Sent when admin cancels active subscription.",
        "placeholders": ["reason"],
        "value": """Your subscription was canceled by an admin.\nReason: {reason}\n\nIf this is unexpected, please contact support.""",
    },
    {
        "key": "assigned_by_admin_template",
        "title": "Subscription assigned by admin",
        "description": "Sent when admin assigns subscription manually.",
        "placeholders": ["days", "premium_link"],
        "value": """Subscription granted by admin. ✅\nYour access has been extended by {days} day(s).\n\nPremium link:\n{premium_link}""",
    },
    {
        "key": "subscription_expiring_template",
        "title": "Subscription expiring reminder",
        "description": "Auto reminder before expiration.",
        "placeholders": ["days"],
        "value": """Напоминание: подписка закончится через {days} дн.\nПродлите ее заранее, чтобы не потерять доступ.\n\nОтправьте /subscribe для продления.""",
    },
    {
        "key": "subscription_expired_template",
        "title": "Subscription expired",
        "description": "Sent after subscription expiration.",
        "placeholders": [],
        "value": """Ваша подписка закончилась.\nДоступ к премиум-каналам отключен.\n\nОтправьте /subscribe для продления доступа.""",
    },
    {
        "key": "admin_subscription_expired_template",
        "title": "Admin expiration report",
        "description": "Sent to admin after auto expiration processing.",
        "placeholders": ["full_name", "username", "user_id", "subscription_end_at", "removed", "failed"],
        "value": """Авто-истечение обработано.\n\nПользователь: {full_name}\nUsername: {username}\nUser ID: {user_id}\nПодписка истекла: {subscription_end_at}\n\nАвто-исключен из чатов: {removed}\nОшибки исключения: {failed}""",
    },
    {
        "key": "info_template",
        "title": "Info command response",
        "description": "Sent on /info.",
        "placeholders": ["full_name", "username", "user_id", "status", "start_date", "end_date"],
        "value": """✨ User Details ✨\n\nFull Name: {full_name}\n\nUsername: {username}\n\nUser ID: {user_id}\n\nSubscription Details:\n\nStatus: {status}\n\n⏳ Start Date:\n{start_date}\n\nEnd Date:\n{end_date}""",
    },
    {
        "key": "info_status_subscribed",
        "title": "Info status: subscribed",
        "description": "Status label in /info for active subscription.",
        "placeholders": [],
        "value": "Subscribed",
    },
    {
        "key": "info_status_not_subscribed",
        "title": "Info status: not subscribed",
        "description": "Status label in /info for inactive subscription.",
        "placeholders": [],
        "value": "Not Subscribed",
    },
    {
        "key": "subscription_flow_canceled_text",
        "title": "Subscribe flow canceled",
        "description": "Sent when user presses Cancel in subscribe flow.",
        "placeholders": [],
        "value": "Subscription flow canceled. Send /subscribe when you're ready.",
    },
    {
        "key": "subscribe_first_before_receipt_text",
        "title": "Receipt before subscribe",
        "description": "Sent when user uploads receipt before /subscribe.",
        "placeholders": [],
        "value": "Please send /subscribe first, then upload your receipt.",
    },
    {
        "key": "receipt_window_expired_text",
        "title": "Receipt window expired",
        "description": "Sent when receipt timeout is exceeded.",
        "placeholders": [],
        "value": "Receipt window expired. Send /subscribe to request a new payment session.",
    },
    {
        "key": "receipt_unreadable_text",
        "title": "Receipt unreadable",
        "description": "Sent when bot cannot parse uploaded receipt file.",
        "placeholders": [],
        "value": "Could not read the receipt. Please send it as a photo or document.",
    },
    {
        "key": "default_help_text",
        "title": "Default help text",
        "description": "Sent on unknown plain text messages.",
        "placeholders": [],
        "value": "Send /subscribe to buy access or /info to view your subscription details.",
    },
    {
        "key": "admin_new_payment_template",
        "title": "Admin new payment caption",
        "description": "Caption sent to admin with uploaded receipt.",
        "placeholders": ["payment_id", "full_name", "username", "user_id", "admin_url", "receipt_text"],
        "value": """New payment request.\n\nPayment ID: {payment_id}\nUser: {full_name}\nUsername: {username}\nUser ID: {user_id}\n\nAdmin panel link: {admin_url}\n\nReceipt text:\n{receipt_text}""",
    },
    {
        "key": "open_admin_panel_button_text",
        "title": "Admin panel button text",
        "description": "Button text in admin notification.",
        "placeholders": [],
        "value": "Open admin panel",
    },
    {
        "key": "open_admin_panel_message_template",
        "title": "Admin panel message",
        "description": "Standalone admin panel link message.",
        "placeholders": ["admin_url"],
        "value": "Open admin panel: {admin_url}",
    },
    {
        "key": "membership_enforcement_error_template",
        "title": "Membership enforcement error",
        "description": "Sent to admin if remove-from-chat fails.",
        "placeholders": ["user_id", "chat_id", "errors"],
        "value": """Membership enforcement error.\nUser ID: {user_id}\nChat ID: {chat_id}\nErrors: {errors}""",
    },
    {
        "key": "bot_online_text",
        "title": "Bot online notification",
        "description": "Startup notification sent to admin.",
        "placeholders": [],
        "value": "Bot is online.",
    },
]

BOT_MESSAGE_DEFAULTS: dict[str, str] = {
    str(item["key"]): str(item["value"])
    for item in BOT_MESSAGE_DEFINITIONS
}


# Backward-compatible aliases for older imports.
START_TEMPLATE = BOT_MESSAGE_DEFAULTS["start_template"]
SUBSCRIBE_TEXT = BOT_MESSAGE_DEFAULTS["subscribe_text"]
RECEIPT_ACCEPTED_TEXT = BOT_MESSAGE_DEFAULTS["receipt_accepted_text"]
APPROVED_TEMPLATE = BOT_MESSAGE_DEFAULTS["approved_template"]
REJECTED_TEMPLATE = BOT_MESSAGE_DEFAULTS["rejected_template"]
CANCELED_BY_ADMIN_TEMPLATE = BOT_MESSAGE_DEFAULTS["canceled_by_admin_template"]
ASSIGNED_BY_ADMIN_TEMPLATE = BOT_MESSAGE_DEFAULTS["assigned_by_admin_template"]
SUBSCRIPTION_EXPIRING_TEMPLATE = BOT_MESSAGE_DEFAULTS["subscription_expiring_template"]
SUBSCRIPTION_EXPIRED_TEMPLATE = BOT_MESSAGE_DEFAULTS["subscription_expired_template"]
ADMIN_SUBSCRIPTION_EXPIRED_TEMPLATE = BOT_MESSAGE_DEFAULTS["admin_subscription_expired_template"]


class _SafeFormatDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def bot_message_setting_key(template_key: str) -> str:
    return f"{BOT_MESSAGE_PREFIX}{template_key}"


def is_known_bot_message_key(template_key: str) -> bool:
    return template_key in BOT_MESSAGE_DEFAULTS


def render_template(template: str, **kwargs: Any) -> str:
    try:
        return template.format_map(_SafeFormatDict(kwargs))
    except Exception:
        return template
