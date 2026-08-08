import os
import sys
import requests
from flask import Flask, request, jsonify, render_template_string
import telebot
from bot import bot
import database as db

# Initialize Flask app
app = Flask(__name__)

PORT = int(os.getenv('PORT') or 3000)

# Sidebar Tables Metadata
DISPLAY_TABLES = [
    {'id': 'users', 'name': 'Foydalanuvchilar (users)', 'icon': '👥'},
    {'id': 'houses', 'name': 'Xonadonlar (houses)', 'icon': '🏰'},
    {'id': 'units', 'name': 'Harbiy Turlar (units)', 'icon': '⚔️'},
    {'id': 'house_units', 'name': 'Xonadon Askarlari (house_units)', 'icon': '🛡️'},
    {'id': 'bank_treasury', 'name': 'Temir Bank (bank_treasury)', 'icon': '🏦'},
    {'id': 'loans', 'name': 'Kreditlar (loans)', 'icon': '💸'},
    {'id': 'transactions', 'name': 'Tranzaksiyalar (transactions)', 'icon': '📜'},
    {'id': 'battles', 'name': 'Janglar (battles)', 'icon': '💥'},
    {'id': 'broadcasts', 'name': 'Xabarlar (broadcasts)', 'icon': '📢'},
    {'id': 'settings', 'name': 'Sozlamalar (settings)', 'icon': '⚙️'}
]

# Helper to check CORS and Admin Password
def verify_admin_password():
    admin_pwd = os.getenv('ADMIN_PASSWORD') or os.getenv('ADMIN_TELEGRAM_ID') or 'admin'
    client_pwd = request.headers.get('X-Admin-Password') or request.args.get('password')
    return str(client_pwd) == str(admin_pwd)

# Enable CORS for external static HTML page
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization,X-Admin-Password'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response

# Handle pre-flight OPTIONS request
@app.route('/api/<path:path>', methods=['OPTIONS'])
def options_handler(path):
    return '', 200

# Helper to fetch columns and primary keys of a table dynamically
def get_table_metadata(table_name):
    cols_query = """
        SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY 
        FROM information_schema.columns 
        WHERE table_schema = %s AND table_name = %s 
        ORDER BY ordinal_position
    """
    cols_data = db.query(cols_query, (db.DB_NAME, table_name))
    
    columns = []
    primary_keys = []
    
    for col in cols_data:
        col_name = col['COLUMN_NAME']
        columns.append({
            'name': col_name,
            'type': col['DATA_TYPE'],
            'nullable': col['IS_NULLABLE'] == 'YES',
            'is_pk': col['COLUMN_KEY'] == 'PRI'
        })
        if col['COLUMN_KEY'] == 'PRI':
            primary_keys.append(col_name)
            
    if not primary_keys:
        if table_name == 'house_units':
            primary_keys = ['house_id', 'unit_id']
        elif table_name == 'casino_broadcasts':
            primary_keys = ['telegram_id', 'message_id']
            
    return columns, primary_keys

# WEB DASHBOARD VIEW ROUTE
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, tables=DISPLAY_TABLES)

# TELEGRAM BOT WEBHOOK ROUTE
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    else:
        return 'Forbidden', 403

# API STATUS ROUTE
@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        'status': 'active',
        'bot_username': bot.get_me().username if os.getenv('BOT_TOKEN') else 'unknown'
    }), 200

# ================= API ENDPOINTS FOR DATABASE =================

@app.route('/api/metadata/<table_name>')
def api_metadata(table_name):
    if not verify_admin_password():
        return jsonify({'success': False, 'error': 'Kirish taqiqlangan (Parol xato).'}), 401
    try:
        columns, pks = get_table_metadata(table_name)
        return jsonify({'success': True, 'columns': columns, 'primary_keys': pks})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/data/<table_name>')
def api_data(table_name):
    if not verify_admin_password():
        return jsonify({'success': False, 'error': 'Kirish taqiqlangan (Parol xato).'}), 401
    try:
        columns, pks = get_table_metadata(table_name)
        order_clause = ""
        if table_name in ['transactions', 'battles', 'broadcasts']:
            order_clause = " ORDER BY timestamp DESC"
            
        rows = db.query(f"SELECT * FROM {table_name}{order_clause}")
        return jsonify({
            'success': True,
            'columns': columns,
            'primary_keys': pks,
            'rows': rows
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/update/<table_name>', methods=['POST'])
def api_update(table_name):
    if not verify_admin_password():
        return jsonify({'success': False, 'error': 'Kirish taqiqlangan (Parol xato).'}), 401
    try:
        data = request.json
        keys = data.get('keys')
        values = data.get('values')
        
        if not keys or not values:
            return jsonify({'success': False, 'error': 'Keys and Values are required.'}), 400
            
        set_clause = ", ".join([f"{col} = %s" for col in values.keys()])
        where_clause = " AND ".join([f"{col} = %s" for col in keys.keys()])
        
        sql = f"UPDATE {table_name} SET {set_clause} WHERE {where_clause}"
        params = list(values.values()) + list(keys.values())
        
        affected = db.execute(sql, params)
        return jsonify({'success': True, 'affected_rows': affected})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/delete/<table_name>', methods=['POST'])
def api_delete(table_name):
    if not verify_admin_password():
        return jsonify({'success': False, 'error': 'Kirish taqiqlangan (Parol xato).'}), 401
    try:
        data = request.json
        keys = data.get('keys')
        
        if not keys:
            return jsonify({'success': False, 'error': 'Keys are required for deletion.'}), 400
            
        where_clause = " AND ".join([f"{col} = %s" for col in keys.keys()])
        sql = f"DELETE FROM {table_name} WHERE {where_clause}"
        params = list(keys.values())
        
        affected = db.execute(sql, params)
        return jsonify({'success': True, 'affected_rows': affected})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/add/<table_name>', methods=['POST'])
def api_add(table_name):
    if not verify_admin_password():
        return jsonify({'success': False, 'error': 'Kirish taqiqlangan (Parol xato).'}), 401
    try:
        data = request.json
        values = data.get('values')
        
        if not values:
            return jsonify({'success': False, 'error': 'Values are required.'}), 400
            
        cleaned_values = {}
        for col, val in values.items():
            if val == '' or val is None:
                cleaned_values[col] = None
            else:
                cleaned_values[col] = val
                
        cols_str = ", ".join(cleaned_values.keys())
        placeholders = ", ".join(["%s"] * len(cleaned_values))
        sql = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders})"
        params = list(cleaned_values.values())
        
        affected = db.execute(sql, params)
        return jsonify({'success': True, 'affected_rows': affected})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def setup_webhook():
    bot_token = os.getenv('BOT_TOKEN')
    public_url = os.getenv('PUBLIC_URL')
    
    if not public_url and os.getenv('RAILWAY_PUBLIC_DOMAIN'):
        public_url = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}"
        
    if bot_token and public_url:
        webhook_url = f"{public_url}/webhook"
        print(f"[INFO] Setting up Telegram Webhook to: {webhook_url}...")
        try:
            bot.remove_webhook()
            success = bot.set_webhook(url=webhook_url)
            if success:
                print("[SUCCESS] Telegram Webhook registered successfully!")
            else:
                print("[WARNING] Telegram Webhook registration failed.")
        except Exception as e:
            print(f"[ERROR] Failed to set up Telegram Webhook: {e}")
    else:
        print("[INFO] BOT_TOKEN or PUBLIC_URL not detected. Webhook not configured.")

# HTML TEMPLATE
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="uz">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Westeros RPG Baza Boshqaruvi</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700;900&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0b0e;
            --bg-secondary: #12141c;
            --bg-glass: rgba(22, 25, 37, 0.6);
            --border-color: rgba(255, 255, 255, 0.08);
            --border-hover: rgba(212, 175, 55, 0.3);
            --accent: #d4af37;
            --accent-hover: #ffdf00;
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --text-muted: #6b7280;
            --success: #10b981;
            --danger: #ef4444;
            --transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-primary); color: var(--text-primary); display: flex; height: 100vh; overflow: hidden; }
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: rgba(0, 0, 0, 0.2); }
        ::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--accent); }
        .sidebar { width: 300px; background-color: var(--bg-secondary); border-right: 1px solid var(--border-color); display: flex; flex-direction: column; padding: 24px; z-index: 10; }
        .brand { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border-color); }
        .brand-logo { font-size: 28px; color: var(--accent); text-shadow: 0 0 10px rgba(212, 175, 55, 0.3); }
        .brand-title { font-family: 'Cinzel', serif; font-size: 16px; font-weight: 700; letter-spacing: 1px; color: var(--text-primary); }
        .table-list { list-style: none; display: flex; flex-direction: column; gap: 8px; overflow-y: auto; flex: 1; padding-right: 4px; }
        .table-item { display: flex; align-items: center; gap: 12px; padding: 12px 16px; border-radius: 8px; cursor: pointer; color: var(--text-secondary); transition: var(--transition); border: 1px solid transparent; }
        .table-item:hover { color: var(--text-primary); background-color: rgba(255, 255, 255, 0.03); border-color: rgba(255, 255, 255, 0.05); transform: translateX(4px); }
        .table-item.active { color: var(--accent); background-color: rgba(212, 175, 55, 0.08); border-color: var(--accent); font-weight: 600; }
        .table-icon { font-size: 18px; }
        .status-container { margin-top: 16px; padding: 12px; background-color: rgba(255, 255, 255, 0.02); border: 1px solid var(--border-color); border-radius: 8px; display: flex; align-items: center; gap: 10px; }
        .status-dot { width: 10px; height: 10px; background-color: var(--success); border-radius: 50%; box-shadow: 0 0 8px var(--success); animation: pulse 2s infinite; }
        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }
        .status-text { font-size: 12px; color: var(--text-secondary); }
        .workspace { flex: 1; display: flex; flex-direction: column; overflow: hidden; background-image: radial-gradient(circle at 50% 20%, rgba(31, 38, 52, 0.2) 0%, transparent 80%); }
        .header { padding: 24px 40px; border-bottom: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; background-color: var(--bg-glass); backdrop-filter: blur(12px); }
        .title-area h1 { font-family: 'Cinzel', serif; font-size: 24px; letter-spacing: 1px; color: var(--accent); text-shadow: 0 0 15px rgba(212, 175, 55, 0.15); }
        .title-area p { font-size: 13px; color: var(--text-secondary); margin-top: 4px; }
        .toolbar { display: flex; gap: 16px; align-items: center; }
        .search-container { position: relative; }
        .search-input { background-color: rgba(255, 255, 255, 0.04); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 16px 10px 40px; color: var(--text-primary); font-size: 14px; width: 250px; transition: var(--transition); }
        .search-input:focus { outline: none; border-color: var(--accent); background-color: rgba(255, 255, 255, 0.06); box-shadow: 0 0 10px rgba(212, 175, 55, 0.1); }
        .search-icon { position: absolute; left: 14px; top: 50%; transform: translateY(-50%); color: var(--text-secondary); font-size: 16px; }
        .btn { background-color: var(--accent); color: var(--bg-primary); border: none; padding: 10px 20px; border-radius: 8px; font-weight: 600; font-size: 14px; cursor: pointer; transition: var(--transition); display: flex; align-items: center; gap: 8px; }
        .btn:hover { background-color: var(--accent-hover); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(212, 175, 55, 0.2); }
        .btn-secondary { background-color: rgba(255, 255, 255, 0.05); color: var(--text-primary); border: 1px solid var(--border-color); }
        .btn-secondary:hover { background-color: rgba(255, 255, 255, 0.08); border-color: var(--accent); box-shadow: none; }
        .table-container { flex: 1; overflow: auto; padding: 40px; position: relative; }
        .card { background-color: var(--bg-glass); border: 1px solid var(--border-color); border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; max-height: 100%; box-shadow: 0 12px 36px rgba(0, 0, 0, 0.4); backdrop-filter: blur(12px); }
        .grid-wrapper { overflow: auto; max-height: 100%; }
        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }
        th { background-color: rgba(18, 20, 28, 0.8); position: sticky; top: 0; padding: 16px 20px; font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.8px; color: var(--text-secondary); border-bottom: 1px solid var(--border-color); z-index: 1; white-space: nowrap; }
        td { padding: 14px 20px; border-bottom: 1px solid var(--border-color); color: var(--text-primary); transition: var(--transition); max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        tr:hover td { background-color: rgba(255, 255, 255, 0.02); border-bottom-color: var(--border-hover); }
        .editable { cursor: pointer; position: relative; }
        .editable:hover::after { content: '✏️'; position: absolute; right: 8px; top: 50%; transform: translateY(-50%); font-size: 10px; opacity: 0.6; }
        .edit-input { width: 100%; background-color: var(--bg-secondary); border: 1px solid var(--accent); border-radius: 4px; color: var(--text-primary); padding: 4px 8px; font-size: 13px; font-family: inherit; outline: none; box-shadow: 0 0 8px rgba(212, 175, 55, 0.2); }
        .delete-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 16px; transition: var(--transition); padding: 4px 8px; border-radius: 4px; }
        .delete-btn:hover { color: var(--danger); background-color: rgba(239, 68, 68, 0.1); }
        .loader-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(10, 11, 14, 0.7); display: flex; justify-content: center; align-items: center; z-index: 5; backdrop-filter: blur(4px); opacity: 0; pointer-events: none; transition: opacity 0.2s ease; }
        .loader-overlay.active { opacity: 1; pointer-events: auto; }
        .spinner { width: 40px; height: 40px; border: 3px solid rgba(212, 175, 55, 0.1); border-top: 3px solid var(--accent); border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .modal-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.75); backdrop-filter: blur(8px); z-index: 100; display: flex; justify-content: center; align-items: center; opacity: 0; pointer-events: none; transition: opacity 0.3s ease; }
        .modal-overlay.active { opacity: 1; pointer-events: auto; }
        .modal-card { background-color: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 12px; width: 500px; max-width: 90%; box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6); display: flex; flex-direction: column; transform: scale(0.9); transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
        .modal-overlay.active .modal-card { transform: scale(1); }
        .modal-header { padding: 20px 24px; border-bottom: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; }
        .modal-header h2 { font-family: 'Cinzel', serif; font-size: 18px; color: var(--accent); }
        .modal-close { background: none; border: none; color: var(--text-secondary); font-size: 20px; cursor: pointer; transition: var(--transition); }
        .modal-close:hover { color: var(--text-primary); }
        .modal-body { padding: 24px; overflow-y: auto; max-height: 400px; display: flex; flex-direction: column; gap: 16px; }
        .form-group { display: flex; flex-direction: column; gap: 8px; }
        .form-group label { font-size: 12px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }
        .form-input { background-color: rgba(255, 255, 255, 0.03); border: 1px solid var(--border-color); border-radius: 6px; padding: 10px 14px; color: var(--text-primary); font-size: 14px; outline: none; transition: var(--transition); }
        .form-input:focus { border-color: var(--accent); background-color: rgba(255, 255, 255, 0.05); box-shadow: 0 0 8px rgba(212, 175, 55, 0.15); }
        .modal-footer { padding: 20px 24px; border-top: 1px solid var(--border-color); display: flex; justify-content: flex-end; gap: 12px; }
        .toast-container { position: fixed; bottom: 24px; right: 24px; display: flex; flex-direction: column; gap: 10px; z-index: 1000; }
        .toast { background-color: var(--bg-secondary); border-left: 4px solid var(--accent); border-top: 1px solid var(--border-color); border-right: 1px solid var(--border-color); border-bottom: 1px solid var(--border-color); padding: 16px 20px; border-radius: 6px; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5); display: flex; align-items: center; gap: 12px; min-width: 300px; max-width: 400px; transform: translateX(120%); transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
        .toast.active { transform: translateX(0); }
        .toast-success { border-left-color: var(--success); }
        .toast-danger { border-left-color: var(--danger); }
        .toast-icon { font-size: 18px; }
        .toast-message { font-size: 13px; color: var(--text-primary); flex: 1; }
        .no-data { padding: 40px; text-align: center; color: var(--text-muted); font-style: italic; }
        .settings-btn { margin-top: auto; padding: 10px 16px; border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; background: rgba(0,0,0,0.15); cursor: pointer; text-align: center; font-size: 12px; color: var(--text-secondary); transition: var(--transition); }
        .settings-btn:hover { border-color: var(--accent); color: var(--text-primary); }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="brand">
            <span class="brand-logo">🛡️</span>
            <div class="brand-title">Vesteros RPG Admin</div>
        </div>
        <ul class="table-list">
            {% for table in tables %}
            <li class="table-item {% if loop.first %}active{% endif %}" data-table-id="{{ table.id }}" onclick="switchTable('{{ table.id }}')">
                <span class="table-icon">{{ table.icon }}</span>
                <span class="table-name">{{ table.name }}</span>
            </li>
            {% endfor %}
        </ul>
        <button class="settings-btn" onclick="changeAdminPassword()">🔑 Parolni O'zgartirish</button>
        <div class="status-container">
            <div class="status-dot"></div>
            <div class="status-text">Baza holati: Railway MySQL Online</div>
        </div>
    </div>
    <div class="workspace">
        <div class="header">
            <div class="title-area">
                <h1 id="table-title">Foydalanuvchilar (users)</h1>
                <p id="table-subtitle">Vizual tahrirlash va saqlash</p>
            </div>
            <div class="toolbar">
                <div class="search-container">
                    <span class="search-icon">🔍</span>
                    <input type="text" id="search-input" class="search-input" placeholder="Qidiruv..." oninput="filterData()">
                </div>
                <button class="btn btn-secondary" onclick="fetchTableData()">🔄 Yangilash</button>
                <button class="btn" onclick="openAddModal()">➕ Qator Qo'shish</button>
            </div>
        </div>
        <div class="table-container">
            <div class="loader-overlay" id="loader"><div class="spinner"></div></div>
            <div class="card">
                <div class="grid-wrapper">
                    <table id="data-table">
                        <thead><tr id="table-headers"></tr></thead>
                        <tbody id="table-body"></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
    <div class="modal-overlay" id="add-modal">
        <div class="modal-card">
            <div class="modal-header">
                <h2 id="modal-title">Yangi Qator Qo'shish</h2>
                <button class="modal-close" onclick="closeAddModal()">&times;</button>
            </div>
            <div class="modal-body" id="modal-fields"></div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeAddModal()">Yopish</button>
                <button class="btn" onclick="submitAddRow()">Qo'shish</button>
            </div>
        </div>
    </div>
    <div class="toast-container" id="toast-container"></div>
    <script>
        let currentTableId = 'users';
        let tableColumns = [];
        let primaryKeys = [];
        let tableRows = [];
        let apiBaseUrl = window.location.origin; // Set backend URL
        
        let adminPassword = localStorage.getItem('admin_password') || '';
        
        if (!adminPassword) {
            adminPassword = prompt("Tizimga kirish uchun admin parolini kiriting (standart Telegram ID):") || '';
            localStorage.setItem('admin_password', adminPassword);
        }

        window.addEventListener('DOMContentLoaded', () => {
            switchTable(currentTableId);
        });

        function changeAdminPassword() {
            const pwd = prompt("Yangi admin parolini kiriting:");
            if (pwd) {
                localStorage.setItem('admin_password', pwd);
                adminPassword = pwd;
                fetchTableData();
            }
        }

        function switchTable(tableId) {
            currentTableId = tableId;
            document.querySelectorAll('.table-item').forEach(item => {
                if (item.getAttribute('data-table-id') === tableId) {
                    item.classList.add('active');
                } else {
                    item.classList.remove('active');
                }
            });
            const tableItem = document.querySelector(`.table-item[data-table-id="${tableId}"]`);
            if (tableItem) {
                document.getElementById('table-title').textContent = tableItem.querySelector('.table-name').textContent;
            }
            fetchTableData();
        }

        function showLoader(show) {
            const loader = document.getElementById('loader');
            if (show) loader.classList.add('active');
            else loader.classList.remove('active');
        }

        async function fetchTableData() {
            showLoader(true);
            try {
                const response = await fetch(`${apiBaseUrl}/api/data/${currentTableId}`, {
                    headers: { 'X-Admin-Password': adminPassword }
                });
                
                if (response.status === 401) {
                    localStorage.removeItem('admin_password');
                    alert("Admin paroli noto'g'ri!");
                    location.reload();
                    return;
                }
                
                const res = await response.json();
                if (res.success) {
                    tableColumns = res.columns;
                    primaryKeys = res.primary_keys;
                    tableRows = res.rows;
                    renderTable();
                } else {
                    showToast(res.error || "Xatolik yuz berdi.", "danger");
                }
            } catch (err) {
                showToast("Server bilan ulanib bo'lmadi.", "danger");
            } finally {
                showLoader(false);
            }
        }

        function renderTable(filteredRows = null) {
            const headerRow = document.getElementById('table-headers');
            const tbody = document.getElementById('table-body');
            headerRow.innerHTML = '';
            tbody.innerHTML = '';
            
            if (tableColumns.length === 0) return;

            tableColumns.forEach(col => {
                const th = document.createElement('th');
                th.textContent = col.name + (col.is_pk ? " 🔑" : "");
                headerRow.appendChild(th);
            });
            
            const actionTh = document.createElement('th');
            actionTh.textContent = 'Amallar';
            actionTh.style.width = '80px';
            actionTh.style.textAlign = 'center';
            headerRow.appendChild(actionTh);

            const rowsToRender = filteredRows || tableRows;
            if (rowsToRender.length === 0) {
                const tr = document.createElement('tr');
                const td = document.createElement('td');
                td.colSpan = tableColumns.length + 1;
                td.className = 'no-data';
                td.textContent = 'Hech qanday ma\'lumot topilmadi.';
                tr.appendChild(td);
                tbody.appendChild(tr);
                return;
            }

            rowsToRender.forEach(row => {
                const tr = document.createElement('tr');
                tableColumns.forEach(col => {
                    const td = document.createElement('td');
                    let cellVal = row[col.name];
                    if (cellVal !== null && typeof cellVal === 'object') {
                        td.textContent = JSON.stringify(cellVal);
                    } else {
                        td.textContent = cellVal === null ? '' : cellVal;
                    }
                    if (!col.is_pk) {
                        td.className = 'editable';
                        td.addEventListener('dblclick', () => makeCellEditable(td, row, col.name));
                    }
                    tr.appendChild(td);
                });

                const actionTd = document.createElement('td');
                actionTd.style.textAlign = 'center';
                const deleteBtn = document.createElement('button');
                deleteBtn.className = 'delete-btn';
                deleteBtn.innerHTML = '🗑️';
                deleteBtn.onclick = () => confirmDeleteRow(row);
                actionTd.appendChild(deleteBtn);
                tr.appendChild(actionTd);
                
                tbody.appendChild(tr);
            });
        }

        function makeCellEditable(td, row, colName) {
            if (td.querySelector('.edit-input')) return;
            const originalVal = td.textContent;
            td.textContent = '';
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'edit-input';
            input.value = originalVal;
            td.appendChild(input);
            input.focus();

            const saveFunc = async () => {
                const newVal = input.value.trim();
                if (newVal === originalVal) {
                    td.textContent = originalVal;
                    return;
                }
                const keys = {};
                primaryKeys.forEach(pk => { keys[pk] = row[pk]; });
                const values = {};
                values[colName] = newVal === '' ? null : newVal;

                showLoader(true);
                try {
                    const response = await fetch(`${apiBaseUrl}/api/update/${currentTableId}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Admin-Password': adminPassword
                        },
                        body: JSON.stringify({ keys, values })
                    });
                    
                    if (response.status === 401) {
                        alert("Parol noto'g'ri!");
                        location.reload();
                        return;
                    }
                    
                    const res = await response.json();
                    if (res.success) {
                        row[colName] = newVal === '' ? null : newVal;
                        td.textContent = newVal;
                        showToast("Saqlandi!", "success");
                    } else {
                        td.textContent = originalVal;
                        showToast(res.error || "Xatolik.", "danger");
                    }
                } catch (err) {
                    td.textContent = originalVal;
                    showToast("Ulanish xatosi.", "danger");
                } finally {
                    showLoader(false);
                }
            };

            input.addEventListener('blur', saveFunc);
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') input.blur();
                else if (e.key === 'Escape') {
                    input.value = originalVal;
                    input.blur();
                }
            });
        }

        async function confirmDeleteRow(row) {
            if (!confirm("Ushbu qatorni o'chirishni tasdiqlaysizmi?")) return;
            const keys = {};
            primaryKeys.forEach(pk => { keys[pk] = row[pk]; });

            showLoader(true);
            try {
                const response = await fetch(`${apiBaseUrl}/api/delete/${currentTableId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Admin-Password': adminPassword
                    },
                    body: JSON.stringify({ keys })
                });
                const res = await response.json();
                if (res.success) {
                    showToast("O'chirildi!", "success");
                    fetchTableData();
                } else {
                    showToast(res.error || "Xatolik.", "danger");
                }
            } catch (err) {
                showToast("Server xatosi.", "danger");
            } finally {
                showLoader(false);
            }
        }

        function filterData() {
            const query = document.getElementById('search-input').value.toLowerCase().trim();
            if (query === '') {
                renderTable();
                return;
            }
            const filtered = tableRows.filter(row => {
                return Object.values(row).some(val => {
                    if (val === null || val === undefined) return false;
                    return String(val).toLowerCase().includes(query);
                });
            });
            renderTable(filtered);
        }

        function openAddModal() {
            const fieldsContainer = document.getElementById('modal-fields');
            fieldsContainer.innerHTML = '';
            tableColumns.forEach(col => {
                const formGroup = document.createElement('div');
                formGroup.className = 'form-group';
                const label = document.createElement('label');
                label.textContent = col.name + (col.is_pk ? " (PK 🔑)" : "") + (!col.nullable ? " *" : "");
                const input = document.createElement('input');
                input.type = 'text';
                input.className = 'form-input';
                input.id = `add-field-${col.name}`;
                formGroup.appendChild(label);
                formGroup.appendChild(input);
                fieldsContainer.appendChild(formGroup);
            });
            document.getElementById('add-modal').classList.add('active');
        }

        function closeAddModal() {
            document.getElementById('add-modal').classList.remove('active');
        }

        async function submitAddRow() {
            const values = {};
            let hasError = false;

            tableColumns.forEach(col => {
                const input = document.getElementById(`add-field-${col.name}`);
                const val = input.value.trim();
                if (!col.nullable && val === '') {
                    showToast(`"${col.name}" maydoni to'ldirilishi shart.`, "danger");
                    hasError = true;
                }
                if (val !== '') values[col.name] = val;
            });

            if (hasError) return;

            showLoader(true);
            closeAddModal();
            try {
                const response = await fetch(`${apiBaseUrl}/api/add/${currentTableId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Admin-Password': adminPassword
                    },
                    body: JSON.stringify({ values })
                });
                const res = await response.json();
                if (res.success) {
                    showToast("Yangi qator qo'shildi!", "success");
                    fetchTableData();
                } else {
                    showToast(res.error || "Xatolik.", "danger");
                    openAddModal();
                }
            } catch (err) {
                showToast("Server xatosi.", "danger");
            } finally {
                showLoader(false);
            }
        }

        function showToast(message, type = 'success') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast toast-${type}`;
            const icon = document.createElement('span');
            icon.className = 'toast-icon';
            icon.textContent = type === 'success' ? '✅' : '❌';
            const msg = document.createElement('span');
            msg.className = 'toast-message';
            msg.textContent = message;
            toast.appendChild(icon);
            toast.appendChild(msg);
            container.appendChild(toast);
            setTimeout(() => toast.classList.add('active'), 50);
            setTimeout(() => {
                toast.classList.remove('active');
                setTimeout(() => toast.remove(), 300);
            }, 4000);
        }
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    setup_webhook()
    print(f"[INFO] Starting Flask web server on port {PORT}...")
    app.run(host='0.0.0.0', port=PORT)
