import telebot
from telebot import types
import sqlite3
from datetime import datetime, timedelta
import time
import threading
import os
from flask import Flask

app = Flask(__name__)

@app.route('/health')
def health():
    return 'OK', 200

TOKEN = os.environ.get('BOT_TOKEN', '')

bot = telebot.TeleBot(TOKEN)

def init_db():
    conn = sqlite3.connect('game.db', check_same_thread=False)
    c = conn.cursor()
    
    # Таблица сбора дохода (24 часа, накапливается)
    c.execute('''CREATE TABLE IF NOT EXISTS income_collect
                 (user_id INTEGER PRIMARY KEY, last_time TEXT)''')
    
    # Таблица прироста населения (72 часа, НЕ накапливается)
    c.execute('''CREATE TABLE IF NOT EXISTS population_collect
                 (user_id INTEGER PRIMARY KEY, last_time TEXT)''')
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, 
                  balance REAL DEFAULT 0,
                  population INTEGER DEFAULT 10)''')
    
    # Таблица зданий
    c.execute('''CREATE TABLE IF NOT EXISTS buildings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  building_type TEXT,
                  income REAL DEFAULT 0,
                  level INTEGER DEFAULT 1)''')
    
    conn.commit()
    return conn

db = init_db()

# ========== СИСТЕМА ДОХОДА (24 часа, накапливается) ==========

def get_user_income(uid):
    """Рассчитывает базовый доход от всех зданий"""
    c = db.cursor()
    c.execute("SELECT SUM(income) FROM buildings WHERE user_id=?", (uid,))
    total = c.fetchone()[0]
    return total if total else 25  # Базовый доход 25 если нет зданий

def can_collect_income(uid):
    """Проверяет возможность сбора дохода (НАКАПЛИВАЕТСЯ)"""
    c = db.cursor()
    c.execute("SELECT last_time FROM income_collect WHERE user_id=?", (uid,))
    row = c.fetchone()
    
    if not row or not row[0]:
        return True, 1, None  # Первый сбор
    
    try:
        last_dt = datetime.strptime(row[0][:19], "%Y-%m-%d %H:%M:%S")
        passed_seconds = (datetime.now() - last_dt).total_seconds()
        
        # Считаем сколько полных 24-часовых циклов прошло
        cycles = int(passed_seconds // 86400)
        
        if cycles >= 1:
            return True, cycles, None  # Можно собрать с множителем
        
        # Прошло меньше 24 часов
        remaining = 86400 - passed_seconds
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        return False, 0, f"{hours}ч {minutes}мин"
        
    except Exception as e:
        print(f"Ошибка в can_collect_income: {e}")
        return True, 1, None

def save_income_time(uid):
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c = db.cursor()
    c.execute("INSERT OR REPLACE INTO income_collect VALUES (?,?)", (uid, today))
    db.commit()

# ========== СИСТЕМА НАСЕЛЕНИЯ (72 часа, НЕ накапливается) ==========

def can_collect_population(uid):
    """Проверяет возможность прироста населения (НЕ накапливается)"""
    c = db.cursor()
    c.execute("SELECT last_time FROM population_collect WHERE user_id=?", (uid,))
    row = c.fetchone()
    
    if not row or not row[0]:
        return True, None  # Первый прирост
    
    try:
        last_dt = datetime.strptime(row[0][:19], "%Y-%m-%d %H:%M:%S")
        passed_seconds = (datetime.now() - last_dt).total_seconds()
        
        if passed_seconds >= 259200:  # 72 часа = 259200 секунд
            return True, None
        
        remaining = 259200 - passed_seconds
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        return False, f"{hours}ч {minutes}мин"
        
    except Exception as e:
        print(f"Ошибка в can_collect_population: {e}")
        return True, None

def save_population_time(uid):
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c = db.cursor()
    c.execute("INSERT OR REPLACE INTO population_collect VALUES (?,?)", (uid, today))
    db.commit()

def add_population(uid):
    """Добавляет население и списывает 70 тенге"""
    c = db.cursor()
    c.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    row = c.fetchone()
    balance = row[0] if row else 0
    
    if balance < 70:
        return False, "Недостаточно тенге! Нужно 70💰", None
    
    c.execute("""INSERT INTO users (user_id, balance, population) 
                 VALUES (?, -70, 11)
                 ON CONFLICT(user_id) DO UPDATE 
                 SET balance = balance - 70,
                     population = population + 1""", (uid,))
    db.commit()
    
    c.execute("SELECT population, balance FROM users WHERE user_id=?", (uid,))
    pop, bal = c.fetchone()
    
    return True, f"👥 Население увеличено! +1 житель\nТекущее население: {pop}\nОстаток: {bal}💰", pop

# ========== ОБЩИЕ ФУНКЦИИ ==========

def add_balance(uid, amount):
    """Добавляет тенге на баланс"""
    c = db.cursor()
    c.execute("""INSERT INTO users (user_id, balance) VALUES (?, ?)
                 ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?""", 
              (uid, amount, amount))
    db.commit()

def get_user_info(uid):
    """Получает информацию о пользователе"""
    c = db.cursor()
    c.execute("SELECT balance, population FROM users WHERE user_id=?", (uid,))
    row = c.fetchone()
    if row:
        return row[0], row[1]
    # Создаем пользователя с начальными значениями
    c.execute("INSERT OR IGNORE INTO users (user_id, balance, population) VALUES (?, 0, 10)", (uid,))
    db.commit()
    return 0, 10

# ========== КОМАНДЫ БОТА ==========

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, 
                 "🎮 Экономическая игра!\n\n"
                 "💰 собрать - собрать доход (раз в 24ч, накапливается)\n"
                 "👥 население - прирост населения (раз в 72ч, 70💰)\n"
                 "📊 статус - баланс, население и таймеры")

@bot.message_handler(func=lambda m: m.text.lower() == 'собрать')
def collect_income(message):
    uid = message.from_user.id
    can, multiplier, remaining = can_collect_income(uid)
    
    if not can:
        bot.reply_to(message, f"❌ Доход уже собран! Следующий через {remaining}")
        return
    
    # Рассчитываем доход с учетом накопления
    base_income = get_user_income(uid)
    total_income = base_income * multiplier
    
    # Начисляем и сохраняем время
    add_balance(uid, total_income)
    save_income_time(uid)
    
    # Получаем обновленный баланс
    balance, _ = get_user_info(uid)
    
    if multiplier > 1:
        bot.reply_to(message, 
                     f"✅ Доход собран!\n"
                     f"+{total_income}💰 (пропущено {multiplier} циклов по {base_income}💰)\n"
                     f"Баланс: {balance}💰\n"
                     f"Следующий сбор через 24 часа.")
    else:
        bot.reply_to(message, 
                     f"✅ Доход собран! +{total_income}💰\n"
                     f"Баланс: {balance}💰\n"
                     f"Следующий сбор через 24 часа.")

@bot.message_handler(func=lambda m: m.text.lower() == 'население')
def collect_population(message):
    uid = message.from_user.id
    can, remaining = can_collect_population(uid)
    
    if not can:
        bot.reply_to(message, f"❌ Прирост населения недоступен! Следующий через {remaining}")
        return
    
    success, msg, _ = add_population(uid)
    
    if not success:
        bot.reply_to(message, f"❌ {msg}")
        return
    
    save_population_time(uid)
    bot.reply_to(message, f"✅ {msg}\nСледующий прирост через 72 часа.")

@bot.message_handler(func=lambda m: m.text.lower() == 'статус')
def status(message):
    uid = message.from_user.id
    balance, population = get_user_info(uid)
    
    # Проверяем таймеры
    can_income, multiplier, income_remaining = can_collect_income(uid)
    can_pop, pop_remaining = can_collect_population(uid)
    
    # Статус дохода
    if can_income:
        base_income = get_user_income(uid)
        potential = base_income * multiplier
        income_status = f"✅ Доступен (+{potential}💰)"
    else:
        income_status = f"⏳ Через {income_remaining}"
    
    # Статус населения
    if can_pop:
        pop_status = "✅ Доступен (70💰)"
    else:
        pop_status = f"⏳ Через {pop_remaining}"
    
    # Считаем доход от зданий
    base_income = get_user_income(uid)
    
    bot.reply_to(message, 
                 f"📊 Статус:\n"
                 f"💰 Баланс: {balance} тенге\n"
                 f"👥 Население: {population}\n"
                 f"🏗 Доход от зданий: {base_income}💰/цикл\n\n"
                 f"Сбор дохода: {income_status}\n"
                 f"Прирост населения: {pop_status}")

if __name__ == '__main__':
    print("🤖 Бот запущен!")
    
    def run_web():
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port)
    
    threading.Thread(target=run_web, daemon=True).start()
    
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)
