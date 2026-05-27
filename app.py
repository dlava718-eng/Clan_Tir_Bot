import os
import sys
import sqlite3
import re
import asyncio
from datetime import datetime, timedelta
from flask import Flask, jsonify
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8882364637:AAHUWNZilUdxotSOXg44owGgCsuozHGlT48")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 5611887050))
COOLDOWN_DAYS = int(os.environ.get("COOLDOWN_DAYS", 7))
DATABASE_FILE = "/tmp/applications.db"  # Используем /tmp для Render

# Проверка переменных
if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не задан!")
    sys.exit(1)

if not ADMIN_ID:
    print("❌ ОШИБКА: ADMIN_ID не задан!")
    sys.exit(1)

print(f"✅ BOT_TOKEN загружен: {BOT_TOKEN[:10]}...")
print(f"✅ ADMIN_ID: {ADMIN_ID}")

# Состояния анкеты
ASK_DESCRIPTION, ASK_LEVEL, ASK_NAME, ASK_SKILLS, ASK_TIMEZONE, ASK_AGE = range(6)

# Хранилище временных данных
user_data_temp = {}
admin_reply_temp = {}

# Flask приложение
flask_app = Flask(__name__)

# ========== РАБОТА С БАЗОЙ ДАННЫХ ==========
def init_database():
    """Инициализация базы данных"""
    try:
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
        print("✅ База данных инициализирована")
        return True
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
        return False

def save_application(user_id, username, clan_choice, answers):
    try:
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
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")
        return None

def load_applications(status_filter=None):
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        if status_filter:
            cursor.execute('SELECT * FROM applications WHERE status = ? ORDER BY id DESC', (status_filter,))
        else:
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
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
        return []

def get_application_by_id(app_id):
    try:
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
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None

def update_application_status(app_id, new_status):
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('UPDATE applications SET status = ? WHERE id = ?', (new_status, app_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def delete_application(app_id):
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM applications WHERE id = ?', (app_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False

def get_user_last_application(user_id):
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM applications WHERE user_id = ? ORDER BY id DESC LIMIT 1', (user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            app = {
                "id": row[0], "user_id": row[1], "username": row[2], "clan_choice": row[3],
                "answers": {
                    "описание": row[4], "уровень": row[5], "имя": row[6],
                    "навыки": row[7], "часовой пояс": row[8], "возраст": row[9]
                },
                "timestamp": row[10], "status": row[11]
            }
            return app, datetime.strptime(app["timestamp"], "%Y-%m-%d %H:%M:%S")
        return None, None
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None, None

def can_submit_application(user_id):
    last_app, last_date = get_user_last_application(user_id)
    if last_app is None:
        return True, None
    days_passed = (datetime.now() - last_date).days
    if days_passed >= COOLDOWN_DAYS:
        return True, None
    else:
        return False, COOLDOWN_DAYS - days_passed

def get_statistics():
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM applications')
        total = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM applications WHERE status = "pending"')
        pending = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM applications WHERE status = "accepted"')
        accepted = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM applications WHERE status = "rejected"')
        rejected = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM applications WHERE clan_choice = "Tir"')
        tir = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM applications WHERE clan_choice = "Academia"')
        academia = cursor.fetchone()[0]
        conn.close()
        return {"total": total, "pending": pending, "accepted": accepted, "rejected": rejected, "tir": tir, "academia": academia}
    except:
        return {"total": 0, "pending": 0, "accepted": 0, "rejected": 0, "tir": 0, "academia": 0}

# ========== ОБРАБОТЧИКИ БОТА ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_temp.pop(user_id, None)
    admin_reply_temp.pop(user_id, None)
    
    keyboard = [
        [InlineKeyboardButton("⚔️ Вступить в Tir", callback_data="join_tir")],
        [InlineKeyboardButton("📚 Вступить в Academia", callback_data="join_academia")],
        [InlineKeyboardButton("🌟 О нас", callback_data="about_us")],
        [InlineKeyboardButton("🔄 Разница между Tir и Academia", callback_data="difference")],
        [InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")]
    ]
    await update.message.reply_text(
        "🏰 Добро пожаловать в клан Tir!\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def my_application(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    last_app, _ = get_user_last_application(user_id)
    
    if last_app is None:
        await update.message.reply_text("📭 У вас нет отправленных заявок.\n\nНажмите /start и выберите клан")
        return
    
    status_emoji = {"pending": "⏳", "accepted": "✅", "rejected": "❌"}.get(last_app["status"], "❓")
    status_text = {"pending": "Ожидает рассмотрения", "accepted": "ПРИНЯТА!", "rejected": "ОТКЛОНЕНА"}.get(last_app["status"], "Неизвестно")
    
    message = f"""{status_emoji} СТАТУС ЗАЯВКИ #{last_app['id']}

Клан: {last_app['clan_choice']}
Дата: {last_app['timestamp']}
Статус: {status_text}

ДАННЫЕ:
• Описание: {last_app['answers']['описание']}
• Уровень: {last_app['answers']['уровень']}
• Имя: {last_app['answers']['имя']}
• Навыки: {last_app['answers']['навыки']}
• Часовой пояс: {last_app['answers']['часовой пояс']}
• Возраст: {last_app['answers']['возраст']}"""
    
    await update.message.reply_text(message)

async def about_us_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = """🏰 О КЛАНЕ TIR 🏰

Мы не просто клан - мы братство воинов!

⚡ Наш путь: сила в единстве
🎯 Философия: честь выше победы
💪 Что даём: развитие, ивенты, поддержку

Стань частью истории TIR!"""
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def difference_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = """РАЗНИЦА МЕЖДУ TIR И ACADEMIA

⚔️ TIR - ОСНОВНОЙ КЛАН
• Элитное подразделение
• Топовые рейды и PvP
• Высокие требования

📚 ACADEMIA - ОБУЧЕНИЕ
• Подготовка новичков
• Помощь в развитии
• Мягкие требования

ВЗАИМОДЕЙСТВИЕ:
Tir помогает развиваться, Academia снабжает ресурсами"""
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def join_tir_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    can_submit, days_left = can_submit_application(user_id)
    
    if not can_submit:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
        await query.edit_message_text(f"⏰ Вы не можете подать заявку!\nСледующая попытка через {days_left} дн.", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    user_data_temp[user_id] = {"clan": "Tir", "step": ASK_DESCRIPTION}
    await query.edit_message_text("⚔️ Клан Tir\n\n📝 Напишите ОПИСАНИЕ о себе:")

async def join_academia_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    can_submit, days_left = can_submit_application(user_id)
    
    if not can_submit:
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
        await query.edit_message_text(f"⏰ Вы не можете подать заявку!\nСледующая попытка через {days_left} дн.", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    user_data_temp[user_id] = {"clan": "Academia", "step": ASK_DESCRIPTION}
    await query.edit_message_text("📚 Клан Academia\n\n📝 Напишите ОПИСАНИЕ о себе:")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    
    if user_id in user_data_temp:
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
            await update.message.reply_text("⚔️ Опишите НАВЫКИ (класс, роль):")
        
        elif step == ASK_SKILLS:
            user_data_temp[user_id]["skills"] = text
            user_data_temp[user_id]["step"] = ASK_TIMEZONE
            await update.message.reply_text("🌍 Ваш ЧАСОВОЙ ПОЯС (UTC+3):")
        
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
                f"✅ Заявка #{app_id} отправлена!\n\nОжидайте ответа лидера.\nСтатус: /myapp",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return
    
    if user_id in admin_reply_temp:
        target = admin_reply_temp[user_id]
        try:
            await context.bot.send_message(chat_id=target["user_id"], text=f"📨 Сообщение от лидеров:\n\n{text}")
            await update.message.reply_text(f"✅ Отправлено пользователю")
            del admin_reply_temp[user_id]
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
        return

async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("⛔ Доступ запрещён!")
        return
    
    stats = get_statistics()
    text = f"""👑 АДМИН-ПАНЕЛЬ

📊 Статистика:
• Всего: {stats['total']}
• Ожидают: {stats['pending']}
• Принято: {stats['accepted']}
• Отклонено: {stats['rejected']}
• Tir: {stats['tir']} | Academia: {stats['academia']}

Выберите действие:"""
    
    keyboard = [
        [InlineKeyboardButton("📋 Новые заявки", callback_data="admin_view_pending")],
        [InlineKeyboardButton("📋 Все заявки", callback_data="admin_view_all")],
        [InlineKeyboardButton("🗑️ Удалить заявку", callback_data="admin_delete_menu")],
        [InlineKeyboardButton("💬 Написать пользователю", callback_data="admin_write_user")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_view_applications(update: Update, context: ContextTypes.DEFAULT_TYPE, status_filter=None):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    apps = load_applications(status_filter)
    if not apps:
        await query.edit_message_text("Нет заявок.", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")
        ]]))
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
        [InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{app['id']}"),
         InlineKeyboardButton("💬 Написать", callback_data=f"reply_{app['user_id']}_{app['id']}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE, app_id, action):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    app = get_application_by_id(app_id)
    if not app:
        await query.edit_message_text("Заявка не найдена!")
        return
    
    new_status = "accepted" if action == "accept" else "rejected"
    update_application_status(app_id, new_status)
    
    status_text = "принята" if action == "accept" else "отклонена"
    
    try:
        await context.bot.send_message(
            chat_id=app["user_id"],
            text=f"{'✅' if action == 'accept' else '❌'} Ваша заявка в {app['clan_choice']} {status_text}!"
        )
        await query.edit_message_text(f"✅ Заявка #{app_id} {status_text}!", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")
        ]]))
    except:
        await query.edit_message_text(f"✅ Заявка #{app_id} {status_text}!")

async def admin_delete_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    apps = load_applications()
    if not apps:
        await query.edit_message_text("Нет заявок.", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")
        ]]))
        return
    
    keyboard = []
    for app in apps[:10]:
        keyboard.append([InlineKeyboardButton(f"#{app['id']} - @{app['username']}", callback_data=f"delete_confirm_{app['id']}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")])
    
    await query.edit_message_text("Выберите заявку для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    app_id = int(query.data.split("_")[2])
    app = get_application_by_id(app_id)
    
    if not app:
        await query.edit_message_text("Заявка не найдена!")
        return
    
    keyboard = [[
        InlineKeyboardButton("✅ Да", callback_data=f"delete_execute_{app_id}"),
        InlineKeyboardButton("❌ Нет", callback_data="admin_delete_menu")
    ]]
    
    await query.edit_message_text(f"Удалить заявку #{app_id} от @{app['username']}?", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_delete_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    app_id = int(query.data.split("_")[2])
    app = get_application_by_id(app_id)
    
    if app:
        delete_application(app_id)
        try:
            await context.bot.send_message(chat_id=app["user_id"], text=f"🗑️ Ваша заявка #{app_id} удалена администрацией.")
        except:
            pass
    
    await query.edit_message_text(f"✅ Заявка #{app_id} удалена!", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")
    ]]))

async def admin_write_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    apps = load_applications()
    if not apps:
        await query.edit_message_text("Нет пользователей.", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")
        ]]))
        return
    
    keyboard = []
    for app in apps[:10]:
        keyboard.append([InlineKeyboardButton(f"@{app['username']} (#{app['id']})", callback_data=f"reply_to_{app['user_id']}_{app['id']}")])
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")])
    
    await query.edit_message_text("Выберите пользователя:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_start_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    parts = query.data.split("_")
    target_user_id = int(parts[2])
    app_id = int(parts[3])
    
    admin_reply_temp[query.from_user.id] = {"user_id": target_user_id, "app_id": app_id}
    await query.edit_message_text("💬 Напишите сообщение для пользователя:\n(Для отмены /cancel)")

async def back_to_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data_temp.pop(user_id, None)
    admin_reply_temp.pop(user_id, None)
    
    keyboard = [
        [InlineKeyboardButton("⚔️ Вступить в Tir", callback_data="join_tir")],
        [InlineKeyboardButton("📚 Вступить в Academia", callback_data="join_academia")],
        [InlineKeyboardButton("🌟 О нас", callback_data="about_us")],
        [InlineKeyboardButton("🔄 Разница", callback_data="difference")],
        [InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")]
    ]
    await query.edit_message_text(
        "🏰 Добро пожаловать в клан Tir!\n\nВыберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in admin_reply_temp:
        del admin_reply_temp[user_id]
        await update.message.reply_text("❌ Отменено.")
    elif user_id in user_data_temp:
        del user_data_temp[user_id]
        await update.message.reply_text("❌ Анкета отменена.")
    else:
        await update.message.reply_text("Нет активных действий.")

# ========== FLASK ДЛЯ HEALTHCHECK ==========
@flask_app.route('/')
@flask_app.route('/health')
def health():
    return {"status": "ok", "bot": "running"}, 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

# ========== ОСНОВНОЙ ЗАПУСК ==========
async def main():
    print("🚀 Запуск бота...")
    
    # Инициализация БД
    if not init_database():
        print("❌ Ошибка БД")
        return
    
    # Создание приложения
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myapp", my_application))
    app.add_handler(CommandHandler("cancel", cancel_command))
    
    # Callback-обработчики
    app.add_handler(CallbackQueryHandler(join_tir_callback, pattern="^join_tir$"))
    app.add_handler(CallbackQueryHandler(join_academia_callback, pattern="^join_academia$"))
    app.add_handler(CallbackQueryHandler(about_us_callback, pattern="^about_us$"))
    app.add_handler(CallbackQueryHandler(difference_callback, pattern="^difference$"))
    app.add_handler(CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(back_to_menu_callback, pattern="^back_to_menu$"))
    app.add_handler(CallbackQueryHandler(admin_view_applications, pattern="^admin_view_"))
    app.add_handler(CallbackQueryHandler(lambda u,c: admin_handle_action(u,c, int(c.matches[0].group(1)), "accept"), pattern=r"^accept_(\d+)$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: admin_handle_action(u,c, int(c.matches[0].group(1)), "reject"), pattern=r"^reject_(\d+)$"))
    app.add_handler(CallbackQueryHandler(admin_delete_menu, pattern="^admin_delete_menu$"))
    app.add_handler(CallbackQueryHandler(admin_delete_confirm, pattern=r"^delete_confirm_(\d+)$"))
    app.add_handler(CallbackQueryHandler(admin_delete_execute, pattern=r"^delete_execute_(\d+)$"))
    app.add_handler(CallbackQueryHandler(admin_write_user_list, pattern="^admin_write_user$"))
    app.add_handler(CallbackQueryHandler(admin_start_reply, pattern=r"^reply_to_\d+_\d+$"))
    
    # Обработчики сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print(f"✅ Бот запущен! Админ: {ADMIN_ID}")
    
    # Запуск polling
    await app.run_polling()

if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Запускаем бота
    asyncio.run(main())
