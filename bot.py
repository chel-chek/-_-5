import telebot
from telebot import types
import sqlite3
from datetime import datetime, timedelta
import random
import time
import threading
import subprocess
import os
import urllib.request
from flask import Flask

app = Flask(__name__)

@app.route('/health')
def health():
    return 'OK', 200

TOKEN = '8786607133:AAGRlo79hTxWroCN-1vppbH9i0nCQrGS6OI'

bot = telebot.TeleBot(TOKEN)

# Константы
BUILDING_POP = {
    'business_center': 350, 'lumberjack': 300, 'construction_factory': 300,
    'university': 400, 'fabric_factory': 350, 'stables': 250, 'barracks': 0,
    'oil_rig': 300, 'iron_mine': 300, 'coal_mine': 250,
}

BUILDING_COSTS = {
    'business_center': 65, 'lumberjack': 55, 'construction_factory': 50,
    'university': 90, 'fabric_factory': 50, 'stables': 60, 'barracks': 70,
    'oil_rig': 70, 'iron_mine': 65, 'coal_mine': 70,
}

BUILDING_NAMES = {
    'business_center': 'Бизнес-центр', 'lumberjack': 'Лесопилка',
    'construction_factory': 'Стройзавод', 'university': 'Университет',
    'fabric_factory': 'Тканевый', 'stables': 'Конюшни', 'barracks': 'Казарма',
    'oil_rig': 'Нефтяная вышка', 'iron_mine': 'Жел.шахта', 'coal_mine': 'Уг.шахта',
}

BUILDING_DEPOSIT = {
    'oil_rig': 'oil', 'iron_mine': 'iron', 'coal_mine': 'coal',
}


creating_country = {}

def init_db():
    conn = sqlite3.connect('game.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS players
                 (user_id INTEGER PRIMARY KEY, username TEXT,
                  country_name TEXT DEFAULT 'Unknown', population REAL DEFAULT 1000,
                  science_points REAL DEFAULT 0, tenge REAL DEFAULT 5000,
                  iron REAL DEFAULT 0, fuel REAL DEFAULT 0, gunpowder REAL DEFAULT 0,
                  rubber REAL DEFAULT 0, fabric REAL DEFAULT 0, coal REAL DEFAULT 0,
                  cement REAL DEFAULT 0, uranium REAL DEFAULT 0, wood REAL DEFAULT 0,
                  horses REAL DEFAULT 0, special_material REAL DEFAULT 0,
                  last_collection TEXT, last_expedition TEXT, game_year REAL DEFAULT 1904)''')
    for col, t in [('created_date','TEXT'),('is_banned','INTEGER DEFAULT 0'),
                   ('is_muted','INTEGER DEFAULT 0'),('warns','INTEGER DEFAULT 0'),
                   ('last_expedition','TEXT')]:
        try: c.execute(f"ALTER TABLE players ADD COLUMN {col} {t}")
        except: pass
    c.execute('''CREATE TABLE IF NOT EXISTS cities
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                  city_name TEXT, is_capital INTEGER DEFAULT 0, is_destroyed INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS buildings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER,
                  city_id INTEGER, building_type TEXT, quantity INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS deposits
                 (user_id INTEGER, deposit_type TEXT, found INTEGER DEFAULT 1, built INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS vehicles
                 (user_id INTEGER, vehicle_name TEXT, quantity INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS vehicle_recipes
                 (vehicle_name TEXT PRIMARY KEY, iron_cost REAL, fuel_cost REAL,
                  gunpowder_cost REAL, rubber_cost REAL, fabric_cost REAL,
                  coal_cost REAL, special_material_cost REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS blueprints
                 (blueprint_name TEXT PRIMARY KEY, owner_id INTEGER, year_researched INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS blueprint_access
                 (blueprint_name TEXT, player_id INTEGER, granted_by INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS expeditions
                 (user_id INTEGER, region TEXT, end_date TEXT,
                  reward_population INTEGER, status TEXT DEFAULT 'active')''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins
                 (user_id INTEGER PRIMARY KEY, admin_level INTEGER DEFAULT 1)''')
    conn.commit()
    return conn

db_conn = init_db()

def get_player(uid):
    c = db_conn.cursor()
    c.execute("SELECT * FROM players WHERE user_id=?", (uid,))
    return c.fetchone()

def has_country(uid):
    p = get_player(uid)
    if not p or not p[2] or p[2] == 'Unknown': return False
    c = db_conn.cursor()
    c.execute("SELECT COUNT(*) FROM cities WHERE user_id=?", (uid,))
    return c.fetchone()[0] >= 5

def upd_res(uid, res, amt):
    c = db_conn.cursor()
    c.execute(f"UPDATE players SET {res}={res}+? WHERE user_id=?", (amt,uid))
    db_conn.commit()

def is_admin(uid, lvl=1):
    c = db_conn.cursor()
    c.execute("SELECT admin_level FROM admins WHERE user_id=?", (uid,))
    a = c.fetchone()
    return a and a[0] >= lvl

def get_uid(uname):
    if not uname: return None
    c = db_conn.cursor()
    c.execute("SELECT user_id FROM players WHERE username=?", (uname.replace('@',''),))
    u = c.fetchone()
    return u[0] if u else None

def count_buildings_pop(uid):
    c = db_conn.cursor()
    c.execute("SELECT building_type, SUM(quantity) FROM buildings WHERE user_id=? GROUP BY building_type", (uid,))
    total = 0
    for bt, q in c.fetchall():
        if q and bt in BUILDING_POP: total += BUILDING_POP[bt] * q
    return total

def has_deposit(uid, dt):
    c = db_conn.cursor()
    c.execute("SELECT COUNT(*) FROM deposits WHERE user_id=? AND deposit_type=? AND built=0", (uid,dt))
    return c.fetchone()[0] > 0

def use_deposit(uid, dt):
    c = db_conn.cursor()
    c.execute("UPDATE deposits SET built=1 WHERE user_id=? AND deposit_type=? AND built=0 LIMIT 1", (uid,dt))
    db_conn.commit()

def can_collect(uid):
    """Проверяет можно ли собирать доход (раз в 24 часа)"""
    p = get_player(uid)
    if not p: return True
    last = p[15]
    if not last or str(last).strip() == '' or str(last) == 'None' or str(last) == 'NULL':
        return True
    try:
        last_str = str(last).strip()
        last_dt = datetime.strptime(last_str[:19], "%Y-%m-%d %H:%M:%S")
        passed = (datetime.now() - last_dt).total_seconds()
        print(f"COLLECT CHECK: uid={uid}, last={last_str}, passed={passed/3600:.1f}h, can={passed >= 86400}")
        return passed >= 86400
    except Exception as e:
        print(f"COLLECT ERROR: {e}")
        return True

def can_expedition(uid):
    """Проверяет можно ли отправить экспедицию (раз в 72 часа)"""
    p = get_player(uid)
    if not p: return True
    last = p[16] if len(p) > 16 else None
    if not last or str(last).strip() == '' or str(last) == 'None':
        return True
    try:
        last_str = str(last).strip()
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"]:
            try:
                last_dt = datetime.strptime(last_str[:19], fmt)
                passed = (datetime.now() - last_dt).total_seconds()
                return passed >= 259200
            except:
                continue
        return True
    except:
        return True

def save_db_to_github():
    try:
        token = os.environ.get('GITHUB_TOKEN','')
        repo = os.environ.get('GITHUB_REPO','')
        if not token or not repo: return
        subprocess.run(['git','config','--global','user.email','bot@render.com'],capture_output=True)
        subprocess.run(['git','config','--global','user.name','Render Bot'],capture_output=True)
        subprocess.run(['git','add','game.db'],capture_output=True,cwd='/opt/render/project/src')
        subprocess.run(['git','commit','-m','Auto-save'],capture_output=True,cwd='/opt/render/project/src')
        subprocess.run(['git','push',f'https://{token}@github.com/{repo}.git','HEAD:main'],capture_output=True,cwd='/opt/render/project/src')
    except: pass

def keep_alive():
    while True:
        time.sleep(840)
        try:
            url = os.environ.get('RENDER_EXTERNAL_URL','')
            if url: urllib.request.urlopen(f"{url}/health",timeout=10)
        except: pass

def show_anketa(uid, tid=None):
    if tid is None: tid = uid
    p = get_player(tid)
    if not p: return "Страна не найдена"
    c = db_conn.cursor()
    c.execute("SELECT city_name, is_capital, is_destroyed FROM cities WHERE user_id=?", (tid,))
    cities = c.fetchall()
    c.execute("SELECT vehicle_name, quantity FROM vehicles WHERE user_id=? AND quantity>0", (tid,))
    veh = c.fetchall()
    yr = p[17] if len(p)>17 and p[17] else 1904
    try: yr = float(yr)
    except: yr = 1904
    used = count_buildings_pop(tid)
    free = p[3] - used
    warns = p[22] if len(p)>22 else 0
    text = f"📋 {p[2]} | {yr:.0f} год\n👤 @{p[1]}\n\n👥 {p[3]:.0f} (занято {used:.0f}, своб {free:.0f})\n💰 {p[5]:.0f} | 🔬 {p[4]:.0f}\n🔩 {p[6]:.0f} | ⛽ {p[7]:.0f} | 💥 {p[8]:.0f} | 🪨 {p[10]:.0f}\n🪵 {p[14]:.0f} | 🏗 {p[11]:.0f}"
    if warns > 0: text += f"\n⚠️ Варны: {warns}/3"
    text += f"\n\n🏙 ГОРОДА:\n"
    for nm, cap, des in cities:
        s = "⭐" if cap else "•"
        if des: s += "❌"
        text += f"{s} {nm}\n"
    if veh:
        text += f"\n📦 СКЛАД: {sum(v[1] for v in veh)} ед.\n"
        for v,q in veh[:5]: text += f"• {v}: {q}\n"
    return text

@bot.message_handler(commands=['set_head_admin'])
def set_head_admin(message):
    uid = message.from_user.id
    c = db_conn.cursor()
    c.execute("SELECT COUNT(*) FROM admins WHERE admin_level=3")
    if c.fetchone()[0] > 0:
        bot.reply_to(message, "❌ Главный админ уже назначен!"); return
    c.execute("INSERT OR REPLACE INTO admins VALUES (?,3)", (uid,))
    db_conn.commit()
    bot.reply_to(message, "✅ Вы стали ГЛАВНЫМ АДМИНОМ!")

@bot.message_handler(commands=['start'])
def start(message):
    uid = message.from_user.id
    uname = message.from_user.username or f"Player_{uid}"
    p = get_player(uid)
    if p and len(p)>20 and p[20]==1:
        bot.reply_to(message, "🚫 Вы забанены!"); return
    if p and has_country(uid):
        show_menu(message.chat.id)
        bot.send_message(message.chat.id, "🎮 С возвращением!")
        return
    c = db_conn.cursor()
    c.execute("INSERT OR REPLACE INTO players (user_id, username, created_date) VALUES (?,?,?)",
              (uid, uname, datetime.now().strftime("%Y-%m-%d")))
    db_conn.commit()
    creating_country[uid] = {'step': 'capital'}
    bot.send_message(message.chat.id, "🎮 Добро пожаловать!\nВведите название столицы:")

def show_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(row_width=3, resize_keyboard=True)
    markup.add('анкета','собрать','строить','поиск','склад','города','чертежи','эксп','помощь')
    bot.send_message(chat_id, "📋 Меню:", reply_markup=markup)

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    try:
        uid = message.from_user.id
        text = message.text.strip()
        
        if uid in creating_country:
            st = creating_country[uid]
            if st['step'] == 'capital':
                c = db_conn.cursor()
                c.execute("INSERT INTO cities (user_id, city_name, is_capital) VALUES (?,?,1)", (uid, text))
                db_conn.commit()
                st['step'] = 'cities'
                bot.send_message(message.chat.id, f"✅ Столица: {text}\nВведите 4 города через запятую:")
                return
            elif st['step'] == 'cities':
                cities = [c.strip() for c in text.split(',')]
                if len(cities) != 4:
                    bot.send_message(message.chat.id, "❌ Нужно ровно 4 города!"); return
                c = db_conn.cursor()
                for city in cities:
                    c.execute("INSERT INTO cities (user_id, city_name) VALUES (?,?)", (uid, city))
                db_conn.commit()
                st['step'] = 'country'
                bot.send_message(message.chat.id, "Введите название страны:"); return
            elif st['step'] == 'country':
                c = db_conn.cursor()
                c.execute("UPDATE players SET country_name=? WHERE user_id=?", (text, uid))
                db_conn.commit()
                del creating_country[uid]
                show_menu(uid)
                bot.send_message(message.chat.id, "🎉 СТРАНА СОЗДАНА!")
                return
        
        p = get_player(uid)
        if not p or not has_country(uid): return
        if len(p)>20 and p[20]==1: return
        if len(p)>21 and p[21]==1: bot.reply_to(message, "🔇 Вы в муте!"); return

        if text in ['анкета']: bot.reply_to(message, show_anketa(uid))
        elif text in ['собрать']: cmd_collect(message)
        elif text in ['строить','стройка']: cmd_build_menu(message)
        elif text == 'поиск': cmd_search_menu(message)
        elif text == 'склад': cmd_warehouse(message)
        elif text == 'города': cmd_cities(message)
        elif text == 'чертежи': cmd_blueprints(message)
        elif text.startswith('эксп'): cmd_expedition(message)
        elif text in ['помощь','команды']: cmd_help(message)
        elif text.startswith('крафт '): cmd_craft(message)
        elif text.startswith('разобрать ') or text.startswith('разбор '): cmd_dismantle(message)
        elif text.startswith('рецепт '): cmd_recipe(message)
        elif text.startswith('!рецепт'): cmd_create_recipe(message)
        elif any(text.startswith(w) for w in ['дот ','бункер ','каземат ']): cmd_fort(message)
        elif text.startswith('город новый '): cmd_new_city(message)
        elif text.startswith('чинить '): cmd_repair_city(message)
        elif text.startswith('столица '): cmd_move_capital(message)
        elif text.startswith('поделиться '): cmd_share_bp(message)
        elif text.startswith('разведка '): cmd_look(message)
        elif text == 'топ': cmd_top(message)
        elif text == 'мойid': bot.reply_to(message, f"Ваш ID: {uid}")
        elif text.startswith('дать '): cmd_give(message)
        elif text.startswith('забрать '): cmd_take(message)
        elif text.startswith('всем '): cmd_give_all(message)
        elif text.startswith('бан '): cmd_ban(message)
        elif text.startswith('разбан '): cmd_unban(message)
        elif text.startswith('мут '): cmd_mute(message)
        elif text.startswith('размут '): cmd_unmute(message)
        elif text.startswith('варн '): cmd_warn(message)
        elif text.startswith('снятьварн '): cmd_unwarn(message)
        elif text == 'админы': cmd_admin_list(message)
    except Exception as e:
        print(f"Ошибка: {e}")

# ==================== КОМАНДЫ С ОГРАНИЧЕНИЯМИ ====================

def cmd_collect(message):
    uid = message.from_user.id
    p = get_player(uid)
    
    if not can_collect(uid):
        bot.reply_to(message, "❌ Доход можно собирать раз в 24 часа!")
        return
    
    if len(p) > 18 and p[18] and p[18] == datetime.now().strftime("%Y-%m-%d"):
        bot.reply_to(message, "❌ Первый день страны! Доход со 2-го дня.")
        return
    
    c = db_conn.cursor()
    c.execute("SELECT b.building_type, SUM(b.quantity) FROM buildings b JOIN cities c ON b.city_id=c.id WHERE b.user_id=? AND c.is_destroyed=0 GROUP BY b.building_type", (uid,))
    bld = dict(c.fetchall())
    
    if not bld:
        bot.reply_to(message, "❌ Нет построек для дохода!")
        return
    
    inc = {}
    if 'lumberjack' in bld: inc['wood'] = 80*bld['lumberjack']
    if 'construction_factory' in bld: inc['cement'] = 100*bld['construction_factory']
    if 'university' in bld: inc['science_points'] = 2*bld['university']
    if 'business_center' in bld: inc['tenge'] = 25*bld['business_center']
    if 'iron_mine' in bld: inc['iron'] = 150*bld['iron_mine']
    if 'oil_rig' in bld: inc['fuel'] = 150*bld['oil_rig']
    if 'coal_mine' in bld: inc['coal'] = 125*bld['coal_mine']
    if 'fabric_factory' in bld: inc['fabric'] = 50*bld['fabric_factory']
    if 'stables' in bld: inc['horses'] = 20*bld['stables']
    
    for res, val in inc.items():
        upd_res(uid, res, val)
    
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("UPDATE players SET last_collection=? WHERE user_id=?", (today, uid))
    db_conn.commit()
    
    nm = {'wood':'🪵','cement':'🏗','science_points':'🔬','tenge':'💰','iron':'🔩','fuel':'⛽','coal':'🪨','fabric':'🧵','horses':'🐴'}
    text = "📊 Доход собран:\n"
    for res, val in inc.items():
        text += f"{nm.get(res,res)} +{val}\n"
    bot.reply_to(message, text)

def cmd_build_menu(message):
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton("🏢 Бизнес-центр 65💰", callback_data="b_business_center"),
           types.InlineKeyboardButton("🪓 Лесопилка 55💰", callback_data="b_lumberjack"),
           types.InlineKeyboardButton("🏗 Стройзавод 50💰", callback_data="b_construction_factory"),
           types.InlineKeyboardButton("🏫 Университет 90💰", callback_data="b_university"),
           types.InlineKeyboardButton("🧵 Тканевый 50💰", callback_data="b_fabric_factory"),
           types.InlineKeyboardButton("🐴 Конюшни 60💰", callback_data="b_stables"),
           types.InlineKeyboardButton("⚔ Казарма 70💰", callback_data="b_barracks"),
           types.InlineKeyboardButton("🛢 Нефть 70💰", callback_data="b_oil_rig"),
           types.InlineKeyboardButton("⛏ Железо 65💰", callback_data="b_iron_mine"),
           types.InlineKeyboardButton("🪨 Уголь 70💰", callback_data="b_coal_mine"))
    bot.reply_to(message, "🏗 Выберите здание:", reply_markup=mk)

def cmd_search_menu(message):
    mk = types.InlineKeyboardMarkup(row_width=2)
    mk.add(types.InlineKeyboardButton("🛢 Нефть 20💰", callback_data="s_oil"),
           types.InlineKeyboardButton("🔩 Железо 20💰", callback_data="s_iron"),
           types.InlineKeyboardButton("🪨 Уголь 20💰", callback_data="s_coal"),
           types.InlineKeyboardButton("💛 Сера 15💰", callback_data="s_sulfur"),
           types.InlineKeyboardButton("☢ Уран 100💰", callback_data="s_uranium"))
    bot.reply_to(message, "🔍 Что ищем?", reply_markup=mk)

def cmd_warehouse(message):
    c = db_conn.cursor()
    c.execute("SELECT vehicle_name, quantity FROM vehicles WHERE user_id=? AND quantity>0", (message.from_user.id,))
    items = c.fetchall()
    if not items: bot.reply_to(message, "📦 Склад пуст"); return
    text = "📦 СКЛАД:\n"
    for n,q in items: text += f"• {n}: {q}\n"
    bot.reply_to(message, text)

def cmd_cities(message):
    c = db_conn.cursor()
    c.execute("SELECT city_name, is_capital, is_destroyed FROM cities WHERE user_id=?", (message.from_user.id,))
    cities = c.fetchall()
    text = "🏙 ГОРОДА:\n"
    for nm, cap, des in cities:
        s = "⭐ " if cap else "• "
        text += f"{s}{nm}{' ❌' if des else ''}\n"
    bot.reply_to(message, text)

def cmd_blueprints(message):
    c = db_conn.cursor()
    c.execute("SELECT blueprint_name FROM blueprints WHERE owner_id=?", (message.from_user.id,))
    own = c.fetchall()
    text = "📋 ЧЕРТЕЖИ:\n"
    if own: text += "\n".join([f"• {b[0]}" for b in own])
    else: text += "Нет чертежей"
    bot.reply_to(message, text)

def cmd_expedition(message):
    uid = message.from_user.id
    if not can_expedition(uid):
        bot.reply_to(message, "❌ Экспедиция доступна раз в 3 дня!")
        return
    mk = types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("🌍 Европа +200", callback_data="e_europe"),
           types.InlineKeyboardButton("🏯 Азия +200", callback_data="e_asia"),
           types.InlineKeyboardButton("🌴 Африка +225", callback_data="e_africa"),
           types.InlineKeyboardButton("🌎 Сев.Америка +200", callback_data="e_america_north"),
           types.InlineKeyboardButton("🌎 Юж.Америка +200", callback_data="e_america_south"),
           types.InlineKeyboardButton("🦘 Австралия +175", callback_data="e_australia"))
    bot.reply_to(message, "🌍 Куда? (70💰, раз в 3 дня)", reply_markup=mk)

def cmd_help(message):
    bot.reply_to(message, "📖 КОМАНДЫ: анкета, собрать, строить, поиск, склад, города, чертежи, эксп, помощь\nкрафт X НАЗВАНИЕ, разобрать X НАЗВАНИЕ, рецепт НАЗВАНИЕ\n!рецепт НАЗВАНИЕ | vehicle | вес | лс | порох | колёса | сверхтяж | уголь | броня\nдать @игрок ресурс кол-во (админ)")

def cmd_craft(message):
    uid = message.from_user.id
    try:
        parts = message.text.replace('крафт ','',1).split(' ',1)
        qty = int(parts[0]); name = parts[1].upper()
        c = db_conn.cursor()
        c.execute("SELECT * FROM vehicle_recipes WHERE vehicle_name=?", (name,))
        rec = c.fetchone()
        if not rec: bot.reply_to(message, f"❌ Нет рецепта!"); return
        p = get_player(uid)
        iron = rec[1]*qty; fuel = rec[2]*qty; gp = rec[3]*qty
        if p[6] < iron: bot.reply_to(message, f"❌ Нужно {iron:.0f}🔩"); return
        if p[7] < fuel: bot.reply_to(message, f"❌ Нужно {fuel:.0f}⛽"); return
        if p[8] < gp: bot.reply_to(message, f"❌ Нужно {gp:.0f}💥"); return
        upd_res(uid,'iron',-iron); upd_res(uid,'fuel',-fuel); upd_res(uid,'gunpowder',-gp)
        c.execute("SELECT quantity FROM vehicles WHERE user_id=? AND vehicle_name=?", (uid,name))
        have = c.fetchone()
        if have: c.execute("UPDATE vehicles SET quantity=quantity+? WHERE user_id=? AND vehicle_name=?", (qty,uid,name))
        else: c.execute("INSERT INTO vehicles (user_id, vehicle_name, quantity) VALUES (?,?,?)", (uid,name,qty))
        db_conn.commit()
        bot.reply_to(message, f"✅ {qty}x {name}")
    except: bot.reply_to(message, "❌ крафт X НАЗВАНИЕ")

def cmd_dismantle(message):
    uid = message.from_user.id
    try:
        text = message.text
        for p in ['разобрать ','разбор ']:
            if text.startswith(p): text = text.replace(p,'',1); break
        parts = text.split(' ',1)
        qty = int(parts[0]); name = parts[1].upper()
        c = db_conn.cursor()
        c.execute("SELECT quantity FROM vehicles WHERE user_id=? AND vehicle_name=?", (uid,name))
        have = c.fetchone()
        if not have or have[0] < qty: bot.reply_to(message, f"❌ Есть: {have[0] if have else 0}"); return
        c.execute("SELECT * FROM vehicle_recipes WHERE vehicle_name=?", (name,))
        rec = c.fetchone()
        if not rec: bot.reply_to(message, "❌ Рецепт не найден!"); return
        upd_res(uid,'iron',rec[1]*qty); upd_res(uid,'fuel',rec[2]*qty); upd_res(uid,'gunpowder',rec[3]*qty)
        c.execute("UPDATE vehicles SET quantity=quantity-? WHERE user_id=? AND vehicle_name=?", (qty,uid,name))
        db_conn.commit()
        bot.reply_to(message, f"♻ {qty}x {name}")
    except: bot.reply_to(message, "❌ разобрать X НАЗВАНИЕ")

def cmd_recipe(message):
    try:
        name = message.text.replace('рецепт ','',1).upper()
        c = db_conn.cursor()
        c.execute("SELECT * FROM vehicle_recipes WHERE vehicle_name=?", (name,))
        rec = c.fetchone()
        if not rec: bot.reply_to(message, "❌ Не найден!"); return
        bot.reply_to(message, f"📋 {name}:\n🔩 {rec[1]:.1f}\n⛽ {rec[2]:.1f}\n💥 {rec[3]:.1f}")
    except: bot.reply_to(message, "рецепт НАЗВАНИЕ")

def cmd_create_recipe(message):
    try:
        text = message.text.replace('!рецепт ','')
        parts = [p.strip() for p in text.split('|')]
        name = parts[0].upper(); weight = float(parts[2]); power = float(parts[3]); gp_grams = float(parts[4])
        wheels = parts[5].lower()=='да' if len(parts)>5 else False
        super_heavy = parts[6].lower()=='да' if len(parts)>6 else False
        coal_pow = parts[7].lower()=='да' if len(parts)>7 else False
        iron = weight * 2
        if gp_grams >= 500: gp = gp_grams/500
        elif gp_grams >= 100: gp = gp_grams/100
        else: gp = gp_grams/50
        fuel = 0 if coal_pow else power/50
        coal = power/50 if coal_pow else 0
        rubber = 1 if wheels else 0
        if super_heavy:
            if weight > 35000: d = 35
            elif weight > 20000: d = 25
            elif weight > 10000: d = 20
            elif weight > 5000: d = 10
            elif weight > 3000: d = 8
            elif weight > 900: d = 6
            else: d = 1
            iron /= d; fuel /= d; coal /= d
        if gp_grams > 200000: gp /= 8
        elif gp_grams > 100000: gp /= 5
        elif gp_grams > 50000: gp /= 3
        elif gp_grams > 25000: gp /= 2
        c = db_conn.cursor()
        c.execute("INSERT OR REPLACE INTO vehicle_recipes VALUES (?,?,?,?,?,?,?,?)",
                  (name,iron,fuel,gp,rubber,0,coal,0))
        db_conn.commit()
        bot.reply_to(message, f"✅ Рецепт {name}:\n🔩 {iron:.1f}\n⛽ {fuel:.1f}\n💥 {gp:.1f}")
    except: bot.reply_to(message, "❌ !рецепт НАЗВАНИЕ | vehicle | вес | лс | порох | колёса | сверхтяж | уголь | броня")

def cmd_fort(message):
    try:
        parts = message.text.split()
        ftype = parts[0]; armor = parts[1].upper(); city = ' '.join(parts[2:])
        costs = {'A':(85,30),'B':(65,25),'C':(45,20),'D':(25,15)}
        if armor not in costs: bot.reply_to(message, "❌ Классы: A,B,C,D"); return
        cem, wood = costs[armor]
        p = get_player(message.from_user.id)
        if p[11] < cem: bot.reply_to(message, f"❌ Нужно {cem}🏗"); return
        if p[14] < wood: bot.reply_to(message, f"❌ Нужно {wood}🪵"); return
        upd_res(message.from_user.id,'cement',-cem); upd_res(message.from_user.id,'wood',-wood)
        bot.reply_to(message, f"✅ {ftype} {armor} в {city}!")
    except: bot.reply_to(message, "дот КЛАСС Город")

def cmd_new_city(message):
    try:
        name = message.text.replace('город новый ','',1)
        uid = message.from_user.id
        p = get_player(uid)
        if p[14] < 850: bot.reply_to(message, "❌ 850🪵"); return
        if p[11] < 1000: bot.reply_to(message, "❌ 1000🏗"); return
        if p[5] < 350: bot.reply_to(message, "❌ 350💰"); return
        upd_res(uid,'wood',-850); upd_res(uid,'cement',-1000); upd_res(uid,'tenge',-350)
        c = db_conn.cursor()
        c.execute("INSERT INTO cities (user_id, city_name) VALUES (?,?)", (uid,name))
        db_conn.commit()
        bot.reply_to(message, f"✅ Город {name}!")
    except: bot.reply_to(message, "город новый Название")

def cmd_repair_city(message):
    try:
        name = message.text.replace('чинить ','',1)
        p = get_player(message.from_user.id)
        if p[14] < 500: bot.reply_to(message, "❌ 500🪵"); return
        if p[11] < 800: bot.reply_to(message, "❌ 800🏗"); return
        if p[5] < 350: bot.reply_to(message, "❌ 350💰"); return
        upd_res(message.from_user.id,'wood',-500); upd_res(message.from_user.id,'cement',-800); upd_res(message.from_user.id,'tenge',-350)
        c = db_conn.cursor()
        c.execute("UPDATE cities SET is_destroyed=0 WHERE user_id=? AND city_name=?", (message.from_user.id,name))
        db_conn.commit()
        bot.reply_to(message, f"✅ {name} восстановлен!")
    except: bot.reply_to(message, "чинить Название")

def cmd_move_capital(message):
    try:
        name = message.text.replace('столица ','',1)
        c = db_conn.cursor()
        c.execute("UPDATE cities SET is_capital=0 WHERE user_id=? AND is_capital=1", (message.from_user.id,))
        c.execute("UPDATE cities SET is_capital=1 WHERE user_id=? AND city_name=?", (message.from_user.id,name))
        db_conn.commit()
        bot.reply_to(message, f"⭐ Столица → {name}")
    except: bot.reply_to(message, "столица Название")

def cmd_share_bp(message):
    try:
        parts = message.text.replace('поделиться ','',1).split()
        bp = parts[0].upper(); tid = get_uid(parts[1].replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("SELECT owner_id FROM blueprints WHERE blueprint_name=?", (bp,))
        own = c.fetchone()
        if not own or own[0] != message.from_user.id: bot.reply_to(message, "❌ Не владелец!"); return
        c.execute("INSERT OR IGNORE INTO blueprint_access VALUES (?,?,?)", (bp,tid,message.from_user.id))
        db_conn.commit()
        bot.reply_to(message, f"✅ {bp} → @{parts[1].replace('@','')}")
    except: bot.reply_to(message, "поделиться НАЗВАНИЕ @игрок")

def cmd_look(message):
    try:
        tid = get_uid(message.text.replace('разведка ','',1).replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        bot.reply_to(message, show_anketa(message.from_user.id, tid))
    except: bot.reply_to(message, "разведка @игрок")

def cmd_top(message):
    c = db_conn.cursor()
    c.execute("SELECT username, country_name, tenge FROM players WHERE is_banned=0 ORDER BY tenge DESC LIMIT 10")
    text = "🏆 ТОП-10:\n"
    for i,(un,cn,tg) in enumerate(c.fetchall(),1): text += f"{i}. {cn} — {tg:.0f}💰\n"
    bot.reply_to(message, text)

def cmd_give(message):
    if not is_admin(message.from_user.id): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        parts = message.text.replace('дать ','',1).split()
        tid = get_uid(parts[0].replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        if tid == message.from_user.id: bot.reply_to(message, "❌ Нельзя себе!"); return
        res = parts[1].lower(); amt = float(parts[2])
        if res not in RESOURCES: bot.reply_to(message, "❌ Ресурс не найден!"); return
        upd_res(tid, RESOURCES[res], amt)
        bot.reply_to(message, f"✅ +{amt} {res}")
    except: bot.reply_to(message, "дать @игрок тенге 500")

def cmd_take(message):
    if not is_admin(message.from_user.id): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        parts = message.text.replace('забрать ','',1).split()
        tid = get_uid(parts[0].replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        res = parts[1].lower(); amt = float(parts[2])
        if res not in RESOURCES: bot.reply_to(message, "❌ Ресурс не найден!"); return
        upd_res(tid, RESOURCES[res], -amt)
        bot.reply_to(message, f"✅ -{amt} {res}")
    except: bot.reply_to(message, "забрать @игрок тенге 500")

def cmd_give_all(message):
    if not is_admin(message.from_user.id, 3): bot.reply_to(message, "❌ Главный админ!"); return
    try:
        parts = message.text.replace('всем ','',1).split()
        res = parts[0].lower(); amt = float(parts[1])
        if res not in RESOURCES: bot.reply_to(message, "❌ Ресурс не найден!"); return
        c = db_conn.cursor()
        c.execute("SELECT user_id FROM players WHERE is_banned=0")
        for (uid,) in c.fetchall(): upd_res(uid, RESOURCES[res], amt)
        bot.reply_to(message, f"✅ Всем +{amt} {res}")
    except: bot.reply_to(message, "всем тенге 1000")

def cmd_ban(message):
    if not is_admin(message.from_user.id, 2): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        parts = message.text.split()
        tid = get_uid(parts[1].replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("DELETE FROM cities WHERE user_id=?", (tid,))
        c.execute("DELETE FROM buildings WHERE user_id=?", (tid,))
        c.execute("DELETE FROM vehicles WHERE user_id=?", (tid,))
        c.execute("UPDATE players SET is_banned=1 WHERE user_id=?", (tid,))
        db_conn.commit()
        bot.reply_to(message, f"🚫 @{parts[1].replace('@','')} забанен!")
    except: bot.reply_to(message, "бан @игрок")

def cmd_unban(message):
    if not is_admin(message.from_user.id, 2): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        parts = message.text.split()
        tid = get_uid(parts[1].replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("UPDATE players SET is_banned=0 WHERE user_id=?", (tid,))
        db_conn.commit()
        bot.reply_to(message, f"✅ @{parts[1].replace('@','')} разбанен!")
    except: bot.reply_to(message, "разбан @игрок")

def cmd_mute(message):
    if not is_admin(message.from_user.id, 1): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        parts = message.text.split()
        tid = get_uid(parts[1].replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("UPDATE players SET is_muted=1 WHERE user_id=?", (tid,))
        db_conn.commit()
        bot.reply_to(message, f"🔇 @{parts[1].replace('@','')} в муте!")
    except: bot.reply_to(message, "мут @игрок")

def cmd_unmute(message):
    if not is_admin(message.from_user.id, 1): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        parts = message.text.split()
        tid = get_uid(parts[1].replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("UPDATE players SET is_muted=0 WHERE user_id=?", (tid,))
        db_conn.commit()
        bot.reply_to(message, f"🔊 @{parts[1].replace('@','')} размучен!")
    except: bot.reply_to(message, "размут @игрок")

def cmd_warn(message):
    if not is_admin(message.from_user.id, 1): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        parts = message.text.split()
        tid = get_uid(parts[1].replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("UPDATE players SET warns=warns+1 WHERE user_id=?", (tid,))
        db_conn.commit()
        bot.reply_to(message, f"⚠️ @{parts[1].replace('@','')} получил варн!")
    except: bot.reply_to(message, "варн @игрок")

def cmd_unwarn(message):
    if not is_admin(message.from_user.id, 1): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        parts = message.text.split()
        tid = get_uid(parts[1].replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("UPDATE players SET warns=MAX(0,warns-1) WHERE user_id=?", (tid,))
        db_conn.commit()
        bot.reply_to(message, f"✅ Варн снят!")
    except: bot.reply_to(message, "снятьварн @игрок")

def cmd_admin_list(message):
    c = db_conn.cursor()
    c.execute("SELECT a.admin_level, p.username FROM admins a JOIN players p ON a.user_id=p.user_id")
    lvls = {1:'Модер',2:'Админ',3:'Главный'}
    text = "👑 АДМИНЫ:\n"
    for lvl, un in c.fetchall(): text += f"• @{un} — {lvls.get(lvl,lvl)}\n"
    bot.reply_to(message, text)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    uid = call.from_user.id
    p = get_player(uid)
    if not p or not has_country(uid):
        bot.answer_callback_query(call.id, "❌ Ай-яй-яй, так нельзя!")
        return
    data = call.data
    
    if data.startswith('b_'):
        bt = data[2:]
        if bt in BUILDING_COSTS:
            cost = BUILDING_COSTS[bt]
            if p[5] < cost: bot.answer_callback_query(call.id, f"❌ {cost}💰"); return
            if bt in BUILDING_DEPOSIT and not has_deposit(uid, BUILDING_DEPOSIT[bt]):
                bot.answer_callback_query(call.id, "❌ Сначала найдите месторождение!"); return
            if bt in BUILDING_POP and BUILDING_POP[bt] > 0:
                free = p[3] - count_buildings_pop(uid)
                if free < BUILDING_POP[bt]:
                    bot.answer_callback_query(call.id, f"❌ Нужно {BUILDING_POP[bt]}👥"); return
            upd_res(uid,'tenge',-cost)
            if bt in BUILDING_DEPOSIT: use_deposit(uid, BUILDING_DEPOSIT[bt])
            c = db_conn.cursor()
            c.execute("SELECT id FROM cities WHERE user_id=? AND is_destroyed=0 ORDER BY is_capital DESC LIMIT 1", (uid,))
            city = c.fetchone()
            if city:
                c.execute("SELECT quantity FROM buildings WHERE user_id=? AND city_id=? AND building_type=?", (uid,city[0],bt))
                have = c.fetchone()
                if have: c.execute("UPDATE buildings SET quantity=quantity+1 WHERE user_id=? AND city_id=? AND building_type=?", (uid,city[0],bt))
                else: c.execute("INSERT INTO buildings (user_id, city_id, building_type) VALUES (?,?,?)", (uid,city[0],bt))
            db_conn.commit()
            bot.answer_callback_query(call.id, f"✅ {BUILDING_NAMES.get(bt,bt)}")
            bot.send_message(call.message.chat.id, f"✅ {BUILDING_NAMES.get(bt,bt)} (-{cost}💰)")
    
    elif data.startswith('s_'):
        dep = data[2:]
        costs = {'oil':20,'iron':20,'coal':20,'sulfur':15,'uranium':100}
        if dep in costs:
            if p[5] < costs[dep]:
                bot.answer_callback_query(call.id, f"❌ Нужно {costs[dep]}💰"); return
            upd_res(uid,'tenge',-costs[dep])
            if dep == 'uranium':
                ok = random.randint(1, 5) == 1
            else:
                ok = random.random() < 0.5
            if ok:
                c = db_conn.cursor()
                c.execute("INSERT OR IGNORE INTO deposits (user_id, deposit_type) VALUES (?,?)", (uid,dep))
                db_conn.commit()
                bot.answer_callback_query(call.id, "✅ Найдено!")
                bot.send_message(call.message.chat.id, "✅ Месторождение найдено!")
            else:
                bot.answer_callback_query(call.id, "❌ Пусто")
                bot.send_message(call.message.chat.id, "❌ Ничего не найдено.")
    
    elif data.startswith('e_'):
        uid = call.from_user.id
        if not can_expedition(uid):
            bot.answer_callback_query(call.id, "❌ Экспедиция раз в 3 дня!")
            return
        reg = data[2:]
        rewards = {'europe':200,'asia':200,'africa':225,'america_north':200,'america_south':200,'australia':175}
        names = {'europe':'Европа','asia':'Азия','africa':'Африка','america_north':'Сев.Америка','america_south':'Юж.Америка','australia':'Австралия'}
        p = get_player(uid)
        if p[5] < 70:
            bot.answer_callback_query(call.id, "❌ Нужно 70💰"); return
        upd_res(uid,'tenge',-70)
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c = db_conn.cursor()
        c.execute("UPDATE players SET last_expedition=? WHERE user_id=?", (today, uid))
        end = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        c.execute("INSERT INTO expeditions (user_id, region, end_date, reward_population) VALUES (?,?,?,?)",
                  (uid, reg, end, rewards[reg]))
        db_conn.commit()
        bot.answer_callback_query(call.id, f"✅ {names.get(reg,reg)}!")
        bot.send_message(call.message.chat.id, f"🌍 Экспедиция в {names.get(reg,reg)} отправлена! +{rewards[reg]}👥 через 3 дня.")

if __name__ == '__main__':
    print("🤖 Бот запущен!")
    
    def run_web():
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
    
    threading.Thread(target=run_web, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=save_db_to_github, daemon=True).start()
    
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)
