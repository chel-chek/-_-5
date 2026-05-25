import telebot
from telebot import types
import sqlite3
from datetime import datetime, timedelta
import random
import time
import traceback
import threading

TOKEN = '8786607133:AAFwAEi3vfw1G7pnW8aDhVyv0dxC5WYiGE4'

bot = telebot.TeleBot(TOKEN)

BUILDING_POP = {
    'business_center': 350, 'lumberjack': 300, 'construction_factory': 300,
    'university': 400, 'fabric_factory': 350, 'stables': 250, 'barracks': 0,
    'oil_rig': 300, 'iron_mine': 300, 'coal_mine': 250, 'vdv_barracks': 100,
    'gunpowder_factory': 400, 'uranium_mine': 800, 'uranium_lab': 600,
    'processing_plant': 700, 'port': 200, 'military_engineering': 0
}

BUILDING_COSTS = {
    'business_center': 65, 'lumberjack': 55, 'construction_factory': 50,
    'university': 90, 'fabric_factory': 50, 'stables': 60, 'barracks': 70,
    'oil_rig': 70, 'iron_mine': 65, 'coal_mine': 70, 'vdv_barracks': 100,
    'military_engineering': 1500
}

BUILDING_NAMES = {
    'business_center': 'Бизнес-центр', 'lumberjack': 'Лесопилка',
    'construction_factory': 'Стройзавод', 'university': 'Университет',
    'fabric_factory': 'Тканевый', 'stables': 'Конюшни', 'barracks': 'Казарма',
    'oil_rig': 'Нефтяная вышка', 'iron_mine': 'Жел.шахта', 'coal_mine': 'Уг.шахта',
    'vdv_barracks': 'Казарма ВДВ', 'military_engineering': 'Воен-инж.завод'
}

BUILDING_DEPOSIT = {
    'oil_rig': 'oil', 'iron_mine': 'iron', 'coal_mine': 'coal', 'uranium_mine': 'uranium'
}

RESOURCES = {
    'тенге':'tenge','деньги':'tenge',
    'железо':'iron','железа':'iron',
    'топливо':'fuel','топлива':'fuel','нефть':'fuel','бензин':'fuel',
    'порох':'gunpowder','пороха':'gunpowder',
    'резина':'rubber','резины':'rubber',
    'ткань':'fabric','ткани':'fabric',
    'уголь':'coal','угля':'coal',
    'цемент':'cement','цемента':'cement','бетон':'cement',
    'уран':'uranium','урана':'uranium',
    'дерево':'wood','дерева':'wood','древесина':'wood',
    'кони':'horses','коней':'horses','лошади':'horses',
    'наука':'science_points','науки':'science_points',
    'население':'population','люди':'population','населения':'population',
    'спецматериал':'special_material'
}

MAX_CITIES = 15

COMMANDS = [
    'анкета','собрать','собрать доход','строить','стройка','поиск','склад',
    'города','чертежи','помощь','команды','топ','мойid','стандарты','админы',
    'эксп','эксп статус'
]

COMMAND_STARTS = [
    'эксп', 'крафт ', 'разобрать ', 'разбор ', 'рецепт ', '!рецепт',
    'дот ', 'бункер ', 'каземат ',
    'город новый ', 'построить город ',
    'чинить ', 'город чинить ',
    'столица ', 'поделиться ', 'разведка ',
    'проверка ', 'дать ', 'забрать ', 'всем ',
    'сброс ', 'логи ', 'стандарт ', 'применить стандарты',
    'модер ', 'админ ', 'главный ', 'снять ',
    'бан ', 'разбан ', 'мут ', 'размут ',
    'варн ', 'пред ', 'предупреждение ', 'снятьварн ', 'откат '
]

def is_command(text):
    text = text.strip().lower()
    if text.startswith('/') or text.startswith('!'): return True
    if text in COMMANDS: return True
    for start in COMMAND_STARTS:
        if text.startswith(start): return True
    return False

def init_db():
    conn = sqlite3.connect('game.db', check_same_thread=False)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS players
                 (user_id INTEGER PRIMARY KEY, username TEXT,
                  country_name TEXT DEFAULT 'Неизвестная',
                  population REAL DEFAULT 1000,
                  science_points REAL DEFAULT 0, tenge REAL DEFAULT 5000,
                  iron REAL DEFAULT 0, fuel REAL DEFAULT 0,
                  gunpowder REAL DEFAULT 0, rubber REAL DEFAULT 0,
                  fabric REAL DEFAULT 0, coal REAL DEFAULT 0,
                  cement REAL DEFAULT 0, uranium REAL DEFAULT 0,
                  wood REAL DEFAULT 0, horses REAL DEFAULT 0,
                  special_material REAL DEFAULT 0,
                  last_collection TEXT, game_year REAL DEFAULT 1904)''')
    
    for col_name, col_type in [
        ('created_date', 'TEXT'),
        ('is_banned', 'INTEGER DEFAULT 0'),
        ('is_muted', 'INTEGER DEFAULT 0'),
        ('warns', 'INTEGER DEFAULT 0'),
        ('last_login', 'TEXT')
    ]:
        try: c.execute(f"ALTER TABLE players ADD COLUMN {col_name} {col_type}")
        except: pass
    
    c.execute('''CREATE TABLE IF NOT EXISTS cities
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER, city_name TEXT,
                  is_capital INTEGER DEFAULT 0, is_destroyed INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS buildings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER, city_id INTEGER,
                  building_type TEXT, quantity INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS deposits
                 (user_id INTEGER, deposit_type TEXT,
                  found INTEGER DEFAULT 1, built INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS vehicles
                 (user_id INTEGER, vehicle_name TEXT, quantity INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS vehicle_recipes
                 (vehicle_name TEXT PRIMARY KEY,
                  iron_cost REAL, fuel_cost REAL, gunpowder_cost REAL,
                  rubber_cost REAL, fabric_cost REAL, coal_cost REAL,
                  special_material_cost REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS blueprints
                 (blueprint_name TEXT PRIMARY KEY, owner_id INTEGER,
                  year_researched INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS blueprint_access
                 (blueprint_name TEXT, player_id INTEGER, granted_by INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS expeditions
                 (user_id INTEGER, region TEXT, end_date TEXT,
                  reward_population INTEGER, status TEXT DEFAULT 'active')''')
    c.execute('''CREATE TABLE IF NOT EXISTS action_log
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER, action_type TEXT, details TEXT,
                  resources TEXT, timestamp TEXT, can_rollback INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins
                 (user_id INTEGER PRIMARY KEY, admin_level INTEGER DEFAULT 1,
                  added_by INTEGER, added_date TEXT)''')
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

def get_player(uid):
    try:
        c = db_conn.cursor()
        c.execute("SELECT * FROM players WHERE user_id=?", (uid,))
        return c.fetchone()
    except: return None

def has_country(uid):
    p = get_player(uid)
    if not p: return False
    if not p[2] or p[2] == 'Неизвестная': return False
    c = db_conn.cursor()
    c.execute("SELECT COUNT(*) FROM cities WHERE user_id=?", (uid,))
    return c.fetchone()[0] > 0

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
    for btype, qty in c.fetchall():
        if btype in BUILDING_POP and qty:
            total += BUILDING_POP[btype] * qty
    return total

def has_deposit(uid, deposit_type):
    c = db_conn.cursor()
    c.execute("SELECT COUNT(*) FROM deposits WHERE user_id=? AND deposit_type=? AND built=0", (uid,deposit_type))
    return c.fetchone()[0] > 0

def use_deposit(uid, deposit_type):
    c = db_conn.cursor()
    c.execute("UPDATE deposits SET built=1 WHERE user_id=? AND deposit_type=? AND built=0 LIMIT 1", (uid,deposit_type))
    db_conn.commit()

def log_action(uid, action_type, details, resources=""):
    try:
        c = db_conn.cursor()
        c.execute("INSERT INTO action_log (user_id, action_type, details, resources, timestamp) VALUES (?,?,?,?,?)",
                  (uid, action_type, str(details)[:200], str(resources)[:200], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        db_conn.commit()
    except: pass

def show_anketa(uid, target_id=None):
    if target_id is None: target_id = uid
    p = get_player(target_id)
    if not p: return "Страна не найдена"
    c = db_conn.cursor()
    c.execute("SELECT id, city_name, is_capital, is_destroyed FROM cities WHERE user_id=?", (target_id,))
    cities = c.fetchall()
    c.execute("SELECT vehicle_name, quantity FROM vehicles WHERE user_id=? AND quantity>0 ORDER BY vehicle_name", (target_id,))
    veh = c.fetchall()
    c.execute("SELECT blueprint_name FROM blueprints WHERE owner_id=?", (target_id,))
    bps = c.fetchall()
    
    year = p[17] if len(p) > 17 and p[17] else 1904
    try: year = float(year)
    except: year = 1904
    
    warns = p[22] if len(p) > 22 else 0
    used_pop = count_buildings_pop(target_id)
    free_pop = p[3] - used_pop
    
    text = f"📋 {p[2]} | 📅 {year:.0f} год\n"
    text += f"👤 @{p[1]}\n\n"
    text += f"👥 {p[3]:.0f} (занято {used_pop:.0f}, свободно {free_pop:.0f})\n"
    text += f"🔬 {p[4]:.0f} | 💰 {p[5]:.0f}\n"
    text += f"🔩 {p[6]:.0f} | ⛽ {p[7]:.0f} | 💥 {p[8]:.0f} | 🪨 {p[10]:.0f}\n"
    text += f"🪵 {p[14]:.0f} | 🏗 {p[11]:.0f} | 🧵 {p[9]:.0f} | 🐴 {p[15]:.0f}\n"
    if len(p) > 12 and p[12] > 0: text += f"☢ Уран: {p[12]:.2f}\n"
    if len(p) > 16 and p[16] > 0: text += f"⚗ Спец: {p[16]:.1f}\n"
    if warns > 0: text += f"⚠️ Варны: {warns}/3\n"
    
    text += f"\n🏙 ГОРОДА ({len(cities)}/{MAX_CITIES}):\n"
    for city_id, nm, cap, des in cities:
        s = "⭐" if cap else "•"
        s += " ❌" if des else ""
        c.execute("SELECT building_type, quantity FROM buildings WHERE user_id=? AND city_id=?", (target_id, city_id))
        blds = c.fetchall()
        text += f"{s} {nm}"
        if blds:
            bld_str = ", ".join([f"{BUILDING_NAMES.get(b[0],b[0])} x{b[1]}" for b in blds])
            text += f" ({bld_str})"
        text += "\n"
    
    if bps:
        text += f"\n📋 ЧЕРТЕЖИ ({len(bps)}):\n"
        for bp in bps[:10]: text += f"• {bp[0]}\n"
    
    if veh:
        total_veh = sum(v[1] for v in veh)
        text += f"\n📦 СКЛАД ({total_veh} ед.):\n"
        for v,q in veh[:10]: text += f"• {v}: {q}\n"
    
    return text

def check_expeditions():
    while True:
        try:
            c = db_conn.cursor()
            today = datetime.now().strftime("%Y-%m-%d")
            c.execute("SELECT user_id, reward_population, region FROM expeditions WHERE status='active' AND end_date <= ?", (today,))
            for uid, reward, region in c.fetchall():
                upd_res(uid, 'population', reward)
                c.execute("UPDATE expeditions SET status='completed' WHERE user_id=? AND end_date<=?", (uid, today))
                try: bot.send_message(uid, f"🌍 Экспедиция в {region} вернулась! +{reward}👥")
                except: pass
            db_conn.commit()
        except: pass
        time.sleep(3600)

def update_game_time():
    while True:
        try:
            c = db_conn.cursor()
            c.execute("SELECT user_id, game_year FROM players WHERE is_banned=0")
            for uid, year in c.fetchall():
                year = year if year else 1904
                try: year = float(year)
                except: year = 1904
                if 1904 <= year < 1914: year += 2
                elif 1914 <= year < 1918: year += 1
                elif 1918 <= year < 1926: year += 1
                elif 1926 <= year < 1934: year += 2
                elif 1934 <= year < 1939: year += 1
                elif 1939 <= year < 1945: year += 0.34
                elif 1945 <= year < 1950: year += 0.5
                elif 1950 <= year < 1960: year += 1
                elif 1960 <= year < 1965: year += 0.34
                elif 1965 <= year < 1975: year += 1
                c.execute("UPDATE players SET game_year=? WHERE user_id=?", (year, uid))
            db_conn.commit()
        except: pass
        time.sleep(86400)

@bot.message_handler(commands=['set_head_admin'])
def set_head_admin(message):
    uid = message.from_user.id
    c = db_conn.cursor()
    c.execute("SELECT COUNT(*) FROM admins WHERE admin_level=3")
    if c.fetchone()[0] > 0:
        bot.reply_to(message, "❌ Главный админ уже назначен!"); return
    c.execute("INSERT OR REPLACE INTO admins VALUES (?,3,0,?)", (uid, datetime.now().strftime("%Y-%m-%d")))
    db_conn.commit()
    bot.reply_to(message, "✅ Вы стали ГЛАВНЫМ АДМИНОМ!")

@bot.message_handler(commands=['start'])
def start(message):
    uid = message.from_user.id
    uname = message.from_user.username or f"Player_{uid}"
    p = get_player(uid)
    
    banned = p[20] if p and len(p) > 20 else 0
    if banned == 1:
        bot.reply_to(message, "🚫 Вы забанены!"); return
    
    # Если уже есть страна - просто показываем меню, новую не создаём
    if p and has_country(uid):
        c = db_conn.cursor()
        c.execute("UPDATE players SET last_login=? WHERE user_id=?", (datetime.now().strftime("%Y-%m-%d"), uid))
        db_conn.commit()
        show_menu(message.chat.id)
        bot.send_message(message.chat.id, "🎮 С возвращением! помощь — команды")
        return
    
    # Новая страна
    c = db_conn.cursor()
    c.execute("INSERT OR REPLACE INTO players (user_id, username, created_date, last_login) VALUES (?,?,?,?)",
              (uid, uname, datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%Y-%m-%d")))
    db_conn.commit()
    msg = bot.send_message(message.chat.id, "🎮 Добро пожаловать!\n\nВведите название столицы:")
    bot.register_next_step_handler(msg, step_cap)

def step_cap(message):
    uid = message.from_user.id
    c = db_conn.cursor()
    c.execute("SELECT COUNT(*) FROM cities WHERE user_id=?", (uid,))
    if c.fetchone()[0] > 0: return  # Уже есть города - игнорируем
    c.execute("INSERT INTO cities (user_id, city_name, is_capital) VALUES (?,?,1)", (uid, message.text.strip()))
    db_conn.commit()
    msg = bot.send_message(message.chat.id, f"✅ Столица: {message.text.strip()}\n\nВведите 4 города через запятую:")
    bot.register_next_step_handler(msg, step_cities, uid)

def step_cities(message, uid=None):
    if uid is None: uid = message.from_user.id
    if message.from_user.id != uid: return  # Чужое сообщение - игнорируем
    
    c = db_conn.cursor()
    c.execute("SELECT COUNT(*) FROM cities WHERE user_id=?", (uid,))
    if c.fetchone()[0] != 1:  # Должна быть только столица
        bot.send_message(message.chat.id, "❌ Ошибка. Напишите /start")
        return
    
    cities = [c.strip() for c in message.text.split(',')]
    if len(cities) != 4:
        msg = bot.send_message(message.chat.id, "❌ Нужно ровно 4 города!")
        bot.register_next_step_handler(msg, step_cities, uid); return
    
    for city in cities:
        c.execute("SELECT COUNT(*) FROM cities WHERE user_id=? AND city_name=?", (uid, city))
        if c.fetchone()[0] > 0:
            msg = bot.send_message(message.chat.id, f"❌ Город {city} уже существует!")
            bot.register_next_step_handler(msg, step_cities, uid); return
        c.execute("INSERT INTO cities (user_id, city_name) VALUES (?,?)", (uid, city))
    db_conn.commit()
    msg = bot.send_message(message.chat.id, "Введите название страны:")
    bot.register_next_step_handler(msg, step_country, uid)

def step_country(message, uid=None):
    if uid is None: uid = message.from_user.id
    if message.from_user.id != uid: return  # Чужое сообщение - игнорируем
    
    c = db_conn.cursor()
    c.execute("SELECT COUNT(*) FROM cities WHERE user_id=?", (uid,))
    if c.fetchone()[0] != 5:  # Должно быть 5 городов
        bot.send_message(message.chat.id, "❌ Ошибка. Напишите /start")
        return
    
    c.execute("UPDATE players SET country_name=? WHERE user_id=?", (message.text.strip(), uid))
    db_conn.commit()
    show_menu(message.chat.id)
    bot.send_message(message.chat.id, "🎉 СТРАНА СОЗДАНА!\n\nпомощь — команды\nсобрать — доход (со 2-го дня)\nстроить — здания")

def show_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(row_width=3, resize_keyboard=True)
    markup.add('анкета','собрать','строить','поиск','склад','города','чертежи','эксп','помощь')
    bot.send_message(chat_id, "📋 Меню:", reply_markup=markup)

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    try:
        uid = message.from_user.id
        text = message.text.strip().lower()
        
        if not is_command(text):
            return
        
        p = get_player(uid)
        
        if not p or not has_country(uid):
            if text == '/start': return
            bot.reply_to(message, "❌ У вас нет страны! Создайте: /start")
            return
        
        banned = p[20] if len(p) > 20 else 0
        muted = p[21] if len(p) > 21 else 0
        
        if banned == 1: return
        if muted == 1: bot.reply_to(message, "🔇 Вы в муте!"); return

        if text in ['анкета']: bot.reply_to(message, show_anketa(uid))
        elif text in ['собрать', 'собрать доход']: cmd_collect(message)
        elif text in ['строить', 'стройка']: cmd_build_menu(message)
        elif text == 'поиск': cmd_search_menu(message)
        elif text == 'склад': cmd_warehouse(message)
        elif text == 'города': cmd_cities(message)
        elif text == 'чертежи': cmd_blueprints(message)
        elif text.startswith('эксп'): cmd_expedition(message)
        elif text in ['помощь', 'команды']: cmd_help(message)
        elif text.startswith('крафт '): cmd_craft(message)
        elif text.startswith('разобрать ') or text.startswith('разбор '): cmd_dismantle(message)
        elif text.startswith('рецепт '): cmd_recipe(message)
        elif text.startswith('!рецепт'): cmd_create_recipe(message)
        elif any(text.startswith(w) for w in ['дот ','бункер ','каземат ']): cmd_fort(message)
        elif any(text.startswith(w) for w in ['город новый ','построить город ']): cmd_new_city(message)
        elif any(text.startswith(w) for w in ['чинить ','город чинить ']): cmd_repair_city(message)
        elif text.startswith('столица '): cmd_move_capital(message)
        elif text.startswith('поделиться '): cmd_share_bp(message)
        elif text.startswith('разведка '): cmd_look(message)
        elif text == 'топ': cmd_top(message)
        elif text == 'мойid': bot.reply_to(message, f"Ваш ID: {uid}")
        elif text.startswith('проверка '): cmd_check_player(message)
        elif text.startswith('дать '): cmd_give(message)
        elif text.startswith('забрать '): cmd_take(message)
        elif text.startswith('всем '): cmd_give_all(message)
        elif text.startswith('сброс '): cmd_reset_player(message)
        elif text.startswith('логи '): cmd_logs(message)
        elif text == 'стандарты': cmd_defaults(message)
        elif text.startswith('стандарт '): cmd_set_default(message)
        elif text == 'применить стандарты': cmd_apply_defaults(message)
        elif text.startswith('модер '): cmd_grant_mod(message)
        elif text.startswith('админ '): cmd_grant_admin(message)
        elif text.startswith('главный '): cmd_grant_head(message)
        elif text.startswith('снять '): cmd_revoke(message)
        elif text == 'админы': cmd_admin_list(message)
        elif text.startswith('бан '): cmd_ban(message)
        elif text.startswith('разбан '): cmd_unban(message)
        elif text.startswith('мут '): cmd_mute(message)
        elif text.startswith('размут '): cmd_unmute(message)
        elif text.startswith('варн ') or text.startswith('пред '): cmd_warn(message)
        elif text.startswith('снятьварн '): cmd_unwarn(message)
        elif text.startswith('откат '): cmd_rollback(message)
    except Exception as e:
        print(f"Ошибка: {e}")

def cmd_collect(message):
    uid = message.from_user.id
    p = get_player(uid)
    today = datetime.now().strftime("%Y-%m-%d")
    last_coll = p[15] if len(p) > 15 else None
    created = p[18] if len(p) > 18 else None
    if last_coll == today: bot.reply_to(message, "❌ Доход уже собран сегодня!"); return
    if created and created == today: bot.reply_to(message, "❌ Первый день страны! Доход со 2-го дня."); return
    c = db_conn.cursor()
    c.execute("SELECT b.building_type, SUM(b.quantity) FROM buildings b JOIN cities c ON b.city_id=c.id WHERE b.user_id=? AND c.is_destroyed=0 GROUP BY b.building_type", (uid,))
    bld = dict(c.fetchall())
    inc = {}
    if 'lumberjack' in bld: inc['wood'] = 80 * bld['lumberjack']
    if 'construction_factory' in bld: inc['cement'] = 100 * bld['construction_factory']
    if 'university' in bld: inc['science_points'] = 2 * bld['university']
    if 'business_center' in bld: inc['tenge'] = 25 * bld['business_center']
    if 'iron_mine' in bld: inc['iron'] = 150 * bld['iron_mine']
    if 'oil_rig' in bld: inc['fuel'] = 150 * bld['oil_rig']
    if 'coal_mine' in bld: inc['coal'] = 125 * bld['coal_mine']
    if 'fabric_factory' in bld: inc['fabric'] = 50 * bld['fabric_factory']
    if 'stables' in bld: inc['horses'] = 20 * bld['stables']
    days = 1
    if last_coll:
        try:
            ld = datetime.strptime(last_coll, "%Y-%m-%d")
            days = max(1, (datetime.now() - ld).days)
        except: days = 1
    for res, val in inc.items(): upd_res(uid, res, val*days)
    c.execute("UPDATE players SET last_collection=? WHERE user_id=?", (today,uid))
    db_conn.commit()
    nm = {'wood':'🪵','cement':'🏗','science_points':'🔬','tenge':'💰','iron':'🔩','fuel':'⛽','coal':'🪨','fabric':'🧵','horses':'🐴'}
    text = f"📊 Доход за {days} дн.:\n"
    for res, val in inc.items(): text += f"{nm.get(res,res)} +{val*days}\n"
    if not inc: text += "Нет работающих зданий.\n"
    bot.reply_to(message, text)

def cmd_build_menu(message):
    c = db_conn.cursor()
    c.execute("SELECT city_name FROM cities WHERE user_id=? AND is_destroyed=0", (message.from_user.id,))
    cities = c.fetchall()
    if not cities: bot.reply_to(message, "❌ Нет доступных городов!"); return
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
    bot.reply_to(message, f"🏗 Выберите здание:\n🏙 Города: {', '.join([c[0] for c in cities])}", reply_markup=mk)

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
    c.execute("SELECT vehicle_name, quantity FROM vehicles WHERE user_id=? AND quantity>0 ORDER BY vehicle_name", (message.from_user.id,))
    items = c.fetchall()
    if not items: bot.reply_to(message, "📦 Склад пуст\nкрафт КОЛИЧЕСТВО НАЗВАНИЕ — построить"); return
    text = "📦 СКЛАД:\n"
    for n,q in items: text += f"• {n}: {q}\n"
    text += f"\nВсего: {sum(i[1] for i in items)} ед."
    bot.reply_to(message, text)

def cmd_cities(message):
    c = db_conn.cursor()
    c.execute("SELECT city_name, is_capital, is_destroyed FROM cities WHERE user_id=?", (message.from_user.id,))
    cities = c.fetchall()
    text = "🏙 ГОРОДА:\n"
    for nm, cap, des in cities:
        s = "⭐ " if cap else "• "
        text += f"{s}{nm}{' ❌' if des else ' ✅'}\n"
    bot.reply_to(message, text)

def cmd_blueprints(message):
    c = db_conn.cursor()
    c.execute("SELECT blueprint_name FROM blueprints WHERE owner_id=?", (message.from_user.id,))
    own = c.fetchall()
    c.execute("SELECT blueprint_name FROM blueprint_access WHERE player_id=?", (message.from_user.id,))
    acc = c.fetchall()
    text = "📋 ЧЕРТЕЖИ:\n"
    if own: text += "\n🔒 Мои:\n" + "\n".join([f"• {b[0]}" for b in own])
    if acc: text += "\n🔓 Доступ:\n" + "\n".join([f"• {b[0]}" for b in acc])
    if not own and not acc: text += "Нет чертежей"
    bot.reply_to(message, text)

def cmd_expedition(message):
    parts = message.text.split()
    if len(parts)>=2 and parts[1]=='статус':
        c = db_conn.cursor()
        c.execute("SELECT region, end_date, reward_population FROM expeditions WHERE user_id=? AND status='active'", (message.from_user.id,))
        exp = c.fetchone()
        if exp: bot.reply_to(message, f"🌍 {exp[0]} | +{exp[2]}👥 | 📅 {exp[1]}")
        else: bot.reply_to(message, "Нет активных экспедиций")
        return
    mk = types.InlineKeyboardMarkup(row_width=1)
    mk.add(types.InlineKeyboardButton("🌍 Европа +200", callback_data="e_europe"),
           types.InlineKeyboardButton("🏯 Азия +200", callback_data="e_asia"),
           types.InlineKeyboardButton("🌴 Африка +225", callback_data="e_africa"),
           types.InlineKeyboardButton("🌎 Сев.Америка +200", callback_data="e_america_north"),
           types.InlineKeyboardButton("🌎 Юж.Америка +200", callback_data="e_america_south"),
           types.InlineKeyboardButton("🦘 Австралия +175", callback_data="e_australia"))
    bot.reply_to(message, "🌍 Куда? (70💰, 3 дня)", reply_markup=mk)

def cmd_help(message):
    bot.reply_to(message, """📖 КОМАНДЫ:
анкета — страна
собрать — доход
строить — здания
поиск — ресурсы
склад — техника
города — города
чертежи — чертежи
эксп — экспедиция

крафт КОЛИЧЕСТВО НАЗВАНИЕ — построить
разобрать КОЛИЧЕСТВО НАЗВАНИЕ — разобрать
рецепт НАЗВАНИЕ — стоимость
!рецепт НАЗВАНИЕ | тип | вес | лс | порох | колёса | сверхтяж | уголь | броня

дот КЛАСС ГОРОД — ДОТ (A,B,C,D)
бункер КЛАСС ГОРОД — бункер
каземат КЛАСС ГОРОД — каземат

город новый НАЗВАНИЕ
чинить НАЗВАНИЕ
столица НАЗВАНИЕ
поделиться НАЗВАНИЕ @игрок
разведка @игрок

топ | мойid | помощь
откат ID — откат""")

def cmd_craft(message):
    uid = message.from_user.id
    try:
        parts = message.text.replace('крафт ','',1).split(' ',1)
        qty = int(parts[0]); name = parts[1].upper()
        c = db_conn.cursor()
        c.execute("SELECT owner_id FROM blueprints WHERE blueprint_name=?", (name,))
        bp = c.fetchone()
        if bp and bp[0] != uid:
            c.execute("SELECT * FROM blueprint_access WHERE blueprint_name=? AND player_id=?", (name,uid))
            if not c.fetchone():
                owner = get_player(bp[0])
                bot.reply_to(message, f"❌ Чертёж {name} у @{owner[1]}! Нет доступа."); return
        c.execute("SELECT * FROM vehicle_recipes WHERE vehicle_name=?", (name,))
        rec = c.fetchone()
        if not rec: bot.reply_to(message, f"❌ Нет рецепта! !рецепт {name} | vehicle | вес | лс | порох | ..."); return
        p = get_player(uid)
        iron = rec[1]*qty; fuel = rec[2]*qty; gp = rec[3]*qty
        if p[6] < iron: bot.reply_to(message, f"❌ Нужно {iron:.0f}🔩 (есть {p[6]:.0f})"); return
        if p[7] < fuel: bot.reply_to(message, f"❌ Нужно {fuel:.0f}⛽ (есть {p[7]:.0f})"); return
        if p[8] < gp: bot.reply_to(message, f"❌ Нужно {gp:.0f}💥 (есть {p[8]:.0f})"); return
        upd_res(uid,'iron',-iron); upd_res(uid,'fuel',-fuel); upd_res(uid,'gunpowder',-gp)
        upd_res(uid,'rubber',-rec[4]*qty); upd_res(uid,'fabric',-rec[5]*qty)
        upd_res(uid,'coal',-rec[6]*qty); upd_res(uid,'special_material',-rec[7]*qty)
        c.execute("SELECT quantity FROM vehicles WHERE user_id=? AND vehicle_name=?", (uid,name))
        have = c.fetchone()
        if have: c.execute("UPDATE vehicles SET quantity=quantity+? WHERE user_id=? AND vehicle_name=?", (qty,uid,name))
        else: c.execute("INSERT INTO vehicles (user_id, vehicle_name, quantity) VALUES (?,?,?)", (uid,name,qty))
        if not bp:
            year = p[17] if len(p) > 17 and p[17] else 1904
            try: year = int(float(year))
            except: year = 1904
            if year <= 1914: sc = 1
            elif year <= 1918: sc = 2
            elif year <= 1926: sc = 3
            elif year <= 1934: sc = 5
            elif year <= 1939: sc = 6
            elif year <= 1945: sc = 8
            elif year <= 1950: sc = 10
            elif year <= 1960: sc = 12
            elif year <= 1965: sc = 15
            else: sc = 20
            if p[4] >= sc:
                upd_res(uid,'science_points',-sc)
                c.execute("INSERT INTO blueprints VALUES (?,?,?)", (name,uid,year))
                bot.send_message(message.chat.id, f"📋 Авто-чертёж {name}! (-{sc}🔬)")
        db_conn.commit()
        log_action(uid, 'craft', f"{qty}x {name}")
        bot.reply_to(message, f"✅ {qty}x {name}\n🔩-{iron:.0f} ⛽-{fuel:.0f} 💥-{gp:.0f}")
    except: bot.reply_to(message, "❌ крафт КОЛИЧЕСТВО НАЗВАНИЕ")

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
        upd_res(uid,'iron',rec[1]*qty); upd_res(uid,'fuel',rec[2]*qty)
        upd_res(uid,'gunpowder',rec[3]*qty); upd_res(uid,'rubber',rec[4]*qty)
        upd_res(uid,'fabric',rec[5]*qty); upd_res(uid,'coal',rec[6]*qty)
        upd_res(uid,'special_material',rec[7]*qty)
        c.execute("UPDATE vehicles SET quantity=quantity-? WHERE user_id=? AND vehicle_name=?", (qty,uid,name))
        db_conn.commit()
        bot.reply_to(message, f"♻ {qty}x {name}\n🔩+{rec[1]*qty:.0f} ⛽+{rec[2]*qty:.0f} 💥+{rec[3]*qty:.0f}")
    except: bot.reply_to(message, "❌ разобрать КОЛИЧЕСТВО НАЗВАНИЕ")

def cmd_recipe(message):
    try:
        name = message.text.replace('рецепт ','',1).upper()
        c = db_conn.cursor()
        c.execute("SELECT * FROM vehicle_recipes WHERE vehicle_name=?", (name,))
        rec = c.fetchone()
        if not rec: bot.reply_to(message, "❌ Не найден!"); return
        text = f"📋 {name}:\n🔩 {rec[1]:.1f}\n⛽ {rec[2]:.1f}\n💥 {rec[3]:.1f}"
        bot.reply_to(message, text)
    except: bot.reply_to(message, "рецепт НАЗВАНИЕ")

def cmd_create_recipe(message):
    uid = message.from_user.id
    try:
        text = message.text.replace('!рецепт ','')
        parts = [p.strip() for p in text.split('|')]
        name = parts[0].upper(); weight = float(parts[2]); power = float(parts[3]); gp_grams = float(parts[4])
        wheels = parts[5].lower()=='да' if len(parts)>5 else False
        super_heavy = parts[6].lower()=='да' if len(parts)>6 else False
        coal_pow = parts[7].lower()=='да' if len(parts)>7 else False
        armor = float(parts[8]) if len(parts)>8 else 0
        iron = weight * 2
        if gp_grams >= 500: gp = gp_grams / 500
        elif gp_grams >= 100: gp = gp_grams / 100
        else: gp = gp_grams / 50
        fuel = 0 if coal_pow else power / 50
        coal = power / 50 if coal_pow else 0
        rubber = 1 if wheels else 0
        special = armor / 1000
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
                  (name,iron,fuel,gp,rubber,0,coal,special))
        db_conn.commit()
        text = f"✅ Рецепт {name}:\n🔩 {iron:.1f}\n⛽ {fuel:.1f}\n💥 {gp:.1f}"
        bot.reply_to(message, text)
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
        names = {'дот':'ДОТ','бункер':'Бункер','каземат':'Каземат'}
        bot.reply_to(message, f"✅ {names.get(ftype,ftype)} {armor} в {city}!")
    except: bot.reply_to(message, "дот КЛАСС Город")

def cmd_new_city(message):
    try:
        for p in ['город новый ','построить город ']:
            if message.text.startswith(p): name = message.text.replace(p,'',1); break
        uid = message.from_user.id
        c = db_conn.cursor()
        if c.execute("SELECT COUNT(*) FROM cities WHERE user_id=?", (uid,)).fetchone()[0] >= MAX_CITIES:
            bot.reply_to(message, f"❌ Максимум {MAX_CITIES} городов!"); return
        p = get_player(uid)
        if p[14] < 850: bot.reply_to(message, "❌ 850🪵"); return
        if p[11] < 1000: bot.reply_to(message, "❌ 1000🏗"); return
        if p[5] < 350: bot.reply_to(message, "❌ 350💰"); return
        upd_res(uid,'wood',-850); upd_res(uid,'cement',-1000); upd_res(uid,'tenge',-350)
        c.execute("INSERT INTO cities (user_id, city_name) VALUES (?,?)", (uid,name))
        db_conn.commit()
        bot.reply_to(message, f"✅ Город {name}!")
    except: bot.reply_to(message, "город новый Название")

def cmd_repair_city(message):
    try:
        for p in ['чинить ','город чинить ']:
            if message.text.startswith(p): name = message.text.replace(p,'',1); break
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

def cmd_check_player(message):
    if not is_admin(message.from_user.id): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        tid = get_uid(message.text.replace('проверка ','',1).replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        bot.reply_to(message, show_anketa(message.from_user.id, tid))
    except: bot.reply_to(message, "проверка @игрок")

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

def cmd_reset_player(message):
    if not is_admin(message.from_user.id, 2): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        tid = get_uid(message.text.replace('сброс ','',1).replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("SELECT resource_name, default_value FROM default_resources")
        for res, val in c.fetchall(): c.execute(f"UPDATE players SET {res}=? WHERE user_id=?", (val,tid))
        c.execute("DELETE FROM buildings WHERE user_id=?", (tid,))
        c.execute("DELETE FROM vehicles WHERE user_id=?", (tid,))
        c.execute("DELETE FROM cities WHERE user_id=?", (tid,))
        db_conn.commit()
        bot.reply_to(message, "✅ Сброшен!")
    except: bot.reply_to(message, "сброс @игрок")

def cmd_logs(message):
    if not is_admin(message.from_user.id): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        tid = get_uid(message.text.replace('логи ','',1).replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("SELECT id, action_type, details, timestamp FROM action_log WHERE user_id=? ORDER BY id DESC LIMIT 10", (tid,))
        logs = c.fetchall()
        text = "📋 Логи:\n"
        for lid, at, det, ts in logs: text += f"#{lid} {at}: {det[:50]} | {ts}\n"
        bot.reply_to(message, text)
    except: bot.reply_to(message, "логи @игрок")

def cmd_defaults(message):
    c = db_conn.cursor()
    c.execute("SELECT * FROM default_resources")
    nm = {'tenge':'💰','iron':'🔩','fuel':'⛽','gunpowder':'💥','coal':'🪨','cement':'🏗','wood':'🪵','fabric':'🧵','horses':'🐴','science_points':'🔬','population':'👥','special_material':'⚗'}
    text = "📋 СТАНДАРТЫ:\n"
    for res, val in c.fetchall(): text += f"{nm.get(res,res)}: {val}\n"
    bot.reply_to(message, text)

def cmd_set_default(message):
    if not is_admin(message.from_user.id, 3): bot.reply_to(message, "❌ Главный админ!"); return
    try:
        parts = message.text.replace('стандарт ','',1).split()
        res = parts[0].lower()
        if res not in RESOURCES: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("INSERT OR REPLACE INTO default_resources VALUES (?,?)", (RESOURCES[res], float(parts[1])))
        db_conn.commit()
        bot.reply_to(message, f"✅ Стандарт {res} = {parts[1]}")
    except: bot.reply_to(message, "стандарт тенге 10000")

def cmd_apply_defaults(message):
    if not is_admin(message.from_user.id, 3): bot.reply_to(message, "❌ Главный админ!"); return
    c = db_conn.cursor()
    c.execute("SELECT resource_name, default_value FROM default_resources")
    defs = c.fetchall()
    c.execute("SELECT user_id FROM players WHERE is_banned=0")
    for (uid,) in c.fetchall():
        for res, val in defs: c.execute(f"UPDATE players SET {res}=? WHERE user_id=?", (val,uid))
    db_conn.commit()
    bot.reply_to(message, "✅ Применено всем!")

def cmd_grant_mod(message):
    if not is_admin(message.from_user.id, 2): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        tid = get_uid(message.text.replace('модер ','',1).replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("INSERT OR REPLACE INTO admins VALUES (?,1,?,?)", (tid, message.from_user.id, datetime.now().strftime("%Y-%m-%d")))
        db_conn.commit()
        bot.reply_to(message, "✅ Модератор!")
    except: bot.reply_to(message, "модер @игрок")

def cmd_grant_admin(message):
    if not is_admin(message.from_user.id, 2): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        tid = get_uid(message.text.replace('админ ','',1).replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("INSERT OR REPLACE INTO admins VALUES (?,2,?,?)", (tid, message.from_user.id, datetime.now().strftime("%Y-%m-%d")))
        db_conn.commit()
        bot.reply_to(message, "✅ Админ!")
    except: bot.reply_to(message, "админ @игрок")

def cmd_grant_head(message):
    if not is_admin(message.from_user.id, 3): bot.reply_to(message, "❌ Главный!"); return
    try:
        tid = get_uid(message.text.replace('главный ','',1).replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("INSERT OR REPLACE INTO admins VALUES (?,3,?,?)", (tid, message.from_user.id, datetime.now().strftime("%Y-%m-%d")))
        db_conn.commit()
        bot.reply_to(message, "✅ Главный админ!")
    except: bot.reply_to(message, "главный @игрок")

def cmd_revoke(message):
    if not is_admin(message.from_user.id, 2): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        tid = get_uid(message.text.replace('снять ','',1).replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("DELETE FROM admins WHERE user_id=?", (tid,))
        db_conn.commit()
        bot.reply_to(message, "✅ Снят!")
    except: bot.reply_to(message, "снять @игрок")

def cmd_admin_list(message):
    c = db_conn.cursor()
    c.execute("SELECT a.admin_level, p.username FROM admins a JOIN players p ON a.user_id=p.user_id")
    lvls = {1:'Модер',2:'Админ',3:'Главный'}
    text = "👑 АДМИНЫ:\n"
    for lvl, un in c.fetchall(): text += f"• @{un} — {lvls.get(lvl,lvl)}\n"
    bot.reply_to(message, text)

def cmd_ban(message):
    if not is_admin(message.from_user.id, 2): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        parts = message.text.split()
        tid = get_uid(parts[1].replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("UPDATE blueprints SET owner_id=0 WHERE owner_id=?", (tid,))
        c.execute("DELETE FROM cities WHERE user_id=?", (tid,))
        c.execute("DELETE FROM buildings WHERE user_id=?", (tid,))
        c.execute("DELETE FROM vehicles WHERE user_id=?", (tid,))
        c.execute("DELETE FROM deposits WHERE user_id=?", (tid,))
        c.execute("DELETE FROM expeditions WHERE user_id=?", (tid,))
        c.execute("DELETE FROM blueprint_access WHERE player_id=?", (tid,))
        c.execute("UPDATE players SET is_banned=1, population=0, tenge=0, iron=0, fuel=0, gunpowder=0, rubber=0, fabric=0, coal=0, cement=0, uranium=0, wood=0, horses=0, special_material=0, science_points=0 WHERE user_id=?", (tid,))
        db_conn.commit()
        bot.reply_to(message, f"🚫 @{parts[1].replace('@','')} забанен! Страна уничтожена.")
    except: bot.reply_to(message, "бан @игрок")

def cmd_unban(message):
    if not is_admin(message.from_user.id, 2): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        parts = message.text.split()
        tid = get_uid(parts[1].replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("DELETE FROM cities WHERE user_id=?", (tid,))
        c.execute("SELECT resource_name, default_value FROM default_resources")
        for res, val in c.fetchall(): c.execute(f"UPDATE players SET {res}=? WHERE user_id=?", (val, tid))
        c.execute("UPDATE players SET is_banned=0, is_muted=0, warns=0, created_date=? WHERE user_id=?", (datetime.now().strftime("%Y-%m-%d"), tid))
        c.execute("INSERT INTO cities (user_id, city_name, is_capital) VALUES (?,?,1)", (tid, "Столица"))
        for i in range(4): c.execute("INSERT INTO cities (user_id, city_name) VALUES (?,?)", (tid, f"Город{i+1}"))
        db_conn.commit()
        bot.reply_to(message, f"✅ @{parts[1].replace('@','')} разбанен!")
    except: bot.reply_to(message, "разбан @игрок")

def cmd_mute(message):
    if not is_admin(message.from_user.id, 1): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        tid = get_uid(message.text.replace('мут ','',1).replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("UPDATE players SET is_muted=1 WHERE user_id=?", (tid,))
        db_conn.commit()
        bot.reply_to(message, f"🔇 @{message.text.split()[1].replace('@','')} в муте!")
    except: bot.reply_to(message, "мут @игрок")

def cmd_unmute(message):
    if not is_admin(message.from_user.id, 1): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        tid = get_uid(message.text.replace('размут ','',1).replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("UPDATE players SET is_muted=0 WHERE user_id=?", (tid,))
        db_conn.commit()
        bot.reply_to(message, f"🔊 @{message.text.split()[1].replace('@','')} размучен!")
    except: bot.reply_to(message, "размут @игрок")

def cmd_warn(message):
    if not is_admin(message.from_user.id, 1): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        tid = get_uid(message.text.replace('варн ','',1).replace('пред ','',1).replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("UPDATE players SET warns=warns+1 WHERE user_id=?", (tid,))
        c.execute("SELECT warns FROM players WHERE user_id=?", (tid,))
        warns = c.fetchone()[0]
        reply = f"⚠️ @{message.text.split()[1].replace('@','')} получил варн! ({warns}/3)"
        if warns >= 3:
            c.execute("UPDATE blueprints SET owner_id=0 WHERE owner_id=?", (tid,))
            c.execute("DELETE FROM cities WHERE user_id=?", (tid,))
            c.execute("DELETE FROM buildings WHERE user_id=?", (tid,))
            c.execute("DELETE FROM vehicles WHERE user_id=?", (tid,))
            c.execute("UPDATE players SET is_banned=1 WHERE user_id=?", (tid,))
            db_conn.commit()
            reply += "\n🚫 3 варна — АВТО-БАН!"
        db_conn.commit()
        bot.reply_to(message, reply)
    except: bot.reply_to(message, "варн @игрок")

def cmd_unwarn(message):
    if not is_admin(message.from_user.id, 1): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        tid = get_uid(message.text.replace('снятьварн ','',1).replace('@',''))
        if not tid: bot.reply_to(message, "❌ Не найден!"); return
        c = db_conn.cursor()
        c.execute("UPDATE players SET warns=MAX(0,warns-1) WHERE user_id=?", (tid,))
        db_conn.commit()
        bot.reply_to(message, "✅ Варн снят!")
    except: bot.reply_to(message, "снятьварн @игрок")

def cmd_rollback(message):
    if not is_admin(message.from_user.id, 1): bot.reply_to(message, "❌ Нет прав!"); return
    try:
        aid = int(message.text.replace('откат ','',1))
        c = db_conn.cursor()
        c.execute("SELECT * FROM action_log WHERE id=? AND can_rollback=1", (aid,))
        a = c.fetchone()
        if not a: bot.reply_to(message, "❌ Не найдено!"); return
        uid, atype, details = a[1], a[2], a[3]
        if atype == 'craft':
            parts = details.split('x ')
            if len(parts)==2:
                qty = int(parts[0]); name = parts[1]
                c.execute("SELECT * FROM vehicle_recipes WHERE vehicle_name=?", (name,))
                rec = c.fetchone()
                if rec:
                    upd_res(uid,'iron',rec[1]*qty); upd_res(uid,'fuel',rec[2]*qty)
                    upd_res(uid,'gunpowder',rec[3]*qty); upd_res(uid,'rubber',rec[4]*qty)
                    upd_res(uid,'fabric',rec[5]*qty); upd_res(uid,'coal',rec[6]*qty)
                    c.execute("UPDATE vehicles SET quantity=quantity-? WHERE user_id=? AND vehicle_name=?", (qty,uid,name))
                    c.execute("UPDATE action_log SET can_rollback=0 WHERE id=?", (aid,))
                    db_conn.commit()
                    bot.reply_to(message, f"♻ Откат #{aid}: {qty}x {name}")
                    return
        bot.reply_to(message, "❌ Не удалось")
    except: bot.reply_to(message, "откат ID")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    uid = call.from_user.id
    p = get_player(uid)
    if not p: return
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
            if p[5] < costs[dep]: bot.answer_callback_query(call.id, f"❌ {costs[dep]}💰"); return
            upd_res(uid,'tenge',-costs[dep])
            ok = random.randint(1,5)==1 if dep=='uranium' else random.random()<0.5
            if ok:
                c = db_conn.cursor()
                c.execute("INSERT OR IGNORE INTO deposits (user_id, deposit_type) VALUES (?,?)", (uid,dep))
                db_conn.commit()
                bot.answer_callback_query(call.id, "✅ Найдено!")
            else: bot.answer_callback_query(call.id, "❌ Пусто")
    
    elif data.startswith('e_'):
        reg = data[2:]
        rewards = {'europe':200,'asia':200,'africa':225,'america_north':200,'america_south':200,'australia':175}
        names = {'europe':'Европа','asia':'Азия','africa':'Африка','america_north':'Сев.Америка','america_south':'Юж.Америка','australia':'Австралия'}
        if p[5] < 70: bot.answer_callback_query(call.id, "❌ 70💰"); return
        c = db_conn.cursor()
        c.execute("SELECT id FROM expeditions WHERE user_id=? AND status='active'", (uid,))
        if c.fetchone(): bot.answer_callback_query(call.id, "❌ Уже есть!"); return
        upd_res(uid,'tenge',-70)
        end = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
        c.execute("INSERT INTO expeditions (user_id, region, end_date, reward_population) VALUES (?,?,?,?)", (uid,reg,end,rewards[reg]))
        db_conn.commit()
        bot.answer_callback_query(call.id, f"✅ {names[reg]}!")
        bot.send_message(call.message.chat.id, f"🌍 {names[reg]} | +{rewards[reg]}👥 | 📅 {end}")

if __name__ == '__main__':
    print("🤖 Бот запущен!")
    threading.Thread(target=check_expeditions, daemon=True).start()
    threading.Thread(target=update_game_time, daemon=True).start()
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)
