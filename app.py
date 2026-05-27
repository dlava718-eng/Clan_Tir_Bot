import os
import sys
import sqlite3
import asyncio
from datetime import datetime
from threading import Thread
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8882364637:AAHUWNZilUdxotSOXg44owGgCsuozHGlT48")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 5611887050))
COOLDOWN_DAYS = int(os.environ.get("COOLDOWN_DAYS", 7))
DATABASE_FILE = "/tmp/applications.db"

if not BOT_TOKEN or not ADMIN_ID:
    print("❌ ОШИБКА: BOT_TOKEN или ADMIN_ID не заданы!")
    sys.exit(1)

# Состояния анкеты
ASK_DESCRIPTION, ASK_LEVEL, ASK_NAME, ASK_SKILLS, ASK_TIMEZONE, ASK_AGE = range(6)

user_data_temp = {}
admin_reply_temp = {}

flask_app = Flask(__name__)

# ========== БАЗА ДАННЫХ ==========
def init_database():
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
    print("✅ База данных готова")

def save_application(user_id, username, clan_choice, answers):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO applications 
        (user_id, username, clan_choice, description, level, ingame_name, skills, timezone, age, timestamp, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, clan_choice,
          answers['описание'], answers['уровень'], answers['имя'],
          answers['навыки'], answers['часовой пояс'], answers['возраст'],
          datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'pending'))
    app_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return app_id

def load_applications():
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

def update_status(app_id, status):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE applications SET status = ? WHERE id = ?', (status, app_id))
    conn.commit()
    conn.close()

def delete_app(app_id):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM applications WHERE id = ?', (app_id,))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM applications')
    total = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM applications WHERE status = "pending"')
    pending = cursor.fetchone()[0]
    conn.close()
    return total, pending

# ========== ОБРАБОТЧИКИ БОТА ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_temp.pop(user_id, None)
    
    keyboard = [
        [InlineKeyboardButton("⚔️ Вступить в Tir", callback_data="join_tir")],
        [InlineKeyboardButton("📚 Вступить в Academia", callback_data="join_academia")],
        [InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")]
    ]
    await update.message.reply_text(
        "🏰 Добро пожаловать в клан Tir!\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def join_tir_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data_temp[user_id] = {"clan": "Tir", "step": ASK_DESCRIPTION}
    await query.edit_message_text("⚔️ Клан Tir\n\n📝 Напишите ОПИСАНИЕ о себе:")

async def join_academia_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data_temp[user_id] = {"clan": "Academia", "step": ASK_DESCRIPTION}
    await query.edit_message_text("📚 Клан Academia\n\n📝 Напишите ОПИСАНИЕ о себе:")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    
    if user_id not in user_data_temp:
        return
    
    step = user_data_temp[user_id].get("step")
    
    if step == ASK_DESCRIPTION:
        user_data_temp[user_id]["description"] = text
        user_data_temp[user_id]["step"] = ASK_LEVEL
        await update.message.reply_text("✨ Введите УРОВЕНЬ (только число):")
    
    elif step == ASK_LEVEL:
        if not text.isdigit():
            await update.message.reply_text("❌ Введите число:")
            return
        user_data_temp[user_id]["level"] = int(text)
        user_data_temp[user_id]["step"] = ASK_NAME
        await update.message.reply_text("🎮 Введите ИМЯ в игре:")
    
    elif step == ASK_NAME:
        user_data_temp[user_id]["name"] = text
        user_data_temp[user_id]["step"] = ASK_SKILLS
        await update.message.reply_text("⚔️ Опишите НАВЫКИ:")
    
    elif step == ASK_SKILLS:
        user_data_temp[user_id]["skills"] = text
        user_data_temp[user_id]["step"] = ASK_TIMEZONE
        await update.message.reply_text("🌍 Ваш ЧАСОВОЙ ПОЯС:")
    
    elif step == ASK_TIMEZONE:
        user_data_temp[user_id]["timezone"] = text
        user_data_temp[user_id]["step"] = ASK_AGE
        await update.message.reply_text("🎂 Сколько вам ЛЕТ?")
    
    elif step == ASK_AGE:
        if not text.isdigit():
            await update.message.reply_text("❌ Введите число:")
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
        
        keyboard = [[InlineKeyboardButton("◀️ Меню", callback_data="back_to_menu")]]
        await update.message.reply_text(
            f"✅ Заявка #{app_id} отправлена!\n\nОжидайте ответа.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("⛔ Доступ запрещён!")
        return
    
    total, pending = get_stats()
    apps = load_applications()
    
    if not apps:
        await query.edit_message_text("Нет заявок.")
        return
    
    # Показываем первую заявку
    app = apps[0]
    text = f"""📋 ЗАЯВКА #{app['id']}
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
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    data = query.data
    action, app_id = data.split("_")
    app_id = int(app_id)
    app = get_application_by_id(app_id)
    
    if not app:
        await query.edit_message_text("Заявка не найдена!")
        return
    
    if action == "accept":
        update_status(app_id, "accepted")
        await context.bot.send_message(chat_id=app["user_id"], text=f"✅ Ваша заявка принята!")
        await query.edit_message_text(f"✅ Заявка #{app_id} принята!")
    elif action == "reject":
        update_status(app_id, "rejected")
        await context.bot.send_message(chat_id=app["user_id"], text=f"❌ Ваша заявка отклонена.")
        await query.edit_message_text(f"❌ Заявка #{app_id} отклонена!")
    elif action == "delete":
        delete_app(app_id)
        await query.edit_message_text(f"🗑️ Заявка #{app_id} удалена!")

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data_temp.pop(user_id, None)
    
    keyboard = [
        [InlineKeyboardButton("⚔️ Вступить в Tir", callback_data="join_tir")],
        [InlineKeyboardButton("📚 Вступить в Academia", callback_data="join_academia")],
        [InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")]
    ]
    await query.edit_message_text(
        "🏰 Добро пожаловать в клан Tir!\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ========== FLASK ==========
@flask_app.route('/')
@flask_app.route('/health')
def health():
    return {"status": "ok"}, 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# ========== ЗАПУСК ==========
async def main():
    print("🚀 Запуск бота...")
    init_database()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(join_tir_callback, pattern="^join_tir$"))
    app.add_handler(CallbackQueryHandler(join_academia_callback, pattern="^join_academia$"))
    app.add_handler(CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(handle_action, pattern="^(accept|reject|delete)_"))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print(f"✅ Бот запущен! Админ: {ADMIN_ID}")
    
    await app.run_polling()

if __name__ == "__main__":
    # Запускаем Flask в фоне
    Thread(target=run_flask, daemon=True).start()
    
    # Запускаем бота
    asyncio.run(main())
