import telebot
from telebot import types
import requests

# আপনার আসল বট টোকেন এখানে দিন
BOT_TOKEN = "এখানে_আপনার_বট_টোকেন_দিন"
bot = telebot.TeleBot(BOT_TOKEN)

FIREBASE_DB = "https://python-store-5571e-default-rtdb.firebaseio.com/"

def get_bot_settings():
    try:
        res = requests.get(f"{FIREBASE_DB}bot_buttons.json", timeout=5)
        data = res.json()
        if data:
            return data
    except Exception as e:
        print("Settings Error:", e)
    
    return {
        "btn_webapp_text": "🗓 JOIN DEVELOPER ZONE",
        "webapp_url": "https://tusar2400.github.io/Python-Bot-Coding-Store/index.html",
        "btn_profile_text": "👤 MY PROFILE",
        "btn_mod_text": "👑 PREMIUM MOD APK",
        "mod_url": "https://t.me/your_channel",
        "btn_support_text": "💬 SUPPORT",
        "support_url": "https://t.me/your_support",
        "start_msg": "👋 আসসালামু আলাইকুম!\nআমাদের স্টোর বটে আপনাকে স্বাগতম। নিচে দেওয়া বাটনগুলো ব্যবহার করুন:"
    }

def save_user_to_db(user):
    user_data = {
        "user_id": user.id,
        "first_name": user.first_name,
        "username": user.username if user.username else "N/A"
    }
    try:
        requests.put(f"{FIREBASE_DB}bot_users/{user.id}.json", json=user_data, timeout=5)
    except:
        pass

@bot.message_handler(commands=['start'])
def handle_start(message):
    save_user_to_db(message.from_user)
    settings = get_bot_settings()

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    webapp_url = settings.get("webapp_url", "https://tusar2400.github.io/Python-Bot-Coding-Store/index.html")
    webapp_info = types.WebAppInfo(url=webapp_url)

    btn_webapp = types.KeyboardButton(text=settings.get("btn_webapp_text", "🗓 JOIN DEVELOPER ZONE"), web_app=webapp_info)
    btn_profile = types.KeyboardButton(text=settings.get("btn_profile_text", "👤 MY PROFILE"))
    btn_mod = types.KeyboardButton(text=settings.get("btn_mod_text", "👑 PREMIUM MOD APK"))
    btn_support = types.KeyboardButton(text=settings.get("btn_support_text", "💬 SUPPORT"))

    markup.add(btn_webapp)
    markup.add(btn_profile, btn_mod)
    markup.add(btn_support)

    start_text = settings.get("start_msg", "👋 আসসালামু আলাইকুম!\nআমাদের স্টোর বটে আপনাকে স্বাগতম।")
    bot.send_message(message.chat.id, start_text, reply_markup=markup)

@bot.message_handler(func=lambda msg: True)
def handle_text_buttons(message):
    settings = get_bot_settings()
    user_id = message.from_user.id

    if message.text == settings.get("btn_profile_text", "👤 MY PROFILE"):
        try:
            res = requests.get(f"{FIREBASE_DB}wallets/{user_id}.json", timeout=5)
            bal = res.json()
            balance = bal if bal is not None else 0
        except:
            balance = 0

        profile_text = (
            f"👤 **আপনার প্রোফাইল তথ্য**:\n\n"
            f"🆔 User ID: `{user_id}`\n"
            f"👤 নাম: {message.from_user.first_name}\n"
            f"💰 ওয়ালেট ব্যালেন্স: ৳{balance}\n"
        )
        bot.send_message(message.chat.id, profile_text, parse_mode="Markdown")

    elif message.text == settings.get("btn_support_text", "💬 SUPPORT"):
        supp_link = settings.get("support_url", "https://t.me/your_support")
        bot.send_message(message.chat.id, f"আমাদের সাপোর্টে যোগাযোগ করতে লিংকে ক্লিক করুন:\n👉 {supp_link}")

    elif message.text == settings.get("btn_mod_text", "👑 PREMIUM MOD APK"):
        mod_link = settings.get("mod_url", "https://t.me/your_channel")
        bot.send_message(message.chat.id, f"আমাদের প্রিমিয়াম চ্যানেল লিঙ্ক:\n👉 {mod_link}")

bot.infinity_polling()
