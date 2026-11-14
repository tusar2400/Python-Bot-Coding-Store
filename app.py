import os
import re
import json
import time
import hmac
import hashlib
import uuid
import base64
import sqlite3
import urllib.request
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, Response
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder=".")
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
WEB_APP_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://python-bot-store.onrender.com").strip().rstrip("/")
WELCOME_IMAGE_URL = os.environ.get("WELCOME_IMAGE_URL", "").strip()

BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY", "").strip()
BINANCE_SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY", "").strip()

SUPPORT_CHANNEL_URL = "https://t.me/DragonTGSupportGroup"
SUPPORT_ADMIN_URL = "https://t.me/Jamil459"
NOTIFY_CHAT_ID = "-1004327400838"

DB_PATH = "store.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            balance REAL DEFAULT 0,
            joined_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            price REAL DEFAULT 0,
            dollar_price REAL DEFAULT 0,
            is_free INTEGER DEFAULT 0,
            coupon_code TEXT DEFAULT '',
            file_url TEXT DEFAULT '',
            logo TEXT DEFAULT '',
            gallery TEXT DEFAULT '[]',
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            sold INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 1
        )
    """)

    try:
        cur.execute("ALTER TABLE products ADD COLUMN gallery TEXT DEFAULT '[]'")
    except sqlite3.OperationalError:
        pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            mimetype TEXT,
            data BLOB
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS banners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag TEXT,
            title TEXT,
            image TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mod_apks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            rank TEXT DEFAULT '1 RANK',
            downloads INTEGER DEFAULT 250,
            icon TEXT DEFAULT '',
            apk_file_url TEXT DEFAULT ''
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            title TEXT,
            type TEXT,
            date TEXT,
            file_url TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            user_name TEXT,
            method TEXT,
            amount REAL,
            trx TEXT,
            sender_number TEXT DEFAULT '',
            screenshot TEXT DEFAULT '',
            status TEXT DEFAULT 'Pending'
        )
    """)

    try:
        cur.execute("ALTER TABLE deposits ADD COLUMN sender_number TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute("ALTER TABLE deposits ADD COLUMN screenshot TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS redeemed_codes (
            user_id TEXT,
            code TEXT,
            PRIMARY KEY (user_id, code)
        )
    """)

    defaults = {
        "bkash": "018XXXXXXXX",
        "nagad": "018XXXXXXXX",
        "usdtAddress": "0x0000000000000000000000000000000000000000",
        "binanceId": "123456789",
        "status_bkash": "on",
        "status_nagad": "on",
        "status_usdt": "on",
        "status_binance": "on",
        "dollarRate": "125",
        "appLogo": ""
    }
    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    conn.commit()
    conn.close()


init_db()


def check_binance_payment(pay_order_id):
    if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
        return False, 0.0, "Binance API Key কনফিগার করা নেই।"
    endpoint = "https://api.binance.com/sapi/v1/pay/transactions"
    timestamp = int(time.time() * 1000)
    query_string = f"timestamp={timestamp}"
    signature = hmac.new(
        BINANCE_SECRET_KEY.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    url = f"{endpoint}?{query_string}&signature={signature}"
    req = urllib.request.Request(
        url,
        headers={"X-MBX-APIKEY": BINANCE_API_KEY},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            if resp.status != 200:
                return False, 0.0, "Binance Server Error বা API ইস্যু।"
            data = json.loads(resp.read().decode("utf-8"))
            transactions = data.get("data", []) if isinstance(data, dict) else data
            target = str(pay_order_id).strip()
            for item in transactions:
                oid = str(item.get("orderId", "")).strip()
                tid = str(item.get("transactionId", "")).strip()
                if target and (oid == target or tid == target):
                    amount = float(item.get("amount", 0.0))
                    currency = str(item.get("currency", "USDT")).upper()
                    if amount <= 0:
                        return False, 0.0, "এটি ইনকামিং পেমেন্ট নয়।"
                    if currency not in ("USDT", "USDC", "BUSD", "FDUSD"):
                        return False, 0.0, f"শুধুমাত্র USDT/USDC গ্রহণযোগ্য (পাওয়া গেছে: {currency})।"
                    return True, amount, f"{amount} {currency}"
            return False, 0.0, "এই Transaction ID টি আপনার Binance Pay হিস্টোরিতে পাওয়া যায়নি।"
    except Exception as e:
        return False, 0.0, f"Binance যাচাইকরণ ত্রুটি: {str(e)}"


def tg_api(method, payload):
    if not BOT_TOKEN:
        return None
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def tg_send_photo_bytes(chat_id, img_bytes, filename, caption, reply_markup=None):
    if not BOT_TOKEN:
        return None
    boundary = f"----Boundary{uuid.uuid4().hex}"
    parts = []

    def add_field(name, value):
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(f"{value}\r\n".encode("utf-8"))

    add_field("chat_id", str(chat_id))
    add_field("caption", caption)
    add_field("parse_mode", "HTML")
    if reply_markup:
        add_field("reply_markup", json.dumps(reply_markup))

    mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n'.encode())
    parts.append(f"Content-Type: {mime}\r\n\r\n".encode())
    parts.append(img_bytes)
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())

    body = b"".join(parts)
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def tg_send_document_bytes(chat_id, file_bytes, filename, mimetype, caption=""):
    if not BOT_TOKEN:
        return None
    boundary = f"----Boundary{uuid.uuid4().hex}"
    parts = []

    def add_field(name, value):
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(f"{value}\r\n".encode("utf-8"))

    add_field("chat_id", str(chat_id))
    if caption and len(caption) <= 1024:
        add_field("caption", caption)
        add_field("parse_mode", "HTML")

    safe_fn = (filename or "file.bin").replace('"', "")
    mime = mimetype or "application/octet-stream"
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="document"; filename="{safe_fn}"\r\n'.encode())
    parts.append(f"Content-Type: {mime}\r\n\r\n".encode())
    parts.append(file_bytes)
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())

    body = b"".join(parts)
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def send_file_or_link(chat_id, file_url, message_text):
    if not BOT_TOKEN or not chat_id:
        return
    url_str = (file_url or "").strip()
    match = re.search(r"/download/(\d+)/", url_str)
    if match:
        fid = int(match.group(1))
        conn = get_db()
        row = conn.execute("SELECT filename, mimetype, data FROM uploads WHERE id = ?", (fid,)).fetchone()
        conn.close()
        if row and row["data"] and len(row["data"]) <= 50 * 1024 * 1024:
            res = tg_send_document_bytes(
                chat_id,
                row["data"],
                row["filename"],
                row["mimetype"],
                message_text if len(message_text) <= 1024 else "",
            )
            if res and res.get("ok"):
                if len(message_text) > 1024:
                    tg_api("sendMessage", {
                        "chat_id": int(chat_id),
                        "text": message_text,
                        "parse_mode": "HTML",
                    })
                return

    tg_api("sendMessage", {
        "chat_id": int(chat_id),
        "text": message_text,
        "parse_mode": "HTML",
    })


def check_admin():
    return request.headers.get("X-Admin-Pass", "") == ADMIN_PASSWORD


def get_settings_dict(conn):
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def ensure_user(conn, user_id, first_name="User", username="user"):
    uid = str(user_id)
    user = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not user:
        year = str(datetime.now().year)
        conn.execute(
            "INSERT INTO users (id, first_name, username, balance, joined_at) VALUES (?, ?, ?, 0, ?)",
            (uid, first_name, username, year),
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return user


def safe_json_list(raw):
    try:
        val = json.loads(raw or "[]")
        return val if isinstance(val, list) else []
    except Exception:
        return []


def full_url(url):
    if url and url.startswith("/"):
        return f"{WEB_APP_URL}{url}"
    return url


@app.route("/")
def serve_index():
    return send_from_directory(".", "index.html")


@app.route("/admin")
@app.route("/admin.html")
def serve_admin():
    return send_from_directory(".", "admin.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/download/<int:fid>/<path:filename>")
def download_uploaded_file(fid, filename):
    conn = get_db()
    row = conn.execute("SELECT filename, mimetype, data FROM uploads WHERE id = ?", (fid,)).fetchone()
    conn.close()
    if not row:
        return "File not found", 404
    return Response(
        row["data"],
        mimetype=row["mimetype"] or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{row["filename"]}"'},
    )


@app.route("/setup-bot")
def setup_bot():
    if not BOT_TOKEN:
        return "❌ Render-এ BOT_TOKEN সেট করা নেই!", 400
    webhook_url = f"{WEB_APP_URL}/telegram-webhook"
    w_res = tg_api("setWebhook", {"url": webhook_url})
    m_res = tg_api("setChatMenuButton", {
        "menu_button": {
            "type": "web_app",
            "text": "OPEN STORE",
            "web_app": {"url": WEB_APP_URL}
        }
    })
    return jsonify({"status": "✅ Bot Connected!", "webhook": w_res, "menu_button": m_res})


@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    msg = update.get("message") or {}
    text = (msg.get("text") or "").strip()
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    from_user = msg.get("from") or {}

    if chat_id and text.startswith("/start"):
        conn = get_db()
        ensure_user(conn, chat_id, from_user.get("first_name", "User"), from_user.get("username", "user"))
        banner = conn.execute("SELECT image FROM banners ORDER BY id DESC LIMIT 1").fetchone()
        settings = get_settings_dict(conn)
        conn.close()

        caption = (
            "<blockquote>✈️ <b><i>WELCOME TO PYTHON BOT CODING STORE!</i></b></blockquote>\n"
            "<blockquote>👑 <b><i>YOUR ULTIMATE DIGITAL RESOURCE HUB!</i></b></blockquote>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<blockquote>💡 <b><i>EXPLORE PYTHON BOT CODING STORE AND FIND WHAT YOU NEED!</i></b></blockquote>\n"
            "<blockquote>🔔 <b><i>ADVANCED DEVELOPER TOOLS</i></b></blockquote>\n"
            "<blockquote>🤖 <b><i>UNLIMITED PREMIUM MOD APKS</i></b></blockquote>\n"
            "<blockquote>💻 <b><i>ALL TYPES CODING FILES AND SOURCES</i></b></blockquote>\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        markup = {
            "inline_keyboard": [
                [{"text": "🚀 OPEN STORE", "web_app": {"url": WEB_APP_URL}}],
                [
                    {"text": "📢 Support Channel", "url": SUPPORT_CHANNEL_URL},
                    {"text": "👨‍💻 Support Admin", "url": SUPPORT_ADMIN_URL},
                ],
            ]
        }

        sent = None
        if WELCOME_IMAGE_URL:
            sent = tg_api("sendPhoto", {
                "chat_id": chat_id, "photo": WELCOME_IMAGE_URL,
                "caption": caption, "parse_mode": "HTML", "reply_markup": markup,
            })

        if not sent or not sent.get("ok"):
            for fname in ["welcome.jpg", "welcome.png", "welcome.jpeg"]:
                if os.path.exists(fname):
                    try:
                        with open(fname, "rb") as f:
                            sent = tg_send_photo_bytes(chat_id, f.read(), fname, caption, markup)
                        if sent and sent.get("ok"):
                            break
                    except Exception:
                        pass

        if not sent or not sent.get("ok"):
            img_data = (banner["image"] if banner else "") or settings.get("appLogo", "")
            if img_data.startswith("data:image") and "," in img_data:
                try:
                    img_bytes = base64.b64decode(img_data.split(",", 1)[1])
                    sent = tg_send_photo_bytes(chat_id, img_bytes, "welcome.jpg", caption, markup)
                except Exception:
                    sent = None
            elif img_data.startswith("http"):
                sent = tg_api("sendPhoto", {
                    "chat_id": chat_id, "photo": img_data,
                    "caption": caption, "parse_mode": "HTML", "reply_markup": markup,
                })

        if not sent or not sent.get("ok"):
            tg_api("sendMessage", {
                "chat_id": chat_id, "text": caption,
                "parse_mode": "HTML", "reply_markup": markup,
            })

    return jsonify({"ok": True})


@app.route("/api/store-data", methods=["POST"])
def api_store_data():
    data = request.get_json(silent=True) or {}
    uid = str(data.get("user_id", "7182227"))
    first_name = data.get("first_name", "User")
    username = data.get("username", "user")

    conn = get_db()
    user = ensure_user(conn, uid, first_name, username)

    prods = conn.execute("SELECT * FROM products WHERE status = 'active' ORDER BY id DESC").fetchall()
    products_list = [
        {
            "id": p["id"],
            "title": p["title"],
            "price": p["price"],
            "dollarPrice": p["dollar_price"],
            "isFree": bool(p["is_free"]),
            "hasCoupon": bool(p["coupon_code"]),
            "logo": p["logo"],
            "gallery": safe_json_list(p["gallery"]),
            "description": p["description"],
            "sold": p["sold"],
            "likes": p["likes"],
        }
        for p in prods
    ]

    banners = [dict(r) for r in conn.execute("SELECT * FROM banners ORDER BY id DESC").fetchall()]
    apks = [dict(r) for r in conn.execute("SELECT * FROM mod_apks ORDER BY id DESC").fetchall()]
    orders = [dict(r) for r in conn.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC", (uid,)).fetchall()]
    deposits = [dict(r) for r in conn.execute("SELECT * FROM deposits WHERE user_id = ? ORDER BY id DESC", (uid,)).fetchall()]
    settings = get_settings_dict(conn)
    conn.close()

    return jsonify({
        "user": {"id": user["id"], "balance": user["balance"], "joined_at": user["joined_at"]},
        "products": products_list,
        "banners": banners,
        "mod_apks": apks,
        "orders": orders,
        "deposits": deposits,
        "settings": settings,
    })


@app.route("/api/like/<int:pid>", methods=["POST"])
def api_like(pid):
    conn = get_db()
    conn.execute("UPDATE products SET likes = likes + 1 WHERE id = ?", (pid,))
    conn.commit()
    row = conn.execute("SELECT likes FROM products WHERE id = ?", (pid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"ok": False}), 404
    return jsonify({"ok": True, "likes": row["likes"]})


@app.route("/api/send-apk", methods=["POST"])
def api_send_apk():
    data = request.get_json(silent=True) or {}
    uid = str(data.get("user_id", ""))
    apk_id = data.get("apk_id")
    conn = get_db()
    conn.execute("UPDATE mod_apks SET downloads = downloads + 1 WHERE id = ?", (apk_id,))
    conn.commit()
    row = conn.execute("SELECT name, apk_file_url FROM mod_apks WHERE id = ?", (apk_id,)).fetchone()
    conn.close()

    url = row["apk_file_url"] if row else "#"
    if row and BOT_TOKEN and uid.isdigit():
        msg_text = f"🤖 <b>{row['name']}</b>\n\n📥 ডাউনলোড লিংক:\n{full_url(url)}"
        send_file_or_link(int(uid), url, msg_text)
    return jsonify({"ok": True, "url": url})


@app.route("/api/buy", methods=["POST"])
def api_buy():
    data = request.get_json(silent=True) or {}
    uid = str(data.get("user_id", ""))
    pid = data.get("product_id")
    coupon = (data.get("coupon") or "").strip().upper()

    conn = get_db()
    user = ensure_user(conn, uid)
    prod = conn.execute("SELECT * FROM products WHERE id = ? AND status = 'active'", (pid,)).fetchone()
    if not prod:
        conn.close()
        return jsonify({"ok": False, "msg": "❌ প্রোডাক্ট পাওয়া যায়নি!"})

    if prod["is_free"]:
        if prod["coupon_code"] and coupon != prod["coupon_code"].strip().upper():
            conn.close()
            return jsonify({"ok": False, "msg": "❌ ভুল কুপন কোড!"})
        order_type = "FREE"
    else:
        if user["balance"] < prod["price"]:
            conn.close()
            return jsonify({"ok": False, "msg": "❌ অপর্যাপ্ত ব্যালেন্স!"})
        conn.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (prod["price"], uid))
        order_type = "PAID"

    conn.execute("UPDATE products SET sold = sold + 1 WHERE id = ?", (pid,))
    now_str = datetime.now().strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO orders (user_id, title, type, date, file_url) VALUES (?, ?, ?, ?, ?)",
        (uid, prod["title"], order_type, now_str, prod["file_url"]),
    )
    conn.commit()
    conn.close()

    if BOT_TOKEN and uid.isdigit():
        msg_text = f"✅ <b>{prod['title']}</b> ফাইলটি আনলক হয়েছে!\n\n📥 ডাউনলোড লিংক:\n{full_url(prod['file_url'])}"
        send_file_or_link(int(uid), prod["file_url"], msg_text)

    return jsonify({"ok": True, "title": prod["title"], "file_url": prod["file_url"]})


@app.route("/api/deposit", methods=["POST"])
def api_deposit():
    data = request.get_json(silent=True) or {}
    uid = str(data.get("user_id", ""))
    user_name = data.get("user_name", "User")
    method = data.get("method", "bKash")
    try:
        amount = float(data.get("amount", 0))
    except (TypeError, ValueError):
        amount = 0
    trx = (data.get("trx") or "").strip()
    sender_number = (data.get("sender_number") or "").strip()
    screenshot = (data.get("screenshot") or "").strip()

    if not uid or amount < 50 or not trx or not sender_number:
        return jsonify({"ok": False, "msg": "সর্বনিম্ন ৳৫০, TrxID এবং Sender নম্বর সঠিকভাবে দিন!"})

    conn = get_db()
    ensure_user(conn, uid, user_name)
    settings = get_settings_dict(conn)

    status_map = {
        "bKash": "status_bkash",
        "Nagad": "status_nagad",
        "USDT (BEP20)": "status_usdt",
        "Binance": "status_binance",
    }
    status_key = status_map.get(method)
    if status_key and settings.get(status_key, "on") == "off":
        conn.close()
        return jsonify({"ok": False, "msg": f"❌ দুঃখিত, বর্তমানে {method} পেমেন্ট মেথডটি বন্ধ রয়েছে!"})

    if method == "Binance":
        existing = conn.execute("SELECT id FROM deposits WHERE UPPER(trx) = UPPER(?)", (trx,)).fetchone()
        if existing:
            conn.close()
            return jsonify({"ok": False, "msg": "❌ এই Order / Transaction ID টি ইতিপূর্বেই ব্যবহার করা হয়েছে!"})

        is_valid, paid_usdt, res_msg = check_binance_payment(trx)
        if not is_valid:
            conn.close()
            return jsonify({"ok": False, "msg": f"❌ {res_msg}"})

        try:
            d_rate = float(settings.get("dollarRate", "125") or 125)
        except ValueError:
            d_rate = 125.0
        added_bdt = round(paid_usdt * d_rate, 2)

        conn.execute(
            """INSERT INTO deposits (user_id, user_name, method, amount, trx, sender_number, screenshot, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'Approved')""",
            (uid, user_name, method, added_bdt, trx, sender_number, screenshot),
        )
        conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (added_bdt, uid))
        conn.commit()
        conn.close()

        if BOT_TOKEN and NOTIFY_CHAT_ID:
            notify_text = (
                f"⚡ <b>Binance Pay অটো ডিপোজিট সফল!</b>\n\n"
                f"👤 User: {user_name} (<code>{uid}</code>)\n"
                f"💳 Method: Binance ({res_msg})\n"
                f"💵 Added: ৳{added_bdt}\n"
                f"📱 Sender: <code>{sender_number}</code>\n"
                f"🧾 TrxID: <code>{trx}</code>"
            )
            tg_api("sendMessage", {
                "chat_id": NOTIFY_CHAT_ID,
                "text": notify_text,
                "parse_mode": "HTML"
            })

        return jsonify({
            "ok": True,
            "auto_approved": True,
            "amount": added_bdt,
            "msg": f"⚡ Binance Pay অটো ভেরিফাই সফল! আপনার ব্যালেন্সে ৳{added_bdt} যুক্ত হয়েছে।"
        })

    conn.execute(
        """INSERT INTO deposits (user_id, user_name, method, amount, trx, sender_number, screenshot, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending')""",
        (uid, user_name, method, amount, trx, sender_number, screenshot),
    )
    conn.commit()
    conn.close()

    if BOT_TOKEN and NOTIFY_CHAT_ID:
        notify_text = (
            f"💰 <b>নতুন ডিপোজিট রিকোয়েস্ট!</b>\n\n"
            f"👤 User: {user_name} (<code>{uid}</code>)\n"
            f"💳 Method: {method}\n"
            f"💵 Amount: ৳{amount}\n"
            f"📱 Sender: <code>{sender_number}</code>\n"
            f"🧾 TrxID: <code>{trx}</code>"
        )
        sent_photo = None
        if screenshot.startswith("data:image") and "," in screenshot:
            try:
                img_bytes = base64.b64decode(screenshot.split(",", 1)[1])
                sent_photo = tg_send_photo_bytes(NOTIFY_CHAT_ID, img_bytes, "deposit.jpg", notify_text)
            except Exception:
                sent_photo = None
        if not sent_photo or not sent_photo.get("ok"):
            tg_api("sendMessage", {
                "chat_id": NOTIFY_CHAT_ID,
                "text": notify_text,
                "parse_mode": "HTML"
            })

    return jsonify({"ok": True, "auto_approved": False})


@app.route("/api/redeem", methods=["POST"])
def api_redeem():
    data = request.get_json(silent=True) or {}
    uid = str(data.get("user_id", ""))
    code = (data.get("code") or "").strip().upper()
    gift_codes = {"WELCOME50": 50, "BONUS20": 20}

    if code not in gift_codes:
        return jsonify({"ok": False, "msg": "❌ ভুল বা মেয়াদোত্তীর্ণ রিডিম কোড!"})

    conn = get_db()
    ensure_user(conn, uid)
    already = conn.execute("SELECT 1 FROM redeemed_codes WHERE user_id = ? AND code = ?", (uid, code)).fetchone()
    if already:
        conn.close()
        return jsonify({"ok": False, "msg": "❌ আপনি এই কোডটি ইতিমধ্যেই ব্যবহার করেছেন!"})

    bonus = gift_codes[code]
    conn.execute("INSERT INTO redeemed_codes (user_id, code) VALUES (?, ?)", (uid, code))
    conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (bonus, uid))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "bonus": bonus})


@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or {}
    if data.get("password") == ADMIN_PASSWORD:
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 401


@app.route("/api/admin/upload", methods=["POST"])
def admin_upload_file():
    if not check_admin():
        return jsonify({"ok": False, "msg": "Unauthorized"}), 401
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "msg": "কোনো ফাইল পাওয়া যায়নি"}), 400
    safe_name = secure_filename(f.filename) or "file.bin"
    raw = f.read()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO uploads (filename, mimetype, data) VALUES (?, ?, ?)",
        (safe_name, f.mimetype or "application/octet-stream", raw),
    )
    fid = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "url": f"/download/{fid}/{safe_name}"})


@app.route("/api/admin/all", methods=["GET"])
def admin_all():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db()
    prods = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    products_list = [
        {
            "id": p["id"],
            "title": p["title"],
            "price": p["price"],
            "dollarPrice": p["dollar_price"],
            "isFree": bool(p["is_free"]),
            "coupon_code": p["coupon_code"],
            "file_url": p["file_url"],
            "logo": p["logo"],
            "gallery": safe_json_list(p["gallery"]),
            "description": p["description"],
            "status": p["status"],
            "sold": p["sold"],
            "likes": p["likes"],
        }
        for p in prods
    ]

    banners = [dict(r) for r in conn.execute("SELECT * FROM banners ORDER BY id DESC").fetchall()]
    apks = [dict(r) for r in conn.execute("SELECT * FROM mod_apks ORDER BY id DESC").fetchall()]
    deps = conn.execute("SELECT * FROM deposits WHERE status = 'Pending' ORDER BY id DESC").fetchall()
    deposits_list = [
        {
            "id": d["id"],
            "userId": d["user_id"],
            "userName": d["user_name"],
            "method": d["method"],
            "amount": d["amount"],
            "trx": d["trx"],
            "senderNumber": d["sender_number"] if "sender_number" in d.keys() else "",
            "screenshot": d["screenshot"] if "screenshot" in d.keys() else "",
            "status": d["status"],
        }
        for d in deps
    ]
    settings = get_settings_dict(conn)
    conn.close()

    return jsonify({
        "products": products_list,
        "banners": banners,
        "mod_apks": apks,
        "deposits": deposits_list,
        "settings": settings,
    })


@app.route("/api/admin/product", methods=["POST"])
def admin_add_product():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    gallery = data.get("gallery") or []
    if not isinstance(gallery, list):
        gallery = []
    conn = get_db()
    conn.execute(
        """INSERT INTO products (title, price, dollar_price, is_free, coupon_code, file_url, logo, gallery, description, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
        (
            data.get("title", ""),
            float(data.get("price", 0)),
            float(data.get("dollarPrice", 0)),
            1 if data.get("isFree") else 0,
            data.get("coupon_code", ""),
            data.get("file_url", ""),
            data.get("logo", ""),
            json.dumps(gallery[:4]),
            data.get("description", ""),
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/product/<int:pid>/toggle", methods=["POST"])
def admin_toggle_product(pid):
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    row = conn.execute("SELECT status FROM products WHERE id = ?", (pid,)).fetchone()
    if row:
        new_status = "inactive" if row["status"] == "active" else "active"
        conn.execute("UPDATE products SET status = ? WHERE id = ?", (new_status, pid))
        conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/product/<int:pid>", methods=["DELETE"])
def admin_delete_product(pid):
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    conn.execute("DELETE FROM products WHERE id = ?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/banner", methods=["POST"])
def admin_add_banner():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    conn = get_db()
    conn.execute(
        "INSERT INTO banners (tag, title, image) VALUES (?, ?, ?)",
        (data.get("tag", ""), data.get("title", ""), data.get("image", "")),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/banner/<int:bid>", methods=["DELETE"])
def admin_delete_banner(bid):
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    conn.execute("DELETE FROM banners WHERE id = ?", (bid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/modapk", methods=["POST"])
def admin_add_apk():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    conn = get_db()
    conn.execute(
        "INSERT INTO mod_apks (name, rank, downloads, icon, apk_file_url) VALUES (?, ?, ?, ?, ?)",
        (
            data.get("name", ""),
            data.get("rank", "1 RANK"),
            int(data.get("downloads", 200)),
            data.get("icon", ""),
            data.get("apk_file_url", ""),
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/modapk/<int:aid>", methods=["DELETE"])
def admin_delete_apk(aid):
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    conn.execute("DELETE FROM mod_apks WHERE id = ?", (aid,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/deposit/<int:did>/<action>", methods=["POST"])
def admin_handle_deposit(did, action):
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    dep = conn.execute("SELECT * FROM deposits WHERE id = ?", (did,)).fetchone()
    if dep and dep["status"] == "Pending":
        if action == "approve":
            conn.execute("UPDATE deposits SET status = 'Approved' WHERE id = ?", (did,))
            ensure_user(conn, dep["user_id"], dep["user_name"])
            conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (dep["amount"], dep["user_id"]))
        elif action == "reject":
            conn.execute("UPDATE deposits SET status = 'Rejected' WHERE id = ?", (did,))
        conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/admin/balance", methods=["POST"])
def admin_balance():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    uid = str(data.get("user_id", "")).strip()
    amount = float(data.get("amount", 0))
    action = data.get("action", "add")

    conn = get_db()
    user = ensure_user(conn, uid)
    new_bal = user["balance"] + amount if action == "add" else max(0, user["balance"] - amount)
    conn.execute("UPDATE users SET balance = ? WHERE id = ?", (new_bal, uid))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "balance": new_bal})


@app.route("/api/admin/settings", methods=["POST"])
def admin_settings():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    conn = get_db()
    allowed_keys = [
        "bkash", "nagad", "usdtAddress", "binanceId",
        "status_bkash", "status_nagad", "status_usdt", "status_binance",
        "dollarRate", "appLogo"
    ]
    for key in allowed_keys:
        if key in data:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(data[key])))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
