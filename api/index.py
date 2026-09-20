"""
FamPay Gateway - Anime Video Background Version
"""

import os
import random
import string
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-please")

# ── CONFIG ──────────────────────────────────────────────
ADMIN_PASSWORD  = os.environ.get("ADMIN_PASSWORD", "mynk2007")
PRIVATE_API_URL = os.environ.get("PRIVATE_API_URL", "https://fam-working.vercel.app/api/fampay")
UPI_ID          = os.environ.get("UPI_ID", "pankaj00010@fam")
UPI_NAME        = os.environ.get("UPI_NAME", "FamPay Payment")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "57671279-30fce8eeb3de1f13286e13532")

# ── IN-MEMORY DATABASE ──────────────────────────────────
ORDERS = {}
USED_UTRS = set()

# ── ANIME VIDEO QUERIES ─────────────────────────────────
ANIME_QUERIES = [
    "anime", "anime aesthetic", "japan neon",
    "japan night city", "sakura", "anime sky",
    "tokyo night", "anime clouds", "cherry blossom",
    "cyberpunk city", "anime loop",
]

FALLBACK_VIDEOS = [
    "https://cdn.pixabay.com/video/2023/10/22/186115-878408953_large.mp4",
    "https://cdn.pixabay.com/video/2023/09/12/181012-864562901_large.mp4",
]


def get_random_anime_video():
    """Pixabay se random anime video URL fetch karo"""
    try:
        query = random.choice(ANIME_QUERIES)
        url = (
            f"https://pixabay.com/api/videos/"
            f"?key={PIXABAY_API_KEY}&q={query}&per_page=20&safesearch=true"
        )
        res = requests.get(url, timeout=10)
        data = res.json()

        if data.get("hits"):
            video = random.choice(data["hits"])
            vids = video.get("videos", {})
            for quality in ["large", "medium", "small", "tiny"]:
                if quality in vids and vids[quality].get("url"):
                    return vids[quality]["url"]
        return random.choice(FALLBACK_VIDEOS)
    except Exception as e:
        print(f"[Video Fetch Error] {e}")
        return random.choice(FALLBACK_VIDEOS)


def generate_order_id():
    return "ORD" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def generate_upi_link(amount, order_id):
    return f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&tr={order_id}&tn=Payment"


# ── ADMIN ROUTES ────────────────────────────────────────
@app.route("/")
def home():
    return redirect(url_for("admin"))


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("dashboard"))
        return render_template("admin_login.html", error="Wrong password")
    if session.get("admin"):
        return redirect(url_for("dashboard"))
    return render_template("admin_login.html")


@app.route("/admin/dashboard")
def dashboard():
    if not session.get("admin"):
        return redirect(url_for("admin"))
    return render_template("dashboard.html", orders=ORDERS, upi_id=UPI_ID)


@app.route("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("admin"))


@app.route("/admin/create", methods=["POST"])
def create_order():
    if not session.get("admin"):
        return jsonify({"error": "Unauthorized"}), 401

    amount = request.form.get("amount", "").strip()
    name = request.form.get("name", "Customer").strip()

    if not amount:
        return jsonify({"error": "Amount required"}), 400

    order_id = generate_order_id()
    ORDERS[order_id] = {
        "order_id": order_id,
        "amount": amount,
        "name": name,
        "status": "pending",
        "utr": None,
        "created_at": datetime.now().isoformat(),
    }

    return jsonify({
        "success": True,
        "order_id": order_id,
        "full_url": f"{request.host_url}pay/{order_id}",
    })


# ── PAYMENT PAGE ────────────────────────────────────────
@app.route("/pay/<order_id>")
def pay(order_id):
    order = ORDERS.get(order_id)
    if not order:
        return "<h1>Order not found</h1><p>Ye link expire ho gaya hai ya galat hai.</p>", 404

    upi_link = generate_upi_link(order["amount"], order_id)
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={upi_link}"
    bg_video_url = get_random_anime_video()

    return render_template(
        "pay.html",
        order=order,
        qr_url=qr_url,
        upi_id=UPI_ID,
        upi_link=upi_link,
        bg_video_url=bg_video_url,
    )


# ── UTR SUBMIT ──────────────────────────────────────────
@app.route("/api/submit-utr", methods=["POST"])
def submit_utr():
    data = request.get_json()
    order_id = data.get("order_id", "").strip()
    utr = data.get("utr", "").strip()

    if not order_id or not utr:
        return jsonify({"error": "Order ID aur UTR dono chahiye"}), 400

    if len(utr) < 10:
        return jsonify({"error": "UTR galat hai (12 digit ka hota hai)"}), 400

    order = ORDERS.get(order_id)
    if not order:
        return jsonify({"error": "Order nahi mila"}), 404

    if utr in USED_UTRS:
        return jsonify({
            "success": False,
            "message": "Ye UTR already use ho chuka hai. Dobara use nahi kar sakte.",
        })

    try:
        api_url = f"{PRIVATE_API_URL}?utr={utr}"
        response = requests.get(api_url, timeout=30)
        result = response.json()

        if not result.get("found"):
            return jsonify({
                "success": False,
                "message": "UTR verify nahi hua. Payment nahi mili.",
            })

        tx = result["results"][0]
        USED_UTRS.add(utr)
        order["status"] = "success"
        order["utr"] = utr
        order["txn_data"] = tx

        return jsonify({
            "success": True,
            "message": "Payment Successful!",
            "data": tx,
        })

    except Exception as e:
        return jsonify({"error": f"Verification failed: {str(e)}"}), 500


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
