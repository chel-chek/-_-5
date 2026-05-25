import telebot
from telebot import types
import sqlite3
from datetime import datetime, timedelta
import random
import time
import threading

TOKEN = '8786607133:AAGRlo79hTxWroCN-1vppbH9i0nCQrGS6OI'

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

# Состояния создания страны
creating_country = {}

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
    for btype, qty in c.fetchall():
        if qty and btype in BUILDING_POP:
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

def show_anketa(uid, target_id=None):
    if target_id is None: target_id = uid
    p = get_player(target_id)
    if not p: return "Страна не найдена"
    c = db_conn.cursor()
    c.execute("SELECT id, city_name, is_capital, is_destroyed FROM cities WHERE user_id=?", (target_id,))
    cities = c.fetchall()
    c.execute("SELECT vehicle_name, quantity FROM vehicles WHERE user_id=? AND quantity>0 ORDER BY vehicle_name", (target_id,))
    veh = c.fetchall()
    
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
    
    if veh:
        total_veh = sum(v[1] for v in veh)
        text += f"\n📦 СКЛАД ({total_veh} ед.):\n"
        for v,q in veh[:10]: text += f"• {v}: {q}\n"
    
    return text

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
    
    if p and has_country(uid):
        show_menu(message.chat.id)
        bot.send_message(message.chat.id, "🎮 С возвращением! помощь — команды")
        return
    
    c = db_conn.cursor()
    c.execute("INSERT OR REPLACE INTO players (user_id, username, created_date, last_login) VALUES (?,?,?,?)",
              (uid, uname, datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%Y-%m-%d")))
    db_conn.commit()
    
    # Начинаем создание страны
    creating_country[uid] = {'step': 'capital'}
    bot.send_message(message.chat.id, "🎮 Добро пожаловать!\n\nВведите название столицы:")

def show_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(row_width=3, resize_keyboard=True)
    markup.add('анкета','собрать','строить','поиск','склад','города','чертежи','эксп','помощь')
    bot.send_message(chat_id, "📋 Меню:", reply_markup=markup)

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    try:
        uid = message.from_user.id
        text = message.text.strip()
        
        # Обработка создания страны
        if uid in creating_country:
            state = creating_country[uid]
            
            if state['step'] == 'capital':
                c = db_conn.cursor()
                c.execute("INSERT INTO cities (user_id, city_name, is_capital) VALUES (?,?,1)", (uid, text))
                db_conn.commit()
                state['step'] = 'cities'
                bot.send_message(message.chat.id, f"✅ Столица: {text}\n\nВведите 4 города через запятую:\nПример: Киев, Одесса, Новгород, Казань")
                return
            
            elif state['step'] == 'cities':
                cities = [c.strip() for c in text.split(',')]
                if len(cities) != 4:
                    bot.send_message(message.chat.id, "❌ Нужно ровно 4 города!")
                    return
                c = db_conn.cursor()
                for city in cities:
                    c.execute("INSERT INTO cities (user_id, city_name) VALUES (?,?)", (uid, city))
                db_conn.commit()
                state['step'] = 'country'
                bot.send_message(message.chat.id, "Введите название страны:")
                return
            
            elif state['step'] == 'country':
                c = db_conn.cursor()
                c.execute("UPDATE players SET country_name=? WHERE user_id=?", (text, uid))
                db_conn.commit()
                del creating_country[uid]
                show_menu(uid)
                bot.send_message(message.chat.id, "🎉 СТРАНА СОЗДАНА!\n\nпомощь — команды\nсобрать — доход (со 2-го дня)\nстроить — здания")
                return
        
        # Обычные команды
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
        elif text.startswith('дать '): cmd_give(message)
        elif text.startswith('забрать '): cmd_take(message)
        elif text.startswith('всем '): cmd_give_all(message)
        elif text.startswith('бан '): cmd_ban(message)
        elif text.startswith('разбан '): cmd_unban(message)
        elif text.startswith('мут '): cmd_mute(message)
        elif text.startswith('размут '): cmd_unmute(message)
        elif text.startswith('варн ') or text.startswith('пред '): cmd_warn(message)
        elif text.startswith('снятьварн '): cmd_unwarn(message)
        elif text.startswith('откат '): cmd_rollback(message)
        elif text == 'админы': cmd_admin_list(message)
    except Exception as e:
        print(f"Ошибка: {e}")

# --- Остальные функции (cmd_collect, cmd_build_menu, ...) оставь без изменений ---

if __name__ == '__main__':
    print("🤖 Бот запущен!")
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)
