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
