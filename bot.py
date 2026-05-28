def cmd_collect(message):
    uid = message.from_user.id
    p = get_player(uid)
    
    can, multiplier, remaining = can_collect_income(uid)
    
    if not can:
        bot.reply_to(message, f"❌ Доход уже собран! Следующий через {remaining}")
        return
    
    if len(p) > 18 and p[18] and p[18] == datetime.now().strftime("%Y-%m-%d"):
        bot.reply_to(message, "❌ Первый день страны! Доход со 2-го дня.")
        return
    
    income = get_buildings_income(uid)
    
    if sum(income.values()) == 0:
        bot.reply_to(message, "❌ Нет построек для дохода!")
        return
    
    for res, val in income.items():
        if val > 0:
            upd_res(uid, res, val * multiplier)
    
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c = db_conn.cursor()
    c.execute("UPDATE players SET last_collection=? WHERE user_id=?", (today, uid))
    db_conn.commit()
    
    # ПРОВЕРКА что сохранилось
    c.execute("SELECT last_collection FROM players WHERE user_id=?", (uid,))
    saved = c.fetchone()
    if not saved or saved[0] != today:
        bot.reply_to(message, "❌ Ошибка сохранения!")
        return
    
    nm = {'tenge':'💰','wood':'🪵','cement':'🏗','science_points':'🔬','iron':'🔩','fuel':'⛽','coal':'🪨','fabric':'🧵','horses':'🐴'}
    text = f"📊 Доход за {multiplier} дн:\n" if multiplier > 1 else "📊 Доход собран:\n"
    for res, val in income.items():
        if val > 0:
            text += f"{nm.get(res,res)} +{val * multiplier}\n"
    bot.reply_to(message, text)
