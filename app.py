from flask import Flask, request, jsonify
import google.generativeai as genai
import requests
import os
import time
import threading
import random
import queue # = v5.0.7 NEW
from collections import defaultdict, deque

app = Flask(__name__)

# = SET MO TO SA RENDER ENV VARS
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
GENERIC_LINK_SHOPEE = "PASTE_YOUR_SHOPEE_LINK_HERE"
GENERIC_LINK_LAZADA = "PASTE_YOUR_LAZADA_LINK_HERE"

# = 20 ITEMS MO = SHOPEE + LAZADA NA = FIX #4
PRODUCT_MAP = {
    "calculator": {"name": "Casio fx-991EX", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "notebook": {"name": "National Notebook 80s", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "bag": {"name": "JanSport Backpack", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "pen": {"name": "Pilot G2 0.5 Gel Pen", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "lamp": {"name": "LED Study Lamp", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "highlighter": {"name": "Zebra Mildliner", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "earphones": {"name": "TWS i12 Earphones", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "headset": {"name": "JBL Headset", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "mouse": {"name": "Logitech M221", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "keyboard": {"name": "Mechanical Keyboard 60%", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "laptop": {"name": "Lenovo Ideapad", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "phone": {"name": "Infinix Smart 8", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "tablet": {"name": "Lenovo Tab M8", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "powerbank": {"name": "Romoss 20000mAh", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "chair": {"name": "Study Chair", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "table": {"name": "Foldable Study Table", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "ringlight": {"name": "10inch Ring Light", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "fan": {"name": "USB Mini Fan", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "organizer": {"name": "Desk Organizer", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
    "glasses": {"name": "Anti-Radiation Glasses", "shopee": "SHOPEE-LINK-HERE", "lazada": "LAZADA-LINK-HERE"},
}

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

MAX_TURNS = 6
chat_sessions = defaultdict(lambda: deque(maxlen=MAX_TURNS))
RATE_LIMIT = defaultdict(list)
LINK_SENT = defaultdict(bool)
LINK_REQUEST_COUNT = defaultdict(int) # = v5.0.6 FIX #3

# = v5.0.7 NEW: QUEUE SYSTEM = FIX #8
SEND_QUEUE = queue.Queue()
def send_worker():
    while True:
        sender_id, text = SEND_QUEUE.get()
        url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        payload = {"recipient": {"id": sender_id}, "message": {"text": text}}
        try: requests.post(url, json=payload, timeout=5)
        except: pass
        time.sleep(0.3) # = 3 msgs/sec = Safe kay Meta
threading.Thread(target=send_worker, daemon=True).start()

# = v5.0.4 RANDOM BANKS
GREETINGS = [
    "Uy! Ako si Study Buddy AI 🤖\n\nType ka lang ng question mo. Math, Science, English = Kaya ko yan.",
    "Yo! Kamusta? 🤓\nAno pag-aaralan natin today? Math, English, Science = Send lang.",
    "Hello! Tutor mo to 😊\n\nNeed help? Type mo lang: '2x + 4 = 10' or 'Saan bibili ng calculator?'",
    "Uy balik ka ulit 😅\n\nMath ba yan or bili ng gamit? Type ka lang."
]
ERROR_REPLIES = ["Ay sorry, nag-lag ako saglit 😅 Try mo ulit send.", "Oops may error. Pa-type ulit boss."]
SOFT_SELL_LINES = ["\nNeed mo ba ng study gamit? Shopee: {s} | Lazada: {l}", "\nBaka need mo to: Shopee: {s} | Lazada: {l}"]
GENERIC_LINK_LINES = ["Shopee: {s}\nLazada: {l}", "Check mo dito: Shopee: {s} | Lazada: {l}"]

def is_rate_limited(user_id, limit=10, window=60):
    now = time.time()
    RATE_LIMIT[user_id] = [t for t in RATE_LIMIT[user_id] if now - t < window]
    if len(RATE_LIMIT[user_id]) >= limit: return True
    RATE_LIMIT[user_id].append(now)
    return False

def send_action(sender_id, action):
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    requests.post(url, json={"recipient": {"id": sender_id}, "sender_action": action}, timeout=5)

def send_messenger_message_safe(sender_id, text): # = v5.0.7 FIX #8
    SEND_QUEUE.put((sender_id, text[:2000]))

def download_file(url): # = v5.0.6 FIX #2
    try: return requests.get(url, timeout=5).content
    except: return None

def is_link_ok(url): # = v5.0.7 FIX #9
    try: return requests.head(url, timeout=3).status_code < 400
    except: return False

def find_product(user_text):
    user_text_lower = user_text.lower()
    for keyword, product in PRODUCT_MAP.items():
        if keyword in user_text_lower:
            return product
    return None

def ask_gemini_safe(chat, parts, retries=2): # = v5.0.7 FIX #7
    for i in range(retries):
        try: return chat.send_message(parts)
        except Exception as e:
            if "quota" in str(e).lower() and i < retries-1: time.sleep(2)
            else: raise e

@app.route("/status")
def status(): return jsonify({"status": "ok"}), 200

@app.route("/privacy") # = v5.0.6 FIX #5 = REQUIREMENT NI META
def privacy(): return "Study Buddy AI collects messages only to answer questions. No data sold. Contact: your@email.com", 200

@app.route("/webhook", methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        VERIFY_TOKEN = "TUBO2026"
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge"), 200
        return "Verify token mali", 403

    data = request.json
    sender_id = data['entry'][0]['messaging'][0]['sender']['id']
    msg_data = data['entry'][0]['messaging'][0]['message']

    if is_rate_limited(sender_id):
        send_messenger_message_safe(sender_id, "Slow down 😅 10 messages/min lang muna.")
        return "ok", 200

    send_action(sender_id, "typing_on")
    chat = model.start_chat(history=list(chat_sessions[sender_id]))
    user_text = ""

    # = v5.0.3 HELP + LIKE = RANDOM GREETING
    help_words = ['help', 'menu', 'utos', 'commands', 'start', 'hi', 'hello', 'hey']
    if 'text' in msg_data:
        user_text = msg_data['text']
        user_text_lower = user_text.lower()

        # = v5.0.6 FIX #3: ANTI-SPAM
        if any(w in user_text_lower for w in ['link', 'shopee', 'bili']):
            LINK_REQUEST_COUNT[sender_id] += 1
            if LINK_REQUEST_COUNT[sender_id] > 3:
                send_messenger_message_safe(sender_id, "Focus tayo sa study muna 😅 Message ka lang pag may tanong.")
                return "ok", 200

        if user_text_lower in help_words:
            chat_sessions[sender_id].clear()
            LINK_SENT[sender_id] = False
            LINK_REQUEST_COUNT[sender_id] = 0
            ai_reply = random.choice(GREETINGS)
            send_messenger_message_safe(sender_id, ai_reply)
            send_action(sender_id, "typing_off")
            return "ok", 200
    else: # = STICKER / LIKE
        chat_sessions[sender_id].clear()
        LINK_SENT[sender_id] = False
        LINK_REQUEST_COUNT[sender_id] = 0
        ai_reply = random.choice(GREETINGS)
        send_messenger_message_safe(sender_id, ai_reply)
        send_action(sender_id, "typing_off")
        return "ok", 200

    # = v5.0.7 FIX #10: TAGALOG FORCE
    system_prompt = f"""You are a Study Buddy AI Tutor.
CRITICAL RULE: If user uses Tagalog words like 'paano, saan, bakit, ano' = REPLY 100% TAGALOG. No English.
If user uses English = REPLY 100% ENGLISH. No Tagalog.
RULE 1 - MATH/LESSON: Answer step-by-step. Max 8 sentences. Do not add links.
RULE 2 - OTHER: Max 3 sentences. Do not add links. Be direct, friendly."""

    try:
        parts = [system_prompt]
        if 'attachments' in msg_data:
            att = msg_data['attachments'][0]
            user_text = msg_data.get('text', 'Explain this file/image in the same language I used.')
            parts.append(user_text)
            if att['type'] == 'image':
                file_data = download_file(att['payload']['url'])
                if file_data: parts.append({"mime_type":"image/jpeg", "data": file_data})
            elif att['type'] == 'file':
                file_data = download_file(att['payload']['url'])
                if file_data: parts.append({"mime_type": att.get('mime_type', 'application/pdf'), "data": file_data})

        response = ask_gemini_safe(chat, parts) # = v5.0.7 FIX #7
        ai_reply = response.text

        # = v5.0.5 AFFILIATE LOGIC + v5.0.7 FIX #9 LINK CHECK
        buy_words = ['saan', 'bili', 'magkano', 'link', 'store', 'shopee', 'lazada', 'gamit', 'buy']
        product = find_product(user_text)

        if not LINK_SENT[sender_id]:
            if product and is_link_ok(product['shopee']): # = SPECIFIC + CHECK LINK
                ai_reply = f"Try mo '{product['name']}'.\nShopee: {product['shopee']}\nLazada: {product['lazada']}"
                LINK_SENT[sender_id] = True
            elif any(w in user_text.lower() for w in buy_words): # = GENERIC
                link_line = random.choice(GENERIC_LINK_LINES).format(s=GENERIC_LINK_SHOPEE, l=GENERIC_LINK_LAZADA)
                ai_reply = link_line
                LINK_SENT[sender_id] = True
            elif len(chat_sessions[sender_id]) >= 6: # = SOFT SELL
                soft_line = random.choice(SOFT_SELL_LINES).format(s=GENERIC_LINK_SHOPEE, l=GENERIC_LINK_LAZADA)
                ai_reply = ai_reply + soft_line
                LINK_SENT[sender_id] = True

        chat_sessions[sender_id].append({"role": "user", "parts": [user_text]})
        chat_sessions[sender_id].append({"role": "model", "parts": [ai_reply]})

    except Exception as e:
        print(f"Error: {e}") # = v5.0.7 FIX #11 LOG LANG
        ai_reply = random.choice(ERROR_REPLIES)

    send_messenger_message_safe(sender_id, ai_reply)
    send_action(sender_id, "typing_off")
    return "ok", 200

def keep_alive():
    url = "https://tutor-bot-xxx.onrender.com/status" # = PALITAN MO URL MO
    while True:
        try: requests.get(url, timeout=5)
        except: pass
        time.sleep(300)

threading.Thread(target=keep_alive, daemon=True).start()

if __name__ == '__main__':
    app.run(port=5000)