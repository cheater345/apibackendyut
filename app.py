from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import os
import requests
import yt_dlp
import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///users.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'super-secret-key-change-this')

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# ----------------------------
# Database Models
# ----------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

# ----------------------------
# Routes
# ----------------------------
@app.route('/')
def home():
    return jsonify({"message": "API is running", "status": "ok"})

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 400

    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({"message": "User created", "username": username}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid credentials"}), 401

    access_token = create_access_token(identity=username)
    return jsonify({"access_token": access_token, "username": username}), 200

@app.route('/download', methods=['POST'])
@jwt_required()
def download():
    data = request.get_json()
    url = data.get('url')
    format_type = data.get('format', 'mp4')  # mp4, mp3

    if not url:
        return jsonify({"error": "URL required"}), 400

    try:
        ydl_opts = {
            'format': 'bestaudio/best' if format_type == 'mp3' else 'bestvideo+bestaudio',
            'quiet': True,
            'no_warnings': True,
            'outtmpl': 'downloads/%(title)s.%(ext)s',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            return jsonify({
                "success": True,
                "title": info.get('title'),
                "url": url,
                "format": format_type,
            }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----------------------------
# Telegram Bot Webhook (for account generation)
# ----------------------------
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_WEBHOOK_URL = os.environ.get('TELEGRAM_WEBHOOK_URL')

@app.route('/telegram/webhook', methods=['POST'])
def telegram_webhook():
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({"error": "Telegram bot not configured"}), 500

    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({"ok": True}), 200

    chat_id = data['message']['chat']['id']
    text = data['message'].get('text', '')

    if text == '/start':
        send_telegram_message(chat_id, "Welcome! Send /newaccount to generate a new account.")
    elif text == '/newaccount':
        username = generate_username()
        password = generate_password()
        send_telegram_message(chat_id, f"✅ Account created!\nUsername: {username}\nPassword: {password}")
    else:
        send_telegram_message(chat_id, "Unknown command. Use /newaccount to generate credentials.")

    return jsonify({"ok": True}), 200

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

def generate_username():
    import random
    import string
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

def generate_password():
    import random
    import string
    return ''.join(random.choices(string.ascii_letters + string.digits, k=12))

# ----------------------------
# Database & Run
# ----------------------------
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
