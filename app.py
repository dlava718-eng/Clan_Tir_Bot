import os
import sys
import sqlite3
import threading
import asyncio
from datetime import datetime
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8882364637:AAHUWNZilUdxotSOXg44owGgCsuozHGlT48")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 5611887050))
COOLDOWN_DAYS = int(os.environ.get("COOLDOWN_DAYS", 7))
DATABASE_FILE = "/data/applications.db"

# Проверка переменных
if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не задан!")
    sys.exit(1)

if not ADMIN_ID:
    print("❌ ОШИБКА: ADMIN_ID не задан!")
    sys.exit(1)

print(f"✅ Токен: {BOT_TOKEN[:10]}...")
print(f"✅ ADMIN_ID: {ADMIN_ID}")

# Состояния анкеты
ASK_DESCRIPTION, ASK_LEVEL, ASK_NAME, ASK_SKILLS, ASK_TIMEZONE, ASK_AGE = range(6)

# Хранилище временных данных
user_data_temp = {}

# Flask приложение
flask_app = Flask(__name__)

# ========== БАЗА ДАННЫХ ==========
def init_database():
    os.makedirs(os.path.dirname(DATABASE_FILE), exist_ok=True)
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            clan_choice TEXT NOT NULL,
            description TEXT,
            level INTEGER,
            ingame_name TEXT,
            skills TEXT,
            timezone TEXT,
            age INTEGER,
            timestamp TEXT NOT NULL,
            status TEXT DEFAULT 'pending'
        )
    ''')
    conn.commit()
    conn.close()
    print(f"✅ База данных: {DATABASE_FILE}")

def save_application(user_id, username, clan_choice, answers):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO applications 
        (user_id, username, clan_choice, description, level, ingame_name, skills, timezone, age, timestamp, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id, username, clan_choice,
        answers['описание'], answers['уровень'], answers['имя'],
        answers['навыки'], answers['часовой пояс'], answers['возраст'],
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'pending'
    ))
    app_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return app_id

def get_all_applications():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM applications ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()
    apps = []
    for row in rows:
        apps.append({
            "id": row[0], "user_id": row[1], "username": row[2], "clan_choice": row[3],
            "answers": {
                "описание": row[4], "уровень": row[5], "имя": row[6],
                "навыки": row[7], "часовой пояс": row[8], "возраст": row[9]
            },
            "timestamp": row[10], "status": row[11]
        })
    return apps

def get_application_by_id(app_id):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM applications WHERE id = ?', (app_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0], "user_id": row[1], "username": row[2], "clan_choice": row[3],
            "answers": {
                "описание": row[4], "уровень": row[5], "имя": row[6],
                "навыки": row[7], "часовой пояс": row[8], "возраст": row[9]
            },
            "timestamp": row[10], "status": row[11]
        }
    return None

def get_user_last_application(user_id):
    apps = get_all_applications()
    for app in apps:
        if app["user_id"] == user_id:
            return app
    return None

def get_statistics():
    apps = get_all_applications()
    total = len(apps)
    pending = len([a for a in apps if a["status"] == "pending"])
    accepted = len([a for a in apps if a["status"] == "accepted"])
    rejected = len([a for a in apps if a["status"] == "rejected"])
    tir = len([a for a in apps if a["clan_choice"] == "Tir"])
    academia = len([a for a in apps if a["clan_choice"] == "Academia"])
    return total, pending, accepted, rejected, tir, academia

def update_status(app_id, new_status):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE applications SET status = ? WHERE id = ?', (new_status, app_id))
    conn.commit()
    conn.close()

def delete_app(app_id):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM applications WHERE id = ?', (app_id,))
    conn.commit()
    conn.close()

# ========== ГЛАВНОЕ МЕНЮ ==========
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None):
    keyboard = [
        [InlineKeyboardButton("⚔️ Вступить в Tir", callback_data="join_tir")],
        [InlineKeyboardButton("📚 Вступить в Academia", callback_data="join_academia")],
        [InlineKeyboardButton("🌟 О нас", callback_data="about_us")],
        [InlineKeyboardButton("🔄 Разница между Tir и Academia", callback_data="difference")],
        [InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    menu_text = "🏰 *Добро пожаловать в клан Tir!* 🏰\n\nВыберите действие из меню ниже:"
    
    if message:
        await message.edit_text(menu_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(menu_text, reply_markup=reply_markup, parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_temp.pop(user_id, None)
    await main_menu(update, context)

# ========== ИНФОРМАЦИОННЫЕ КНОПКИ ==========
async def about_us_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    about_text = """
🏰 **О клане Tir** 🏰

*Мы не просто клан — мы братство воинов, объединённых одной целью: стать легендой!*

⚡ **Наш путь** ⚡
Мы прошли через огонь и воду, через сотни битв и тысячи побед. Tir — это не название, это клеймо на сердце каждого из нас.

🎯 **Наша философия** 🎯
— Сила в единстве
— Честь выше победы
— Дисциплина ведёт к величию
— Помощь ближнему — закон

💪 **Что мы даём игрокам** 💪
• Профессиональное развитие от опытных игроков
• Участие в топовых ивентах и рейдах
• Дружное комьюнити без токсичности
• Поддержку 24/7 в любых начинаниях

🔥 **Наши достижения** 🔥
Топ-10 кланов по PvP | 3-кратные победители клановых турниров | Более 500 совместных побед

*Стань частью истории. Стань частью TIR!* 🐉
"""
    keyboard = [[InlineKeyboardButton("◀️ Вернуться в меню", callback_data="back_to_menu")]]
    await query.edit_message_text(about_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def difference_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    diff_text = """
🔄 **Разница между Tir и Academia** 🔄

⚔️ **TIR — ОСНОВНОЙ КЛАН** ⚔️

*Элитное подразделение, кузница чемпионов*

• Ядро клана, состоящее из опытных ветеранов
• Участие в топовых рейдах и PvP-сражениях
• Стратегическое планирование и управление
• Наставничество над академией
• Более высокие требования к уровню и навыкам
• Основные ресурсы клана

---

📚 **ACADEMIA — КУЗНИЦА КАДРОВ** 📚

*Школа будущих чемпионов*

• Подготовка новых игроков к основному составу
• Обучение механикам и тактикам
• Помощь в развитии и прокачке
• Более мягкие требования к уровню
• Ресурсная база для основного клана

---

🔄 **ВЗАИМОДЕЙСТВИЕ** 🔄

🤝 **Как они работают вместе:**

• Tir помогает Academia развиваться: передаёт опыт, проводит обучение, защищает на ивентах
• Academia снабжает Tir ресурсами: собирает материалы, выполняет вспомогательные задачи, готовит новобранцев

🎯 **Путь развития:** Academia → Обучение → Повышение навыков → Вступление в Tir

*Вместе мы создаём идеальную клановую экосистему!* 💪
"""
    keyboard = [[InlineKeyboardButton("◀️ Вернуться в меню", callback_data="back_to_menu")]]
    await query.edit_message_text(diff_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ========== АНКЕТА ==========
async def join_tir_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    last_app = get_user_last_application(user_id)
    if last_app and last_app["status"] in ["pending", "accepted"]:
        keyboard = [[InlineKeyboardButton("◀️ Вернуться в меню", callback_data="back_to_menu")]]
        await query.edit_message_text(
            "⏰ Вы уже подавали заявку!\n\nСтатус вашей заявки можно проверить командой /myapp",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    user_data_temp[user_id] = {"clan": "Tir", "step": ASK_DESCRIPTION}
    await query.edit_message_text(
        "⚔️ *Ты выбрал клан Tir!* ⚔️\n\n"
        "📝 *Напиши ОПИСАНИЕ о себе:*\n"
        "(Кратко расскажи, кто ты, чем занимаешься в игре)",
        parse_mode="Markdown"
    )

async def join_academia_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    last_app = get_user_last_application(user_id)
    if last_app and last_app["status"] in ["pending", "accepted"]:
        keyboard = [[InlineKeyboardButton("◀️ Вернуться в меню", callback_data="back_to_menu")]]
        await query.edit_message_text(
            "⏰ Вы уже подавали заявку!\n\nСтатус вашей заявки можно проверить командой /myapp",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    user_data_temp[user_id] = {"clan": "Academia", "step": ASK_DESCRIPTION}
    await query.edit_message_text(
        "📚 *Ты выбрал Academia!* 📚\n\n"
        "📝 *Напиши ОПИСАНИЕ о себе:*\n"
        "(Кто ты, какой у тебя опыт, чего хочешь достичь)",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    
    if user_id not in user_data_temp:
        return
    
    step = user_data_temp[user_id].get("step")
    
    if step == ASK_DESCRIPTION:
        user_data_temp[user_id]["description"] = text
        user_data_temp[user_id]["step"] = ASK_LEVEL
        await update.message.reply_text("✨ *Введите УРОВЕНЬ персонажа:*\n(Только число)", parse_mode="Markdown")
    
    elif step == ASK_LEVEL:
        if not text.isdigit():
            await update.message.reply_text("❌ Пожалуйста, введите число (уровень):")
            return
        user_data_temp[user_id]["level"] = int(text)
        user_data_temp[user_id]["step"] = ASK_NAME
        await update.message.reply_text("🎮 *Как ваше ИМЯ в игре?*", parse_mode="Markdown")
    
    elif step == ASK_NAME:
        user_data_temp[user_id]["name"] = text
        user_data_temp[user_id]["step"] = ASK_SKILLS
        await update.message.reply_text("⚔️ *Опишите свои НАВЫКИ:*\n(Класс, роль в команде)", parse_mode="Markdown")
    
    elif step == ASK_SKILLS:
        user_data_temp[user_id]["skills"] = text
        user_data_temp[user_id]["step"] = ASK_TIMEZONE
        await update.message.reply_text("🌍 *Ваш ЧАСОВОЙ ПОЯС:*\n(Например: UTC+3, Москва)", parse_mode="Markdown")
    
    elif step == ASK_TIMEZONE:
        user_data_temp[user_id]["timezone"] = text
        user_data_temp[user_id]["step"] = ASK_AGE
        await update.message.reply_text("🎂 *Сколько вам ЛЕТ?*", parse_mode="Markdown")
    
    elif step == ASK_AGE:
        if not text.isdigit():
            await update.message.reply_text("❌ Пожалуйста, введите число (возраст):")
            return
        
        user_data_temp[user_id]["age"] = int(text)
        
        answers = {
            "описание": user_data_temp[user_id]["description"],
            "уровень": user_data_temp[user_id]["level"],
            "имя": user_data_temp[user_id]["name"],
            "навыки": user_data_temp[user_id]["skills"],
            "часовой пояс": user_data_temp[user_id]["timezone"],
            "возраст": user_data_temp[user_id]["age"]
        }
        
        app_id = save_application(
            user_id=user_id,
            username=update.message.from_user.username or "нет_username",
            clan_choice=user_data_temp[user_id]["clan"],
            answers=answers
        )
        
        del user_data_temp[user_id]
        
        keyboard = [[InlineKeyboardButton("◀️ Вернуться в меню", callback_data="back_to_menu")]]
        await update.message.reply_text(
            f"✅ *Заявка #{app_id} отправлена!*\n\n"
            "Ожидайте ответа лидера или зама.\n"
            "Спасибо, что выбрали наш клан! 🙌\n\n"
            "Статус заявки можно проверить командой /myapp",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def my_application(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    last_app = get_user_last_application(user_id)
    
    if last_app is None:
        await update.message.reply_text(
            "📭 *У вас нет отправленных заявок.*\n\n"
            "Нажмите /start и выберите 'Вступить в Tir' или 'Вступить в Academia'",
            parse_mode="Markdown"
        )
        return
    
    status_emoji = {"pending": "⏳", "accepted": "✅", "rejected": "❌"}.get(last_app["status"], "❓")
    status_text = {"pending": "Ожидает рассмотрения", "accepted": "✅ ПРИНЯТА!", "rejected": "❌ ОТКЛОНЕНА"}.get(last_app["status"], "Неизвестно")
    
    message = f"""
{status_emoji} *Статус вашей заявки*

📋 *Заявка #{last_app['id']}*
🏰 Клан: {last_app['clan_choice']}
📅 Дата: {last_app['timestamp']}
📊 Статус: {status_text}

📝 *Ваши данные:*
• Описание: {last_app['answers']['описание']}
• Уровень: {last_app['answers']['уровень']}
• Имя в игре: {last_app['answers']['имя']}
• Навыки: {last_app['answers']['навыки']}
• Часовой пояс: {last_app['answers']['часовой пояс']}
• Возраст: {last_app['answers']['возраст']}
"""
    await update.message.reply_text(message, parse_mode="Markdown")

# ========== АДМИН-ПАНЕЛЬ (С КНОПКОЙ НАЗАД ДЛЯ ОБЫЧНЫХ ПОЛЬЗОВАТЕЛЕЙ) ==========
async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Проверка на админа
    if user_id != ADMIN_ID:
        keyboard = [[InlineKeyboardButton("◀️ Вернуться в меню", callback_data="back_to_menu")]]
        await query.edit_message_text(
            "⛔ *Доступ запрещён!*\n\nЭта панель доступна только лидерам и замам клана Tir.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return
    
    # Админ видит панель управления
    total, pending, accepted, rejected, tir, academia = get_statistics()
    
    admin_text = f"""
👑 *Админ-панель клана Tir* 👑

📊 *Статистика:*
• Всего заявок: {total}
• Ожидают рассмотрения: {pending}
• ✅ Подтверждённые: {accepted}
• ❌ Отклонённые: {rejected}
• ⚔️ В Tir: {tir} | 📚 В Academia: {academia}

Выберите действие:
"""
    
    keyboard = [
        [InlineKeyboardButton("📋 Список всех заявок", callback_data="admin_view_all")],
        [InlineKeyboardButton("⏳ Только новые (ожидают)", callback_data="admin_view_pending")],
        [InlineKeyboardButton("✅ Подтверждённые", callback_data="admin_view_accepted")],
        [InlineKeyboardButton("❌ Отклонённые", callback_data="admin_view_rejected")],
        [InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_menu")]
    ]
    await query.edit_message_text(admin_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_view_applications(update: Update, context: ContextTypes.DEFAULT_TYPE, status_filter=None):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    apps = get_all_applications()
    if status_filter:
        apps = [app for app in apps if app["status"] == status_filter]
    
    if not apps:
        await query.edit_message_text("📭 Нет заявок.", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")
        ]]))
        return
    
    app = apps[0]
    text = f"""📋 *Заявка #{app['id']}*

👤 @{app['username']}
🏰 {app['clan_choice']}
📅 {app['timestamp']}
📊 Статус: {app['status']}

📝 {app['answers']['описание']}
✨ Уровень: {app['answers']['уровень']}
🎮 Имя: {app['answers']['имя']}
⚔️ Навыки: {app['answers']['навыки']}
🌍 Часовой пояс: {app['answers']['часовой пояс']}
🎂 Возраст: {app['answers']['возраст']}"""
    
    keyboard = [
        [InlineKeyboardButton("✅ Принять", callback_data=f"accept_{app['id']}"),
         InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{app['id']}")],
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{app['id']}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    action, app_id = query.data.split("_")
    app_id = int(app_id)
    app = get_application_by_id(app_id)
    
    if not app:
        await query.edit_message_text("❌ Заявка не найдена!")
        return
    
    if action == "accept":
        update_status(app_id, "accepted")
        await context.bot.send_message(chat_id=app["user_id"], text="✅ Ваша заявка принята! Добро пожаловать в клан!")
        await query.edit_message_text(f"✅ Заявка #{app_id} принята!")
    elif action == "reject":
        update_status(app_id, "rejected")
        await context.bot.send_message(chat_id=app["user_id"], text="❌ Ваша заявка отклонена. Вы можете подать новую через 7 дней.")
        await query.edit_message_text(f"❌ Заявка #{app_id} отклонена!")
    elif action == "delete":
        delete_app(app_id)
        await query.edit_message_text(f"🗑️ Заявка #{app_id} удалена!")

async def back_to_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await main_menu(update, context, message=query.message)

# ========== FLASK ==========
@flask_app.route('/')
@flask_app.route('/health')
def health():
    return {"status": "ok"}, 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ========== ЗАПУСК БОТА ==========
def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def start_bot():
        global telegram_app
        
        print("🚀 Запуск бота...")
        init_database()
        
        telegram_app = Application.builder().token(BOT_TOKEN).build()
        
        # Команды
        telegram_app.add_handler(CommandHandler("start", start))
        telegram_app.add_handler(CommandHandler("myapp", my_application))
        
        # Callback-обработчики меню
        telegram_app.add_handler(CallbackQueryHandler(join_tir_callback, pattern="^join_tir$"))
        telegram_app.add_handler(CallbackQueryHandler(join_academia_callback, pattern="^join_academia$"))
        telegram_app.add_handler(CallbackQueryHandler(about_us_callback, pattern="^about_us$"))
        telegram_app.add_handler(CallbackQueryHandler(difference_callback, pattern="^difference$"))
        telegram_app.add_handler(CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$"))
        telegram_app.add_handler(CallbackQueryHandler(back_to_menu_callback, pattern="^back_to_menu$"))
        
        # Админские просмотры
        telegram_app.add_handler(CallbackQueryHandler(lambda u,c: admin_view_applications(u,c, None), pattern="^admin_view_all$"))
        telegram_app.add_handler(CallbackQueryHandler(lambda u,c: admin_view_applications(u,c, "pending"), pattern="^admin_view_pending$"))
        telegram_app.add_handler(CallbackQueryHandler(lambda u,c: admin_view_applications(u,c, "accepted"), pattern="^admin_view_accepted$"))
        telegram_app.add_handler(CallbackQueryHandler(lambda u,c: admin_view_applications(u,c, "rejected"), pattern="^admin_view_rejected$"))
        
        # Действия с заявками
        telegram_app.add_handler(CallbackQueryHandler(handle_action, pattern="^(accept|reject|delete)_"))
        
        # Обработка сообщений
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        print(f"✅ Бот запущен! Админ: {ADMIN_ID}")
        
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling()
        
        while True:
            await asyncio.sleep(1)
    
    try:
        loop.run_until_complete(start_bot())
    except KeyboardInterrupt:
        print("🛑 Остановка бота...")
    finally:
        loop.close()

if __name__ == "__main__":
    telegram_app = None
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("✅ Flask запущен на порту", os.environ.get("PORT", 10000))
    
    # Запускаем бота
    run_bot()
