import os
import json
import time
import random
import datetime
import requests
import telebot
from telebot import types
import database as db

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_TELEGRAM_ID = os.getenv('ADMIN_TELEGRAM_ID')

bot = telebot.TeleBot(BOT_TOKEN, num_threads=50)

# Helper functions for Telegram API
def send_telegram_message(chat_id, text, reply_markup=None):
    if not BOT_TOKEN or not chat_id:
        return None
    for _ in range(3):
        try:
            return bot.send_message(chat_id, text, parse_mode='Markdown', reply_markup=reply_markup)
        except Exception as e:
            if '429' in str(e):
                time.sleep(1.5)
                continue
            # Fallback to plain text if Markdown parsing fails
            try:
                return bot.send_message(chat_id, text, reply_markup=reply_markup)
            except Exception as inner_e:
                print(f"sendTelegramMessage error: {inner_e}")
                break
    return None

def edit_telegram_message(chat_id, message_id, text, reply_markup=None):
    if not BOT_TOKEN:
        return None
    try:
        # Default to removing keyboard if None passed
        markup = reply_markup if reply_markup else types.InlineKeyboardMarkup()
        return bot.edit_message_text(text, chat_id, message_id, parse_mode='Markdown', reply_markup=markup)
    except Exception as e:
        try:
            markup = reply_markup if reply_markup else types.InlineKeyboardMarkup()
            return bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        except Exception as inner_e:
            print(f"editTelegramMessage error: {inner_e}")
            return None

def answer_callback_query(callback_query_id, text=None):
    if not BOT_TOKEN:
        return
    try:
        bot.answer_callback_query(callback_query_id, text=text)
    except Exception:
        pass

def send_telegram_dice(chat_id):
    if not BOT_TOKEN:
        return None
    try:
        return bot.send_dice(chat_id, emoji='🎰')
    except Exception as e:
        print(f"sendTelegramDice error: {e}")
        return None

def copy_telegram_message(target_chat_id, from_chat_id, message_id):
    if not BOT_TOKEN:
        return
    for _ in range(3):
        try:
            bot.copy_message(target_chat_id, from_chat_id, message_id)
            break
        except Exception as e:
            if '429' in str(e):
                time.sleep(1.5)
                continue
            break

# Game notifications
def notify_house(house_id, text):
    rows = db.query("SELECT telegram_id FROM users WHERE house_id = %s", (house_id,))
    for row in rows:
        send_telegram_message(row['telegram_id'], text)

def notify_banker(text):
    rows = db.query("SELECT telegram_id FROM users WHERE role = 'banker' OR role = 'admin'")
    for row in rows:
        send_telegram_message(row['telegram_id'], text)

def notify_global(text, reply_markup=None):
    # Send to house group chats
    rows = db.query("SELECT group_chat_id FROM houses WHERE group_chat_id IS NOT NULL AND group_chat_id != ''")
    for row in rows:
        send_telegram_message(row['group_chat_id'], text, reply_markup)
    # Send to general chat
    general_chat_id = db.get_setting('general_chat_id')
    if general_chat_id:
        send_telegram_message(general_chat_id, text, reply_markup)

# Casino spin check and execution
def check_casino_eligible(user_id, bet=10):
    bet = float(bet)
    casino_state = db.get_setting('casino_state', 'closed')
    if casino_state != 'open':
        return {'eligible': False, 'message': "🔴 Kazino yopiq! Hozir o'ynab bo'lmaydi."}

    user = db.get_user(user_id)
    if not user:
        return {'eligible': False, 'message': "Foydalanuvchi topilmadi."}
    if user['role'] == 'admin':
        return {'eligible': False, 'message': "🚫 Admin kazino o'ynay olmaydi!"}

    today = datetime.date.today().isoformat()
    if user['last_casino_spin_date'] != today:
        db.execute('UPDATE users SET casino_spins_left = 3, last_casino_spin_date = %s WHERE telegram_id = %s', (today, str(user_id)))
        user['casino_spins_left'] = 3
        user['last_casino_spin_date'] = today

    if user['casino_spins_left'] <= 0:
        return {'eligible': False, 'message': "🚫 Bugun imkoniyat tugadi! (Maks: 3/kun)"}
    if user['wallet_balance'] < bet:
        return {'eligible': False, 'message': f"💸 Balansingizda yetarli pul yo'q! Tikish uchun kamida {bet} tanga kerak."}
    
    return {'eligible': True}

def deduct_casino_fee(user_id, bet):
    bet = float(bet)
    today = datetime.date.today().isoformat()
    db.execute(
        'UPDATE users SET wallet_balance = wallet_balance - %s, casino_spins_left = casino_spins_left - 1, '
        'last_casino_spin_date = %s WHERE telegram_id = %s',
        (bet, today, str(user_id))
    )

def process_casino_dice_result(user_id, val, bet):
    bet = float(bet)
    user = db.get_user(user_id)
    house = db.get_house(user['house_id'])
    currency_symbol = house['currency_symbol']

    is_win = val in [1, 22, 43, 64]
    prize = 0.0
    combination = ""

    if val == 1:
        prize = float(int(bet * 4.5))
        combination = "Limonlar 🍋 🍋 🍋"
    elif val == 22:
        prize = float(int(bet * 2))
        combination = "Giloslar 🍇 🍇 🍇"
    elif val == 43:
        prize = float(int(bet * 2))
        combination = "BAR BAR BAR 💎"
    elif val == 64:
        prize = float(int(bet * 7.5))
        combination = "Jekpot 777! 🔥🎰🏆"

    user = db.get_user(user_id)
    balance = user['wallet_balance']
    remaining_spins = user['casino_spins_left']

    if is_win:
        new_bal = balance + prize
        db.execute('UPDATE users SET wallet_balance = %s WHERE telegram_id = %s', (new_bal, str(user_id)))
        # Casino revenue tracks banker treasury
        db.execute('UPDATE bank_treasury SET casino_revenue = casino_revenue - %s LIMIT 1', (prize,))
        db.log_transaction("CENTRAL_BANK", user_id, prize, f"Casino Dice Win: {combination} (Bet: {bet})")
        return {
            'success': True,
            'message': f"🎉 *KAZINO NATIJASI: {combination}*\n\n"
                       f"Siz yutdingiz! 🎉\n\n"
                       f"• Tikilgan pul: *{bet} {currency_symbol}*\n"
                       f"• Yutuq: *+{prize} {currency_symbol}*\n"
                       f"• Qolgan imkoniyatlar: *{remaining_spins} ta*\n"
                       f"• Yangi balans: *{new_bal} {currency_symbol}*\n\n"
                       f"Omad kelganda yana o'ynaysizmi?"
        }
    else:
        # Casino collects losses
        db.execute('UPDATE bank_treasury SET casino_revenue = casino_revenue + %s LIMIT 1', (bet,))
        db.log_transaction(user_id, "CENTRAL_BANK", bet, f"Casino Dice Loss (Value: {val}, Bet: {bet})")
        return {
            'success': False,
            'message': f"🎰 *KAZINO NATIJASI (Kombinatsiya tushmadi: {val})*\n\n"
                       f"Afsuski yutqazdingiz. 😢\n\n"
                       f"• Tikilgan pul: *{bet} {currency_symbol}*\n"
                       f"• Yo'qotildi: *-{bet} {currency_symbol}*\n"
                       f"• Qolgan imkoniyatlar: *{remaining_spins} ta*\n"
                       f"• Yangi balans: *{balance} {currency_symbol}*\n\n"
                       f"Yana urinib ko'rasizmi?"
        }

# Shop Wall upgrade and Unit purchase
def process_wall_upgrade(user_id, wall_type):
    user = db.get_user(user_id)
    if user['role'] not in ['lord', 'king', 'co_admin', 'admin']:
        return {'success': False, 'message': "🚫 Faqat Lord yoki Qirol devorni yangilay oladi!"}

    house_id = user['house_id']
    house = db.get_house(house_id)
    if not house or house_id == 'admin':
        return {'success': False, 'message': "⚠️ Siz ma'lum bir xonadonga biriktirilmagansiz!"}

    types_meta = {
        'yogoch': {'cost': 80.0, 'hp': 100, 'label': "🪵 Yog'och devor"},
        'tosh': {'cost': 250.0, 'hp': 300, 'label': "🧱 Tosh devor"},
        'qora': {'cost': 500.0, 'hp': 600, 'label': "🌌 Qora devor"}
    }

    if wall_type not in types_meta:
        return {'success': False, 'message': "⚠️ Noto'g'ri devor turi! Faqat: `yogoch`, `tosh` yoki `qora`"}

    meta = types_meta[wall_type]
    if house['treasury_balance'] < meta['cost']:
        return {'success': False, 'message': f"💸 Xonadon g'aznasida yetarli pul yo'q! Kerak: {meta['cost']} {house['currency_symbol']}"}

    db.update_house_treasury(house_id, -meta['cost'])
    # Add to Temir Bank
    db.execute('UPDATE bank_treasury SET total_bank_coins = total_bank_coins + %s LIMIT 1', (meta['cost'],))
    db.execute('UPDATE houses SET wall_type = %s, wall_health = %s, wall_max_health = %s WHERE house_id = %s', (wall_type, meta['hp'], meta['hp'], house_id))
    db.log_transaction(house_id, "SHOP", meta['cost'], f"Devor upgrade: {meta['label']}")

    return {'success': True, 'message': f"🧱 *{house['house_name']}* devorlari muvaffaqiyatli *{meta['label']}* (HP: {meta['hp']}) ga yangilandi!"}

def process_unit_purchase(user_id, unit_id, quantity):
    shop_state = db.get_setting('shop_state', 'open')
    if shop_state != 'open':
        return {'success': False, 'message': "⚠️ Harbiy savdolar (xaridlar) vaqtincha yopilgan!"}

    user = db.get_user(user_id)
    if user['role'] not in ['lord', 'king', 'co_admin', 'admin', 'builder']:
        return {'success': False, 'message': "🚫 Ruxsat yo'q! Harbiy xaridlar faqat Lord yoki Quruvchiga tegishli."}

    house_id = user['house_id']
    house = db.get_house(house_id)
    if not house or house_id == 'admin':
        return {'success': False, 'message': "⚠️ Siz ma'lum bir xonadonga biriktirilmagansiz!"}

    if quantity <= 0:
        return {'success': False, 'message': "⚠️ Noto'g'ri askar soni!"}

    units_meta = db.load_units_meta()
    if unit_id not in units_meta:
        return {'success': False, 'message': f"⚠️ Bunday harbiy birlik topilmadi: {unit_id}"}

    meta = units_meta[unit_id]
    total_cost = meta['cost_tanga'] * quantity

    if house['treasury_balance'] < total_cost:
        return {'success': False, 'message': f"💸 Xonadon g'aznasida yetarli pul yo'q! Kerak: {total_cost} {house['currency_symbol']}"}

    db.update_house_treasury(house_id, -total_cost)
    db.execute('UPDATE bank_treasury SET total_bank_coins = total_bank_coins + %s LIMIT 1', (total_cost,))
    db.add_house_units(house_id, {unit_id: quantity})
    db.log_transaction(house_id, "SHOP", total_cost, f"Harbiy Xarid: {quantity} ta {unit_id}")

    return {'success': True, 'message': f"🗡️ *{quantity} ta {meta['name']}* muvaffaqiyatli sotib olindi!"}

# Alliance Logic
def process_alliance_proposal(user_id, target_house_id):
    user = db.get_user(user_id)
    if user['role'] not in ['lord', 'king', 'co_admin', 'admin']:
        return {'success': False, 'message': "🚫 Faqat Lord yoki Qirol ittifoq taklif qilishi mumkin!"}

    sender_house_id = user['house_id']
    if sender_house_id == target_house_id:
        return {'success': False, 'message': "O'z Xonadoningiz bilan ittifoq tuzolmaysiz!"}

    sender_house = db.get_house(sender_house_id)
    target_house = db.get_house(target_house_id)

    if not sender_house or sender_house_id == 'admin':
        return {'success': False, 'message': "Xonadoningiz aniqlanmadi."}
    if not target_house or target_house_id == 'admin':
        return {'success': False, 'message': "Maqsad xonadon topilmadi."}

    if sender_house['alliance_house_id']:
        partner = db.get_house(sender_house['alliance_house_id'])
        partner_name = partner['house_name'] if partner else sender_house['alliance_house_id']
        return {'success': False, 'message': f"⚠️ Sizning xonadoningiz allaqachon *{partner_name}* bilan ittifoq tuzgan!"}
    
    if target_house['alliance_house_id']:
        return {'success': False, 'message': f"⚠️ *{target_house['house_name']}* xonadoni allaqachon boshqa ittifoqdoshga ega!"}

    defender_lord_id = target_house['lord_id'].strip() if target_house['lord_id'] else "0"
    if defender_lord_id == "0" or defender_lord_id == "":
        return {'success': False, 'message': f"⚠️ *{target_house['house_name']}* xonadonida faol Lord yo'q!"}

    proposal_text = (
        f"🤝 *ITTIFOQ TAKLIFNOMASI* 🤝\n\n"
        f"*{sender_house['house_name']}* xonadoni sizning xonadoningiz bilan harbiy-siyosiy ittifoq tuzishni taklif qilmoqda!\n\n"
        f"Ittifoqdoshlar bir-biriga hujum qila olmaydilar (avval ittifoqni buzish kerak) va janglarda yordam bera oladilar."
    )

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🤝 Qabul qilish", callback_data=f"cb_alliance_decision:{sender_house_id}:{target_house_id}:accept"),
        types.InlineKeyboardButton("❌ Rad etish", callback_data=f"cb_alliance_decision:{sender_house_id}:{target_house_id}:reject")
    )

    send_telegram_message(defender_lord_id, proposal_text, kb)
    if target_house['group_chat_id']:
        send_telegram_message(target_house['group_chat_id'], proposal_text, kb)

    return {'success': True, 'message': f"🤝 *Ittifoq taklifi yuborildi!* *{target_house['house_name']}* Lordining javobi kutilmoqda."}

def process_alliance_dissolve(user_id):
    user = db.get_user(user_id)
    if user['role'] not in ['lord', 'king', 'co_admin', 'admin']:
        return {'success': False, 'message': "🚫 Faqat Lord yoki Qirol ittifoqni buza oladi!"}

    house_id = user['house_id']
    house = db.get_house(house_id)
    if not house or house_id == 'admin':
        return {'success': False, 'message': "Xonadoningiz aniqlanmadi."}

    ally_id = house['alliance_house_id']
    if not ally_id:
        return {'success': False, 'message': "⚠️ Sizning xonadoningizda hech qanday faol ittifoq yo'q!"}
    
    ally_house = db.get_house(ally_id)

    db.execute('UPDATE houses SET alliance_house_id = NULL WHERE house_id = %s OR house_id = %s', (house_id, ally_id))

    dissolve_text = (
        f"🤝❌ *ITTIFOQ BUZILDI!* 🤝❌\n\n"
        f"*{house['house_name']}* va *{ally_house['house_name'] if ally_house else ally_id.upper()}* xonadonlari o'rtasidagi ittifoq rasman buzildi!"
    )
    notify_global(dissolve_text)

    return {'success': True, 'message': "✅ Ittifoq muvaffaqiyatli buzildi!"}

def process_alliance_help(user_id, text_command):
    user = db.get_user(user_id)
    if user['role'] not in ['lord', 'king', 'co_admin', 'admin']:
        return {'success': False, 'message': "🚫 Faqat Lord yoki Qirol ittifoqdoshga yordam yubora oladi!"}

    parts = text_command.strip().split()
    if len(parts) < 2:
        return {'success': False, 'message': "⚠️ Foydalanish: `/yordam_berish <battle_id> <harbiy_nomi> <miqdor>`"}

    battle_id = parts[1]
    battle = db.get_battle_record(battle_id)
    if not battle:
        return {'success': False, 'message': "Urush topilmadi!"}
    if battle['status'] != 'pending':
        return {'success': False, 'message': "Bu urush yakunlangan!"}

    house_id = user['house_id']
    is_attacker_ally = False
    is_defender_ally = False

    attacker_house = db.get_house(battle['attacker_house'])
    defender_house = db.get_house(battle['defender_house'])

    if attacker_house['alliance_house_id'] == house_id:
        is_attacker_ally = True
    elif defender_house['alliance_house_id'] == house_id:
        is_defender_ally = True
    else:
        return {'success': False, 'message': "⚠️ Siz ushbu urushda ishtirok etayotgan xonadonlarning ittifoqdoshi emassiz!"}

    troops_to_send = {}
    specified_troops = False

    if len(parts) >= 4:
        i = 2
        while i < len(parts):
            u_id = parts[i].lower().strip()
            if i + 1 >= len(parts):
                break
            try:
                qty = int(parts[i+1])
            except ValueError:
                qty = 0
            if u_id and qty > 0:
                troops_to_send[u_id] = troops_to_send.get(u_id, 0) + qty
                specified_troops = True
            i += 2

    if not specified_troops:
        ally_army = db.get_house_army(house_id)
        for u, q in ally_army.items():
            if q > 0:
                troops_to_send[u] = q

    units_meta = db.load_units_meta()
    has_troops = False
    for u, q in troops_to_send.items():
        if q > 0:
            has_troops = True
            if u not in units_meta:
                return {'success': False, 'message': f"⚠️ Noto'g'ri qo'shin turi kiritildi: *{u}*."}

    if not has_troops:
        return {'success': False, 'message': "⚠️ Sizda yuborish uchun hech qanday qo'shin yo'q!"}

    ally_army = db.get_house_army(house_id)
    for u, q in troops_to_send.items():
        if ally_army.get(u, 0) < q:
            return {'success': False, 'message': f"⚠️ Sizda yetarli miqdorda *{u.upper()}* yo'q! Balans: *{ally_army.get(u, 0)}*"}

    db.deduct_house_units(house_id, troops_to_send)

    if is_attacker_ally:
        curr_ally_troops = {}
        if battle['attacker_ally_troops_json']:
            try:
                curr_ally_troops = json.loads(battle['attacker_ally_troops_json'])
            except Exception:
                pass
        for u, q in troops_to_send.items():
            curr_ally_troops[u] = curr_ally_troops.get(u, 0) + q
        db.execute('UPDATE battles SET attacker_ally_house = %s, attacker_ally_troops_json = %s WHERE battle_id = %s', (house_id, json.dumps(curr_ally_troops), battle_id))
    elif is_defender_ally:
        curr_ally_troops = {}
        if battle['defender_ally_troops_json']:
            try:
                curr_ally_troops = json.loads(battle['defender_ally_troops_json'])
            except Exception:
                pass
        for u, q in troops_to_send.items():
            curr_ally_troops[u] = curr_ally_troops.get(u, 0) + q
        db.execute('UPDATE battles SET defender_ally_house = %s, defender_ally_troops_json = %s WHERE battle_id = %s', (house_id, json.dumps(curr_ally_troops), battle_id))

    troops_str = "\n".join([f"• {u.upper()}: *{q} ta*" for u, q in troops_to_send.items() if q > 0])
    notify_text = (
        f"🤝 *ITTIFOQDOSH YORDAMI YETIB KELDI!* 🤝\n\n"
        f"*{db.get_house(house_id)['house_name']}* xonadoni jangga qo'shin yubordi!\n\n"
        f"*Yordam qo'shini:*\n{troops_str}"
    )

    other_house_id = battle['defender_house'] if battle['attacker_house'] == house_id else battle['attacker_house']
    send_telegram_message(other_house_id, notify_text)
    if attacker_house['group_chat_id']:
        send_telegram_message(attacker_house['group_chat_id'], notify_text)
    if defender_house['group_chat_id']:
        send_telegram_message(defender_house['group_chat_id'], notify_text)

    return {'success': True, 'message': "✅ Ittifoqdoshingizga yordam qo'shini muvaffaqiyatli yuborildi!"}

# Combat Mechanics
def calculate_side_score(troops, house, units_meta):
    score = 0.0
    steel = house.get('valyrian_steel_count', 0)
    for u, qty in troops.items():
        if qty <= 0:
            continue
        meta = units_meta.get(u)
        if not meta:
            continue
        unit_atk = meta['attack'] * qty
        if steel > 0:
            effects = meta.get('special_effects', {})
            boost_rule = effects.get('valyrian_boost')
            if boost_rule is None:
                if u in ['askar', 'bori']:
                    boost_rule = 'unlimited'
                elif u in ['otliq', 'kamonchi']:
                    boost_rule = 50

            if boost_rule == 'unlimited':
                unit_atk += qty * meta['attack']
            elif isinstance(boost_rule, (int, float)) or (isinstance(boost_rule, str) and boost_rule.isdigit()):
                mult = int(boost_rule)
                boosted_qty = min(qty, steel * mult)
                unit_atk += boosted_qty * meta['attack']
        score += unit_atk
    return score

def calculate_defender_score(army, house, units_meta):
    score = 0.0
    steel = house.get('valyrian_steel_count', 0)
    for u, qty in army.items():
        if qty <= 0:
            continue
        meta = units_meta.get(u)
        if not meta:
            continue
        unit_def = meta['defense'] * qty
        if steel > 0:
            effects = meta.get('special_effects', {})
            boost_rule = effects.get('valyrian_boost')
            if boost_rule is None:
                if u in ['askar', 'bori']:
                    boost_rule = 'unlimited'
                elif u in ['otliq', 'kamonchi']:
                    boost_rule = 50

            if boost_rule == 'unlimited':
                unit_def += qty * meta['defense']
            elif isinstance(boost_rule, (int, float)) or (isinstance(boost_rule, str) and boost_rule.isdigit()):
                mult = int(boost_rule)
                boosted_qty = min(qty, steel * mult)
                unit_def += boosted_qty * meta['defense']
        score += unit_def
    return score

def resolve_battle_immediately(attacker_id, defender_id, troops_to_send):
    attacker_house = db.get_house(attacker_id)
    defender_house = db.get_house(defender_id)
    defender_army = db.get_house_army(defender_id)
    units_meta = db.load_units_meta()

    atk_score = calculate_side_score(troops_to_send, attacker_house, units_meta)
    def_score = calculate_defender_score(defender_army, defender_house, units_meta)
    def_score += defender_house['wall_health']

    if defender_army.get('afsungar', 0) > 0:
        def_score *= 1.5

    winner = ""
    attacker_wall_breaker = troops_to_send.get('devor_buzuvchi', 0)
    wall_dmg = attacker_wall_breaker * 300
    battle_log = (
        f"⚔️ *URUSH (Lord yo'q bo'lgani uchun avtomatik yakunlandi): "
        f"{attacker_house['house_name']} VS {defender_house['house_name']}*\n\n"
    )

    new_wall_health = defender_house['wall_health']
    attacker_casualties = {}
    defender_casualties = {}

    if atk_score > def_score:
        winner = attacker_id
        loot = int(defender_house['treasury_balance'] * 0.35)
        db.update_house_treasury(defender_id, -loot)
        db.update_house_treasury(attacker_id, loot)
        db.log_transaction(defender_id, attacker_id, loot, "Avtomat Urush O'ljasi")

        new_wall_health = max(0, defender_house['wall_health'] - wall_dmg - 100)
        db.update_wall_hp(defender_id, new_wall_health)
        db.set_house_shield(defender_id, 7)

        surviving_troops = {}
        for u, qty in troops_to_send.items():
            killed = int(qty * 0.15)
            if killed > 0:
                attacker_casualties[u] = killed
            surviving = qty - killed
            if surviving > 0:
                surviving_troops[u] = surviving
        db.add_house_units(attacker_id, surviving_troops)

        db.reduce_army(defender_id, 0.10, defender_casualties)
        if defender_army.get('afsungar', 0) > 0:
            for u, qty in defender_casualties.items():
                saved = int(qty * 0.1)
                if saved > 0:
                    db.add_house_units(defender_id, {u: saved})
                    defender_casualties[u] -= saved

        battle_log += (
            f"🏆 *G'OLIB (Hujumchi):* {attacker_house['house_name']}\n"
            f"💰 Talon-toroj qilingan o'lja: *{loot} tanga*\n"
            f"🧱 Devor HP: *{new_wall_health}/{defender_house['wall_max_health']} HP*\n\n"
        )
    else:
        winner = defender_id
        penalty = int(attacker_house['treasury_balance'] * 0.15)
        db.update_house_treasury(attacker_id, -penalty)
        db.update_house_treasury(defender_id, penalty)
        db.log_transaction(attacker_id, defender_id, penalty, "Avtomat Urush Mag'lubiyati")

        surviving_troops = {}
        total_killed = 0
        atk_keys = list(troops_to_send.keys())
        for u, qty in troops_to_send.items():
            killed = int(qty * 0.30)
            if killed > 0:
                attacker_casualties[u] = killed
            total_killed += killed
        
        if total_killed == 0 and len(atk_keys) > 0:
            first = atk_keys[0]
            if troops_to_send[first] > 0:
                attacker_casualties[first] = 1

        for u, qty in troops_to_send.items():
            killed = attacker_casualties.get(u, 0)
            surviving = qty - killed
            if surviving > 0:
                surviving_troops[u] = surviving
        db.add_house_units(attacker_id, surviving_troops)

        db.reduce_army(defender_id, 0.05, defender_casualties)
        if defender_army.get('afsungar', 0) > 0:
            for u, qty in defender_casualties.items():
                saved = int(qty * 0.1)
                if saved > 0:
                    db.add_house_units(defender_id, {u: saved})
                    defender_casualties[u] -= saved

        battle_log += (
            f"🏆 *G'OLIB (Himoyachi):* {defender_house['house_name']}\n"
            f"💸 Hujumchidan jarima: *{penalty} tanga* g'aznaga olindi.\n\n"
        )

    battle_log += "*Yo'qotishlar (Talofatlar):*\n"
    battle_log += f"🗡️ *{attacker_house['house_name']}* (Hujumchi):\n"
    atk_cas_str = "\n".join([f"  • {u.upper()}: -{qty} ta" for u, qty in attacker_casualties.items() if qty > 0])
    battle_log += (atk_cas_str or "  • Talofatlar yo'q") + "\n"
    battle_log += f"🛡️ *{defender_house['house_name']}* (Himoyachi):\n"
    def_cas_str = "\n".join([f"  • {u.upper()}: -{qty} ta" for u, qty in defender_casualties.items() if qty > 0])
    battle_log += (def_cas_str or "  • Talofatlar yo'q")

    # Log battle record
    battle_id = f"auto_battle_{int(time.time())}"
    db.execute(
        'INSERT INTO battles (battle_id, timestamp, attacker_house, defender_house, attacker_troops_json, winner_house, '
        'attacker_casualties_json, defender_casualties_json, battle_log, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
        (battle_id, datetime.datetime.now().isoformat(), attacker_id, defender_id, json.dumps(troops_to_send), winner,
         json.dumps(attacker_casualties), json.dumps(defender_casualties), battle_log, 'auto_resolved')
    )

    notify_war_result(attacker_id, defender_id, f"⚔️ *URUSH YAKUNLANDI!*\n\n{battle_log}")
    return {'success': True, 'message': "Jang avtomatik yakunlandi!"}

def declare_war(user_id, target_house_id, text_command=None):
    war_state = db.get_setting('war_state', 'open')
    if war_state != 'open':
        return {'success': False, 'message': "⚠️ Urushlar vaqtincha muzlatilgan! Hozir boshqa xonadonga urush e'lon qilib bo'lmaydi."}

    user = db.get_user(user_id)
    if user['role'] not in ['lord', 'king', 'co_admin', 'admin']:
        return {'success': False, 'message': "🚫 Faqat Lord yoki Qirol urush e'lon qilishi mumkin!"}
    if user['house_id'] == target_house_id:
        return {'success': False, 'message': "O'z Xonadoningizga hujum qila olmaysiz!"}

    attacker_id = user['house_id']
    defender_id = target_house_id

    # Check pending battle timeout (10 mins)
    pending_battles = db.query("SELECT * FROM battles WHERE status = 'pending' LIMIT 1")
    if pending_battles:
        pending = pending_battles[0]
        # Parse timestamp
        # In Python:
        # pending['timestamp'] is a string in ISO format
        try:
            battle_time = datetime.datetime.fromisoformat(pending['timestamp'])
        except Exception:
            battle_time = datetime.datetime.now()
        
        elapsed = (datetime.datetime.now() - battle_time).total_seconds()
        if elapsed >= 600:
            resolve_war_decision(ADMIN_TELEGRAM_ID, pending['battle_id'], 'surrender')
        else:
            rem = int(600 - elapsed)
            minutes = rem // 60
            seconds = rem % 60
            return {'success': False, 'message': f"⚠️ Tizimda faol urush ketmoqda! Navbat kuting. Qolgan vaqt: *{minutes} daqiqa {seconds} soniya*"}

    attacker_house = db.get_house(attacker_id)
    defender_house = db.get_house(defender_id)

    if attacker_house['alliance_house_id'] == defender_id:
        return {'success': False, 'message': "⚠️ Siz ittifoqdoshingizga urush e'lon qila olmaysiz! Avval `/ittifoq_buzish` buyrug'i orqali ittifoqni buzing."}

    # Shield Check
    if defender_house['defense_cooldown_until']:
        try:
            cooldown_time = datetime.datetime.fromisoformat(defender_house['defense_cooldown_until'])
        except Exception:
            cooldown_time = datetime.datetime.now()
        
        if cooldown_time > datetime.datetime.now():
            diff = cooldown_time - datetime.datetime.now()
            days = diff.days
            hours = (diff.seconds // 3600)
            minutes = (diff.seconds % 3600) // 60
            cooldown_str = ""
            if days > 0:
                cooldown_str += f"{days} kun "
            if hours > 0:
                cooldown_str += f"{hours} soat "
            cooldown_str += f"{minutes} daqiqa"
            return {'success': False, 'message': f"⚠️ Dushman xonadoni hozirda mudofaa qalqoni ostida! Qalqon tugashiga: *{cooldown_str}* qoldi."}

    units_meta = db.load_units_meta()
    troops_to_send = {}
    specified_troops = False

    if text_command:
        parts = text_command.strip().split()
        i = 2
        while i < len(parts):
            u_id = parts[i].lower().strip()
            if i + 1 >= len(parts):
                break
            try:
                qty = int(parts[i+1])
            except ValueError:
                qty = 0
            if u_id and qty > 0:
                troops_to_send[u_id] = troops_to_send.get(u_id, 0) + qty
                specified_troops = True
            i += 2

    if not specified_troops:
        attacker_army = db.get_house_army(attacker_id)
        for u, q in attacker_army.items():
            if q > 0:
                troops_to_send[u] = q

    has_troops = False
    for u, q in troops_to_send.items():
        if q > 0:
            has_troops = True
            if u not in units_meta:
                return {'success': False, 'message': f"⚠️ Noto'g'ri qo'shin turi kiritildi: *{u}*."}

    if not has_troops:
        return {'success': False, 'message': "⚠️ Hujum qilish uchun sizda kamida bitta askar bo'lishi shart!"}

    attacker_army = db.get_house_army(attacker_id)
    for u, q in troops_to_send.items():
        if attacker_army.get(u, 0) < q:
            return {'success': False, 'message': f"⚠️ Sizda yetarli miqdorda *{u.upper()}* yo'q! Balans: *{attacker_army.get(u, 0)}*"}

    db.deduct_house_units(attacker_id, troops_to_send)

    defender_lord_id = defender_house['lord_id'].strip() if defender_house['lord_id'] else "0"
    if defender_lord_id == "0" or defender_lord_id == "":
        return resolve_battle_immediately(attacker_id, defender_id, troops_to_send)

    battle_id = f"battle_{int(time.time()*1000)}"
    db.execute(
        'INSERT INTO battles (battle_id, timestamp, attacker_house, defender_house, attacker_troops_json, status) '
        'VALUES (%s, %s, %s, %s, %s, %s)',
        (battle_id, datetime.datetime.now().isoformat(), attacker_id, defender_id, json.dumps(troops_to_send), 'pending')
    )

    msg_text = (
        f"⚔️ *XONADONINGIZGA HUJUM BOSHLAHDAN OGOHLANTIRISH!* ⚔️\n\n"
        f"*{attacker_house['house_name']}* xonadoni sizning xonadoningizga qarshi urush boshladi!\n\n"
        f"*Hujumchi kuchlari:*\n"
        + "\n".join([f"• {u.upper()}: *{qty} ta*" for u, qty in troops_to_send.items() if qty > 0]) + "\n\n"
        f"Lord sifatida sizda 2 ta tanlov bor:\n"
        f"1️⃣ *Jang qilish* — Xonadoningiz bor kuchi va devorlari bilan himoyalanadi.\n"
        f"2️⃣ *Taslim bo'lish* — Xonadon g'aznasining 20% qismi raqibga o'tadi va jang bo'lmaydi."
    )

    reply_markup = types.InlineKeyboardMarkup()
    reply_markup.add(
        types.InlineKeyboardButton("⚔️ Jang qilish", callback_data=f"cb_war_decision:{battle_id}:fight"),
        types.InlineKeyboardButton("🏳️ Taslim bo'lish", callback_data=f"cb_war_decision:{battle_id}:surrender")
    )

    send_telegram_message(defender_lord_id, msg_text, reply_markup)
    if defender_house['group_chat_id']:
        send_telegram_message(defender_house['group_chat_id'], msg_text, reply_markup)

    # Defender ally alert
    if defender_house['alliance_house_id']:
        defender_ally = db.get_house(defender_house['alliance_house_id'])
        if defender_ally and defender_ally['lord_id'] and defender_ally['lord_id'] != '0':
            ally_msg = (
                f"🛡️ *ITTIFOQDOSHINGIZ HUJUMGA UCHRADI!* 🛡️\n\n"
                f"*{attacker_house['house_name']}* xonadoni sizning ittifoqdoshingiz *{defender_house['house_name']}* ga hujum qildi!\n\n"
                f"Lord sifatida siz jangga yordam berish uchun mudofaa qo'shini yuborishingiz mumkin."
            )
            ally_markup = types.InlineKeyboardMarkup()
            ally_markup.add(types.InlineKeyboardButton("🛡️ Mudofaaga yordam berish", callback_data=f"cb_war_help_prompt:{battle_id}:defender"))
            send_telegram_message(defender_ally['lord_id'], ally_msg, ally_markup)
            if defender_ally['group_chat_id']:
                send_telegram_message(defender_ally['group_chat_id'], ally_msg, ally_markup)

    # Attacker notification
    attacker_msg = (
        f"⚔️ *URUSH E'LON QILINDI!* ⚔️\n\n"
        f"*{defender_house['house_name']}* xonadoniga urush e'lon qilindi! Dushman Lordining qarorini kutamiz.\n\n"
        f"*Yuborilgan qo'shinlar:*\n"
        + "\n".join([f"• {u.upper()}: *{qty} ta*" for u, qty in troops_to_send.items() if qty > 0])
    )
    send_telegram_message(user_id, attacker_msg)
    if attacker_house['group_chat_id']:
        send_telegram_message(attacker_house['group_chat_id'], attacker_msg)

    # Attacker ally alert
    if attacker_house['alliance_house_id']:
        attacker_ally = db.get_house(attacker_house['alliance_house_id'])
        if attacker_ally and attacker_ally['lord_id'] and attacker_ally['lord_id'] != '0':
            ally_msg = (
                f"🗡️ *ITTIFOQDOSHINGIZ URUSH BOSHLADI!* 🗡️\n\n"
                f"*{attacker_house['house_name']}* xonadoni *{defender_house['house_name']}* ga urush e'lon qildi!\n\n"
                f"Lord sifatida siz jangga yordam berish uchun hujum qo'shini yuborishingiz mumkin."
            )
            ally_markup = types.InlineKeyboardMarkup()
            ally_markup.add(types.InlineKeyboardButton("🗡️ Hujumga yordam berish", callback_data=f"cb_war_help_prompt:{battle_id}:attacker"))
            send_telegram_message(attacker_ally['lord_id'], ally_msg, ally_markup)
            if attacker_ally['group_chat_id']:
                send_telegram_message(attacker_ally['group_chat_id'], ally_msg, ally_markup)

    return {'success': True, 'message': "⚔️ Urush e'lon qilindi! Dushman Lordining qarori kutilmoqda."}

def notify_war_result(attacker_id, defender_id, text, reply_markup=None):
    # Sends to both house lords and groups
    attacker = db.get_house(attacker_id)
    defender = db.get_house(defender_id)
    
    if attacker and attacker['lord_id'] and attacker['lord_id'] != '0':
        send_telegram_message(attacker['lord_id'], text, reply_markup)
    if attacker and attacker['group_chat_id']:
        send_telegram_message(attacker['group_chat_id'], text, reply_markup)

    if defender and defender['lord_id'] and defender['lord_id'] != '0':
        send_telegram_message(defender['lord_id'], text, reply_markup)
    if defender and defender['group_chat_id']:
        send_telegram_message(defender['group_chat_id'], text, reply_markup)

    general_chat_id = db.get_setting('general_chat_id')
    if general_chat_id:
        send_telegram_message(general_chat_id, text, reply_markup)

def resolve_war_decision(user_id, battle_id, decision):
    battle = db.get_battle_record(battle_id)
    if not battle:
        return {'success': False, 'message': "Urush topilmadi!"}
    if battle['status'] != 'pending':
        return {'success': False, 'message': f"Bu urush allaqachon yakunlangan! Holat: {battle['status']}"}

    clicker = db.get_user(user_id)
    is_clicker_admin = (str(user_id) == str(ADMIN_TELEGRAM_ID)) or (clicker and clicker['role'] == 'admin')
    defender_id = battle['defender_house']

    if not is_clicker_admin and (not clicker or clicker['house_id'] != defender_id or clicker['role'] not in ['lord', 'king', 'co_admin']):
        return {'success': False, 'message': "Sizda ushbu qarorni qabul qilish uchun ruxsat yo'q!"}

    attacker_id = battle['attacker_house']
    attacker_house = db.get_house(attacker_id)
    defender_house = db.get_house(defender_id)
    sent_troops = json.loads(battle['attacker_troops_json'])

    if decision == 'surrender':
        loot = int(defender_house['treasury_balance'] * 0.20)
        db.update_house_treasury(defender_id, -loot)
        db.update_house_treasury(attacker_id, loot)
        db.log_transaction(defender_id, attacker_id, loot, "Urushda taslim bo'lish")
        
        db.add_house_units(attacker_id, sent_troops)

        battle_log = (
            f"🏳️ *TASLIM BO'LISH!* 🏳️\n\n"
            f"*{defender_house['house_name']}* xonadoni *{attacker_house['house_name']}* xonadoniga taslim bo'ldi!\n\n"
            f"💰 O'lja: *{loot} tanga* (Himoyachi g'aznasining 20% qismi Hujumchiga o'tdi).\n"
            f"🗡️ Hujumchining barcha qo'shinlari talofatsiz o'z xonadoniga qaytdi."
        )

        db.update_battle_record(battle_id, {
            'winner_house': attacker_id,
            'attacker_casualties_json': {},
            'defender_casualties_json': {},
            'battle_log': battle_log,
            'status': 'surrendered'
        })

        db.set_house_shield(defender_id, 7)
        notify_war_result(attacker_id, defender_id, f"⚔️ *URUSH YAKUNLANDI!*\n\n{battle_log}")
        return {'success': True, 'message': f"Siz taslim bo'lishni tanladingiz. G'aznadan *{loot} tanga* yechildi va raqibga berildi."}

    elif decision == 'fight':
        defender_army = db.get_house_army(defender_id)
        units_meta = db.load_units_meta()

        attacker_ally_id = battle['attacker_ally_house']
        attacker_ally_house = db.get_house(attacker_ally_id) if attacker_ally_id else None
        attacker_ally_troops = {}
        if battle['attacker_ally_troops_json']:
            try:
                attacker_ally_troops = json.loads(battle['attacker_ally_troops_json'])
            except Exception:
                pass

        defender_ally_id = battle['defender_ally_house']
        defender_ally_house = db.get_house(defender_ally_id) if defender_ally_id else None
        defender_ally_troops = {}
        if battle['defender_ally_troops_json']:
            try:
                defender_ally_troops = json.loads(battle['defender_ally_troops_json'])
            except Exception:
                pass

        # Calculate Scores
        atk_score = calculate_side_score(sent_troops, attacker_house, units_meta)
        if attacker_ally_house:
            atk_score += calculate_side_score(attacker_ally_troops, attacker_ally_house, units_meta)

        def_score = calculate_defender_score(defender_army, defender_house, units_meta)
        if defender_ally_house:
            def_score += calculate_defender_score(defender_ally_troops, defender_ally_house, units_meta)
        def_score += defender_house['wall_health']

        has_wizard = (defender_army.get('afsungar', 0) > 0) or (defender_ally_troops.get('afsungar', 0) > 0)
        if has_wizard:
            def_score *= 1.5

        winner = ''
        wall_dmg = sent_troops.get('devor_buzuvchi', 0) * 300
        if attacker_ally_house:
            wall_dmg += attacker_ally_troops.get('devor_buzuvchi', 0) * 300

        battle_log = f"⚔️ *URUSH NATIJASI: {attacker_house['house_name']} VS {defender_house['house_name']}*\n\n"
        if attacker_ally_house:
            battle_log += f"🤝 Hujumchi Ittifoqchisi: *{attacker_ally_house['house_name']}*\n"
        if defender_ally_house:
            battle_log += f"🤝 Himoyachi Ittifoqchisi: *{defender_ally_house['house_name']}*\n\n"

        loot = 0
        penalty = 0
        new_wall_health = defender_house['wall_health']
        
        attacker_casualties = {}
        attacker_ally_casualties = {}
        defender_casualties = {}
        defender_ally_casualties = {}

        if atk_score > def_score:
            winner = attacker_id
            loot = int(defender_house['treasury_balance'] * 0.35)

            if attacker_ally_house:
                share1 = loot // 2
                share2 = loot - share1
                db.update_house_treasury(attacker_id, share1)
                db.update_house_treasury(attacker_ally_id, share2)
                db.log_transaction(defender_id, attacker_id, share1, "Urush O'ljasi (Hujumchi)")
                db.log_transaction(defender_id, attacker_ally_id, share2, "Urush O'ljasi (Ittifoqdosh)")
            else:
                db.update_house_treasury(attacker_id, loot)
                db.log_transaction(defender_id, attacker_id, loot, "Urush O'ljasi")
            db.update_house_treasury(defender_id, -loot)

            new_wall_health = max(0, defender_house['wall_health'] - wall_dmg - 100)
            db.update_wall_hp(defender_id, new_wall_health)
            db.set_house_shield(defender_id, 7)

            # Attacker casualties & survivors
            surviving_troops = {}
            for u, qty in sent_troops.items():
                killed = int(qty * 0.15)
                if killed > 0:
                    attacker_casualties[u] = killed
                survivors = qty - killed
                if survivors > 0:
                    surviving_troops[u] = survivors
            db.add_house_units(attacker_id, surviving_troops)

            # Attacker Ally casualties & survivors
            if attacker_ally_house:
                surviving_ally_troops = {}
                for u, qty in attacker_ally_troops.items():
                    killed = int(qty * 0.15)
                    if killed > 0:
                        attacker_ally_casualties[u] = killed
                    survivors = qty - killed
                    if survivors > 0:
                        surviving_ally_troops[u] = survivors
                db.add_house_units(attacker_ally_id, surviving_ally_troops)

            # Defender standing casualties
            db.reduce_army(defender_id, 0.10, defender_casualties)
            if defender_army.get('afsungar', 0) > 0:
                for u, qty in defender_casualties.items():
                    saved = int(qty * 0.1)
                    if saved > 0:
                        db.add_house_units(defender_id, {u: saved})
                        defender_casualties[u] -= saved

            # Defender Ally casualties
            if defender_ally_house:
                surviving_def_ally_troops = {}
                for u, qty in defender_ally_troops.items():
                    killed = int(qty * 0.10)
                    if killed > 0:
                        defender_ally_casualties[u] = killed
                    survivors = qty - killed
                    if survivors > 0:
                        surviving_def_ally_troops[u] = survivors
                if defender_ally_troops.get('afsungar', 0) > 0:
                    for u, qty in defender_ally_casualties.items():
                        saved = int(qty * 0.1)
                        if saved > 0:
                            surviving_def_ally_troops[u] = surviving_def_ally_troops.get(u, 0) + saved
                            defender_ally_casualties[u] -= saved
                db.add_house_units(defender_ally_id, surviving_def_ally_troops)

            battle_log += (
                f"🏆 *G'OLIB (Hujumchi):* {attacker_house['house_name']}\n"
                f"💰 Talon-toroj qilingan o'lja: *{loot} tanga* (Xonadonlar g'aznasiga o'tkazildi).\n"
                f"🧱 Dushman devori holati: *{new_wall_health}/{defender_house['wall_max_health']} HP*\n\n"
            )
        else:
            winner = defender_id
            penalty = int(attacker_house['treasury_balance'] * 0.15)

            if attacker_ally_house:
                pen1 = penalty // 2
                pen2 = penalty - pen1
                db.update_house_treasury(attacker_id, -pen1)
                db.update_house_treasury(attacker_ally_id, -pen2)
                db.log_transaction(attacker_id, defender_id, pen1, "Urush Jarimasi (Hujumchi)")
                db.log_transaction(attacker_ally_id, defender_id, pen2, "Urush Jarimasi (Ittifoqdosh)")
            else:
                db.update_house_treasury(attacker_id, -penalty)
                db.log_transaction(attacker_id, defender_id, penalty, "Urush Jarimasi")

            # Penalty split for defender
            if defender_ally_house:
                share1 = penalty // 2
                share2 = penalty - share1
                db.update_house_treasury(defender_id, share1)
                db.update_house_treasury(defender_ally_id, share2)
            else:
                db.update_house_treasury(defender_id, penalty)

            # Attacker casualties & survivors (loser constraint: at least 1 dies)
            surviving_troops = {}
            total_atk_killed = 0
            atk_keys = list(sent_troops.keys())
            for u, qty in sent_troops.items():
                killed = int(qty * 0.30)
                if killed > 0:
                    attacker_casualties[u] = killed
                total_atk_killed += killed
            
            if total_atk_killed == 0 and len(atk_keys) > 0:
                first = atk_keys[0]
                if sent_troops[first] > 0:
                    attacker_casualties[first] = 1

            for u, qty in sent_troops.items():
                killed = attacker_casualties.get(u, 0)
                survivors = qty - killed
                if survivors > 0:
                    surviving_troops[u] = survivors
            db.add_house_units(attacker_id, surviving_troops)

            # Attacker Ally casualties & survivors
            if attacker_ally_house:
                surviving_ally_troops = {}
                total_ally_killed = 0
                ally_keys = list(attacker_ally_troops.keys())
                for u, qty in attacker_ally_troops.items():
                    killed = int(qty * 0.30)
                    if killed > 0:
                        attacker_ally_casualties[u] = killed
                    total_ally_killed += killed
                
                if total_ally_killed == 0 and len(ally_keys) > 0:
                    first = ally_keys[0]
                    if attacker_ally_troops[first] > 0:
                        attacker_ally_casualties[first] = 1

                for u, qty in attacker_ally_troops.items():
                    killed = attacker_ally_casualties.get(u, 0)
                    survivors = qty - killed
                    if survivors > 0:
                        surviving_ally_troops[u] = survivors
                db.add_house_units(attacker_ally_id, surviving_ally_troops)

            # Defender standing casualties
            db.reduce_army(defender_id, 0.05, defender_casualties)
            if defender_army.get('afsungar', 0) > 0:
                for u, qty in defender_casualties.items():
                    saved = int(qty * 0.1)
                    if saved > 0:
                        db.add_house_units(defender_id, {u: saved})
                        defender_casualties[u] -= saved

            # Defender Ally casualties
            if defender_ally_house:
                surviving_def_ally_troops = {}
                for u, qty in defender_ally_troops.items():
                    killed = int(qty * 0.05)
                    if killed > 0:
                        defender_ally_casualties[u] = killed
                    survivors = qty - killed
                    if survivors > 0:
                        surviving_def_ally_troops[u] = survivors
                if defender_ally_troops.get('afsungar', 0) > 0:
                    for u, qty in defender_ally_casualties.items():
                        saved = int(qty * 0.1)
                        if saved > 0:
                            surviving_def_ally_troops[u] = surviving_def_ally_troops.get(u, 0) + saved
                            defender_ally_casualties[u] -= saved
                db.add_house_units(defender_ally_id, surviving_def_ally_troops)

            battle_log += (
                f"🏆 *HIMOYA MUVAFFAQIYATLI! G'olib:* {defender_house['house_name']}\n"
                f"💸 Hujumchidan jarima: *{penalty} tanga* g'aznaga olindi.\n\n"
            )

        battle_log += "*Yo'qotishlar (Talofatlar):*\n"
        battle_log += f"🗡️ *{attacker_house['house_name']}* (Hujumchi):\n"
        atk_cas = [f"  • {u.upper()}: -{q} ta" for u, q in attacker_casualties.items() if q > 0]
        battle_log += ("\n".join(atk_cas) if atk_cas else "  • Talofatlar yo'q") + "\n"

        if attacker_ally_house:
            battle_log += f"🤝 *{attacker_ally_house['house_name']}* (Hujumchi Ittifoqdoshi):\n"
            ally_cas = [f"  • {u.upper()}: -{q} ta" for u, q in attacker_ally_casualties.items() if q > 0]
            battle_log += ("\n".join(ally_cas) if ally_cas else "  • Talofatlar yo'q") + "\n"

        battle_log += f"🛡️ *{defender_house['house_name']}* (Himoyachi):\n"
        def_cas = [f"  • {u.upper()}: -{q} ta" for u, q in defender_casualties.items() if q > 0]
        battle_log += ("\n".join(def_cas) if def_cas else "  • Talofatlar yo'q") + "\n"

        if defender_ally_house:
            battle_log += f"🤝 *{defender_ally_house['house_name']}* (Himoyachi Ittifoqdoshi):\n"
            ally_cas = [f"  • {u.upper()}: -{q} ta" for u, q in defender_ally_casualties.items() if q > 0]
            battle_log += ("\n".join(ally_cas) if ally_cas else "  • Talofatlar yo'q")

        db.update_battle_record(battle_id, {
            'winner_house': winner,
            'attacker_casualties_json': attacker_casualties,
            'defender_casualties_json': defender_casualties,
            'battle_log': battle_log,
            'status': 'resolved'
        })

        notify_war_result(attacker_id, defender_id, f"⚔️ *URUSH YAKUNLANDI!*\n\n{battle_log}")
        return {'success': True, 'message': "Jang muvaffaqiyatli yakunlandi! Natija guruhlarga yuborildi."}

    return {'success': False, 'message': "Noto'g'ri qaror!"}

# Admin Commands logic
def distribute_bonus_global(admin_id, amount):
    user = db.get_user(admin_id)
    if not user or user['role'] not in ['admin', 'banker']:
        return {'success': False, 'message': "Ruxsat yo'q!"}
    if amount <= 0:
        return {'success': False, 'message': "Noto'g'ri bonus miqdori!"}

    players = db.query("SELECT telegram_id FROM users WHERE role != 'admin'")
    count = 0

    bonus_kb = types.InlineKeyboardMarkup()
    bonus_kb.add(
        types.InlineKeyboardButton("✅ Qabul qilish", callback_data=f"cb_bonus_action:accept:{amount}"),
        types.InlineKeyboardButton("❌ Rad etish", callback_data=f"cb_bonus_action:reject:{amount}")
    )

    for p in players:
        send_telegram_message(p['telegram_id'], f"🎁 *Sizga bonus taklif qilindi!* 🎁\n\nBanker/Admin sizga *{amount} tanga* bonus taklif qildi. Qabul qilasizmi?", bonus_kb)
        count += 1
    return {'success': True, 'message': f"✅ Barcha {count} ta o'yinchiga {amount} tangalik bonus taklifi yuborildi!"}

def admin_distribute_bonus(admin_id, text):
    user = db.get_user(admin_id)
    if not user or user['role'] not in ['admin', 'co_admin', 'banker']:
        return {'success': False, 'message': "Ruxsat yo'q!"}

    clean_text = text.replace('/bonus', '', 1).strip()
    if not clean_text:
        return {
            'success': False,
            'message': "👑 *Bonus tarqatish paneli:*\n\nFormat:\n`/bonus <miqdor>\n@username1\n@username2`\n\nYoki barcha uchun:\n`/bonus <miqdor> @all`"
        }

    lines = clean_text.split('\n')
    parts = lines[0].strip().split()
    try:
        amount = float(parts[0])
    except ValueError:
        return {'success': False, 'message': "⚠️ Noto'g'ri bonus miqdori! Iltimos, musbat son yozing."}

    if amount <= 0:
        return {'success': False, 'message': "⚠️ Noto'g'ri bonus miqdori! Iltimos, musbat son yozing."}

    targets = []
    all_text = clean_text[len(parts[0]):].strip()
    
    is_all = '@all' in all_text.lower()
    if not is_all:
        import re
        matches = re.findall(r'@([a-zA-Z0-9_]+)', all_text)
        for m in matches:
            targets.append(m.lower())
        for line in lines[1:]:
            matches_line = re.findall(r'@([a-zA-Z0-9_]+)', line)
            for m in matches_line:
                u_name = m.lower()
                if u_name not in targets:
                    targets.append(u_name)

    bonus_kb = types.InlineKeyboardMarkup()
    bonus_kb.add(
        types.InlineKeyboardButton("✅ Qabul qilish", callback_data=f"cb_bonus_action:accept:{amount}"),
        types.InlineKeyboardButton("❌ Rad etish", callback_data=f"cb_bonus_action:reject:{amount}")
    )

    players = db.query('SELECT telegram_id, username, role FROM users')

    if is_all:
        count = 0
        for p in players:
            if p['role'] == 'admin':
                continue
            send_telegram_message(p['telegram_id'], f"🎁 *Sizga bonus taklif qilindi!* 🎁\n\nBanker/Admin sizga *{amount} tanga* bonus taklif qildi. Qabul qilasizmi?", bonus_kb)
            count += 1
        return {'success': True, 'message': f"✅ Barcha {count} ta o'yinchiga {amount} tangalik bonus taklifi yuborildi!"}
    else:
        count = 0
        not_found = []
        user_row_map = {}
        for p in players:
            if p['username']:
                user_row_map[p['username'].lower().replace('@', '')] = p

        for username in targets:
            target_user = user_row_map.get(username)
            if target_user:
                if target_user['role'] == 'admin':
                    continue
                send_telegram_message(target_user['telegram_id'], f"🎁 *Sizga shaxsiy bonus taklif qilindi!* 🎁\n\nBanker/Admin sizga *{amount} tanga* bonus taklif qildi. Qabul qilasizmi?", bonus_kb)
                count += 1
            else:
                not_found.append(f"@{username}")

        msg = f"✅ {count} ta foydalanuvchiga {amount} tangalik bonus taklifi yuborildi."
        if not_found:
            msg += f"\n⚠️ Quyidagi foydalanuvchilar botdan ro'yxatdan o'tmagan yoki topilmadi: {', '.join(not_found)}"
        return {'success': True, 'message': msg}

def add_coins_admin(admin_id, target_id, amount):
    user = db.get_user(admin_id)
    if not user or user['role'] != 'admin':
        return {'success': False, 'message': "Ruxsat yo'q!"}

    target = db.get_user(target_id)
    if not target:
        return {'success': False, 'message': "Foydalanuvchi topilmadi!"}

    db.execute('UPDATE users SET wallet_balance = wallet_balance + %s WHERE telegram_id = %s', (amount, str(target_id)))
    send_telegram_message(target_id, f"👑 *Tizim Bonusi!*\nBalansingizga *{amount}* tanga kiritildi!")
    return {'success': True, 'message': f"{target_id} hamyoniga {amount} tanga qo'shildi!"}

def grant_role(admin_id, target_id, role, house_id=None):
    user = db.get_user(admin_id)
    if not user or user['role'] not in ['admin', 'co_admin']:
        return {'success': False, 'message': "Faqat Bosh Admin va Co-Admin ruxsati bor!"}

    valid_roles = ["lord", "citizen", "co_admin", "king", "admin", "banker", "muhbir"]
    if role not in valid_roles:
        return {'success': False, 'message': f"Noto'g'ri rol! Valid rollar: {', '.join(valid_roles)}"}

    target = db.get_user(target_id)
    if not target:
        return {'success': False, 'message': "Foydalanuvchi topilmadi!"}

    db.execute('UPDATE users SET role = %s WHERE telegram_id = %s', (role, str(target_id)))
    if house_id:
        db.execute('UPDATE users SET house_id = %s WHERE telegram_id = %s', (house_id, str(target_id)))
    if role == 'lord' and house_id:
        db.execute('UPDATE houses SET lord_id = %s WHERE house_id = %s', (str(target_id), house_id))

    send_telegram_message(target_id, f"👑 *Sizga yangi vazifa yuklatildi!*\nRolingiz: *{role.upper()}*")
    return {'success': True, 'message': "Muvaffaqiyatli biriktirildi!"}

# Daily checkin & cycle
def process_daily_checkin(user_id):
    user = db.get_user(user_id)
    if user and user['role'] == 'admin':
        return {'success': False, 'message': "⚠️ Admin kunlik bonus ola olmaydi!"}

    today = datetime.date.today().isoformat()
    if user['last_checkin'] == today:
        return {'success': False, 'message': "⚠️ Bugungi kunlik bonusni olgansiz!"}

    db.execute(
        'UPDATE users SET wallet_balance = wallet_balance + 65, last_checkin = %s, '
        'casino_spins_left = 3, last_casino_spin_date = %s WHERE telegram_id = %s',
        (today, today, str(user_id))
    )
    db.log_transaction("SYSTEM", user_id, 65, "Daily Check-in bonus")
    return {'success': True, 'message': "🎉 +65 tanga kunlik bonus berildi! Kazino aylanmalari (3 ta imkoniyat) tiklandi."}

def process_donation(user_id, amount):
    if amount <= 0:
        return {'success': False, 'message': "Noto'g'ri miqdor!"}

    user = db.get_user(user_id)
    if not user:
        return {'success': False, 'message': "User not found"}
    if user['wallet_balance'] < amount:
        return {'success': False, 'message': "Mablag' yetarli emas!"}

    db.execute('UPDATE users SET wallet_balance = wallet_balance - %s WHERE telegram_id = %s', (amount, str(user_id)))
    db.update_house_treasury(user['house_id'], amount)
    db.log_transaction(user_id, user['house_id'], amount, "Qishloq G'aznasiga Xayriya")

    return {'success': True, 'message': "🏰 Xayriya muvaffaqiyatli amalga oshirildi!"}

def process_set_tax(user_id, rate):
    user = db.get_user(user_id)
    if user['role'] not in ['lord', 'admin']:
        return {'success': False, 'message': "Faqat Lord ruxsati bor!"}
    if rate < 0.0 or rate > 0.3:
        return {'success': False, 'message': "Soliq stavkasi 0% va 30% oralig'ida bo'lishi kerak!"}

    db.execute('UPDATE houses SET tax_rate = %s WHERE house_id = %s', (rate, user['house_id']))
    return {'success': True, 'message': f"📈 Soliq stavkasi {rate * 100:.1f}% qilib belgilandi!"}

def process_loan_request(user_id, amount):
    user = db.get_user(user_id)
    if user['role'] not in ['lord', 'king', 'co_admin', 'admin']:
        return {'success': False, 'message': "🚫 Kredit so'rash huquqi faqat Lord, Qirol va Adminlarga tegishli!"}
    if amount < 100 or amount > 500:
        return {'success': False, 'message': "💸 Kredit miqdori minimum 100 va maksimum 500 tanga bo'lishi kerak!"}

    loan_id = f"loan_{int(time.time()*1000)}"
    db.execute(
        'INSERT INTO loans (loan_id, house_id, amount, status, requested_at) VALUES (%s, %s, %s, %s, %s)',
        (loan_id, user['house_id'], amount, 'pending', datetime.datetime.now().isoformat())
    )
    
    notify_banker(f"🏦 Xonadon *{user['house_id'].upper()}* bankdan *{amount}* tanga qarz so'ramoqda (Ustama bilan qaytariladigan summa: *{amount * 1.3:.1f}* tanga).")
    return {'success': True, 'message': "🏦 Kredit so'rovi yuborildi. Admin tasdiqini kuting."}

def process_loan_repay(user_id, amount):
    if amount <= 0:
        return {'success': False, 'message': "⚠️ Noto'g'ri miqdor kiritildi!"}

    user = db.get_user(user_id)
    if user['role'] not in ['lord', 'king', 'co_admin', 'admin']:
        return {'success': False, 'message': "🚫 Kreditni qaytarish huquqi faqat Lord, Qirol va Adminlarga tegishli!"}

    house_id = user['house_id']
    house = db.get_house(house_id)
    if not house or house_id == 'admin':
        return {'success': False, 'message': "⚠️ Siz ma'lum bir xonadonga biriktirilmagansiz!"}

    if house['treasury_balance'] < amount:
        return {'success': False, 'message': f"💸 Xonadon g'aznasida yetarli pul yo'q! G'azna balansi: {house['treasury_balance']}"}

    loans = db.query("SELECT * FROM loans WHERE house_id = %s AND status = 'approved' ORDER BY requested_at ASC", (house_id,))
    total_paid = 0.0
    remaining_to_pay = amount

    for l in loans:
        loan_debt = float(l['amount'])
        if loan_debt <= 0:
            continue

        if remaining_to_pay >= loan_debt:
            remaining_to_pay -= loan_debt
            db.execute("UPDATE loans SET amount = 0, status = 'repaid' WHERE loan_id = %s", (l['loan_id'],))
            total_paid += loan_debt
        else:
            new_debt = loan_debt - remaining_to_pay
            db.execute("UPDATE loans SET amount = %s WHERE loan_id = %s", (new_debt, l['loan_id'],))
            total_paid += remaining_to_pay
            remaining_to_pay = 0
            break

    if total_paid == 0:
        return {'success': False, 'message': "⚠️ Sizning xonadoningizda faol (to'lanmagan) kreditlar mavjud emas!"}

    db.update_house_treasury(house_id, -total_paid)
    db.execute('UPDATE bank_treasury SET total_bank_coins = total_bank_coins + %s LIMIT 1', (total_paid,))
    db.log_transaction(house_id, 'BANK', total_paid, "Kredit to'lash")

    return {'success': True, 'message': f"✅ Kredit muvaffaqiyatli to'landi! Qaytarilgan summa: *{total_paid}* tanga."}

def process_daily_cycle(admin_id):
    user = db.get_user(admin_id)
    if not user or user['role'] not in ['admin', 'co_admin']:
        return {'success': False, 'message': "Ruxsat yo'q!"}

    # 1. Distribute wages to houses
    db.execute("UPDATE houses SET treasury_balance = treasury_balance + 65.0 WHERE house_id != 'admin'")
    
    # 2. Get king id and pay wage
    king_row = db.query_one("SELECT telegram_id FROM users WHERE role = 'king' LIMIT 1")
    king_id = king_row['telegram_id'] if king_row else None
    
    if king_id:
        db.execute("UPDATE users SET wallet_balance = wallet_balance + 117.0 WHERE telegram_id = %s", (king_id,))
        db.log_transaction("SYSTEM", king_id, 117.0, "Qirol maoshi")

    # 3. Soliq yig'ish (tax collect)
    houses = db.query("SELECT * FROM houses WHERE house_id != 'admin'")
    tax_logs = []
    
    for h in houses:
        bal = h['treasury_balance']
        tax_rate = h['tax_rate']
        tax_amt = int(bal * tax_rate)
        if tax_amt > 0:
            db.update_house_treasury(h['house_id'], -tax_amt)
            if king_id:
                db.execute("UPDATE users SET wallet_balance = wallet_balance + %s WHERE telegram_id = %s", (tax_amt, king_id))
                db.log_transaction(h['house_id'], king_id, tax_amt, f"Qirollik solig'i ({h['house_id']})")
                tax_logs.append(f"• {h['house_name']}: -{tax_amt} {h['currency_symbol']} ({tax_rate*100:.1f}%)")
            else:
                db.execute("UPDATE bank_treasury SET total_bank_coins = total_bank_coins + %s LIMIT 1", (tax_amt,))
                db.log_transaction(h['house_id'], "BANK", tax_amt, f"Qirollik solig'i (Qirol yo'q, Bankka o'tdi)")
                tax_logs.append(f"• {h['house_name']}: -{tax_amt} {h['currency_symbol']} (Qirol yo'q, Bankka)")
                
    tax_str = "\n".join(tax_logs) if tax_logs else "• Soliq yig'ilmadi (Gaznalar bo'sh)."
    
    report = (
        f"👑 *KUNLIK DOIRA HISOBOTI (DAILY CYCLE)* 👑\n\n"
        f"✅ Barcha xonadonlar g'aznasiga *+65 tanga* maosh qo'shildi!\n"
        f"👑 Qirolga *+117 tanga* kunlik maosh berildi!\n\n"
        f"*Yig'ilgan Qirollik soliqlari:*\n{tax_str}"
    )
    
    notify_global(report)
    return {'success': True, 'message': "Kunlik davr yakunlandi va hisobot guruhlarga yuborildi."}

def approve_loan(admin_id, loan_id, approve):
    user = db.get_user(admin_id)
    if not user or user['role'] not in ['admin', 'co_admin', 'banker']:
        return {'success': False, 'message': "Ruxsat yo'q!"}

    loan = db.query_one("SELECT * FROM loans WHERE loan_id = %s", (loan_id,))
    if not loan:
        return {'success': False, 'message': "Kredit so'rovi topilmadi!"}
    if loan['status'] != 'pending':
        return {'success': False, 'message': "Bu so'rov allaqachon bajarilgan!"}

    house_id = loan['house_id']
    amount = float(loan['amount'])
    
    if approve:
        # Check Temir Bank Treasury
        bt_row = db.query_one("SELECT total_bank_coins FROM bank_treasury LIMIT 1")
        bank_coins = float(bt_row['total_bank_coins']) if bt_row else 10000.0
        
        if bank_coins < amount:
            return {'success': False, 'message': f"💸 Temir Bank g'aznasida yetarli tanga yo'q! Baza balansi: {bank_coins}"}

        db.execute("UPDATE loans SET status = 'approved', approved_at = %s WHERE loan_id = %s", (datetime.datetime.now().isoformat(), loan_id))
        db.update_house_treasury(house_id, amount)
        db.execute('UPDATE bank_treasury SET total_bank_coins = total_bank_coins - %s LIMIT 1', (amount,))
        db.log_transaction("BANK", house_id, amount, "Kredit ajratish")
        
        lord_msg = f"🏦 *Kreditingiz tasdiqlandi!* 🏦\n\nXonadoningiz g'aznasiga *{amount}* tanga qo'shildi!"
        # Notify Lord
        house = db.get_house(house_id)
        if house['lord_id'] and house['lord_id'] != '0':
            send_telegram_message(house['lord_id'], lord_msg)
        if house['group_chat_id']:
            send_telegram_message(house['group_chat_id'], lord_msg)
            
        return {'success': True, 'message': f"✅ Kredit tasdiqlandi. G'aznaga {amount} tanga o'tkazildi."}
    else:
        db.execute("UPDATE loans SET status = 'rejected' WHERE loan_id = %s", (loan_id,))
        lord_msg = f"❌ *Kredit so'rovingiz rad etildi!* ❌\n\nMiqdor: {amount} tanga."
        house = db.get_house(house_id)
        if house['lord_id'] and house['lord_id'] != '0':
            send_telegram_message(house['lord_id'], lord_msg)
        return {'success': True, 'message': "❌ Kredit so'rovi rad etildi."}

def process_military_report():
    rows = db.query("SELECT * FROM houses WHERE house_id != 'admin'")
    report = "⚔️ *VESTEROS HARBIY VA IQTISODIY HISOBOTI* ⚔️\n\n"

    for r in rows:
        house_id = r['house_id']
        house_name = r['house_name']
        currency_symbol = r['currency_symbol'] or '🪙'
        treasury = float(r['treasury_balance']) if r['treasury_balance'] is not None else 0.0
        wall_hp = int(r['wall_health']) if r['wall_health'] is not None else 0
        wall_type = r['wall_type'] or 'qora'
        wall_max_hp = int(r['wall_max_health']) if r['wall_max_health'] is not None else 600
        defense_cooldown = r['defense_cooldown_until']

        army = db.get_house_army(house_id)
        total_troops = sum(army.values())
        bori_count = army.get("bori", 0)

        shield_status = "❌ Himoya yo'q"
        if defense_cooldown:
            try:
                cooldown_time = datetime.datetime.fromisoformat(defense_cooldown)
            except Exception:
                cooldown_time = datetime.datetime.now()
                
            if cooldown_time > datetime.datetime.now():
                diff = cooldown_time - datetime.datetime.now()
                days = diff.days
                hours = (diff.seconds // 3600)
                minutes = (diff.seconds % 3600) // 60
                
                shield_status = "🛡️ Faol ("
                if days > 0:
                    shield_status += f"{days}k "
                if hours > 0:
                    shield_status += f"{hours}s "
                shield_status += f"{minutes}m)"

        wall_type_label = "🌌 Qora"
        if wall_type == 'yogoch':
            wall_type_label = "🪵 Yog'och"
        elif wall_type == 'tosh':
            wall_type_label = "🧱 Tosh"

        report += (
            f"🏰 *{house_name}* (ID: `{house_id}`):\n"
            f"💰 G'azna: *{treasury} {currency_symbol}*\n"
            f"🧱 Devor: *{wall_hp}/{wall_max_hp}* ({wall_type_label})\n"
            f"🛡️ Qalqon: *{shield_status}*\n"
            f"🗡️ Armiya: *{total_troops}* ta askar (shundan *{bori_count}* ta bo'ri)\n\n"
        )
    return report

def process_broadcast(user_id, target_type, message_text):
    user = db.get_user(user_id)
    if not user or user['role'] not in ['admin', 'muhbir', 'co_admin']:
        return {'success': False, 'message': "Ruxsat yo'q!"}

    broadcast_id = f"bc_{int(time.time()*1000)}"
    db.execute(
        'INSERT INTO broadcasts (broadcast_id, timestamp, sender_id, target_type, message_text, status) '
        'VALUES (%s, %s, %s, %s, %s, %s)',
        (broadcast_id, datetime.datetime.now().isoformat(), str(user_id), target_type, message_text, 'sending')
    )

    formatted_msg = f"📢 *E'LON / XABAR:*\n\n{message_text}"
    count = 0

    if target_type == 'all':
        players = db.query("SELECT telegram_id FROM users WHERE role != 'admin'")
        for p in players:
            send_telegram_message(p['telegram_id'], formatted_msg)
            count += 1
    elif target_type == 'lords':
        players = db.query("SELECT telegram_id FROM users WHERE role IN ('lord', 'king')")
        for p in players:
            send_telegram_message(p['telegram_id'], formatted_msg)
            count += 1
    else:
        # Specific house
        players = db.query("SELECT telegram_id FROM users WHERE house_id = %s", (target_type,))
        for p in players:
            send_telegram_message(p['telegram_id'], formatted_msg)
            count += 1

    db.execute("UPDATE broadcasts SET status = 'sent' WHERE broadcast_id = %s", (broadcast_id,))
    return {'success': True, 'message': f"✅ Xabar {count} ta foydalanuvchiga yuborildi."}

def process_broadcast_copy(user_id, target_type, from_chat_id, message_id):
    user = db.get_user(user_id)
    if not user or user['role'] not in ['admin', 'muhbir', 'co_admin']:
        return {'success': False, 'message': "Ruxsat yo'q!"}

    count = 0
    if target_type == 'all':
        players = db.query("SELECT telegram_id FROM users WHERE role != 'admin'")
        for p in players:
            copy_telegram_message(p['telegram_id'], from_chat_id, message_id)
            count += 1
    elif target_type == 'lords':
        players = db.query("SELECT telegram_id FROM users WHERE role IN ('lord', 'king')")
        for p in players:
            copy_telegram_message(p['telegram_id'], from_chat_id, message_id)
            count += 1
    else:
        players = db.query("SELECT telegram_id FROM users WHERE house_id = %s", (target_type,))
        for p in players:
            copy_telegram_message(p['telegram_id'], from_chat_id, message_id)
            count += 1

    return {'success': True, 'message': f"✅ Xabar nusxasi {count} ta foydalanuvchiga yuborildi."}

# Help and Dashboard Markup
def get_dashboard_markup(user):
    keyboard = []
    
    if user['role'] == "admin":
        keyboard.append([
            types.InlineKeyboardButton("⚙️ Admin Sozlamalari", callback_data="cb_admin_menu"),
            types.InlineKeyboardButton("🎁 Bonus tarqatish", callback_data="cb_bonus")
        ])
        keyboard.append([
            types.InlineKeyboardButton("⚙️ O'yin Sozlamalari", callback_data="cb_admin_game_settings"),
            types.InlineKeyboardButton("🏦 Kredit so'rovlari", callback_data="cb_list_loans")
        ])
        keyboard.append([
            types.InlineKeyboardButton("📣 E'lon yuborish", callback_data="cb_broadcast_prompt"),
            types.InlineKeyboardButton("📊 Iqtisodiyot", callback_data="cb_economy")
        ])
        keyboard.append([
            types.InlineKeyboardButton("📜 Yordam", callback_data="cb_help")
        ])
    else:
        keyboard.append([
            types.InlineKeyboardButton("💰 Balans", callback_data="cb_hamyon"),
            types.InlineKeyboardButton("🏰 Qishloq", callback_data="cb_qishloq")
        ])
        keyboard.append([
            types.InlineKeyboardButton("💸 Xayriya", callback_data="cb_xayriya_prompt"),
            types.InlineKeyboardButton("📊 Iqtisodiyot", callback_data="cb_economy")
        ])
        
        if user['role'] in ["lord", "king", "co_admin"]:
            keyboard.append([
                types.InlineKeyboardButton("🗡️ Harbiy Xarid", callback_data="cb_buy_units_list"),
                types.InlineKeyboardButton("📈 Soliq stavkasi", callback_data="cb_set_tax_prompt")
            ])
            keyboard.append([
                types.InlineKeyboardButton("🏦 Kredit so'rash", callback_data="cb_request_loan_prompt"),
                types.InlineKeyboardButton("⚔️ Urush e'lon qilish", callback_data="cb_declare_war_list")
            ])
            
        if user['role'] == "co_admin":
            keyboard.append([
                types.InlineKeyboardButton("⚙️ Admin Sozlamalari", callback_data="cb_admin_menu"),
                types.InlineKeyboardButton("🎁 Bonus tarqatish", callback_data="cb_bonus")
            ])
            keyboard.append([
                types.InlineKeyboardButton("⚙️ O'yin Sozlamalari", callback_data="cb_admin_game_settings"),
                types.InlineKeyboardButton("🏦 Kredit so'rovlari", callback_data="cb_list_loans")
            ])
            keyboard.append([
                types.InlineKeyboardButton("📣 E'lon yuborish", callback_data="cb_broadcast_prompt")
            ])
            
        keyboard.append([
            types.InlineKeyboardButton("📜 Yordam", callback_data="cb_help")
        ])
        
    markup = types.InlineKeyboardMarkup(keyboard)
    return markup

def send_help_message(chat_id, user, message_id=None):
    help_text = "📜 *BOT BUYRUQLARI VA QO'LLANMASI:*\n\n"
    
    if user['role'] == "admin":
        help_text += "🛠️ *Admin buyruqlari:*\n" \
                     "• `/menu` - Boshqaruv interfeysi\n" \
                     "• `/iqtisodiyot` - O'yin iqtisodiyoti va shaffoflik\n\n"
    else:
        help_text += "Foydalanuvchi: Citizen\n" \
                     "• `/start` yoki `/menu` - Bosh menyu\n" \
                     "• `/hamyon` - Shaxsiy balans, rol va xonadon\n" \
                     "• `/qishloq` - Qishloq g'aznasi, devor HP, askarlar\n" \
                     "• `/bonus` - Kunlik bonus (65 tanga)\n" \
                     "• `/casino` - Interaktiv pul tikish va risk rejimi (Slot machine)\n" \
                     "• `/xayriya <miqdor>` - G'aznaga xayriya\n" \
                     "• `/iqtisodiyot` - O'yin iqtisodiyoti va shaffoflik\n\n"

    if user['role'] in ["lord", "king", "co_admin", "admin"]:
        help_text += "👑 *Lord / Qirol maxsus buyruqlari:*\n" \
                     "• `/soliq <foiz>` - Soliq foizini sozlash\n" \
                     "• `/kredit <miqdor>` - Temir Bankdan kredit so'rash\n" \
                     "• `/kredit_tolash <miqdor>` - Kreditni qaytarish\n" \
                     "• `/urush <xonadon_id> [tur] [soni]` - Urush e'lon qilish\n" \
                     "• `/sotib_olish <harbiy_birlik_id> <soni>` - Askarlar sotib olish\n\n"

    if user['role'] in ["co_admin", "admin"]:
        help_text += "⚙️ *Admin / Co-Admin buyruqlari:*\n" \
                     "• `/kreditlar` - Kredit so'rovlari\n" \
                     "• `/elon <kimga> <matn>` - Xabarnoma yuborish\n" \
                     "• `/kunlik` - Kunlik davrni yakunlash (maosh va soliqlar yig'ish)\n" \
                     "• `/role <user_id> <rol> <xonadon_id>` - Rol tayinlash\n" \
                     "• `/tangaber <user_id> <miqdor>` - Foydalanuvchiga tanga berish\n" \
                     "• `/hamma_bonus <miqdor>` - Barcha foydalanuvchilarga bonus taklif qilish\n"

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="cb_menu"))

    if message_id:
        edit_telegram_message(chat_id, message_id, help_text, kb)
    else:
        send_telegram_message(chat_id, help_text, kb)

# Unified message gateway to port NodeJS doPost
def handle_bot_message(msg):
    try:
        chat_id = str(msg.chat.id)
        text = msg.text or ""
        user_id = str(msg.from_user.id)
        username = msg.from_user.username or msg.from_user.first_name or "User"
        chat_type = msg.chat.type

        # 1. GROUP CHATS LOGIC
        if chat_type in ["group", "supergroup"]:
            house = db.get_house_by_group_chat_id(chat_id)
            
            if text.startswith("/setgroup"):
                if user_id == str(ADMIN_TELEGRAM_ID):
                    parts = text.split()
                    if len(parts) >= 2:
                        target_house_id = parts[1].lower().strip()
                        # Set group chat id
                        rows = db.execute('UPDATE houses SET group_chat_id = %s WHERE house_id = %s', (chat_id, target_house_id))
                        if rows > 0:
                            send_telegram_message(chat_id, f"✅ Ushbu guruh muvaffaqiyatli *{target_house_id.upper()}* xonadoniga bog'landi!")
                        else:
                            send_telegram_message(chat_id, "⚠️ Xatolik! Xonadon topilmadi.")
                    else:
                        send_telegram_message(chat_id, "⚠️ Foydalanish: `/setgroup <house_id>`")
                else:
                    send_telegram_message(chat_id, "⚠️ Faqat Bosh Admin guruhlarni xonadonga bog'lay oladi!")
                return

            if house:
                db.get_or_create_user_in_group(user_id, username, house['house_id'])
            return

        # 2. PRIVATE CHATS LOGIC
        if text == "/ping":
            send_telegram_message(chat_id, "🏓 Pong! Bot ishlayapti.")
            return

        user = db.get_user(user_id)

        if not user:
            if text.startswith("/start"):
                if user_id == str(ADMIN_TELEGRAM_ID):
                    db.execute(
                        'INSERT INTO users (telegram_id, username, house_id, role, wallet_balance, casino_spins_left) '
                        'VALUES (%s, %s, %s, %s, %s, %s)',
                        (str(user_id), username, 'admin', 'admin', 10000.0, 3)
                    )
                    user = db.get_user(user_id)
                else:
                    invite_text = (
                        "🏰 *Game of Thrones Strategy RPG o'yiniga xush kelibsiz!* 🏰\n\n"
                        "Ushbu bot orqali siz Vesteros olamidagi buyuk xonadonlardan biriga a'zo bo'lib, "
                        "strategik urushlarda, iqtisodiy savdolarda va qiziqarli o'yinlarda qatnashasiz!\n\n"
                        "O'yinni boshlash va xonadoningizni aniqlash uchun quyidagi tugmani bosing:"
                    )
                    kb = types.InlineKeyboardMarkup()
                    kb.add(types.InlineKeyboardButton("🏰 Xonadon tanlash", callback_data="cb_join_random_house"))
                    send_telegram_message(chat_id, invite_text, kb)
                    return
            else:
                send_telegram_message(chat_id, "⚠️ Tizimdan foydalanish uchun avval `/start` buyrug'ini yuboring.")
                return

        house = db.get_house(user['house_id'])
        if not house:
            send_telegram_message(chat_id, "⚠️ *Xonadoningiz topilmadi.* Iltimos, `/start` ni qayta yuboring.")
            return

        if text.startswith("/start") or text.startswith("/menu"):
            welcome = (
                f"🏰 *Salom, {username}!*\n"
                f"Xonadoningiz: *{house['house_name']}*\n"
                f"Rolingiz: *{user['role'].upper()}*\n\n"
                f"Quyidagi boshqaruv panelidan foydalaning:"
            )
            send_telegram_message(chat_id, welcome, get_dashboard_markup(user))

        elif text.startswith("/hamyon"):
            txt = (
                f"💼 *Shaxsiy Hamyoningiz:*\n\n"
                f"👤 Foydalanuvchi: *{username}*\n"
                f"🏰 Xonadon: *{house['house_name']}*\n"
                f"💰 Balans: *{user['wallet_balance']} {house['currency_symbol']}*\n"
                f"🎖️ Rol: *{user['role'].upper()}*"
            )
            send_telegram_message(chat_id, txt)

        elif text.startswith("/qishloq"):
            army = db.get_house_army(user['house_id'])
            army_str = "\n".join([f"  • {k.upper()}: *{v} ta*" for k, v in army.items() if v > 0]) or "  • Harbiy birliklar yo'q"
            txt = (
                f"🏰 *{house['house_name']} Qishlog'i*\n"
                f"📈 G'azna: *{house['treasury_balance']} {house['currency_symbol']}*\n"
                f"Devor: *{house['wall_health']}/{house['wall_max_health']} HP* ({house['wall_type']})\n"
                f"Valeriya Po'lati: *{house['valyrian_steel_count']} ta*\n"
                f"📈 Soliq Stavkasi: *{house['tax_rate']*100:.1f}%*\n\n"
                f"*Harbiy Birlar:*\n{army_str}"
            )
            send_telegram_message(chat_id, txt)

        elif text.startswith("/bonus"):
            if user['role'] in ["admin", "banker"]:
                res = admin_distribute_bonus(user_id, text)
                send_telegram_message(chat_id, res['message'])
            else:
                res = process_daily_checkin(user_id)
                send_telegram_message(chat_id, res['message'])

        elif text.startswith("/casino"):
            parts = text.split()
            if len(parts) >= 2:
                try:
                    bet = float(parts[1])
                except ValueError:
                    bet = 0
                if bet not in [10, 20, 50, 70, 100]:
                    send_telegram_message(chat_id, "⚠️ Noto'g'ri tikish miqdori! Stavka faqat: 10, 20, 50, 70 yoki 100 tanga bo'lishi mumkin.")
                    return
                check_res = check_casino_eligible(user_id, bet)
                if not check_res['eligible']:
                    send_telegram_message(chat_id, check_res['message'])
                    return
                deduct_casino_fee(user_id, bet)
                dice_res = send_telegram_dice(chat_id)
                if dice_res and dice_res.dice:
                    val = dice_res.dice.value
                    process_res = process_casino_dice_result(user_id, val, bet)
                    send_telegram_message(chat_id, process_res['message'])
                else:
                    db.execute('UPDATE users SET wallet_balance = wallet_balance + %s, casino_spins_left = casino_spins_left + 1 WHERE telegram_id = %s', (bet, str(user_id)))
                    send_telegram_message(chat_id, "⚠️ Kazino aylanmadi. Qayta urinib ko'ring.")
            else:
                txt = "🎰 *KAZINO MODULI* 🎰\n\nTikish miqdorini tanlang:"
                kb = types.InlineKeyboardMarkup([
                    [types.InlineKeyboardButton("10 🪙", callback_data="cb_casino_bet:10"), types.InlineKeyboardButton("20 🪙", callback_data="cb_casino_bet:20"), types.InlineKeyboardButton("50 🪙", callback_data="cb_casino_bet:50")],
                    [types.InlineKeyboardButton("70 🪙", callback_data="cb_casino_bet:70"), types.InlineKeyboardButton("100 🪙", callback_data="cb_casino_bet:100")],
                    [types.InlineKeyboardButton("🔙 Orqaga", callback_data="cb_menu")]
                ])
                send_telegram_message(chat_id, txt, kb)

        elif text.startswith("/xayriya"):
            parts = text.split()
            if len(parts) >= 2:
                try:
                    amt = float(parts[1])
                except ValueError:
                    amt = 0
                res = process_donation(user_id, amt)
                send_telegram_message(chat_id, res['message'])
            else:
                send_telegram_message(chat_id, "⚠️ Foydalanish: `/xayriya <miqdor>`")

        elif text.startswith("/soliq"):
            parts = text.split()
            if len(parts) >= 2:
                try:
                    rate = float(parts[1])
                except ValueError:
                    rate = -1
                res = process_set_tax(user_id, rate)
                send_telegram_message(chat_id, res['message'])
            else:
                send_telegram_message(chat_id, "⚠️ Foydalanish: `/soliq <foiz>` (masalan: `/soliq 0.05` -> 5%)")

        elif text.startswith("/kreditlar"):
            if user['role'] not in ["admin", "co_admin"]:
                return
            loans = db.get_pending_loans_list()
            if not loans:
                send_telegram_message(chat_id, "🏦 *Hech qanday faol kredit so'rovlari mavjud emas.*")
            else:
                for l in loans:
                    txt = f"🏦 *Kredit So'rovi:*\nID: *{l['loan_id']}*\nXonadon: *{l['house_id'].upper()}*\nMiqdor: *{l['amount']}*\nSana: *{l['requested_at']}*"
                    kb = types.InlineKeyboardMarkup()
                    kb.add(
                        types.InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"cb_loan_decision:{l['loan_id']}:approve"),
                        types.InlineKeyboardButton("❌ Rad etish", callback_data=f"cb_loan_decision:{l['loan_id']}:reject")
                    )
                    send_telegram_message(chat_id, txt, kb)

        elif text.startswith("/kredit_tolash") or text.startswith("/qarz_tolash"):
            parts = text.split()
            if len(parts) >= 2:
                try:
                    amt = float(parts[1])
                except ValueError:
                    amt = 0
                res = process_loan_repay(user_id, amt)
                send_telegram_message(chat_id, res['message'])
            else:
                send_telegram_message(chat_id, "⚠️ Foydalanish: `/kredit_tolash <miqdor>`")

        elif text.startswith("/kunlik") or text.startswith("/soliq_yigish"):
            res = process_daily_cycle(user_id)
            send_telegram_message(chat_id, res['message'])

        elif text.startswith("/kredit"):
            parts = text.split()
            if len(parts) >= 2:
                try:
                    amt = float(parts[1])
                except ValueError:
                    amt = 0
                res = process_loan_request(user_id, amt)
                send_telegram_message(chat_id, res['message'])
            else:
                send_telegram_message(chat_id, "⚠️ Foydalanish: `/kredit <miqdor>`")

        elif text.startswith("/sotib_olish"):
            parts = text.split()
            if len(parts) >= 3:
                u_id = parts[1].lower().strip()
                try:
                    qty = int(parts[2])
                except ValueError:
                    qty = 0
                res = process_unit_purchase(user_id, u_id, qty)
                send_telegram_message(chat_id, res['message'])
            else:
                send_telegram_message(chat_id, "⚠️ Foydalanish: `/sotib_olish <harbiy_nomi> <miqdor>`")

        elif text.startswith("/devor"):
            parts = text.split()
            if len(parts) >= 2:
                wall_type = parts[1].lower().strip()
                res = process_wall_upgrade(user_id, wall_type)
                send_telegram_message(chat_id, res['message'])
            else:
                send_telegram_message(chat_id, "⚠️ Foydalanish: `/devor <yogoch/tosh/qora>`")

        elif text.startswith("/urush"):
            parts = text.split()
            if len(parts) >= 2:
                target_house = parts[1].lower().strip()
                res = declare_war(user_id, target_house, text)
                if not res.get('success'):
                    send_telegram_message(chat_id, f"⚠️ Xatolik: {res['message']}")
            else:
                send_telegram_message(chat_id, "⚠️ Foydalanish: `/urush <xonadon_id> [harbiy] [soni]`")

        elif text.startswith("/elon"):
            parts = text.split()
            is_reply = msg.reply_to_message is not None
            target_type = "all"
            msg_text = ""

            valid_targets = ["all", "lords", "king", "citizen"]
            for h in db.query("SELECT house_id FROM houses"):
                valid_targets.append(h['house_id'].lower())

            if is_reply:
                if len(parts) >= 2 and parts[1].lower() in valid_targets:
                    target_type = parts[1].lower()
                res = process_broadcast_copy(user_id, target_type, chat_id, msg.reply_to_message.message_id)
                send_telegram_message(chat_id, res['message'])
            else:
                if len(parts) >= 2:
                    first = parts[1].lower()
                    if first in valid_targets:
                        target_type = first
                        idx = text.find(parts[1])
                        msg_text = text[idx + len(parts[1]):].strip()
                    else:
                        target_type = "all"
                        idx = text.find(parts[0])
                        msg_text = text[idx + len(parts[0]):].strip()

                if msg_text:
                    res = process_broadcast(user_id, target_type, msg_text)
                    send_telegram_message(chat_id, res['message'])
                else:
                    send_telegram_message(chat_id, "⚠️ Foydalanish: `/elon <kimga> <matn>`")

        elif text.startswith("/role"):
            parts = text.split()
            if len(parts) >= 3:
                t_id = parts[1]
                role = parts[2].lower()
                h_id = parts[3].lower() if len(parts) >= 4 else None
                res = grant_role(user_id, t_id, role, h_id)
                send_telegram_message(chat_id, res['message'])
            else:
                send_telegram_message(chat_id, "⚠️ Foydalanish: `/role <user_id> <rol> [xonadon_id]`")

        elif text.startswith("/tangaber"):
            parts = text.split()
            if len(parts) >= 3:
                t_id = parts[1]
                try:
                    amt = float(parts[2])
                except ValueError:
                    amt = 0.0
                res = add_coins_admin(user_id, t_id, amt)
                send_telegram_message(chat_id, res['message'])
            else:
                send_telegram_message(chat_id, "⚠️ Foydalanish: `/tangaber <user_id> <miqdor>`")

        elif text.startswith("/hamma_bonus"):
            parts = text.split()
            if len(parts) >= 2:
                try:
                    amt = float(parts[1])
                except ValueError:
                    amt = 0.0
                res = distribute_bonus_global(user_id, amt)
                send_telegram_message(chat_id, res['message'])
            else:
                send_telegram_message(chat_id, "⚠️ Foydalanish: `/hamma_bonus <miqdor>`")

        elif text.startswith("/savdo"):
            if user['role'] not in ['admin', 'co_admin']:
                return
            parts = text.split()
            if len(parts) >= 2:
                state = parts[1].lower().strip()
                if state in ['on', 'open']:
                    db.set_setting('shop_state', 'open')
                    send_telegram_message(chat_id, "✅ Harbiy savdolar yoqildi!")
                    notify_global("🛒 *HARBIY SAVDOLAR OCHILDI!* 🛒\nLordlar endi armiya sotib olishlari mumkin.")
                else:
                    db.set_setting('shop_state', 'closed')
                    send_telegram_message(chat_id, "✅ Harbiy savdolar o'chirildi!")
                    notify_global("🔒 *HARBIY SAVDOLAR YOPILDI!* 🔒")
            else:
                cur = db.get_setting('shop_state', 'open')
                send_telegram_message(chat_id, f"Savdolar holati: *{'🟢 OCHIQ' if cur == 'open' else '🔴 YOPIQ'}*")

        elif text.startswith("/iqtisodiyot") or text.startswith("/shaffof"):
            stats = db.get_economy_stats()
            send_telegram_message(chat_id, stats)

        elif text.startswith("/set_general_chat"):
            if user['role'] != 'admin':
                return
            db.set_setting('general_chat_id', chat_id)
            send_telegram_message(chat_id, "✅ Ushbu guruh Umumiy Chat (General Chat) sifatida belgilandi!")

        elif text.startswith("/harbiy") or text.startswith("/xonadonlar"):
            report = process_military_report()
            send_telegram_message(chat_id, report)

        elif text.startswith("/ittifoq"):
            if text.startswith("/ittifoq_buzish"):
                res = process_alliance_dissolve(user_id)
                send_telegram_message(chat_id, res['message'])
            else:
                parts = text.split()
                if len(parts) >= 2:
                    target_house = parts[1].lower().strip()
                    res = process_alliance_proposal(user_id, target_house)
                    send_telegram_message(chat_id, res['message'])
                else:
                    send_telegram_message(chat_id, "⚠️ Foydalanish: `/ittifoq <xonadon_id>`\nBuzish uchun: `/ittifoq_buzish`")

        elif text.startswith("/yordam_berish"):
            res = process_alliance_help(user_id, text)
            send_telegram_message(chat_id, res['message'])

        elif text.startswith("/help"):
            send_help_message(chat_id, user)

    except Exception as err:
        print(f"handle_bot_message error: {err}")

# Callback Query Handler
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    try:
        chat_id = str(call.message.chat.id)
        message_id = call.message.message_id
        data = call.data
        user_id = str(call.from_user.id)
        username = call.from_user.username or call.from_user.first_name or "User"

        answer_callback_query(call.id)

        user = db.get_user(user_id)
        
        if not user and data != "cb_join_random_house":
            send_telegram_message(chat_id, "⚠️ Tizimdan foydalanish uchun avval `/start` buyrug'ini yuboring.")
            return

        if data == "cb_join_random_house":
            if user:
                house = db.get_house(user['house_id'])
                send_telegram_message(chat_id, f"⚠️ Siz allaqachon xonadonga a'zo bo'lgansiz: *{house['house_name']}*")
                return
            
            user = db.get_or_create_user(user_id, username, BOT_TOKEN)
            assigned_house = db.get_house(user['house_id'])
            
            txt = (
                f"🎉 *Tabriklaymiz! Siz muvaffaqiyatli ro'yxatdan o'tdingiz!*\n\n"
                f"Sizning xonadoningiz: *{assigned_house['house_name']} {assigned_house['currency_symbol']}*\n"
                f"Rolingiz: *Fuqaro (Citizen)*\n"
                f"Boshlang'ich balans: *100 {assigned_house['currency_symbol']}*\n\n"
                f"O'yinda qatnashish va guruhga a'zo bo'lish uchun havolalardan foydalaning:"
            )
            
            kb = types.InlineKeyboardMarkup()
            if assigned_house['group_link']:
                kb.add(types.InlineKeyboardButton("💬 Guruhga kirish 🔗", url=assigned_house['group_link']))
            kb.add(types.InlineKeyboardButton("🎮 O'yinni boshlash", callback_data="cb_menu"))
            
            edit_telegram_message(chat_id, message_id, txt, kb)
            return

        house = db.get_house(user['house_id'])
        if not house:
            send_telegram_message(chat_id, "⚠️ Xonadoningiz topilmadi.")
            return

        if data == "cb_hamyon":
            txt = (
                f"💼 *Shaxsiy Hamyoningiz:*\n\n"
                f"👤 Foydalanuvchi: *{username}*\n"
                f"🏰 Xonadon: *{house['house_name']}*\n"
                f"💰 Balans: *{user['wallet_balance']} {house['currency_symbol']}*\n"
                f"🎖️ Rol: *{user['role'].upper()}*"
            )
            kb = types.InlineKeyboardMarkup([[types.InlineKeyboardButton("🔙 Orqaga", callback_data="cb_menu")]])
            edit_telegram_message(chat_id, message_id, txt, kb)

        elif data == "cb_qishloq":
            army = db.get_house_army(user['house_id'])
            army_str = "\n".join([f"🗡️ {k.upper()}: *{v} ta*" for k, v in army.items() if v > 0]) or "Harbiy birliklar yo'q"
            txt = (
                f"🏰 *{house['house_name']} Qishlog'i*\n"
                f"📈 G'azna: *{house['treasury_balance']} {house['currency_symbol']}*\n"
                f"Devor: *{house['wall_health']}/{house['wall_max_health']} HP* ({house['wall_type']})\n"
                f"Valeriya Po'lati: *{house['valyrian_steel_count']} ta*\n"
                f"📈 Soliq Stavkasi: *{house['tax_rate']*100:.1f}%*\n\n"
                f"*Harbiy Birlar:*\n{army_str}"
            )
            kb = types.InlineKeyboardMarkup([[types.InlineKeyboardButton("🔙 Orqaga", callback_data="cb_menu")]])
            edit_telegram_message(chat_id, message_id, txt, kb)

        elif data == "cb_bonus":
            if user['role'] in ["admin", "banker"]:
                txt = (
                    f"👑 *Bonus tarqatish paneli:*\n\n"
                    f"Format:\n`/bonus <miqdor>\n@username1\n@username2`"
                )
                kb = types.InlineKeyboardMarkup([[types.InlineKeyboardButton("🔙 Orqaga", callback_data="cb_menu")]])
                edit_telegram_message(chat_id, message_id, txt, kb)
            else:
                res = process_daily_checkin(user_id)
                send_telegram_message(chat_id, res['message'])

        elif data == "cb_casino_menu":
            txt = (
                f"🎰 *KAZINO MODULI* 🎰\n\n"
                f"Omadingizni sinab ko'ring!\n"
                f"Tikish miqdorini tanlang:"
            )
            kb = types.InlineKeyboardMarkup([
                [types.InlineKeyboardButton("10 🪙", callback_data="cb_casino_bet:10"), types.InlineKeyboardButton("20 🪙", callback_data="cb_casino_bet:20"), types.InlineKeyboardButton("50 🪙", callback_data="cb_casino_bet:50")],
                [types.InlineKeyboardButton("70 🪙", callback_data="cb_casino_bet:70"), types.InlineKeyboardButton("100 🪙", callback_data="cb_casino_bet:100")],
                [types.InlineKeyboardButton("🔙 Orqaga", callback_data="cb_menu")]
            ])
            edit_telegram_message(chat_id, message_id, txt, kb)

        elif data == "cb_casino_spin":
            res = check_casino_eligible(user_id, 20)
            if not res['eligible']:
                send_telegram_message(chat_id, res['message'])
                return
            deduct_casino_fee(user_id, 20)
            dice_res = send_telegram_dice(chat_id)
            if dice_res and dice_res.dice:
                val = dice_res.dice.value
                process_res = process_casino_dice_result(user_id, val, 20)
                send_telegram_message(chat_id, process_res['message'])
            else:
                send_telegram_message(chat_id, "⚠️ Kazino aylanmadi. Qayta urinib ko'ring.")

        elif data.startswith("cb_casino_bet:"):
            bet = float(data.split(":")[1])
            res = check_casino_eligible(user_id, bet)
            if not res['eligible']:
                send_telegram_message(chat_id, res['message'])
                return
            deduct_casino_fee(user_id, bet)
            edit_telegram_message(chat_id, message_id, f"🎰 *Kazino: Slot-mashinasi aylantirilmoqda...*\nTikilgan miqdor: *{bet} {house['currency_symbol']}*")
            dice_res = send_telegram_dice(chat_id)
            if dice_res and dice_res.dice:
                val = dice_res.dice.value
                process_res = process_casino_dice_result(user_id, val, bet)
                send_telegram_message(chat_id, process_res['message'])
            else:
                db.execute('UPDATE users SET wallet_balance = wallet_balance + %s, casino_spins_left = casino_spins_left + 1 WHERE telegram_id = %s', (bet, str(user_id)))
                send_telegram_message(chat_id, "⚠️ Kazino aylanmadi. Tanga qaytarildi.")

        elif data == "cb_xayriya_prompt":
            txt = (
                f"💸 *G'aznaga xayriya qilish*\n\n"
                f"Buyruq shakli: `/xayriya <miqdor>`\nMasalan: `/xayriya 150`"
            )
            send_telegram_message(chat_id, txt)

        elif data == "cb_set_tax_prompt":
            txt = (
                f"📈 *Soliq stavkasini sozlash (Lordlar uchun)*\n\n"
                f"Buyruq shakli: `/soliq <foiz>`\nMasalan: `/soliq 0.05` (5%)"
            )
            send_telegram_message(chat_id, txt)

        elif data == "cb_request_loan_prompt":
            txt = (
                f"🏦 *Bankdan kredit so'rash (Lordlar uchun)*\n\n"
                f"Buyruq shakli: `/kredit <miqdor>`\nMasalan: `/kredit 500`"
            )
            send_telegram_message(chat_id, txt)

        elif data == "cb_buy_units_list":
            txt = (
                f"🗡️ *HARBIY XARIDLAR PANEL* 🗡️\n\n"
                f"Askar: 10 tanga (Atk: 1, Def: 1)\n"
                f"Bo'ri: 10 tanga (Atk: 10, Def: 10) 🐺\n"
                f"Kamonchi: 20 tanga (Atk: 2, Def: 4)\n"
                f"Otliq: 35 tanga (Atk: 4, Def: 2)\n"
                f"Katapulta: 70 tanga (Atk: 70, Def: 0)\n"
                f"Chayon/Arbalet: 180 tanga (Atk: 100, Def: 100)\n"
                f"Afsungar: 250 tanga (Atk: 50, Def: 100)\n"
                f"Devor buzuvchi: 300 tanga (Atk: 300, Def: 0)\n\n"
                f"Buyruq shakli: `/sotib_olish <harbiy_nomi> <miqdor>`\n"
                f"Sotib olish tugmalari (+5 ta):"
            )
            kb = types.InlineKeyboardMarkup([
                [types.InlineKeyboardButton("🗡️ Oddiy Askar (+5)", callback_data="cb_buy_quick:askar"), types.InlineKeyboardButton("🐺 Bo'ri (+5)", callback_data="cb_buy_quick:bori")],
                [types.InlineKeyboardButton("🏹 Kamonchi (+5)", callback_data="cb_buy_quick:kamonchi"), types.InlineKeyboardButton("🐎 Otliq (+5)", callback_data="cb_buy_quick:otliq")],
                [types.InlineKeyboardButton("☄️ Katapulta (+5)", callback_data="cb_buy_quick:katapulta"), types.InlineKeyboardButton("🦂 Chayon (+5)", callback_data="cb_buy_quick:chayon")],
                [types.InlineKeyboardButton("🔮 Afsungar (+5)", callback_data="cb_buy_quick:afsungar"), types.InlineKeyboardButton("🪵 Devor Buzuvchi (+5)", callback_data="cb_buy_quick:devor_buzuvchi")]
            ])
            send_telegram_message(chat_id, txt, kb)

        elif data.startswith("cb_buy_quick:"):
            shop_state = db.get_setting('shop_state', 'open')
            if shop_state != 'open':
                send_telegram_message(chat_id, "⚠️ Harbiy savdolar (xaridlar) vaqtincha yopilgan!")
                return
            if user['role'] not in ['lord', 'king', 'co_admin', 'admin', 'builder']:
                send_telegram_message(chat_id, "⚠️ Ruxsat yo'q!")
                return
            u_id = data.split(":")[1]
            res = process_unit_purchase(user_id, u_id, 5)
            send_telegram_message(chat_id, res['message'])

        elif data == "cb_declare_war_list":
            houses_list = [
                {'id': 'stark', 'name': 'House Stark 🐺'},
                {'id': 'lannister', 'name': 'House Lannister 🦁'},
                {'id': 'baratheon', 'name': 'House Baratheon 🦌'},
                {'id': 'tyrell', 'name': 'House Tyrell 🌹'},
                {'id': 'martell', 'name': 'House Martell ☀️'},
                {'id': 'arryn', 'name': 'House Arryn 🦅'},
                {'id': 'greyjoy', 'name': 'House Greyjoy 🦑'},
                {'id': 'tully', 'name': 'House Tully 🐟'},
                {'id': 'hightower', 'name': 'House Hightower 🗼'},
                {'id': 'bolton', 'name': 'House Bolton ⚔️'},
                {'id': 'blackwood', 'name': 'House Blackwood 🌳'},
                {'id': 'bracken', 'name': 'House Bracken 🐎'},
                {'id': 'targaryen', 'name': 'House Targaryen 🐲'}
            ]
            row = []
            kb_list = []
            for h in houses_list:
                if h['id'] != user['house_id']:
                    row.append(types.InlineKeyboardButton(h['name'], callback_data=f"cb_war_attack:{h['id']}"))
                    if len(row) == 2:
                        kb_list.append(row)
                        row = []
            if row:
                kb_list.append(row)
            kb = types.InlineKeyboardMarkup(kb_list)
            txt = (
                f"⚔️ *URUSH E'LON QILISH*\n\n"
                f"Hujum qilinadigan xonadonni tanlang:"
            )
            send_telegram_message(chat_id, txt, kb)

        elif data.startswith("cb_war_attack:"):
            target = data.split(":")[1]
            res = declare_war(user_id, target)
            if not res.get('success'):
                send_telegram_message(chat_id, f"⚠️ Xatolik: {res['message']}")
            else:
                send_telegram_message(chat_id, "⚔️ Siz dushman xonadonga qarshi barcha qo'shiningiz bilan yurish boshladingiz!")

        elif data.startswith("cb_war_decision:"):
            parts = data.split(":")
            b_id = parts[1]
            decision = parts[2]
            res = resolve_war_decision(user_id, b_id, decision)
            if res.get('success'):
                edit_telegram_message(chat_id, message_id, res['message'])
            else:
                send_telegram_message(chat_id, f"⚠️ Xatolik: {res['message']}")

        elif data.startswith("cb_alliance_decision:"):
            parts = data.split(":")
            sender = parts[1]
            target = parts[2]
            action = parts[3]

            sender_house = db.get_house(sender)
            target_house = db.get_house(target)

            if user['role'] != 'admin' and (user['house_id'] != target or user['role'] not in ['lord', 'king', 'co_admin']):
                return

            if action == 'accept':
                if sender_house['alliance_house_id']:
                    edit_telegram_message(chat_id, message_id, "❌ Raqib allaqachon ittifoqqa ega.")
                    return
                if target_house['alliance_house_id']:
                    edit_telegram_message(chat_id, message_id, "❌ Siz allaqachon ittifoqdoshga egasiz.")
                    return

                db.execute('UPDATE houses SET alliance_house_id = %s WHERE house_id = %s', (target, sender))
                db.execute('UPDATE houses SET alliance_house_id = %s WHERE house_id = %s', (sender, target))

                txt = (
                    f"🤝 *YANGI ITTIFOQ!* 🤝\n\n"
                    f"*{sender_house['house_name']}* va *{target_house['house_name']}* xonadonlari o'rtasida harbiy-siyosiy ittifoq tuzildi!"
                )
                notify_global(txt)
                edit_telegram_message(chat_id, message_id, "✅ Ittifoq taklifi qabul qilindi!")
            else:
                if sender_house['lord_id'] and sender_house['lord_id'] != '0':
                    send_telegram_message(sender_house['lord_id'], f"❌ *{target_house['house_name']}* xonadoni ittifoq taklifingizni rad etdi.")
                edit_telegram_message(chat_id, message_id, "❌ Ittifoq taklifi rad etildi.")

        elif data.startswith("cb_war_help_prompt:"):
            parts = data.split(":")
            b_id = parts[1]
            side = parts[2]
            battle = db.get_battle_record(b_id)
            if not battle or battle['status'] != 'pending':
                send_telegram_message(chat_id, "⚠️ Ushbu urush allaqachon tugagan!")
                return
            if user['role'] not in ['lord', 'king', 'co_admin', 'admin']:
                return

            txt = (
                f"🤝 *Jangga yordam berish panel:*\n\n"
                f"Format:\n`/yordam_berish {b_id} <harbiy_nomi> <miqdor>`\n"
                f"Masalan: `/yordam_berish {b_id} otliq 15`"
            )
            send_telegram_message(chat_id, txt)

        elif data == "cb_list_loans":
            if user['role'] not in ["admin", "co_admin"]:
                return
            loans = db.get_pending_loans_list()
            if not loans:
                send_telegram_message(chat_id, "🏦 *Hech qanday faol kredit so'rovlari mavjud emas.*")
            else:
                for l in loans:
                    txt = f"🏦 *Kredit So'rovi:*\nID: *{l['loan_id']}*\nXonadon: *{l['house_id'].upper()}*\nMiqdor: *{l['amount']}*\nSana: *{l['requested_at']}*"
                    kb = types.InlineKeyboardMarkup()
                    kb.add(
                        types.InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"cb_loan_decision:{l['loan_id']}:approve"),
                        types.InlineKeyboardButton("❌ Rad etish", callback_data=f"cb_loan_decision:{l['loan_id']}:reject")
                    )
                    send_telegram_message(chat_id, txt, kb)

        elif data.startswith("cb_loan_decision:"):
            parts = data.split(":")
            l_id = parts[1]
            decision = parts[2]
            res = approve_loan(user_id, l_id, decision == 'approve')
            send_telegram_message(chat_id, res['message'])

        elif data == "cb_broadcast_prompt":
            txt = (
                f"📣 *E'lon yuborish format:*\n\n"
                f"`/elon <kimga> <matn>`\n"
                f"Targetlar: `all`, `lords`, yoki xonadon ID si (masalan: `stark`)"
            )
            send_telegram_message(chat_id, txt)

        elif data == "cb_admin_menu":
            txt = (
                f"⚙️ *ADMIN PANEL CENTRAL COMMAND*\n\n"
                f"1️⃣ Rol berish:\n`/role <user_id> <rol> [xonadon]`\n"
                f"2️⃣ Tanga berish:\n`/tangaber <user_id> <miqdor>`\n"
                f"3️⃣ Hammaga bonus:\n`/hamma_bonus <miqdor>`"
            )
            send_telegram_message(chat_id, txt)

        elif data == "cb_admin_game_settings":
            if user['role'] not in ["admin", "co_admin"]:
                return
            casino = db.get_setting('casino_state', 'closed')
            shop = db.get_setting('shop_state', 'open')
            war = db.get_setting('war_state', 'open')

            txt = (
                f"⚙️ *O'YIN TIZIMLARI SOZLAMALARI* ⚙️\n\n"
                f"🎰 **Kazino:** {'🟢 OCHIQ' if casino == 'open' else '🔴 YOPIQ'}\n"
                f"🛒 **Harbiy savdo:** {'🟢 OCHIQ' if shop == 'open' else '🔴 YOPIQ'}\n"
                f"⚔️ **Urush:** {'🟢 OCHIQ' if war == 'open' else '🔴 YOPIQ'}"
            )
            kb = types.InlineKeyboardMarkup([
                [types.InlineKeyboardButton("🎰 Kazino: ON", callback_data="cb_game_toggle:casino:open"), types.InlineKeyboardButton("🎰 Kazino: OFF", callback_data="cb_game_toggle:casino:closed")],
                [types.InlineKeyboardButton("🛒 Savdo: ON", callback_data="cb_game_toggle:shop:open"), types.InlineKeyboardButton("🛒 Savdo: OFF", callback_data="cb_game_toggle:shop:closed")],
                [types.InlineKeyboardButton("⚔️ Urush: ON", callback_data="cb_game_toggle:war:open"), types.InlineKeyboardButton("⚔️ Urush: OFF", callback_data="cb_game_toggle:war:closed")],
                [types.InlineKeyboardButton("📢 Saqlash & E'lon qilish", callback_data="cb_game_save_broadcast")],
                [types.InlineKeyboardButton("🔙 Bosh menyu", callback_data="cb_menu")]
            ])
            edit_telegram_message(chat_id, message_id, txt, kb)

        elif data.startswith("cb_game_toggle:"):
            if user['role'] not in ["admin", "co_admin"]:
                return
            parts = data.split(":")
            system = parts[1]
            state = parts[2]
            
            key = 'casino_state' if system == 'casino' else ('shop_state' if system == 'shop' else 'war_state')
            db.set_setting(key, state)
            
            # Refresh menu
            casino = db.get_setting('casino_state', 'closed')
            shop = db.get_setting('shop_state', 'open')
            war = db.get_setting('war_state', 'open')

            txt = (
                f"⚙️ *O'YIN TIZIMLARI SOZLAMALARI* ⚙️\n\n"
                f"🎰 **Kazino:** {'🟢 OCHIQ' if casino == 'open' else '🔴 YOPIQ'}\n"
                f"🛒 **Harbiy savdo:** {'🟢 OCHIQ' if shop == 'open' else '🔴 YOPIQ'}\n"
                f"⚔️ **Urush:** {'🟢 OCHIQ' if war == 'open' else '🔴 YOPIQ'}"
            )
            kb = types.InlineKeyboardMarkup([
                [types.InlineKeyboardButton("🎰 Kazino: ON", callback_data="cb_game_toggle:casino:open"), types.InlineKeyboardButton("🎰 Kazino: OFF", callback_data="cb_game_toggle:casino:closed")],
                [types.InlineKeyboardButton("🛒 Savdo: ON", callback_data="cb_game_toggle:shop:open"), types.InlineKeyboardButton("🛒 Savdo: OFF", callback_data="cb_game_toggle:shop:closed")],
                [types.InlineKeyboardButton("⚔️ Urush: ON", callback_data="cb_game_toggle:war:open"), types.InlineKeyboardButton("⚔️ Urush: OFF", callback_data="cb_game_toggle:war:closed")],
                [types.InlineKeyboardButton("📢 Saqlash & E'lon qilish", callback_data="cb_game_save_broadcast")],
                [types.InlineKeyboardButton("🔙 Bosh menyu", callback_data="cb_menu")]
            ])
            edit_telegram_message(chat_id, message_id, txt, kb)

        elif data == "cb_game_save_broadcast":
            if user['role'] not in ["admin", "co_admin"]:
                return
            casino = db.get_setting('casino_state', 'closed')
            shop = db.get_setting('shop_state', 'open')
            war = db.get_setting('war_state', 'open')

            last_casino = db.get_setting('last_bc_casino', '')
            last_shop = db.get_setting('last_bc_shop', '')
            last_war = db.get_setting('last_bc_war', '')

            messages = []
            
            if casino != last_casino:
                txt = "🎰 *KAZINO OCHILDI!* 🎰\n\nOmadingizni `/casino` orqali sinab ko'ring." if casino == 'open' else "🎰 *Kazino yopildi!* 🎰"
                for u in db.query("SELECT telegram_id FROM users WHERE role != 'admin'"):
                    messages.append((u['telegram_id'], txt))
                db.set_setting('last_bc_casino', casino)

            if shop != last_shop:
                txt = "⚔️ *HARBIY SAVDOLAR OCHILDI!* ⚔️" if shop == 'open' else "🔒 *HARBIY SAVDOLAR YOPILDI!* 🔒"
                for u in db.query("SELECT telegram_id FROM users WHERE role IN ('lord', 'king', 'co_admin')"):
                    messages.append((u['telegram_id'], txt))
                db.set_setting('last_bc_shop', shop)

            if war != last_war:
                txt = "⚔️ *URUSHLAR OCHILDI!* ⚔️\n\nLordlar dushman xonadonlarga `/urush <xonadon_id>` orqali hujum qila oladilar!" if war == 'open' else "🛡️ *URUSHLAR TO'XTATILDI (MUZLATILDI)!* 🛡️"
                for h in db.query("SELECT group_chat_id FROM houses WHERE group_chat_id IS NOT NULL AND group_chat_id != ''"):
                    messages.append((h['group_chat_id'], txt))
                db.set_setting('last_bc_war', war)

            if messages:
                for target, text in messages:
                    send_telegram_message(target, text)
                send_telegram_message(chat_id, f"✅ O'zgarishlar e'lon qilindi! Xabarlar soni: {len(messages)}")
            else:
                send_telegram_message(chat_id, "⚠️ Hech qanday o'zgarish aniqlanmadi!")

        elif data == "cb_menu":
            welcome = (
                f"🏰 *Salom, {username}!*\n"
                f"Xonadoningiz: *{house['house_name']}*\n"
                f"Rolingiz: *{user['role'].upper()}*\n\n"
                f"Quyidagi boshqaruv panelidan foydalaning:"
            )
            edit_telegram_message(chat_id, message_id, welcome, get_dashboard_markup(user))

        elif data == "cb_economy":
            stats = db.get_economy_stats()
            kb = types.InlineKeyboardMarkup([[types.InlineKeyboardButton("🔙 Orqaga", callback_data="cb_menu")]])
            edit_telegram_message(chat_id, message_id, stats, kb)

        elif data == "cb_help":
            send_help_message(chat_id, user, message_id)

        elif data.startswith("cb_bonus_action:"):
            parts = data.split(":")
            action = parts[1]
            amount = float(parts[2])
            
            # Check if already processed
            msg_text = call.message.text or ""
            if "qabul qilindi" in msg_text or "rad etildi" in msg_text:
                return

            if action == "accept":
                db.execute('UPDATE users SET wallet_balance = wallet_balance + %s WHERE telegram_id = %s', (amount, str(user_id)))
                db.log_transaction("CENTRAL_BANK", user_id, amount, "System Bonus Accepted")
                edit_telegram_message(chat_id, message_id, f"✅ *Bonus qabul qilindi!*\n\nBalansingizga *{amount} {house['currency_symbol']}* qo'shildi!")
            else:
                edit_telegram_message(chat_id, message_id, "❌ *Bonus rad etildi!*")

    except Exception as e:
        print(f"handle_callback_query error: {e}")

# Wire up the default message handler
@bot.message_handler(func=lambda msg: True)
def default_message_handler(msg):
    handle_bot_message(msg)
