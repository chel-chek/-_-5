import telebot
from telebot import types
import sqlite3
from datetime import datetime, timedelta
import random
import time
import threading
import os
import subprocess
import urllib.request
from flask import Flask

app = Flask(__name__)

@app.route('/health')
def health():
    return 'OK', 200

TOKEN = os.environ.get('BOT_TOKEN', '')

bot = telebot.TeleBot(TOKEN)

# ==================== КОНСТАНТЫ ====================
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

RESOURCES = {
    'тенге':'tenge','железо':'iron','топливо':'fuel','порох':'gunpowder',
    'резина':'rubber','ткань':'fabric','уголь':'coal','цемент':'cement',
    'уран':'uranium','дерево':'wood','кони':'horses','наука':'science_points',
    'население':'population','спецматериал':'special_material'
}

RESOURCE_NAMES = {
    'tenge':'💰Тенге','iron':'🔩Железо','fuel':'⛽Топливо','gunpowder':'💥Порох',
    'rubber':'🛢Резина','fabric':'🧵Ткань','coal':'🪨Уголь','cement':'🏗Цемент',
    'uranium':'☢Уран','wood':'🪵Дерево','horses':'🐴Кони',
    'science_points':'🔬Наука','population':'👥Население','special_material':'⚗Спецматериал'
}

creating_country = {}
capture_requests = {}

# ==================== БАЗА ДАННЫХ ====================
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
                  last_collection TEXT, last_expedition TEXT, created_date TEXT)''')
    
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
                 (blueprint_name TEXT PRIMARY KEY, owner_id INTEGER)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS blueprint_access
                 (blueprint_name TEXT, player_id INTEGER, granted_by INTEGER)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS expeditions
                 (user_id INTEGER, region TEXT, end_date TEXT,
                  reward_population INTEGER, status TEXT DEFAULT 'active')''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS admins
                 (user_id INTEGER PRIMARY KEY, admin_level INTEGER DEFAULT 1)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS action_log
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER, action_type TEXT, details TEXT,
                  resources TEXT, timestamp TEXT, can_rollback INTEGER DEFAULT 1)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS market
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  seller_id INTEGER, item_type TEXT, item_name TEXT,
                  quantity REAL, timestamp TEXT, active INTEGER DEFAULT 1)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS wars
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  attacker_id INTEGER, defender_id INTEGER,
                  status TEXT DEFAULT 'active', start_date TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS default_resources
                 (resource_name TEXT PRIMARY KEY, default_value REAL)''')
    
    defaults = [('population',1000),('tenge',5000),('science_points',0),('iron',0),('fuel',0),
                ('gunpowder',0),('rubber',0),('fabric',0),('coal',0),('cement',0),
                ('uranium',0),('wood',0),('horses',0),('special_material',0)]
    for res, val in defaults:
        c.execute("INSERT OR IGNORE INTO default_resources VALUES (?,?)", (res,val))
    
    conn.commit()
    return conn

db_conn = init_db()

# ==================== ФУНКЦИИ ====================
def get_player(uid):
    try:
        c = db_conn.cursor()
        c.execute("SELECT * FROM players WHERE user_id=?", (uid,))
        return c.fetchone()
    except: return None

def get_username(uid):
    p = get_player(uid)
    return f"@{p[1]}" if p else f"ID:{uid}"

def has_country(uid):
    try:
        p = get_player(uid)
        if not p or not p[2] or p[2] == 'Unknown': return False
        c = db_conn.cursor()
        c.execute("SELECT COUNT(*) FROM cities WHERE user_id=?", (uid,))
        return c.fetchone()[0] >= 5
    except: return False

def upd_res(uid, res, amt):
    try:
        c = db_conn.cursor()
        c.execute(f"UPDATE players SET {res}={res}+? WHERE user_id=?", (amt,uid))
        db_conn.commit()
    except: pass

def is_admin(uid, lvl=1):
    try:
        c = db_conn.cursor()
        c.execute("SELECT admin_level FROM admins WHERE user_id=?", (uid,))
        a = c.fetchone()
        return a and a[0] >= lvl
    except: return False

def get_uid(uname):
    if not uname: return None
    try:
        c = db_conn.cursor()
        c.execute("SELECT user_id FROM players WHERE username=?", (uname.replace('@',''),))
        u = c.fetchone()
        return u[0] if u else None
    except: return None

def count_buildings_pop(uid):
    try:
        c = db_conn.cursor()
        c.execute("SELECT building_type, SUM(quantity) FROM buildings WHERE user_id=? GROUP BY building_type", (uid,))
        total = 0
        for bt, q in c.fetchall():
            if q and bt in BUILDING_POP: total += BUILDING_POP[bt] * q
        return total
    except: return 0

def has_deposit(uid, dt):
    try:
        c = db_conn.cursor()
        c.execute("SELECT COUNT(*) FROM deposits WHERE user_id=? AND deposit_type=? AND built=0", (uid,dt))
        return c.fetchone()[0] > 0
    except: return False

def use_deposit(uid, dt):
    try:
        c = db_conn.cursor()
        c.execute("UPDATE deposits SET built=1 WHERE user_id=? AND deposit_type=? AND built=0 LIMIT 1", (uid,dt))
        db_conn.commit()
    except: pass

def can_collect_income(uid):
    try:
        c = db_conn.cursor()
        c.execute("SELECT last_collection FROM players WHERE user_id=?", (uid,))
        row = c.fetchone()
        if not row or not row[0]: return True, 1, None
        last_str = str(row[0])
        if ' ' in last_str: last_dt = datetime.strptime(last_str[:19], "%Y-%m-%d %H:%M:%S")
        else: last_dt = datetime.strptime(last_str[:10], "%Y-%m-%d")
        passed = (datetime.now() - last_dt).total_seconds()
        if passed < 86400:
            remaining = 86400 - passed
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            return False, 0, f"{hours}ч {minutes}мин"
        multiplier = int(passed // 86400)
        return True, multiplier, None
    except: return True, 1, None

def can_collect_expedition(uid):
    """Экспедиция: раз в 72 часа, БЕЗ накопления"""
    try:
        p = get_player(uid)
        if not p: return True, None
        last = p[16]
        if not last or str(last) in ['0', '0.0', 'None', 'NULL', '']: return True, None
        last_dt = datetime.strptime(str(last)[:19], "%Y-%m-%d %H:%M:%S")
        passed = (datetime.now() - last_dt).total_seconds()
        if passed >= 259200: return True, None
        remaining = 259200 - passed
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        return False, f"{hours}ч {minutes}мин"
    except: return True, None

def get_buildings_income(uid):
    try:
        c = db_conn.cursor()
        c.execute("SELECT b.building_type, SUM(b.quantity) FROM buildings b JOIN cities ct ON b.city_id=ct.id WHERE b.user_id=? AND ct.is_destroyed=0 GROUP BY b.building_type", (uid,))
        bld = dict(c.fetchall())
        income = {'tenge': 0, 'wood': 0, 'cement': 0, 'science_points': 0, 'iron': 0, 'fuel': 0, 'coal': 0, 'fabric': 0, 'horses': 0}
        if 'business_center' in bld: income['tenge'] += 25 * bld['business_center']
        if 'lumberjack' in bld: income['wood'] += 80 * bld['lumberjack']
        if 'construction_factory' in bld: income['cement'] += 100 * bld['construction_factory']
        if 'university' in bld: income['science_points'] += 2 * bld['university']
        if 'iron_mine' in bld: income['iron'] += 150 * bld['iron_mine']
        if 'oil_rig' in bld: income['fuel'] += 150 * bld['oil_rig']
        if 'coal_mine' in bld: income['coal'] += 125 * bld['coal_mine']
        if 'fabric_factory' in bld: income['fabric'] += 50 * bld['fabric_factory']
        if 'stables' in bld: income['horses'] += 20 * bld['stables']
        return income
    except: return {'tenge': 0, 'wood': 0, 'cement': 0, 'science_points': 0, 'iron': 0, 'fuel': 0, 'coal': 0, 'fabric': 0, 'horses': 0}

def log_action(uid, action_type, details, resources=""):
    try:
        c = db_conn.cursor()
        c.execute("INSERT INTO action_log (user_id, action_type, details, resources, timestamp) VALUES (?,?,?,?,?)",
                  (uid, action_type, str(details)[:200], str(resources)[:200], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        db_conn.commit()
        return c.lastrowid
    except: return None

def get_city_count(uid):
    c = db_conn.cursor()
    c.execute("SELECT COUNT(*) FROM cities WHERE user_id=?", (uid,))
    return c.fetchone()[0]

def calculate_capitulation(defender_id):
    city_count = get_city_count(defender_id)
    c = db_conn.cursor()
    c.execute("SELECT COUNT(*) FROM cities WHERE user_id=? AND is_destroyed=1", (defender_id,))
    destroyed = c.fetchone()[0]
    if city_count <= 5: return 100 if destroyed >= 1 else 0
    elif city_count <= 10: return min(50 + (destroyed - 1) * 25, 100) if destroyed >= 1 else 0
    elif city_count <= 20: return min(25 + (destroyed - 1) * 16.6, 100) if destroyed >= 1 else 0
    elif city_count <= 25: return min(destroyed * 7.5, 100)
    else: return min(destroyed * 7, 100)

def save_db_to_github():
    while True:
        time.sleep(1800)
        try:
            token = os.environ.get('GITHUB_TOKEN','')
            repo = os.environ.get('GITHUB_REPO','')
            if not token or not repo: continue
            subprocess.run(['git','config','--global','user.email','bot@render.com'],capture_output=True)
            subprocess.run(['git','config','--global','user.name','Render Bot'],capture_output=True)
            subprocess.run(['git','add','game.db'],capture_output=True,cwd='/opt/render/project/src')
            subprocess.run(['git','commit','-m','Auto-save database'],capture_output=True,cwd='/opt/render/project/src')
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
    try:
        if tid is None: tid = uid
        p = get_player(tid)
        if not p: return "❌ Страна не найдена"
        c = db_conn.cursor()
        c.execute("SELECT city_name, is_capital, is_destroyed FROM cities WHERE user_id=?", (tid,))
        cities = c.fetchall()
        c.execute("SELECT building_type, SUM(quantity) FROM buildings WHERE user_id=? GROUP BY building_type", (tid,))
        buildings = dict(c.fetchall())
        c.execute("SELECT vehicle_name, quantity FROM vehicles WHERE user_id=? AND quantity>0 ORDER BY vehicle_name", (tid,))
        veh = c.fetchall()
        income = get_buildings_income(tid)
        used = count_buildings_pop(tid)
        free = p[3] - used
        city_count = get_city_count(tid)
        cap_progress = calculate_capitulation(tid)
        
        text = f"""
╔══════════════════════════════╗
║  🏴 {p[2]}
║  👤 @{p[1]}
╚══════════════════════════════╝

👥 Население: {p[3]:.0f}
   (занято: {used:.0f} | свободно: {free:.0f})

💰 Ресурсы:
   💰 Тенге: {p[5]:.0f}
   🔩 Железо: {p[6]:.0f} | ⛽ Топливо: {p[7]:.0f}
   💥 Порох: {p[8]:.0f} | 🪨 Уголь: {p[10]:.0f}
   🪵 Дерево: {p[14]:.0f} | 🏗 Цемент: {p[11]:.0f}
   🧵 Ткань: {p[9]:.0f} | 🐴 Кони: {p[15]:.0f}
   🔬 Наука: {p[4]:.0f}

🏗 Здания:
"""
        if buildings:
            for bt, qty in buildings.items():
                if qty > 0: text += f"   {BUILDING_NAMES.get(bt, bt)}: {qty} шт.\n"
        else: text += "   Нет построек\n"
        
        text += f"\n🏙 Города: ({city_count})\n"
        for nm, cap_flag, des in cities:
            s = "⭐" if cap_flag else "•"
            if des: s += "❌"
            text += f"   {s} {nm}\n"
        
        if cap_progress > 0:
            text += f"\n⚠️ Капитуляция: {cap_progress:.1f}%\n"
        
        text += f"\n📦 Техника: {sum(v[1] for v in veh) if veh else 0} ед.\n"
        if veh:
            for v, q in veh[:10]:
                text += f"   • {v}: {q}\n"
        
        text += f"""
📈 Доход в день:
   💰{income['tenge']} 🪵{income['wood']} 🏗{income['cement']}
   🔩{income['iron']} ⛽{income['fuel']} 🪨{income['coal']}
   🔬{income['science_points']} 🧵{income['fabric']} 🐴{income['horses']}
"""
        return text
    except Exception as e:
        print(f"Ошибка анкеты: {e}")
        return "❌ Ошибка загрузки профиля"

def build_direct(message, bt):
    try:
        uid = message.from_user.id
        p = get_player(uid)
        uname = get_username(uid)
        if not p or not has_country(uid):
            bot.reply_to(message, f"{uname} ❌ Нет страны!"); return
        if bt not in BUILDING_COSTS:
            bot.reply_to(message, f"{uname} ❌ Неизвестное здание!"); return
        cost = BUILDING_COSTS[bt]
        if p[5] < cost:
            bot.reply_to(message, f"{uname} ❌ Нужно {cost}💰 (у вас {p[5]:.0f})"); return
        if bt in BUILDING_DEPOSIT and not has_deposit(uid, BUILDING_DEPOSIT[bt]):
            bot.reply_to(message, f"{uname} ❌ Сначала найдите месторождение!"); return
        if bt in BUILDING_POP and BUILDING_POP[bt] > 0:
            free = p[3] - count_buildings_pop(uid)
            if free < BUILDING_POP[bt]:
                bot.reply_to(message, f"{uname} ❌ Нужно {BUILDING_POP[bt]}👥 (свободно {free:.0f})"); return
        upd_res(uid, 'tenge', -cost)
        if bt in BUILDING_DEPOSIT: use_deposit(uid, BUILDING_DEPOSIT[bt])
        c = db_conn.cursor()
        c.execute("SELECT id FROM cities WHERE user_id=? AND is_destroyed=0 ORDER BY is_capital DESC LIMIT 1", (uid,))
        city = c.fetchone()
        if city:
            c.execute("SELECT quantity FROM buildings WHERE user_id=? AND city_id=? AND building_type=?", (uid, city[0], bt))
            have = c.fetchone()
            if have: c.execute("UPDATE buildings SET quantity=quantity+1 WHERE user_id=? AND city_id=? AND building_type=?", (uid, city[0], bt))
            else: c.execute("INSERT INTO buildings (user_id, city_id, building_type) VALUES (?,?,?)", (uid, city[0], bt))
        db_conn.commit()
        log_action(uid, 'build', f"{BUILDING_NAMES.get(bt, bt)}", f"tenge:{cost}")
        bot.reply_to(message, f"{uname} ✅ Построено: {BUILDING_NAMES.get(bt, bt)} (-{cost}💰)")
    except Exception as e:
        print(f"Ошибка build_direct: {e}")
        bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Ошибка при постройке!")

# ==================== КОМАНДЫ БОТА ====================
@bot.message_handler(commands=['set_head_admin'])
def set_head_admin(message):
    try:
        uid = message.from_user.id
        c = db_conn.cursor()
        c.execute("SELECT COUNT(*) FROM admins WHERE admin_level=3")
        if c.fetchone()[0] > 0:
            bot.reply_to(message, "❌ Главный админ уже назначен!"); return
        c.execute("INSERT OR REPLACE INTO admins VALUES (?,3)", (uid,))
        db_conn.commit()
        bot.reply_to(message, f"{get_username(uid)} ✅ Вы стали ГЛАВНЫМ АДМИНОМ!")
    except: bot.reply_to(message, "❌ Ошибка!")

@bot.message_handler(commands=['start'])
def start(message):
    try:
        uid = message.from_user.id
        uname = get_username(uid)
        p = get_player(uid)
        if p and has_country(uid):
            show_menu(message.chat.id)
            bot.send_message(message.chat.id, f"{uname} 🎮 С возвращением!")
            return
        c = db_conn.cursor()
        c.execute("INSERT OR REPLACE INTO players (user_id, username, created_date) VALUES (?,?,?)",
                  (uid, message.from_user.username or f"Player_{uid}", datetime.now().strftime("%Y-%m-%d")))
        db_conn.commit()
        creating_country[uid] = {'step': 'capital'}
        bot.send_message(message.chat.id, f"{uname} 🎮 Добро пожаловать!\nВведите название столицы:")
    except: bot.reply_to(message, "❌ Ошибка! Попробуйте /start ещё раз.")

def show_menu(chat_id):
    try:
        markup = types.ReplyKeyboardMarkup(row_width=3, resize_keyboard=True)
        markup.add('проф','собрать','строить','поиск','склад','города','чертежи','эксп','помощь')
        bot.send_message(chat_id, "📋 Меню:", reply_markup=markup)
    except: pass

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    try:
        uid = message.from_user.id
        text = message.text.strip().lower()
        uname = get_username(uid)
        
        if uid in creating_country:
            st = creating_country[uid]
            if st['step'] == 'capital':
                c = db_conn.cursor()
                c.execute("INSERT INTO cities (user_id, city_name, is_capital) VALUES (?,?,1)", (uid, text))
                db_conn.commit()
                st['step'] = 'cities'
                bot.send_message(message.chat.id, f"{uname} ✅ Столица: {text}\nВведите 4 города через запятую:")
                return
            elif st['step'] == 'cities':
                cities = [c.strip() for c in text.split(',')]
                if len(cities) != 4:
                    bot.send_message(message.chat.id, f"{uname} ❌ Нужно ровно 4 города!"); return
                c = db_conn.cursor()
                for city in cities:
                    c.execute("INSERT INTO cities (user_id, city_name) VALUES (?,?)", (uid, city))
                db_conn.commit()
                st['step'] = 'country'
                bot.send_message(message.chat.id, f"{uname} Введите название страны:"); return
            elif st['step'] == 'country':
                c = db_conn.cursor()
                c.execute("UPDATE players SET country_name=? WHERE user_id=?", (text, uid))
                db_conn.commit()
                del creating_country[uid]
                show_menu(uid)
                bot.send_message(message.chat.id, f"{uname} 🎉 СТРАНА СОЗДАНА!")
                return
        
        p = get_player(uid)
        if not p or not has_country(uid): return

        if text in ['анкета','проф','профиль']: bot.reply_to(message, show_anketa(uid))
        elif text in ['собрать']: cmd_collect(message)
        elif text in ['строить','стройка']: cmd_build_menu(message)
        elif text.startswith('построить '):
            building_name = text.replace('построить ','',1).lower()
            eng_name = None
            for eng, rus in BUILDING_NAMES.items():
                if rus.lower() == building_name: eng_name = eng; break
            if eng_name: build_direct(message, eng_name)
            else: bot.reply_to(message, f"{uname} ❌ Здание не найдено!")
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
        elif text.startswith('дот ') or text.startswith('бункер ') or text.startswith('каземат '): cmd_fort(message)
        elif text.startswith('город новый '): cmd_new_city(message)
        elif text.startswith('чинить '): cmd_repair_city(message)
        elif text.startswith('столица '): cmd_move_capital(message)
        elif text.startswith('название страны '):
            new_name = text.replace('название страны ','',1)
            c = db_conn.cursor()
            c.execute("UPDATE players SET country_name=? WHERE user_id=?", (new_name, uid))
            db_conn.commit()
            bot.reply_to(message, f"{uname} ✅ Страна переименована в: {new_name}")
        elif text.startswith('название города '):
            parts = text.replace('название города ','',1).split(' на ')
            if len(parts) != 2: bot.reply_to(message, f"{uname} ❌ Формат: название города СТАРОЕ на НОВОЕ")
            else:
                old_name, new_name = parts[0].strip(), parts[1].strip()
                c = db_conn.cursor()
                c.execute("SELECT id FROM cities WHERE user_id=? AND city_name=?", (uid, old_name))
                city = c.fetchone()
                if not city: bot.reply_to(message, f"{uname} ❌ Город '{old_name}' не найден!")
                else:
                    c.execute("UPDATE cities SET city_name=? WHERE user_id=? AND id=?", (new_name, uid, city[0]))
                    db_conn.commit()
                    bot.reply_to(message, f"{uname} ✅ Город '{old_name}' переименован в '{new_name}'")
        elif text.startswith('поделиться '): cmd_share_bp(message)
        elif text.startswith('разведка '): cmd_look(message)
        elif text == 'топ': cmd_top(message)
        elif text == 'мойid': bot.reply_to(message, f"{uname} Ваш ID: {uid}")
        elif text == 'очистить профиль': cmd_reset(message)
        elif text.startswith('дать '): cmd_give(message)
        elif text.startswith('забрать '): cmd_take(message)
        elif text.startswith('стандарт '): cmd_set_default(message)
        elif text == 'стандарты': cmd_show_defaults(message)
        elif text.startswith('бан '): cmd_ban(message)
        elif text.startswith('разбан '): cmd_unban(message)
        elif text.startswith('мут '): cmd_mute(message)
        elif text.startswith('размут '): cmd_unmute(message)
        elif text.startswith('варн '): cmd_warn(message)
        elif text.startswith('снятьварн '): cmd_unwarn(message)
        elif text == 'админы': cmd_admin_list(message)
        elif text.startswith('откат '): cmd_rollback(message)
        elif text.startswith('логи '): cmd_logs(message)
        elif text.startswith('главный '): cmd_grant_head(message)
        elif text.startswith('админ '): cmd_grant_admin(message)
        elif text.startswith('модер '): cmd_grant_mod(message)
        elif text.startswith('снять '): cmd_revoke(message)
        elif text.startswith('продаю '): cmd_sell(message)
        elif text == 'биржа': cmd_market(message)
        elif text.startswith('купить '): cmd_buy(message)
        elif text == 'мои предложения': cmd_my_offers(message)
        elif text.startswith('отменить '): cmd_cancel_offer(message)
        elif text.startswith('передать '): cmd_transfer(message)
        elif text.startswith('война '): cmd_declare_war(message)
        elif text.startswith('захватить '): cmd_capture_request(message)
        elif text.startswith('одобрить захват '): cmd_approve_capture(message)
        elif text.startswith('отклонить захват '): cmd_reject_capture(message)
        elif text == 'мир': cmd_peace(message)
    except Exception as e:
        print(f"Ошибка handle_all: {e}")

# ==================== ОЧИСТКА ПРОФИЛЯ ====================
def cmd_reset(message):
    try:
        uid = message.from_user.id
        uname = get_username(uid)
        c = db_conn.cursor()
        c.execute("DELETE FROM cities WHERE user_id=?", (uid,))
        c.execute("DELETE FROM buildings WHERE user_id=?", (uid,))
        c.execute("DELETE FROM vehicles WHERE user_id=?", (uid,))
        c.execute("DELETE FROM deposits WHERE user_id=?", (uid,))
        c.execute("SELECT resource_name, default_value FROM default_resources")
        for res, val in c.fetchall():
            c.execute(f"UPDATE players SET {res}=? WHERE user_id=?", (val, uid))
        c.execute("UPDATE players SET country_name='Unknown', last_collection=NULL, last_expedition=NULL WHERE user_id=?", (uid,))
        db_conn.commit()
        creating_country[uid] = {'step': 'capital'}
        bot.reply_to(message, f"{uname} ♻ Профиль очищен! Введите название столицы:")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Ошибка!")

# ==================== СТАНДАРТЫ ====================
def cmd_set_default(message):
    if not is_admin(message.from_user.id, 3):
        bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Только главный админ!"); return
    try:
        parts = message.text.replace('стандарт ','',1).split()
        res = parts[0].lower(); val = float(parts[1])
        if res not in RESOURCES: bot.reply_to(message, "❌ Ресурс не найден!"); return
        c = db_conn.cursor()
        c.execute("INSERT OR REPLACE INTO default_resources VALUES (?,?)", (RESOURCES[res], val))
        db_conn.commit()
        bot.reply_to(message, f"{get_username(message.from_user.id)} ✅ Стандарт {res} = {val}")
    except: bot.reply_to(message, "стандарт тенге 10000")

def cmd_show_defaults(message):
    c = db_conn.cursor()
    c.execute("SELECT * FROM default_resources")
    text = f"{get_username(message.from_user.id)} 📋 СТАНДАРТНЫЕ РЕСУРСЫ:\n"
    for res, val in c.fetchall():
        text += f"{RESOURCE_NAMES.get(res, res)}: {val}\n"
    bot.reply_to(message, text)

# ==================== ВОЙНА ====================
def cmd_declare_war(message):
    try:
        uid = message.from_user.id
        uname = get_username(uid)
        target_name = message.text.replace('война ','',1).replace('@','')
        tid = get_uid(target_name)
        if not tid: bot.reply_to(message, f"{uname} ❌ Игрок не найден!"); return
        if tid == uid: bot.reply_to(message, f"{uname} ❌ Нельзя объявить войну себе!"); return
        tuname = get_username(tid)
        c = db_conn.cursor()
        c.execute("SELECT id FROM wars WHERE ((attacker_id=? AND defender_id=?) OR (attacker_id=? AND defender_id=?)) AND status='active'",
                  (uid, tid, tid, uid))
        if c.fetchone(): bot.reply_to(message, f"{uname} ❌ Война уже идёт!"); return
        c.execute("INSERT INTO wars (attacker_id, defender_id, start_date) VALUES (?,?,?)",
                  (uid, tid, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        db_conn.commit()
        bot.reply_to(message, f"⚔️ {uname} объявил войну {tuname}!")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ война @игрок")

def cmd_capture_request(message):
    try:
        uid = message.from_user.id
        uname = get_username(uid)
        parts = message.text.replace('захватить ','',1).split(' у ')
        if len(parts) != 2:
            bot.reply_to(message, f"{uname} ❌ Формат: захватить ГОРОД у @игрок"); return
        city_name = parts[0].strip()
        target_name = parts[1].strip().replace('@','')
        tid = get_uid(target_name)
        if not tid: bot.reply_to(message, f"{uname} ❌ Игрок не найден!"); return
        tuname = get_username(tid)
        c = db_conn.cursor()
        c.execute("SELECT id FROM cities WHERE user_id=? AND city_name=? AND is_destroyed=0", (tid, city_name))
        if not c.fetchone():
            bot.reply_to(message, f"{uname} ❌ Город '{city_name}' не найден у {tuname}!"); return
        c.execute("SELECT id FROM wars WHERE ((attacker_id=? AND defender_id=?) OR (attacker_id=? AND defender_id=?)) AND status='active'",
                  (uid, tid, tid, uid))
        if not c.fetchone():
            bot.reply_to(message, f"{uname} ❌ Сначала объявите войну! война @игрок"); return
        
        req_id = len(capture_requests) + 1
        capture_requests[req_id] = {'attacker': uid, 'defender': tid, 'city': city_name, 'time': datetime.now()}
        
        c.execute("SELECT user_id FROM admins")
        for (aid,) in c.fetchall():
            try:
                bot.send_message(aid, f"📨 Запрос на захват #{req_id}!\n⚔️ {uname} хочет захватить '{city_name}' у {tuname}\nОдобрить: одобрить захват {req_id}\nОтклонить: отклонить захват {req_id}")
            except: pass
        
        bot.reply_to(message, f"{uname} 📨 Запрос на захват '{city_name}' отправлен администрации!")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ захватить ГОРОД у @игрок")

def cmd_approve_capture(message):
    if not is_admin(message.from_user.id, 1):
        bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Нет прав!"); return
    try:
        req_id = int(message.text.replace('одобрить захват ','',1))
        if req_id not in capture_requests:
            bot.reply_to(message, "❌ Запрос не найден!"); return
        req = capture_requests[req_id]
        uid, tid, city_name = req['attacker'], req['defender'], req['city']
        uname = get_username(uid)
        tuname = get_username(tid)
        c = db_conn.cursor()
        c.execute("UPDATE cities SET is_destroyed=1 WHERE user_id=? AND city_name=?", (tid, city_name))
        c.execute("INSERT INTO cities (user_id, city_name) VALUES (?,?)", (uid, f"{city_name}(з)"))
        db_conn.commit()
        cap_progress = calculate_capitulation(tid)
        text = f"✅ Город '{city_name}' захвачен {uname} у {tuname}!"
        if cap_progress >= 100:
            c.execute("DELETE FROM cities WHERE user_id=?", (tid,))
            c.execute("DELETE FROM buildings WHERE user_id=?", (tid,))
            c.execute("UPDATE vehicles SET user_id=? WHERE user_id=?", (uid, tid))
            c.execute("UPDATE players SET tenge=0, population=0 WHERE user_id=?", (tid,))
            c.execute("UPDATE wars SET status='ended' WHERE (attacker_id=? AND defender_id=?) OR (attacker_id=? AND defender_id=?)",
                      (uid, tid, tid, uid))
            db_conn.commit()
            text += f"\n🏳️ {tuname} КАПИТУЛИРОВАЛ! Все ресурсы и техника переходят победителю!"
        elif cap_progress > 0:
            text += f"\n⚠️ Капитуляция {tuname}: {cap_progress:.1f}%"
        del capture_requests[req_id]
        bot.reply_to(message, text)
    except: bot.reply_to(message, "❌ одобрить захват НОМЕР")

def cmd_reject_capture(message):
    if not is_admin(message.from_user.id, 1):
        bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Нет прав!"); return
    try:
        req_id = int(message.text.replace('отклонить захват ','',1))
        if req_id in capture_requests: del capture_requests[req_id]
        bot.reply_to(message, f"❌ Захват #{req_id} отклонён!")
    except: bot.reply_to(message, "отклонить захват НОМЕР")

def cmd_peace(message):
    try:
        uid = message.from_user.id
        uname = get_username(uid)
        c = db_conn.cursor()
        c.execute("UPDATE wars SET status='ended' WHERE (attacker_id=? OR defender_id=?) AND status='active'", (uid, uid))
        db_conn.commit()
        bot.reply_to(message, f"{uname} 🕊️ Война завершена!")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ мир")

# ==================== КОМАНДЫ С @username ====================
def cmd_collect(message):
    try:
        uid = message.from_user.id; p = get_player(uid); uname = get_username(uid)
        can, multiplier, remaining = can_collect_income(uid)
        if not can: bot.reply_to(message, f"{uname} ❌ Доход уже собран! Следующий через {remaining}"); return
        if len(p) > 18 and p[18] and p[18] == datetime.now().strftime("%Y-%m-%d"):
            bot.reply_to(message, f"{uname} ❌ Первый день страны! Доход со 2-го дня."); return
        income = get_buildings_income(uid)
        if sum(income.values()) == 0: bot.reply_to(message, f"{uname} ❌ Нет построек для дохода!"); return
        for res, val in income.items():
            if val > 0: upd_res(uid, res, val * multiplier)
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c = db_conn.cursor(); c.execute("UPDATE players SET last_collection=? WHERE user_id=?", (today, uid)); db_conn.commit()
        nm = {'tenge':'💰','wood':'🪵','cement':'🏗','science_points':'🔬','iron':'🔩','fuel':'⛽','coal':'🪨','fabric':'🧵','horses':'🐴'}
        text = f"{uname} 📊 Доход за {multiplier} дн:\n" if multiplier > 1 else f"{uname} 📊 Доход собран:\n"
        for res, val in income.items():
            if val > 0: text += f"{nm.get(res,res)} +{val * multiplier}\n"
        bot.reply_to(message, text)
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Ошибка при сборе!")

def cmd_expedition(message):
    try:
        uid = message.from_user.id
        uname = get_username(uid)
        can, remaining = can_collect_expedition(uid)
        if not can:
            bot.reply_to(message, f"{uname} ❌ Экспедиция уже отправлена! Следующая через {remaining}")
            return
        mk = types.InlineKeyboardMarkup(row_width=1)
        mk.add(types.InlineKeyboardButton("🌍 Европа +200", callback_data="e_europe"),
               types.InlineKeyboardButton("🏯 Азия +200", callback_data="e_asia"),
               types.InlineKeyboardButton("🌴 Африка +225", callback_data="e_africa"),
               types.InlineKeyboardButton("🌎 Сев.Америка +200", callback_data="e_america_north"),
               types.InlineKeyboardButton("🌎 Юж.Америка +200", callback_data="e_america_south"),
               types.InlineKeyboardButton("🦘 Австралия +175", callback_data="e_australia"))
        bot.reply_to(message, f"{uname} 🌍 Куда? (70💰, раз в 3 дня)", reply_markup=mk)
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Ошибка!")

def cmd_build_menu(message):
    try:
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
        bot.reply_to(message, f"{get_username(message.from_user.id)} 🏗 Выберите здание:", reply_markup=mk)
    except: bot.reply_to(message, "❌ Ошибка!")

def cmd_search_menu(message):
    try:
        mk = types.InlineKeyboardMarkup(row_width=2)
        mk.add(types.InlineKeyboardButton("🛢 Нефть 20💰", callback_data="s_oil"),
               types.InlineKeyboardButton("🔩 Железо 20💰", callback_data="s_iron"),
               types.InlineKeyboardButton("🪨 Уголь 20💰", callback_data="s_coal"),
               types.InlineKeyboardButton("💛 Сера 15💰", callback_data="s_sulfur"),
               types.InlineKeyboardButton("☢ Уран 100💰", callback_data="s_uranium"))
        bot.reply_to(message, f"{get_username(message.from_user.id)} 🔍 Что ищем?", reply_markup=mk)
    except: bot.reply_to(message, "❌ Ошибка!")

def cmd_warehouse(message):
    try:
        c = db_conn.cursor()
        c.execute("SELECT vehicle_name, quantity FROM vehicles WHERE user_id=? AND quantity>0", (message.from_user.id,))
        items = c.fetchall()
        uname = get_username(message.from_user.id)
        if not items: bot.reply_to(message, f"{uname} 📦 Склад пуст"); return
        text = f"{uname} 📦 СКЛАД:\n"
        for n,q in items: text += f"• {n}: {q}\n"
        bot.reply_to(message, text)
    except: bot.reply_to(message, "❌ Ошибка!")

def cmd_cities(message):
    try:
        uid = message.from_user.id; uname = get_username(uid)
        c = db_conn.cursor()
        c.execute("SELECT city_name, is_capital, is_destroyed FROM cities WHERE user_id=?", (uid,))
        cities = c.fetchall()
        text = f"{uname} 🏙 ГОРОДА:\n"
        for nm, cap, des in cities:
            s = "⭐" if cap else "•"
            if des: s += "❌"
            text += f"   {s} {nm}\n"
        bot.reply_to(message, text)
    except: bot.reply_to(message, "❌ Ошибка!")

def cmd_blueprints(message):
    try:
        uname = get_username(message.from_user.id)
        c = db_conn.cursor()
        c.execute("SELECT blueprint_name FROM blueprints WHERE owner_id=?", (message.from_user.id,))
        own = c.fetchall()
        text = f"{uname} 📋 ЧЕРТЕЖИ:\n"
        if own: text += "\n".join([f"• {b[0]}" for b in own])
        else: text += "Нет чертежей"
        bot.reply_to(message, text)
    except: bot.reply_to(message, "❌ Ошибка!")

def cmd_help(message):
    text = """
📖 **КОМАНДЫ БОТА**

🏙 **Страна:**
• проф — посмотреть профиль
• разведка @игрок — посмотреть чужого
• топ — рейтинг игроков
• мойid — узнать свой ID
• название страны Х — переименовать
• название города А на Б — переименовать
• очистить профиль — сбросить страну

💰 **Экономика:**
• собрать — собрать доход (раз в 24ч)
• построить НАЗВАНИЕ — построить здание
• строить — меню построек
• поиск — найти месторождение

🏗 **Города:**
• города — список | город новый Х
• чинить Х | столица Х

⚔️ **Война:**
• война @игрок — объявить войну
• захватить ГОРОД у @игрок — запрос на захват
• мир — завершить войну

👑 **Админ (война):**
• одобрить захват НОМЕР
• отклонить захват НОМЕР

👑 **Админ:**
• дать/забрать @игрок РЕСУРС КОЛ-ВО
• бан/разбан/мут/размут @игрок
• варн @игрок | снятьварн @игрок
• админы | логи @игрок | откат ID
• главный/админ/модер @игрок | снять @игрок
• стандарт РЕСУРС ЗНАЧЕНИЕ | стандарты

💱 **Биржа:**
• продаю КОЛ-ВО РЕСУРС | биржа | купить НОМЕР
• передать @игрок КОЛ-ВО РЕСУРС

📊 **Прочее:**
• склад | помощь | эксп
"""
    try: bot.reply_to(message, text)
    except: pass

def cmd_craft(message):
    try:
        uid = message.from_user.id; uname = get_username(uid)
        parts = message.text.replace('крафт ','',1).split(' ',1)
        qty = int(parts[0]); name = parts[1].upper()
        c = db_conn.cursor()
        c.execute("SELECT * FROM vehicle_recipes WHERE vehicle_name=?", (name,))
        rec = c.fetchone()
        if not rec: bot.reply_to(message, f"{uname} ❌ Нет рецепта!"); return
        p = get_player(uid)
        iron = rec[1]*qty; fuel = rec[2]*qty; gp = rec[3]*qty
        if p[6] < iron: bot.reply_to(message, f"{uname} ❌ Нужно {iron:.0f}🔩"); return
        if p[7] < fuel: bot.reply_to(message, f"{uname} ❌ Нужно {fuel:.0f}⛽"); return
        if p[8] < gp: bot.reply_to(message, f"{uname} ❌ Нужно {gp:.0f}💥"); return
        upd_res(uid,'iron',-iron); upd_res(uid,'fuel',-fuel); upd_res(uid,'gunpowder',-gp)
        c.execute("SELECT quantity FROM vehicles WHERE user_id=? AND vehicle_name=?", (uid,name))
        have = c.fetchone()
        if have: c.execute("UPDATE vehicles SET quantity=quantity+? WHERE user_id=? AND vehicle_name=?", (qty,uid,name))
        else: c.execute("INSERT INTO vehicles (user_id, vehicle_name, quantity) VALUES (?,?,?)", (uid,name,qty))
        c.execute("SELECT owner_id FROM blueprints WHERE blueprint_name=?", (name,))
        if not c.fetchone(): c.execute("INSERT INTO blueprints VALUES (?,?)", (name, uid))
        db_conn.commit()
        log_action(uid, 'craft', f"{qty}x {name}")
        bot.reply_to(message, f"{uname} ✅ {qty}x {name}")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ крафт КОЛ-ВО НАЗВАНИЕ")

def cmd_dismantle(message):
    try:
        uid = message.from_user.id; uname = get_username(uid)
        text = message.text
        for p in ['разобрать ','разбор ']:
            if text.startswith(p): text = text.replace(p,'',1); break
        parts = text.split(' ',1)
        qty = int(parts[0]); name = parts[1].upper()
        c = db_conn.cursor()
        c.execute("SELECT quantity FROM vehicles WHERE user_id=? AND vehicle_name=?", (uid,name))
        have = c.fetchone()
        if not have or have[0] < qty: bot.reply_to(message, f"{uname} ❌ Есть: {have[0] if have else 0}"); return
        c.execute("SELECT * FROM vehicle_recipes WHERE vehicle_name=?", (name,))
        rec = c.fetchone()
        if not rec: bot.reply_to(message, f"{uname} ❌ Рецепт не найден!"); return
        upd_res(uid,'iron',rec[1]*qty); upd_res(uid,'fuel',rec[2]*qty); upd_res(uid,'gunpowder',rec[3]*qty)
        c.execute("UPDATE vehicles SET quantity=quantity-? WHERE user_id=? AND vehicle_name=?", (qty,uid,name))
        db_conn.commit()
        bot.reply_to(message, f"{uname} ♻ {qty}x {name}")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ разобрать КОЛ-ВО НАЗВАНИЕ")

def cmd_recipe(message):
    try:
        name = message.text.replace('рецепт ','',1).upper()
        uname = get_username(message.from_user.id)
        c = db_conn.cursor()
        c.execute("SELECT * FROM vehicle_recipes WHERE vehicle_name=?", (name,))
        rec = c.fetchone()
        if not rec: bot.reply_to(message, f"{uname} ❌ Не найден!"); return
        bot.reply_to(message, f"{uname} 📋 {name}:\n🔩 {rec[1]:.1f}\n⛽ {rec[2]:.1f}\n💥 {rec[3]:.1f}")
    except: bot.reply_to(message, "рецепт НАЗВАНИЕ")

def cmd_create_recipe(message):
    try:
        uname = get_username(message.from_user.id)
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
        fuel = 0 if coal_pow else power/50; coal = power/50 if coal_pow else 0; rubber = 1 if wheels else 0
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
        log_action(message.from_user.id, 'recipe', name)
        bot.reply_to(message, f"{uname} ✅ Рецепт {name}:\n🔩 {iron:.1f}\n⛽ {fuel:.1f}\n💥 {gp:.1f}")
    except: bot.reply_to(message, "❌ !рецепт НАЗВАНИЕ | vehicle | вес | лс | порох | колёса | сверхтяж | уголь | броня")

def cmd_fort(message):
    try:
        uname = get_username(message.from_user.id)
        parts = message.text.split(); ftype = parts[0]; armor = parts[1].upper(); city = ' '.join(parts[2:])
        costs = {'A':(85,30),'B':(65,25),'C':(45,20),'D':(25,15)}
        if armor not in costs: bot.reply_to(message, f"{uname} ❌ Классы: A,B,C,D"); return
        cem, wood = costs[armor]
        p = get_player(message.from_user.id)
        if p[11] < cem: bot.reply_to(message, f"{uname} ❌ Нужно {cem}🏗"); return
        if p[14] < wood: bot.reply_to(message, f"{uname} ❌ Нужно {wood}🪵"); return
        upd_res(message.from_user.id,'cement',-cem); upd_res(message.from_user.id,'wood',-wood)
        bot.reply_to(message, f"{uname} ✅ {ftype} {armor} в {city}!")
    except: bot.reply_to(message, "дот КЛАСС Город")

def cmd_new_city(message):
    try:
        name = message.text.replace('город новый ','',1); uid = message.from_user.id; p = get_player(uid)
        uname = get_username(uid)
        if p[14] < 850: bot.reply_to(message, f"{uname} ❌ 850🪵"); return
        if p[11] < 1000: bot.reply_to(message, f"{uname} ❌ 1000🏗"); return
        if p[5] < 350: bot.reply_to(message, f"{uname} ❌ 350💰"); return
        upd_res(uid,'wood',-850); upd_res(uid,'cement',-1000); upd_res(uid,'tenge',-350)
        c = db_conn.cursor(); c.execute("INSERT INTO cities (user_id, city_name) VALUES (?,?)", (uid,name)); db_conn.commit()
        bot.reply_to(message, f"{uname} ✅ Город {name}!")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ город новый Название")

def cmd_repair_city(message):
    try:
        name = message.text.replace('чинить ','',1); p = get_player(message.from_user.id)
        uname = get_username(message.from_user.id)
        if p[14] < 500: bot.reply_to(message, f"{uname} ❌ 500🪵"); return
        if p[11] < 800: bot.reply_to(message, f"{uname} ❌ 800🏗"); return
        if p[5] < 350: bot.reply_to(message, f"{uname} ❌ 350💰"); return
        upd_res(message.from_user.id,'wood',-500); upd_res(message.from_user.id,'cement',-800); upd_res(message.from_user.id,'tenge',-350)
        c = db_conn.cursor(); c.execute("UPDATE cities SET is_destroyed=0 WHERE user_id=? AND city_name=?", (message.from_user.id,name)); db_conn.commit()
        bot.reply_to(message, f"{uname} ✅ {name} восстановлен!")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ чинить Название")

def cmd_move_capital(message):
    try:
        name = message.text.replace('столица ','',1); uname = get_username(message.from_user.id)
        c = db_conn.cursor()
        c.execute("UPDATE cities SET is_capital=0 WHERE user_id=? AND is_capital=1", (message.from_user.id,))
        c.execute("UPDATE cities SET is_capital=1 WHERE user_id=? AND city_name=?", (message.from_user.id,name))
        db_conn.commit()
        bot.reply_to(message, f"{uname} ⭐ Столица → {name}")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ столица Название")

def cmd_share_bp(message):
    try:
        uname = get_username(message.from_user.id)
        parts = message.text.replace('поделиться ','',1).split()
        bp = parts[0].upper(); tid = get_uid(parts[1].replace('@',''))
        if not tid: bot.reply_to(message, f"{uname} ❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("SELECT owner_id FROM blueprints WHERE blueprint_name=?", (bp,))
        own = c.fetchone()
        if not own or own[0] != message.from_user.id: bot.reply_to(message, f"{uname} ❌ Не владелец!"); return
        c.execute("INSERT OR IGNORE INTO blueprint_access VALUES (?,?,?)", (bp,tid,message.from_user.id))
        db_conn.commit()
        bot.reply_to(message, f"{uname} ✅ {bp} → @{parts[1].replace('@','')}")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ поделиться НАЗВАНИЕ @игрок")

def cmd_look(message):
    try:
        uname = get_username(message.from_user.id)
        tid = get_uid(message.text.replace('разведка ','',1).replace('@',''))
        if not tid: bot.reply_to(message, f"{uname} ❌ Не найден!"); return
        bot.reply_to(message, show_anketa(message.from_user.id, tid))
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ разведка @игрок")

def cmd_top(message):
    try:
        c = db_conn.cursor()
        c.execute("SELECT username, country_name, tenge FROM players WHERE tenge>0 ORDER BY tenge DESC LIMIT 10")
        text = "🏆 ТОП-10:\n"
        for i,(un,cn,tg) in enumerate(c.fetchall(),1): text += f"{i}. {cn} — {tg:.0f}💰\n"
        bot.reply_to(message, text)
    except: bot.reply_to(message, "❌ Ошибка!")

def cmd_give(message):
    if not is_admin(message.from_user.id): bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Нет прав!"); return
    try:
        uname = get_username(message.from_user.id)
        parts = message.text.replace('дать ','',1).split()
        tid = get_uid(parts[0].replace('@',''))
        if not tid: bot.reply_to(message, f"{uname} ❌ Не найден!"); return
        if tid == message.from_user.id: bot.reply_to(message, f"{uname} ❌ Нельзя себе!"); return
        res = parts[1].lower(); amt = float(parts[2])
        if res not in RESOURCES: bot.reply_to(message, f"{uname} ❌ Ресурс не найден!"); return
        upd_res(tid, RESOURCES[res], amt)
        bot.reply_to(message, f"{uname} ✅ +{amt} {res} → @{parts[0].replace('@','')}")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ дать @игрок тенге 500")

def cmd_take(message):
    if not is_admin(message.from_user.id): bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Нет прав!"); return
    try:
        uname = get_username(message.from_user.id)
        parts = message.text.replace('забрать ','',1).split()
        tid = get_uid(parts[0].replace('@',''))
        if not tid: bot.reply_to(message, f"{uname} ❌ Не найден!"); return
        res = parts[1].lower(); amt = float(parts[2])
        if res not in RESOURCES: bot.reply_to(message, f"{uname} ❌ Ресурс не найден!"); return
        upd_res(tid, RESOURCES[res], -amt)
        bot.reply_to(message, f"{uname} ✅ -{amt} {res} у @{parts[0].replace('@','')}")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ забрать @игрок тенге 500")

def cmd_ban(message):
    if not is_admin(message.from_user.id, 2): bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Нет прав!"); return
    try:
        parts = message.text.split(); tid = get_uid(parts[1].replace('@',''))
        if not tid: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("DELETE FROM cities WHERE user_id=?", (tid,))
        c.execute("DELETE FROM buildings WHERE user_id=?", (tid,))
        c.execute("DELETE FROM vehicles WHERE user_id=?", (tid,))
        c.execute("UPDATE players SET tenge=0, population=0 WHERE user_id=?", (tid,))
        db_conn.commit()
        bot.reply_to(message, f"🚫 @{parts[1].replace('@','')} забанен!")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ бан @игрок")

def cmd_unban(message):
    if not is_admin(message.from_user.id, 2): bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Нет прав!"); return
    try:
        parts = message.text.split(); tid = get_uid(parts[1].replace('@',''))
        if not tid: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("UPDATE players SET tenge=5000, population=1000 WHERE user_id=?", (tid,))
        db_conn.commit()
        bot.reply_to(message, f"✅ @{parts[1].replace('@','')} разбанен!")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ разбан @игрок")

def cmd_mute(message):
    if not is_admin(message.from_user.id, 1): bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Нет прав!"); return
    bot.reply_to(message, f"{get_username(message.from_user.id)} 🔇 Мут (заглушка)")

def cmd_unmute(message):
    if not is_admin(message.from_user.id, 1): bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Нет прав!"); return
    bot.reply_to(message, f"{get_username(message.from_user.id)} 🔊 Размут (заглушка)")

def cmd_warn(message):
    if not is_admin(message.from_user.id, 1): bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Нет прав!"); return
    bot.reply_to(message, f"{get_username(message.from_user.id)} ⚠️ Варн (заглушка)")

def cmd_unwarn(message):
    if not is_admin(message.from_user.id, 1): bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Нет прав!"); return
    bot.reply_to(message, f"{get_username(message.from_user.id)} ✅ Варн снят (заглушка)")

def cmd_admin_list(message):
    try:
        c = db_conn.cursor()
        c.execute("SELECT a.admin_level, p.username FROM admins a JOIN players p ON a.user_id=p.user_id")
        lvls = {1:'Модер',2:'Админ',3:'Главный'}
        text = "👑 АДМИНЫ:\n"
        for lvl, un in c.fetchall(): text += f"• @{un} — {lvls.get(lvl,lvl)}\n"
        bot.reply_to(message, text)
    except: bot.reply_to(message, "❌ Ошибка!")

def cmd_rollback(message):
    if not is_admin(message.from_user.id, 1): bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Нет прав!"); return
    try:
        action_id = int(message.text.replace('откат ','',1))
        c = db_conn.cursor()
        c.execute("SELECT * FROM action_log WHERE id=? AND can_rollback=1", (action_id,))
        action = c.fetchone()
        if not action: bot.reply_to(message, "❌ Действие не найдено!"); return
        uid, atype, details = action[1], action[2], action[3]
        if atype == 'build':
            for eng_name, rus_name in BUILDING_NAMES.items():
                if rus_name in details:
                    cost = BUILDING_COSTS.get(eng_name, 0)
                    upd_res(uid, 'tenge', cost)
                    c.execute("DELETE FROM buildings WHERE user_id=? AND building_type=? AND id IN (SELECT id FROM buildings WHERE user_id=? AND building_type=? LIMIT 1)", (uid, eng_name, uid, eng_name))
                    db_conn.commit()
                    bot.reply_to(message, f"♻ Откат #{action_id}: {rus_name} удалён, +{cost}💰"); break
        elif atype == 'craft':
            parts = details.split('x ')
            if len(parts) == 2:
                qty = int(parts[0]); name = parts[1]
                c.execute("SELECT * FROM vehicle_recipes WHERE vehicle_name=?", (name,))
                rec = c.fetchone()
                if rec:
                    upd_res(uid, 'iron', rec[1]*qty); upd_res(uid, 'fuel', rec[2]*qty); upd_res(uid, 'gunpowder', rec[3]*qty)
                    c.execute("UPDATE vehicles SET quantity=quantity-? WHERE user_id=? AND vehicle_name=?", (qty, uid, name))
                    db_conn.commit()
                    bot.reply_to(message, f"♻ Откат #{action_id}: {qty}x {name}")
        c.execute("UPDATE action_log SET can_rollback=0 WHERE id=?", (action_id,))
        db_conn.commit()
    except: bot.reply_to(message, "❌ Не удалось откатить.")

def cmd_logs(message):
    if not is_admin(message.from_user.id, 1): bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Нет прав!"); return
    try:
        parts = message.text.split()
        if len(parts) < 2: bot.reply_to(message, "❌ логи @игрок"); return
        tid = get_uid(parts[1].replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("SELECT id, action_type, details, timestamp FROM action_log WHERE user_id=? AND can_rollback=1 ORDER BY id DESC LIMIT 10", (tid,))
        logs = c.fetchall()
        if not logs: bot.reply_to(message, "📋 Нет действий для отката."); return
        text = "📋 Последние действия:\n"
        for lid, atype, details, ts in logs: text += f"#{lid} [{atype}] {details} — {ts}\n"
        text += "\nДля отката: откат ID"
        bot.reply_to(message, text)
    except: bot.reply_to(message, "логи @игрок")

def cmd_grant_head(message):
    if not is_admin(message.from_user.id, 3): bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Только главный!"); return
    try:
        tid = get_uid(message.text.replace('главный ','',1).replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor(); c.execute("INSERT OR REPLACE INTO admins VALUES (?,3)", (tid,)); db_conn.commit()
        bot.reply_to(message, f"✅ @{message.text.replace('главный ','',1).replace('@','')} → Главный админ!")
    except: bot.reply_to(message, "главный @игрок")

def cmd_grant_admin(message):
    if not is_admin(message.from_user.id, 2): bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Нет прав!"); return
    try:
        tid = get_uid(message.text.replace('админ ','',1).replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor(); c.execute("INSERT OR REPLACE INTO admins VALUES (?,2)", (tid,)); db_conn.commit()
        bot.reply_to(message, f"✅ @{message.text.replace('админ ','',1).replace('@','')} → Админ!")
    except: bot.reply_to(message, "админ @игрок")

def cmd_grant_mod(message):
    if not is_admin(message.from_user.id, 2): bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Нет прав!"); return
    try:
        tid = get_uid(message.text.replace('модер ','',1).replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor(); c.execute("INSERT OR REPLACE INTO admins VALUES (?,1)", (tid,)); db_conn.commit()
        bot.reply_to(message, f"✅ @{message.text.replace('модер ','',1).replace('@','')} → Модератор!")
    except: bot.reply_to(message, "модер @игрок")

def cmd_revoke(message):
    if not is_admin(message.from_user.id, 2): bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ Нет прав!"); return
    try:
        tid = get_uid(message.text.replace('снять ','',1).replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor(); c.execute("DELETE FROM admins WHERE user_id=?", (tid,)); db_conn.commit()
        bot.reply_to(message, f"✅ @{message.text.replace('снять ','',1).replace('@','')} лишён прав!")
    except: bot.reply_to(message, "снять @игрок")

# ==================== БИРЖА ====================
def cmd_sell(message):
    try:
        uid = message.from_user.id; uname = get_username(uid)
        parts = message.text.replace('продаю ','',1).split(' ',1)
        if len(parts) < 2: bot.reply_to(message, f"{uname} ❌ продаю КОЛ-ВО РЕСУРС"); return
        qty = float(parts[0]); item_name = parts[1].lower()
        p = get_player(uid)
        if item_name in RESOURCES:
            eng = RESOURCES[item_name]
            player_has = p[5] if eng == 'tenge' else (p[6] if eng == 'iron' else (p[7] if eng == 'fuel' else (p[8] if eng == 'gunpowder' else (p[10] if eng == 'coal' else (p[14] if eng == 'wood' else (p[11] if eng == 'cement' else (p[9] if eng == 'fabric' else (p[15] if eng == 'horses' else 0))))))))
            if player_has < qty: bot.reply_to(message, f"{uname} ❌ Недостаточно! У вас: {player_has:.0f}"); return
            upd_res(uid, eng, -qty)
        else:
            c = db_conn.cursor()
            c.execute("SELECT quantity FROM vehicles WHERE user_id=? AND vehicle_name=?", (uid, item_name.upper()))
            have = c.fetchone()
            if not have or have[0] < qty: bot.reply_to(message, f"{uname} ❌ Недостаточно! У вас: {have[0] if have else 0}"); return
            c.execute("UPDATE vehicles SET quantity=quantity-? WHERE user_id=? AND vehicle_name=?", (int(qty), uid, item_name.upper()))
            db_conn.commit()
        c = db_conn.cursor()
        c.execute("INSERT INTO market (seller_id, item_type, item_name, quantity, timestamp) VALUES (?,?,?,?,?)",
                  (uid, 'resource' if item_name in RESOURCES else 'vehicle', item_name.upper() if item_name not in RESOURCES else item_name, qty, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        db_conn.commit()
        offer_id = c.lastrowid
        bot.reply_to(message, f"{uname} ✅ Предложение #{offer_id}: {qty} {item_name.upper() if item_name not in RESOURCES else item_name}\nЗабрать: купить {offer_id}")
        log_action(uid, 'sell', f"#{offer_id}: {qty} {item_name}")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ продаю КОЛ-ВО РЕСУРС")

def cmd_market(message):
    try:
        c = db_conn.cursor()
        c.execute("SELECT m.id, m.item_name, m.quantity, p.username FROM market m JOIN players p ON m.seller_id=p.user_id WHERE m.active=1 ORDER BY m.id")
        offers = c.fetchall()
        if not offers: bot.reply_to(message, "📊 Биржа пуста."); return
        text = "📊 БИРЖА:\n\n"
        for oid, item, qty, uname in offers: text += f"#{oid} | {qty} {item} | @{uname}\n"
        text += "\nЗабрать: купить НОМЕР"
        bot.reply_to(message, text)
    except: bot.reply_to(message, "❌ Ошибка!")

def cmd_buy(message):
    try:
        uid = message.from_user.id; uname = get_username(uid)
        offer_id = int(message.text.replace('купить ','',1))
        c = db_conn.cursor()
        c.execute("SELECT * FROM market WHERE id=? AND active=1", (offer_id,))
        offer = c.fetchone()
        if not offer: bot.reply_to(message, f"{uname} ❌ Предложение не найдено!"); return
        if offer[1] == uid: bot.reply_to(message, f"{uname} ❌ Нельзя забрать своё!"); return
        item_name, qty = offer[3], offer[4]
        if offer[2] == 'resource':
            if item_name in RESOURCES: upd_res(uid, RESOURCES[item_name], qty)
            else: upd_res(uid, item_name, qty)
        else:
            c.execute("SELECT quantity FROM vehicles WHERE user_id=? AND vehicle_name=?", (uid, item_name))
            have = c.fetchone()
            if have: c.execute("UPDATE vehicles SET quantity=quantity+? WHERE user_id=? AND vehicle_name=?", (int(qty), uid, item_name))
            else: c.execute("INSERT INTO vehicles (user_id, vehicle_name, quantity) VALUES (?,?,?)", (uid, item_name, int(qty)))
            db_conn.commit()
        c.execute("UPDATE market SET active=0 WHERE id=?", (offer_id,))
        db_conn.commit()
        seller_uname = get_username(offer[1])
        bot.reply_to(message, f"{uname} ✅ Забрано #{offer_id}: {qty} {item_name} от {seller_uname}!")
        log_action(uid, 'buy', f"#{offer_id}: {qty} {item_name}")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ купить НОМЕР")

def cmd_my_offers(message):
    try:
        uid = message.from_user.id; uname = get_username(uid)
        c = db_conn.cursor()
        c.execute("SELECT id, item_name, quantity FROM market WHERE seller_id=? AND active=1", (uid,))
        offers = c.fetchall()
        if not offers: bot.reply_to(message, f"{uname} Нет активных предложений."); return
        text = f"{uname} 📋 Мои предложения:\n"
        for oid, item, qty in offers: text += f"#{oid} | {qty} {item}\n"
        text += "\nОтменить: отменить НОМЕР"
        bot.reply_to(message, text)
    except: bot.reply_to(message, "❌ Ошибка!")

def cmd_cancel_offer(message):
    try:
        uid = message.from_user.id; uname = get_username(uid)
        offer_id = int(message.text.replace('отменить ','',1))
        c = db_conn.cursor()
        c.execute("SELECT * FROM market WHERE id=? AND seller_id=? AND active=1", (offer_id, uid))
        offer = c.fetchone()
        if not offer: bot.reply_to(message, f"{uname} ❌ Не найдено!"); return
        item_name, qty = offer[3], offer[4]
        if offer[2] == 'resource':
            if item_name in RESOURCES: upd_res(uid, RESOURCES[item_name], qty)
            else: upd_res(uid, item_name, qty)
        else:
            c.execute("UPDATE vehicles SET quantity=quantity+? WHERE user_id=? AND vehicle_name=?", (int(qty), uid, item_name))
            db_conn.commit()
        c.execute("UPDATE market SET active=0 WHERE id=?", (offer_id,))
        db_conn.commit()
        bot.reply_to(message, f"{uname} ✅ Предложение #{offer_id} отменено.")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ отменить НОМЕР")

def cmd_transfer(message):
    try:
        uid = message.from_user.id; uname = get_username(uid)
        parts = message.text.replace('передать ','',1).split(' ')
        if len(parts) < 3: bot.reply_to(message, f"{uname} ❌ передать @игрок КОЛ-ВО РЕСУРС"); return
        tid = get_uid(parts[0].replace('@',''))
        if not tid: bot.reply_to(message, f"{uname} ❌ Игрок не найден!"); return
        if tid == uid: bot.reply_to(message, f"{uname} ❌ Нельзя себе!"); return
        qty = float(parts[1]); item_name = ' '.join(parts[2:]).lower()
        p = get_player(uid)
        if item_name in RESOURCES:
            eng = RESOURCES[item_name]
            player_has = p[5] if eng == 'tenge' else (p[6] if eng == 'iron' else (p[7] if eng == 'fuel' else (p[8] if eng == 'gunpowder' else 0)))
            if player_has < qty: bot.reply_to(message, f"{uname} ❌ Недостаточно! У вас: {player_has:.0f}"); return
            upd_res(uid, eng, -qty); upd_res(tid, eng, qty)
        else:
            c = db_conn.cursor()
            c.execute("SELECT quantity FROM vehicles WHERE user_id=? AND vehicle_name=?", (uid, item_name.upper()))
            have = c.fetchone()
            if not have or have[0] < qty: bot.reply_to(message, f"{uname} ❌ Недостаточно! У вас: {have[0] if have else 0}"); return
            c.execute("UPDATE vehicles SET quantity=quantity-? WHERE user_id=? AND vehicle_name=?", (int(qty), uid, item_name.upper()))
            c.execute("SELECT quantity FROM vehicles WHERE user_id=? AND vehicle_name=?", (tid, item_name.upper()))
            thave = c.fetchone()
            if thave: c.execute("UPDATE vehicles SET quantity=quantity+? WHERE user_id=? AND vehicle_name=?", (int(qty), tid, item_name.upper()))
            else: c.execute("INSERT INTO vehicles (user_id, vehicle_name, quantity) VALUES (?,?,?)", (tid, item_name.upper(), int(qty)))
            db_conn.commit()
        bot.reply_to(message, f"{uname} ✅ Передано @{parts[0].replace('@','')}: {qty} {item_name.upper() if item_name not in RESOURCES else item_name}")
    except: bot.reply_to(message, f"{get_username(message.from_user.id)} ❌ передать @игрок КОЛ-ВО РЕСУРС")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        uid = call.from_user.id; p = get_player(uid)
        uname = get_username(uid)
        if not p or not has_country(uid):
            bot.answer_callback_query(call.id, "❌ Ай-яй-яй, так нельзя!")
            return
        data = call.data
        
        if data.startswith('b_'):
            bt = data[2:]
            if bt in BUILDING_COSTS:
                cost = BUILDING_COSTS[bt]
                if p[5] < cost:
                    bot.answer_callback_query(call.id, f"❌ {cost}💰")
                    bot.send_message(call.message.chat.id, f"{uname} ❌ Недостаточно тенге! Нужно {cost}💰"); return
                if bt in BUILDING_DEPOSIT and not has_deposit(uid, BUILDING_DEPOSIT[bt]):
                    bot.answer_callback_query(call.id, "❌ Нет месторождения!")
                    bot.send_message(call.message.chat.id, f"{uname} ❌ Сначала найдите месторождение!"); return
                if bt in BUILDING_POP and BUILDING_POP[bt] > 0:
                    free = p[3] - count_buildings_pop(uid)
                    if free < BUILDING_POP[bt]:
                        bot.answer_callback_query(call.id, f"❌ Нужно {BUILDING_POP[bt]}👥")
                        bot.send_message(call.message.chat.id, f"{uname} ❌ Недостаточно населения! Нужно {BUILDING_POP[bt]}👥"); return
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
                log_action(uid, 'build', f"{BUILDING_NAMES.get(bt,bt)}", f"tenge:{cost}")
                bot.answer_callback_query(call.id, f"✅ {BUILDING_NAMES.get(bt,bt)}")
                bot.send_message(call.message.chat.id, f"{uname} ✅ {BUILDING_NAMES.get(bt,bt)} (-{cost}💰)")
        
        elif data.startswith('s_'):
            dep = data[2:]
            costs = {'oil':20,'iron':20,'coal':20,'sulfur':15,'uranium':100}
            if dep in costs:
                if p[5] < costs[dep]:
                    bot.answer_callback_query(call.id, f"❌ {costs[dep]}💰")
                    bot.send_message(call.message.chat.id, f"{uname} ❌ Недостаточно тенге для поиска!"); return
                upd_res(uid,'tenge',-costs[dep])
                ok = random.randint(1,5)==1 if dep=='uranium' else random.random()<0.5
                if ok:
                    c = db_conn.cursor()
                    c.execute("INSERT OR IGNORE INTO deposits (user_id, deposit_type) VALUES (?,?)", (uid,dep))
                    db_conn.commit()
                    bot.answer_callback_query(call.id, "✅ Найдено!")
                    bot.send_message(call.message.chat.id, f"{uname} ✅ Месторождение найдено!")
                else:
                    bot.answer_callback_query(call.id, "❌ Пусто")
                    bot.send_message(call.message.chat.id, f"{uname} ❌ Месторождение не найдено.")
        
        elif data.startswith('e_'):
            can, remaining = can_collect_expedition(uid)
            if not can:
                bot.answer_callback_query(call.id, f"❌ Экспедиция через {remaining}")
                bot.send_message(call.message.chat.id, f"{uname} ❌ Экспедиция недоступна! Следующая через {remaining}")
                return
            reg = data[2:]
            rewards = {'europe':200,'asia':200,'africa':225,'america_north':200,'america_south':200,'australia':175}
            names = {'europe':'Европа','asia':'Азия','africa':'Африка','america_north':'Сев.Америка','america_south':'Юж.Америка','australia':'Австралия'}
            if p[5] < 70:
                bot.answer_callback_query(call.id, "❌ Нужно 70💰")
                bot.send_message(call.message.chat.id, f"{uname} ❌ Недостаточно тенге для экспедиции! Нужно 70💰"); return
            upd_res(uid,'tenge',-70)
            today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c = db_conn.cursor(); c.execute("UPDATE players SET last_expedition=? WHERE user_id=?", (today, uid)); db_conn.commit()
            upd_res(uid, 'population', rewards[reg])
            bot.answer_callback_query(call.id, f"✅ {names.get(reg,reg)}!")
            bot.send_message(call.message.chat.id, f"{uname} 🌍 Экспедиция в {names.get(reg,reg)}! +{rewards[reg]}👥\nСледующая через 72 часа.")
    except Exception as e:
        print(f"Ошибка callback: {e}")
        try: bot.answer_callback_query(call.id, "❌ Ошибка!")
        except: pass

if __name__ == '__main__':
    print("🤖 Бот запущен!")
    
    def run_web():
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port)
    
    threading.Thread(target=run_web, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=save_db_to_github, daemon=True).start()
    
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"Ошибка polling: {e}")
            time.sleep(5)
