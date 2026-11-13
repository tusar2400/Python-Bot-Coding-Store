import os
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder=".")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB limit

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
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
            description TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            sold INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 1
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
            downloads INTEGER DEFAULT 100,
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
            status TEXT DEFAULT 'Pending'
        )
    """)

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
        "dollarRate": "125",
        "appLogo": ""
    }
    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    conn.commit()
    conn.close()


init_db()


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


# ==================== HTML পেজ সার্ভ ====================
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


# ==================== ইউজার / স্টোর API ====================
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
    apk_id = data.get("apk_id")
    conn = get_db()
    conn.execute("UPDATE mod_apks SET downloads = downloads + 1 WHERE id = ?", (apk_id,))
    conn.commit()
    row = conn.execute("SELECT apk_file_url FROM mod_apks WHERE id = ?", (apk_id,)).fetchone()
    conn.close()
    return jsonify({"ok": True, "url": row["apk_file_url"] if row else "#"})


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
    return jsonify({"ok": True, "title": prod["title"], "file_url": prod["file_url"]})


@app.route("/api/deposit", methods=["POST"])
def api_deposit():
    data = request.get_json(silent=True) or {}
    uid = str(data.get("user_id", ""))
    user_name = data.get("user_name", "User")
    method = data.get("method", "bKash")
    amount = float(data.get("amount", 0))
    trx = (data.get("trx") or "").strip()

    if not uid or amount <= 0 or not trx:
        return jsonify({"ok": False, "msg": "সঠিক তথ্য দিন!"})

    conn = get_db()
    ensure_user(conn, uid, user_name)
    conn.execute(
        "INSERT INTO deposits (user_id, user_name, method, amount, trx, status) VALUES (?, ?, ?, ?, ?, 'Pending')",
        (uid, user_name, method, amount, trx),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/redeem", methods=["POST"])
def api_redeem():
    data = request.get_json(silent=True) or {}
    uid = str(data.get("user_id", ""))
    code = (data.get("code") or "").strip().upper()

    # গিফট কোড তালিকা (চাইলে এখানে নতুন কোড যোগ করতে পারবেন)
    gift_codes = {
        "WELCOME50": 50,
        "BONUS20": 20,
    }

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


# ==================== অ্যাডমিন API ====================
@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or {}
    if data.get("password") == ADMIN_PASSWORD:
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 401


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
    conn = get_db()
    conn.execute(
        """INSERT INTO products (title, price, dollar_price, is_free, coupon_code, file_url, logo, description, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
        (
            data.get("title", ""),
            float(data.get("price", 0)),
            float(data.get("dollarPrice", 0)),
            1 if data.get("isFree") else 0,
            data.get("coupon_code", ""),
            data.get("file_url", ""),
            data.get("logo", ""),
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
            int(data.get("downloads", 100)),
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
    for key in ["bkash", "nagad", "dollarRate", "appLogo"]:
        if key in data:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(data[key])))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
