import os
import json
import pymysql
import datetime
from dbutils.pooled_db import PooledDB
from dotenv import load_dotenv

load_dotenv()

# MySQL Database configuration from environment variables
DB_HOST = os.getenv('MYSQLHOST') or os.getenv('DB_HOST') or 'localhost'
DB_USER = os.getenv('MYSQLUSER') or os.getenv('DB_USER') or 'root'
DB_PASSWORD = os.getenv('MYSQLPASSWORD') or os.getenv('DB_PASSWORD') or ''
DB_NAME = os.getenv('MYSQLDATABASE') or os.getenv('DB_NAME') or 'vesteros_rpg'
DB_PORT = int(os.getenv('MYSQLPORT') or os.getenv('DB_PORT') or '3306')
ADMIN_TELEGRAM_ID = os.getenv('ADMIN_TELEGRAM_ID')

# Connection Pool Initialization
db_pool = PooledDB(
    creator=pymysql,
    maxconnections=50,
    mincached=5,
    host=DB_HOST,
    user=DB_USER,
    password=DB_PASSWORD,
    database=DB_NAME,
    port=DB_PORT,
    charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=True
)

def query(sql, params=None):
    """Execute a SELECT query and return all results."""
    conn = db_pool.connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params or ())
            return cursor.fetchall()
    finally:
        conn.close()

def query_one(sql, params=None):
    """Execute a SELECT query and return the first result or None."""
    res = query(sql, params)
    return res[0] if res else None

def execute(sql, params=None):
    """Execute an INSERT, UPDATE, or DELETE query and return affected rows."""
    conn = db_pool.connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params or ())
            return cursor.rowcount
    finally:
        conn.close()

# Helpers
def format_date(val):
    if not val:
        return ''
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.strftime('%Y-%m-%d')
    return str(val)[:10]

# Settings Management
def get_setting(key, default_value=''):
    row = query_one('SELECT setting_value FROM settings WHERE setting_key = %s', (key,))
    if not row:
        return default_value
    return row['setting_value']

def set_setting(key, value):
    execute(
        'INSERT INTO settings (setting_key, setting_value) VALUES (%s, %s) '
        'ON DUPLICATE KEY UPDATE setting_value = %s',
        (key, str(value), str(value))
    )

# User Operations
def get_user(user_id):
    if not user_id:
        return None
    str_user_id = str(user_id)
    row = query_one('SELECT * FROM users WHERE telegram_id = %s', (str_user_id,))
    if not row:
        return None
    
    user_obj = {
        'telegram_id': row['telegram_id'],
        'username': row['username'] or 'User',
        'house_id': row['house_id'] or 'none',
        'role': row['role'] or 'citizen',
        'wallet_balance': float(row['wallet_balance']) if row['wallet_balance'] is not None else 0.0,
        'last_checkin': format_date(row['last_checkin']),
        'casino_spins_left': int(row['casino_spins_left']) if row['casino_spins_left'] is not None else 0,
        'last_casino_spin_date': format_date(row['last_casino_spin_date'])
    }

    # Auto-correct admin role
    if str_user_id == str(ADMIN_TELEGRAM_ID):
        if user_obj['house_id'] != 'admin' or user_obj['role'] != 'admin':
            user_obj['house_id'] = 'admin'
            user_obj['role'] = 'admin'
            execute("UPDATE users SET house_id = 'admin', role = 'admin' WHERE telegram_id = %s", (str_user_id,))
            
    return user_obj

def get_house(house_id):
    if house_id == 'admin' or house_id == 'none' or not house_id:
        return {
            'house_id': 'admin',
            'house_name': "Boshqaruvchi / Tizim",
            'currency_name': "Tizim Tangasi",
            'currency_symbol': "🪙",
            'lord_id': "0",
            'treasury_balance': 0.0,
            'wall_health': 0,
            'valyrian_steel_count': 0,
            'tax_rate': 0.0,
            'group_link': "",
            'group_chat_id': "",
            'defense_cooldown_until': "",
            'wall_type': "qora",
            'wall_max_health': 600,
            'alliance_house_id': ""
        }

    row = query_one('SELECT * FROM houses WHERE house_id = %s', (house_id,))
    if not row:
        return None
        
    return {
        'house_id': row['house_id'],
        'house_name': row['house_name'],
        'currency_name': row['currency_name'],
        'currency_symbol': row['currency_symbol'],
        'lord_id': row['lord_id'],
        'treasury_balance': float(row['treasury_balance']) if row['treasury_balance'] is not None else 0.0,
        'wall_health': int(row['wall_health']) if row['wall_health'] is not None else 0,
        'valyrian_steel_count': int(row['valyrian_steel_count']) if row['valyrian_steel_count'] is not None else 0,
        'tax_rate': float(row['tax_rate']) if row['tax_rate'] is not None else 0.0,
        'group_link': row['group_link'] or "",
        'group_chat_id': row['group_chat_id'] or "",
        'defense_cooldown_until': row['defense_cooldown_until'] or "",
        'wall_type': row['wall_type'] or "qora",
        'wall_max_health': int(row['wall_max_health']) if row['wall_max_health'] is not None else 600,
        'alliance_house_id': row['alliance_house_id'] or ""
    }

def get_house_army(house_id):
    if not house_id:
        return {}
    rows = query('SELECT unit_id, quantity FROM house_units WHERE house_id = %s', (house_id,))
    army = {u: 0 for u in ['askar', 'bori', 'otliq', 'kamonchi', 'devor_buzuvchi', 'katapulta', 'chayon', 'afsungar']}
    for row in rows:
        army[row['unit_id']] = int(row['quantity']) if row['quantity'] is not None else 0
    return army

def get_house_by_group_chat_id(chat_id):
    if not chat_id:
        return None
    str_chat_id = str(chat_id)
    row = query_one('SELECT house_id FROM houses WHERE group_chat_id = %s', (str_chat_id,))
    if not row:
        return None
    return get_house(row['house_id'])

def get_least_populated_house():
    rows = query(
        "SELECT h.house_id, COUNT(u.telegram_id) as count "
        "FROM houses h LEFT JOIN users u ON h.house_id = u.house_id "
        "WHERE h.house_id != 'admin' "
        "GROUP BY h.house_id "
        "ORDER BY count ASC"
    )
    if not rows:
        return 'stark'
    
    import random
    min_count = rows[0]['count']
    candidates = [r['house_id'] for r in rows if r['count'] == min_count]
    return random.choice(candidates)

def check_user_group_membership(user_id, bot_token):
    import requests
    rows = query("SELECT house_id, group_chat_id FROM houses WHERE group_chat_id IS NOT NULL AND group_chat_id != ''")
    for row in rows:
        url = f"https://api.telegram.org/bot{bot_token}/getChatMember?chat_id={row['group_chat_id']}&user_id={user_id}"
        try:
            res = requests.get(url, timeout=5).json()
            if res.get('ok') and res.get('result'):
                status = res['result'].get('status')
                if status in ['member', 'administrator', 'creator', 'restricted']:
                    return row['house_id']
        except Exception:
            pass
    return None

def get_or_create_user(user_id, username, bot_token):
    user = get_user(user_id)
    if user:
        return user

    house_id = check_user_group_membership(user_id, bot_token)
    if not house_id:
        house_id = get_least_populated_house()

    execute(
        'INSERT INTO users (telegram_id, username, house_id, role, wallet_balance, casino_spins_left) '
        'VALUES (%s, %s, %s, %s, %s, %s)',
        (str(user_id), username, house_id, 'citizen', 100.0, 3)
    )
    return get_user(user_id)

def get_or_create_user_in_group(user_id, username, house_id):
    user = get_user(user_id)
    if user:
        if user['role'] == 'admin':
            return user
        if user['house_id'] != house_id:
            execute('UPDATE users SET house_id = %s WHERE telegram_id = %s', (house_id, str(user_id)))
            user['house_id'] = house_id
        return user

    execute(
        'INSERT INTO users (telegram_id, username, house_id, role, wallet_balance, casino_spins_left) '
        'VALUES (%s, %s, %s, %s, %s, %s)',
        (str(user_id), username, house_id, 'citizen', 100.0, 3)
    )
    return get_user(user_id)

# Treasury & Balance modification
def update_house_treasury(house_id, amount):
    execute(
        'UPDATE houses SET treasury_balance = GREATEST(0.0, treasury_balance + %s) WHERE house_id = %s',
        (float(amount), house_id)
    )

def update_wall_hp(house_id, health):
    execute('UPDATE houses SET wall_health = %s WHERE house_id = %s', (int(health), house_id))

def set_house_shield(house_id, days):
    until = (datetime.datetime.now() + datetime.timedelta(days=days)).isoformat()
    execute('UPDATE houses SET defense_cooldown_until = %s WHERE house_id = %s', (until, house_id))

def log_transaction(from_id, to_id, amount, desc):
    import random
    import time
    tx_id = f"tx_{int(time.time()*1000)}_{random.randint(0, 999)}"
    execute(
        'INSERT INTO transactions (tx_id, timestamp, from_id, to_id, amount, currency, tx_type, description) '
        'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
        (tx_id, datetime.datetime.now().isoformat(), str(from_id), str(to_id), float(amount), 'SW', 'payment', desc)
    )

# Army operations
def add_house_units(house_id, troops):
    for unit_id, quantity in troops.items():
        if quantity <= 0:
            continue
        execute(
            'INSERT INTO house_units (house_id, unit_id, quantity) VALUES (%s, %s, %s) '
            'ON DUPLICATE KEY UPDATE quantity = quantity + %s',
            (house_id, unit_id, int(quantity), int(quantity))
        )

def deduct_house_units(house_id, troops):
    for unit_id, quantity in troops.items():
        if quantity <= 0:
            continue
        execute(
            'UPDATE house_units SET quantity = GREATEST(0, quantity - %s) '
            'WHERE house_id = %s AND unit_id = %s',
            (int(quantity), house_id, unit_id)
        )

def reduce_army(house_id, pct, casualties_store):
    army = get_house_army(house_id)
    for u, qty in army.items():
        if qty > 0:
            killed = int(qty * pct)
            if killed > 0:
                casualties_store[u] = killed
                execute(
                    'UPDATE house_units SET quantity = GREATEST(0, quantity - %s) '
                    'WHERE house_id = %s AND unit_id = %s',
                    (killed, house_id, u)
                )

def load_units_meta():
    rows = query('SELECT * FROM units')
    meta = {}
    for r in rows:
        meta[r['unit_id']] = {
            'unit_id': r['unit_id'],
            'name': r['name'],
            'cost_tanga': float(r['cost_tanga']),
            'attack': float(r['attack']),
            'defense': float(r['defense']),
            'type': r['type'],
            'special_effects': json.loads(r['special_effects']) if r['special_effects'] else {}
        }
    return meta

# Battles Record
def get_battle_record(battle_id):
    return query_one('SELECT * FROM battles WHERE battle_id = %s', (battle_id,))

def update_battle_record(battle_id, updates):
    if not updates:
        return
    sets = []
    vals = []
    for k, v in updates.items():
        sets.append(f"{k} = %s")
        if isinstance(v, dict):
            vals.append(json.dumps(v))
        else:
            vals.append(v)
    vals.append(battle_id)
    sql = f"UPDATE battles SET {', '.join(sets)} WHERE battle_id = %s"
    execute(sql, tuple(vals))

# Loans
def get_pending_loans_list():
    return query("SELECT * FROM loans WHERE status = 'pending' ORDER BY requested_at ASC")

# Economy & Reporting
def get_economy_stats():
    # Iron Bank Treasury
    bt_row = query_one('SELECT total_bank_coins, casino_revenue FROM bank_treasury LIMIT 1')
    tb_coins = float(bt_row['total_bank_coins']) if bt_row else 10000.0
    casino_rev = float(bt_row['casino_revenue']) if bt_row else 0.0

    # Total user balances
    u_sum = query_one('SELECT SUM(wallet_balance) as total FROM users')
    total_users_bal = float(u_sum['total']) if u_sum and u_sum['total'] else 0.0

    # Total house treasuries
    h_sum = query_one("SELECT SUM(treasury_balance) as total FROM houses WHERE house_id != 'admin'")
    total_houses_bal = float(h_sum['total']) if h_sum and h_sum['total'] else 0.0

    total_circulation = total_users_bal + total_houses_bal

    stats = (
        f"📊 *VESTEROS IQTISODIY HISOBOTI* 📊\n\n"
        f"🏦 **Temir Bank G'aznasi:** *{tb_coins} 🪙*\n"
        f"🎰 **Kazino Jamg'armasi:** *{casino_rev} 🪙*\n"
        f"💸 **Muomaladagi jami pullar:** *{total_circulation:.1f} 🪙*\n"
        f"   • O'yinchilar qo'lida: *{total_users_bal:.1f} 🪙*\n"
        f"   • Xonadonlar g'aznasida: *{total_houses_bal:.1f} 🪙*\n\n"
        f"*Xonadonlar G'aznalari:*\n"
    )

    houses = query("SELECT house_name, treasury_balance, currency_symbol FROM houses WHERE house_id != 'admin'")
    for h in houses:
        bal = float(h['treasury_balance']) if h['treasury_balance'] is not None else 0.0
        stats += f"• {h['house_name']}: *{bal:.1f} {h['currency_symbol']}*\n"

    return stats
