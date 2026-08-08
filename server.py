import os
import requests
from flask import Flask, request, jsonify
import telebot
from bot import bot

app = Flask(__name__)

PORT = int(os.getenv('PORT') or 3000)

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        
        # Process updates in a separate thread (handled by telebot's thread pool)
        bot.process_new_updates([update])
        return 'OK', 200
    else:
        return 'Forbidden', 403

@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        'status': 'active',
        'bot_username': bot.get_me().username if os.getenv('BOT_TOKEN') else 'unknown'
    }), 200

def setup_webhook():
    bot_token = os.getenv('BOT_TOKEN')
    public_url = os.getenv('PUBLIC_URL')
    
    # If RAILWAY_PUBLIC_DOMAIN is provided by Railway, build the URL from it
    if not public_url and os.getenv('RAILWAY_PUBLIC_DOMAIN'):
        public_url = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}"
        
    if bot_token and public_url:
        webhook_url = f"{public_url}/webhook"
        print(f"[INFO] Setting up Telegram Webhook to: {webhook_url}...")
        try:
            bot.remove_webhook()
            # Set webhook
            success = bot.set_webhook(url=webhook_url)
            if success:
                print("[SUCCESS] Telegram Webhook registered successfully!")
            else:
                print("[WARNING] Telegram Webhook registration failed.")
        except Exception as e:
            print(f"[ERROR] Failed to set up Telegram Webhook: {e}")
    else:
        print("[INFO] BOT_TOKEN or PUBLIC_URL/RAILWAY_PUBLIC_DOMAIN not detected. Webhook not set automatically.")

if __name__ == '__main__':
    setup_webhook()
    print(f"[INFO] Starting Flask web server on port {PORT}...")
    app.run(host='0.0.0.0', port=PORT)
