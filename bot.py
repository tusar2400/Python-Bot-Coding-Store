import os
import html
import logging
import requests
import telebot
from telebot import types

# ==============================
# BOT CONFIGURATION
# ==============================

# Keep the bot token in an environment variable named BOT_TOKEN.
# Do not paste the token into this file or commit it to GitHub.
BOT_TOKEN = os.getenv("9221828836:AAE_VzVTWuFvGXE-NU9e59bnpkYnC2yGBbw")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing. Set BOT_TOKEN in the environment.")

bot = telebot.TeleBot(BOT_TOKEN)

FIREBASE_DB = "https://python-store-5571e-default-rtdb.firebaseio.com/"

logging.basicConfig(level=logging.INFO)

# ==============================
# DEFAULT BOT SETTINGS
# ==============================

DEFAULT_SETTINGS = {
    "btn_webapp_text": "🗓 JOIN DEVELOPER ZONE",
    "webapp_url": "https://tusar2400.github.io/Python-Bot-Coding-Store/index.html",
    "btn_profile_text": "👤 MY PROFILE",
    "btn_mod_text": "👑 PREMIUM MOD APK",
    "btn_support_text": "💬 SUPPORT",
    "mod_url": "https://t.me/your_channel",
    "support_url": "https://t.me/your_support",
    "start_msg": (
        "👋 আসসালামু আলাইকুম!\n"
        "আমাদের স্টোর বটে আপনাকে স্বাগতম।\n"
        "নিচে দেওয়া বাটনগুলো ব্যবহার করুন:"
    )
}

# ==============================
# FIREBASE SETTINGS
# ==============================

def get_bot_settings():
    try:
        response = requests.get(
            f"{FIREBASE_DB}bot_buttons.json",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict):
            settings = DEFAULT_SETTINGS.copy()
            settings.update(data)
            return settings

    except requests.RequestException:
        logging.exception("Firebase settings request failed")
    except ValueError:
        logging.exception("Firebase returned invalid JSON")

    return DEFAULT_SETTINGS.copy()


# ==============================
# SAVE USER INFORMATION
# ==============================

def save_user_to_db(user):
    user_data = {
        "user_id": user.id,
        "first_name": user.first_name or "User",
        "username": user.username or "N/A"
    }

    try:
        response = requests.put(
            f"{FIREBASE_DB}bot_users/{user.id}.json",
            json=user_data,
            timeout=10
        )
        response.raise_for_status()
    except requests.RequestException:
        logging.exception("Could not save user to Firebase")


# ==============================
# START COMMAND
# ==============================

@bot.message_handler(commands=["start"])
def handle_start(message):
    save_user_to_db(message.from_user)
    settings = get_bot_settings()

    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )

    webapp_url = settings.get(
        "webapp_url",
        DEFAULT_SETTINGS["webapp_url"]
    )

    btn_webapp = types.KeyboardButton(
        text=settings["btn_webapp_text"],
        web_app=types.WebAppInfo(url=webapp_url)
    )
    btn_profile = types.KeyboardButton(text=settings["btn_profile_text"])
    btn_mod = types.KeyboardButton(text=settings["btn_mod_text"])
    btn_support = types.KeyboardButton(text=settings["btn_support_text"])

    markup.add(btn_webapp)
    markup.add(btn_profile, btn_mod)
    markup.add(btn_support)

    bot.send_message(
        message.chat.id,
        settings["start_msg"],
        reply_markup=markup
    )


# ==============================
# PROFILE BUTTON
# ==============================

def show_profile(message):
    user_id = message.from_user.id

    try:
        response = requests.get(
            f"{FIREBASE_DB}wallets/{user_id}.json",
            timeout=10
        )
        response.raise_for_status()
        balance_data = response.json()

        if isinstance(balance_data, dict):
            balance = balance_data.get("balance", 0)
        else:
            balance = balance_data if balance_data is not None else 0

    except (requests.RequestException, ValueError):
        logging.exception("Could not read wallet balance")
        balance = 0

    name = html.escape(message.from_user.first_name or "User")
    safe_balance = html.escape(str(balance))

    profile_text = (
        "👤 <b>আপনার প্রোফাইল তথ্য</b>\n\n"
        f"🆔 User ID: <code>{user_id}</code>\n"
        f"👤 নাম: {name}\n"
        f"💰 ওয়ালেট ব্যালেন্স: ৳{safe_balance}"
    )

    bot.send_message(
        message.chat.id,
        profile_text,
        parse_mode="HTML"
    )


# ==============================
# TEXT BUTTON HANDLER
# ==============================

@bot.message_handler(func=lambda message: True)
def handle_text_buttons(message):
    if not message.text:
        return

    settings = get_bot_settings()

    if message.text == settings["btn_profile_text"]:
        show_profile(message)

    elif message.text == settings["btn_support_text"]:
        bot.send_message(
            message.chat.id,
            "💬 আমাদের সাপোর্টে যোগাযোগ করুন:\n"
            f"👉 {settings['support_url']}"
        )

    elif message.text == settings["btn_mod_text"]:
        bot.send_message(
            message.chat.id,
            "👑 আমাদের প্রিমিয়াম চ্যানেল:\n"
            f"👉 {settings['mod_url']}"
        )


# ==============================
# RUN TELEGRAM BOT
# ==============================

if __name__ == "__main__":
    logging.info("Telegram Bot is starting...")
    bot.infinity_polling(
        timeout=30,
        long_polling_timeout=30,
        skip_pending=True
    )
