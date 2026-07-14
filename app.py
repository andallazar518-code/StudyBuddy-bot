from flask import Flask, request, jsonify
import google.generativeai as genai
import requests
import os
import time
import threading
import random
import queue
from collections import defaultdict, deque

app = Flask(__name__)

# = SET MO TO SA RENDER ENV VARS
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = "RAINIER22"
GENERIC_LINK_SHOPEE = "https://s.shopee.ph/qhsFU3xcr?smtt=0.0.9" # = PALITAN MO TO NG SHOP LINK MO

# = 20 ITEMS = SHOPEE ONLY NA = WALANG LAZADA
PRODUCT_MAP = {
    "calculator": {"name": "Casio fx-991EX", "shopee": "https://s.shopee.ph/903Zywb2BV"},
    "notebook": {"name": "National Notebook 80s", "shopee": "https://s.shopee.ph/BSBSox6US"},
    "bag": {"name": "JanSport Backpack", "shopee": "https://s.shopee.ph/5AqrQ58Yd1"},
    "pen": {"name": "Pilot G2 0.5 Gel Pen", "shopee": "https://s.shopee.ph/AAFXNKQ3JD"},
    "lamp": {"name": "LED Study Lamp", "shopee": "https://s.shopee.ph/2Vq6FK56cb"},
    "highlighter": {"name": "Zebra Mildliner", "shopee": "https://s.shopee.ph/7KvM0GTd26"},
    "earphones": {"name": "TWS i12 Earphones", "shopee": "https://s.shopee.ph/3qLTptaf8f"},
    "headset": {"name": "JBL Headset", "shopee": "https://s.shopee.ph/8V7JOZxv8i"},
    "mouse": {"name": "Logitech M221", "shopee": "https://s.shopee.ph/3LPDF9KEgu"},
    "keyboard": {"name": "Mechanical Keyboard 60%", "shopee": "https://s.shopee.ph/2LWg3OZZ8m"},
    "laptop": {"name": "Lenovo Ideapad", "shopee": "https://s.shopee.ph/9AN0C8jKBb"},
    "phone": {"name": "Tecno", "shopee": "https://s.shopee.ph/30mMqwHnbk"},
    "tablet": {"name": "Xiaomi Pad 8", "shopee": "https://s.shopee.ph/9zw7BuiTnq"},
    "powerbank": {"name": "Orashare", "shopee": "https://s.shopee.ph/8pk9nssxgj"},
    "chair": {"name": "Study Chair", "shopee": "https://s.shopee.ph/3B5n3bxDay"},
    "table": {"name": "Foldable Study Table", "shopee": "https://s.shopee.ph/9KgQP0uXPG"},
    "ringlight": {"name": "10inch Ring Light", "shopee": "https://s.shopee.ph/1BKig5InOJ"},
    "fan": {"name": "USB Mini Fan", "shopee": "https://s.shopee.ph/7KvM1WX2k9"},
    "organizer": {"name": "Desk Organizer", "shopee": "https://s.shopee.ph/6AjOdQwGtB"},
    "glasses": {"name": "Anti-Radiation Glasses", "shopee": "https://s.shopee.ph/3B5n3yEf2m"},
}

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

MAX_TURNS = 6
chat_sessions = defaultdict(lambda: deque(maxlen=MAX_TURNS))
RATE_LIMIT = defaultdict(list)
LINK_SENT = defaultdict(bool)
LINK_REQUEST_COUNT = defaultdict(int)

# = QUEUE SYSTEM = ANTI-BAN KAY META
SEND_QUEUE = queue.Queue()
def send_worker():
    while True:
        sender_id, text = SEND_QUEUE.get()
        url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        payload = {"recipient": {"id": sender_id}, "message": {"text": text}}
        try: requests.post(url, json=payload, timeout=5)
        except: pass
        time.sleep(0.3) # = 3 msgs/sec
threading.Thread(target=send_worker, daemon=True).start()

# = RANDOM BANKS
GREETINGS = [
    "Uy! Ako si Study Buddy AI 🤖\n\nType ka lang ng question mo. Math, Science, English = Kaya ko yan.",
    "Yo! Kamusta? 🤓\nAno pag-aaralan natin today? Math, English, Science = Send lang.",
    "Hello! Tutor mo to 😊\n\nNeed help? Type mo lang: '2x + 4 = 10' or 'Saan bibili ng calculator?'",
]
ERROR_REPLIES = ["Ay sorry, nag-lag ako saglit 😅 Try mo ulit send.", "Oops may error. Pa-type ulit boss."]
SOFT_SELL_LINES = ["\nNeed mo ba ng study gamit? Check mo dito: {s}", "\nBaka need mo to: {s}"]
GENERIC_LINK_LINES = ["Shopee: {s}", "Check mo dito: {s}"]

def is_rate_limited(user_id, limit=10, window=60):
    now = time.time()
    RATE_LIMIT[user_id] = [t for t in RATE_LIMIT[user_id] if now - t < window]
    if len(RATE_LIMIT[user_id]) >= limit: return True
    RATE_LIMIT[user_id].append(now)
    return False

def send_action(sender_id, action):
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    try: requests.post(url, json={"recipient": {"id": sender_id}, "sender_action": action}, timeout=5)
    except: pass

def send_messenger_message_safe(sender_id, text):
    SEND_QUEUE.put((sender_id, text[:2000]))

def is_link_ok(text):
    text = text.lower()
    return "link" in text or "shopee" in text or "bili" in text or "saan" in text # = WALA NG LAZADA

def get_ai_response(user_id, user_message):
    chat_sessions[user_id].append({"role": "user", "parts": [user_message]})
    history = list(chat_sessions[user_id])
    prompt = "Ikaw si Study Buddy AI. Sumagot ng TAGALOG. Max 4 sentences. Friendly ka.\n\n"
    for msg in history: prompt += f"{msg['role']}: {msg['parts'][0]}\n"
    try:
        response = model.generate_content(prompt)
        ai_text = response.text
        chat_sessions[user_id].append({"role": "model", "parts": [ai_text]})
        return ai_text
    except:
        return random.choice(ERROR_REPLIES)

# = WEBHOOK = TANK BUILD
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "Error", 403

    if request.method == 'POST':
        data = request.get_json()
        if data['object'] == 'page':
            for entry in data['entry']:
                for event in entry['messaging']:
                    sender_id = event['sender']['id']

                    if is_rate_limited(sender_id):
                        send_messenger_message_safe(sender_id, "Ang bilis mo boss 😅 Wait 1 min")
                        continue

                    if 'message' in event and 'text' in event['message']:
                        user_message = event['message']['text']
                        send_action(sender_id, "typing_on")
                        time.sleep(random.uniform(1,2)) # = Human typing

                        # = PRODUCT DETECT = AUTO SHOPEE LINK
                        product_reply = ""
                        for product in PRODUCT_MAP:
                            if product in user_message.lower():
                                p = PRODUCT_MAP[product]
                                product_reply = f"\n\n💡 {p['name']}\nShopee: {p['shopee']}"
                                LINK_SENT[sender_id] = True
                                break

                        # = PAG NAG-REQUEST NG LINK
                        if is_link_ok(user_message) and not LINK_SENT[sender_id]:
                            LINK_REQUEST_COUNT[sender_id] += 1
                            if LINK_REQUEST_COUNT[sender_id] <= 2: # = Max 2x lang
                                product_reply = random.choice(GENERIC_LINK_LINES).format(s=GENERIC_LINK_SHOPEE)
                                LINK_SENT[sender_id] = True

                        ai_text = get_ai_response(sender_id, user_message)

                        # = SOFT SELL 30% CHANCE
                        if not product_reply and random.random() < 0.3:
                            product_reply = random.choice(SOFT_SELL_LINES).format(s=GENERIC_LINK_SHOPEE)

                        final_reply = ai_text + product_reply
                        send_messenger_message_safe(sender_id, final_reply)
        return "ok", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
