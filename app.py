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
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
COOLDOWN_DAYS = int(os.environ.get("COOLDOWN_DAYS", 7))
DATABASE_FILE = "/data/applications.db"

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

# Хранилища временных данных
user_data_temp = {}
admin_reply_temp = {}

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
• Элитное подразделение, кузница чемпионов
• Ядро клана, состоящее из опытных ветеранов
• Участие в топовых рейдах и PvP-сражениях
• Наставничество над академией
• Более высокие требования к уровню и навыкам

📚 **ACADEMIA — КУЗНИЦА КАДРОВ** 📚
• Подготовка новых игроков к основному составу
• Обучение механикам и тактикам
• Помощь в развитии и прокачке
• Более мягкие требования к уровню
• Ресурсная база для основного клана

🔄 **ВЗАИМОДЕЙСТВИЕ** 🔄
Tir помогает Academia развиваться, Academia снабжает Tir ресурсами.

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
        "⚔️ *Ты выбрал клан Tir!* ⚔️\n\n📝 *Напиши ОПИСАНИЕ о себе:*",
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
        "📚 *Ты выбрал Academia!* 📚\n\n📝 *Напиши ОПИСАНИЕ о себе:*",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    
    # Проверяем режим отправки сообщения админом
    if user_id in admin_reply_temp:
        target_data = admin_reply_temp[user_id]
        target_user_id = target_data["target_user_id"]
        app_id = target_data["app_id"]
        
        app = get_application_by_id(app_id)
        username = app["username"] if app else "пользователь"
        
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"📨 *Сообщение от лидеров клана Tir:*\n\n{text}",
                parse_mode="Markdown"
            )
            
            await update.message.reply_text(
                f"✅ *Сообщение отправлено!*\n\nПользователь: @{username}\nID заявки: #{app_id}",
                parse_mode="Markdown"
            )
            
            del admin_reply_temp[user_id]
            
            keyboard = [[InlineKeyboardButton("◀️ Вернуться в админ-панель", callback_data="admin_panel")]]
            await update.message.reply_text("Вернуться в админ-панель?", reply_markup=InlineKeyboardMarkup(keyboard))
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
        return
    
    # Проверяем режим анкеты
    if user_id not in user_data_temp:
        return
    
    step = user_data_temp[user_id].get("step")
    
    if step == ASK_DESCRIPTION:
        user_data_temp[user_id]["description"] = text
        user_data_temp[user_id]["step"] = ASK_LEVEL
        await update.message.reply_text("✨ *Введите УРОВЕНЬ персонажа:*\n(Только число)", parse_mode="Markdown")
    
    elif step == ASK_LEVEL:
        if not text.isdigit():
            await update.message.reply_text("❌ Введите число:")
            return
        user_data_temp[user_id]["level"] = int(text)
        user_data_temp[user_id]["step"] = ASK_NAME
        await update.message.reply_text("🎮 *Как ваше ИМЯ в игре?*", parse_mode="Markdown")
    
    elif step == ASK_NAME:
        user_data_temp[user_id]["name"] = text
        user_data_temp[user_id]["step"] = ASK_SKILLS
        await update.message.reply_text("⚔️ *Опишите свои НАВЫКИ:*", parse_mode="Markdown")
    
    elif step == ASK_SKILLS:
        user_data_temp[user_id]["skills"] = text
        user_data_temp[user_id]["step"] = ASK_TIMEZONE
        await update.message.reply_text("🌍 *Ваш ЧАСОВОЙ ПОЯС:*", parse_mode="Markdown")
    
    elif step == ASK_TIMEZONE:
        user_data_temp[user_id]["timezone"] = text
        user_data_temp[user_id]["step"] = ASK_AGE
        await update.message.reply_text("🎂 *Сколько вам ЛЕТ?*", parse_mode="Markdown")
    
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
        
        keyboard = [[InlineKeyboardButton("◀️ Вернуться в меню", callback_data="back_to_menu")]]
        await update.message.reply_text(
            f"✅ *Заявка #{app_id} отправлена!*\n\nОжидайте ответа.\nСтатус: /myapp",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def my_application(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    last_app = get_user_last_application(user_id)
    
    if last_app is None:
        await update.message.reply_text(
            "📭 *У вас нет отправленных заявок.*\n\nНажмите /start и выберите клан",
            parse_mode="Markdown"
        )
        return
    
    status_emoji = {"pending": "⏳", "accepted": "✅", "rejected": "❌"}.get(last_app["status"], "❓")
    status_text = {"pending": "Ожидает рассмотрения", "accepted": "ПРИНЯТА!", "rejected": "ОТКЛОНЕНА"}.get(last_app["status"], "Неизвестно")
    
    message = f"""{status_emoji} *Статус вашей заявки*

📋 *Заявка #{last_app['id']}*
🏰 Клан: {last_app['clan_choice']}
📅 Дата: {last_app['timestamp']}
📊 Статус: {status_text}

📝 *Ваши данные:*
• Описание: {last_app['answers']['описание']}
• Уровень: {last_app['answers']['уровень']}
• Имя: {last_app['answers']['имя']}
• Навыки: {last_app['answers']['навыки']}
• Часовой пояс: {last_app['answers']['часовой пояс']}
• Возраст: {last_app['answers']['возраст']}"""
    await update.message.reply_text(message, parse_mode="Markdown")

# ========== АДМИН-ПАНЕЛЬ ==========
async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        keyboard = [[InlineKeyboardButton("◀️ Вернуться в меню", callback_data="back_to_menu")]]
        await query.edit_message_text(
            "⛔ *Доступ запрещён!*\n\nЭта панель доступна только лидерам клана Tir.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return
    
    total, pending, accepted, rejected, tir, academia = get_statistics()
    
    admin_text = f"""👑 *Админ-панель клана Tir* 👑

📊 *Статистика:*
• Всего заявок: {total}
• Ожидают: {pending}
• ✅ Принято: {accepted}
• ❌ Отклонено: {rejected}
• ⚔️ Tir: {tir} | 📚 Academia: {academia}

Выберите действие:"""
    
    keyboard = [
        [InlineKeyboardButton("📋 Все заявки", callback_data="admin_view_all")],
        [InlineKeyboardButton("⏳ Новые (ожидают)", callback_data="admin_view_pending")],
        [InlineKeyboardButton("✅ Принятые", callback_data="admin_view_accepted")],
        [InlineKeyboardButton("❌ Отклонённые", callback_data="admin_view_rejected")],
        [InlineKeyboardButton("💬 Написать пользователю", callback_data="admin_write_user")],
        [InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_menu")]
    ]
    await query.edit_message_text(admin_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_view_applications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    # Определяем фильтр по callback_data
    if query.data == "admin_view_pending":
        status_filter = "pending"
    elif query.data == "admin_view_accepted":
        status_filter = "accepted"
    elif query.data == "admin_view_rejected":
        status_filter = "rejected"
    else:
        status_filter = None
    
    apps = get_all_applications()
    if status_filter:
        apps = [app for app in apps if app["status"] == status_filter]
    
    if not apps:
        await query.edit_message_text(
            "📭 Нет заявок.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")
            ]])
        )
        return
    
    # Сохраняем в context
    context.user_data["admin_apps"] = apps
    context.user_data["admin_index"] = 0
    
    await show_application(update, context, query)

async def show_application(update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
    """Показывает текущую заявку с кнопками навигации"""
    if query is None:
        query = update.callback_query
        await query.answer()
    
    apps = context.user_data.get("admin_apps", [])
    index = context.user_data.get("admin_index", 0)
    
    if not apps or index >= len(apps):
        await query.edit_message_text(
            "✅ Все заявки обработаны!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")
            ]])
        )
        return
    
    app = apps[index]
    total = len(apps)
    
    text = f"""📋 *Заявка {index + 1} из {total}* | #{app['id']}

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
    
    keyboard = []
    
    # Навигация
    nav_buttons = []
    if index > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Пред.", callback_data="admin_prev"))
    if index < total - 1:
        nav_buttons.append(InlineKeyboardButton("След. ▶️", callback_data="admin_next"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Действия
    keyboard.append([
        InlineKeyboardButton("✅ Принять", callback_data=f"admin_accept_{app['id']}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"admin_reject_{app['id']}")
    ])
    keyboard.append([
        InlineKeyboardButton("🗑️ Удалить", callback_data=f"admin_delete_{app['id']}"),
        InlineKeyboardButton("💬 Написать", callback_data=f"admin_reply_to_{app['user_id']}_{app['id']}")
    ])
    keyboard.append([
        InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")
    ])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_navigate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Навигация между заявками"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    current_index = context.user_data.get("admin_index", 0)
    if query.data == "admin_next":
        context.user_data["admin_index"] = current_index + 1
    elif query.data == "admin_prev":
        context.user_data["admin_index"] = current_index - 1
    
    await show_application(update, context, query)

async def admin_handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка действий с заявкой"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    # Парсим callback_data: "admin_accept_123" или "admin_reject_123" или "admin_delete_123"
    parts = query.data.split("_")
    action = parts[1]  # accept, reject, delete
    app_id = int(parts[2])
    
    app = get_application_by_id(app_id)
    if not app:
        await query.edit_message_text("❌ Заявка не найдена!")
        return
    
    if action == "accept":
        update_status(app_id, "accepted")
        await context.bot.send_message(chat_id=app["user_id"], text="✅ Ваша заявка принята! Добро пожаловать в клан!")
        await query.answer("✅ Заявка принята!", show_alert=True)
    elif action == "reject":
        update_status(app_id, "rejected")
        await context.bot.send_message(chat_id=app["user_id"], text="❌ Ваша заявка отклонена.")
        await query.answer("❌ Заявка отклонена!", show_alert=True)
    elif action == "delete":
        delete_app(app_id)
        await query.answer("🗑️ Заявка удалена!", show_alert=True)
    
    # Обновляем список заявок
    apps = context.user_data.get("admin_apps", [])
    apps = [a for a in apps if a["id"] != app_id]
    context.user_data["admin_apps"] = apps
    
    if not apps:
        await query.edit_message_text(
            "✅ Все заявки обработаны!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")
            ]])
        )
        return
    
    # Корректируем индекс
    current_index = context.user_data.get("admin_index", 0)
    if current_index >= len(apps):
        context.user_data["admin_index"] = len(apps) - 1
    
    await show_application(update, context, query)

# ========== ОТПРАВКА СООБЩЕНИЙ ПОЛЬЗОВАТЕЛЯМ ==========
async def admin_write_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список пользователей для отправки сообщения"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    apps = get_all_applications()
    if not apps:
        await query.edit_message_text(
            "📭 Нет пользователей для связи.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")
            ]])
        )
        return
    
    keyboard = []
    for app in apps[:15]:
        status_emoji = "⏳" if app["status"] == "pending" else "✅" if app["status"] == "accepted" else "❌"
        keyboard.append([
            InlineKeyboardButton(
                f"{status_emoji} @{app['username']} (заявка #{app['id']})",
                callback_data=f"admin_reply_to_{app['user_id']}_{app['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="admin_panel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "💬 *Выберите пользователя для отправки сообщения:*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def admin_start_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает процесс отправки сообщения пользователю"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    parts = query.data.split("_")
    target_user_id = int(parts[3])
    app_id = int(parts[4])
    
    admin_reply_temp[query.from_user.id] = {
        "target_user_id": target_user_id,
        "app_id": app_id
    }
    
    await query.edit_message_text(
        "💬 *Режим отправки сообщения*\n\n"
        "Напишите сообщение, которое хотите отправить пользователю.\n\n"
        "Сообщение придёт ОТ ИМЕНИ БОТА.\n\n"
        "❌ Для отмены напишите /cancel",
        parse_mode="Markdown"
    )

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
async def back_to_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await main_menu(update, context, message=query.message)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in admin_reply_temp:
        del admin_reply_temp[user_id]
        await update.message.reply_text("❌ Режим отправки сообщения отменён.")
    elif user_id in user_data_temp:
        del user_data_temp[user_id]
        await update.message.reply_text("❌ Анкета отменена.")
    else:
        await update.message.reply_text("Нет активных действий для отмены.")
    
    keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]]
    await update.message.reply_text("Вернуться в меню?", reply_markup=InlineKeyboardMarkup(keyboard))

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
        print("🚀 Запуск бота...")
        init_database()
        
        telegram_app = Application.builder().token(BOT_TOKEN).build()
        
        # Команды
        telegram_app.add_handler(CommandHandler("start", start))
        telegram_app.add_handler(CommandHandler("myapp", my_application))
        telegram_app.add_handler(CommandHandler("cancel", cancel_command))
        
        # Главное меню
        telegram_app.add_handler(CallbackQueryHandler(join_tir_callback, pattern="^join_tir$"))
        telegram_app.add_handler(CallbackQueryHandler(join_academia_callback, pattern="^join_academia$"))
        telegram_app.add_handler(CallbackQueryHandler(about_us_callback, pattern="^about_us$"))
        telegram_app.add_handler(CallbackQueryHandler(difference_callback, pattern="^difference$"))
        telegram_app.add_handler(CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$"))
        telegram_app.add_handler(CallbackQueryHandler(back_to_menu_callback, pattern="^back_to_menu$"))
        
        # Админ-панель (просмотр списков)
        telegram_app.add_handler(CallbackQueryHandler(admin_view_applications, pattern="^admin_view_(all|pending|accepted|rejected)$"))
        
        # Навигация
        telegram_app.add_handler(CallbackQueryHandler(admin_navigate, pattern="^admin_(next|prev)$"))
        
        # Действия с заявками
        telegram_app.add_handler(CallbackQueryHandler(admin_handle_action, pattern=r"^admin_(accept|reject|delete)_\d+$"))
        
        # Отправка сообщений пользователям
        telegram_app.add_handler(CallbackQueryHandler(admin_write_user_list, pattern="^admin_write_user$"))
        telegram_app.add_handler(CallbackQueryHandler(admin_start_reply, pattern=r"^admin_reply_to_\d+_\d+$"))
        
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
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("✅ Flask запущен")
    run_bot()
