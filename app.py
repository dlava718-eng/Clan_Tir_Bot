import os
import sys
import sqlite3
import re
import threading
from datetime import datetime, timedelta
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8882364637:AAHUWNZilUdxotSOXg44owGgCsuozHGlT48")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 123456789))
COOLDOWN_DAYS = int(os.environ.get("COOLDOWN_DAYS", 7))
DATABASE_FILE = "applications.db"

# Состояния анкеты
ASK_DESCRIPTION, ASK_LEVEL, ASK_NAME, ASK_SKILLS, ASK_TIMEZONE, ASK_AGE = range(6)

# Хранилище временных данных
user_data_temp = {}
admin_reply_temp = {}

# Создаём Flask-приложение для healthcheck
flask_app = Flask(__name__)

# ========== РАБОТА С БАЗОЙ ДАННЫХ SQLITE ==========
def init_database():
    """Инициализация базы данных и создание таблиц"""
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
    print("✅ База данных SQLite инициализирована")

def save_application(user_id, username, clan_choice, answers):
    """Сохраняет заявку в базу данных"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO applications 
        (user_id, username, clan_choice, description, level, ingame_name, skills, timezone, age, timestamp, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id,
        username,
        clan_choice,
        answers['описание'],
        answers['уровень'],
        answers['имя'],
        answers['навыки'],
        answers['часовой пояс'],
        answers['возраст'],
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'pending'
    ))
    
    app_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return app_id

def load_applications(status_filter=None):
    """Загружает заявки из базы данных с фильтром по статусу"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    if status_filter:
        cursor.execute('''
            SELECT id, user_id, username, clan_choice, description, level, ingame_name, 
                   skills, timezone, age, timestamp, status
            FROM applications WHERE status = ? ORDER BY id DESC
        ''', (status_filter,))
    else:
        cursor.execute('''
            SELECT id, user_id, username, clan_choice, description, level, ingame_name, 
                   skills, timezone, age, timestamp, status
            FROM applications ORDER BY id DESC
        ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    apps = []
    for row in rows:
        apps.append({
            "id": row[0],
            "user_id": row[1],
            "username": row[2],
            "clan_choice": row[3],
            "answers": {
                "описание": row[4],
                "уровень": row[5],
                "имя": row[6],
                "навыки": row[7],
                "часовой пояс": row[8],
                "возраст": row[9]
            },
            "timestamp": row[10],
            "status": row[11]
        })
    
    return apps

def get_application_by_id(app_id):
    """Получает заявку по ID"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, user_id, username, clan_choice, description, level, ingame_name, 
               skills, timezone, age, timestamp, status
        FROM applications WHERE id = ?
    ''', (app_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row[0],
            "user_id": row[1],
            "username": row[2],
            "clan_choice": row[3],
            "answers": {
                "описание": row[4],
                "уровень": row[5],
                "имя": row[6],
                "навыки": row[7],
                "часовой пояс": row[8],
                "возраст": row[9]
            },
            "timestamp": row[10],
            "status": row[11]
        }
    return None

def update_application_status(app_id, new_status):
    """Обновляет статус заявки"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE applications SET status = ? WHERE id = ?', (new_status, app_id))
    conn.commit()
    conn.close()

def delete_application(app_id):
    """Удаляет заявку из базы данных"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM applications WHERE id = ?', (app_id,))
    conn.commit()
    conn.close()

def get_user_last_application(user_id):
    """Возвращает последнюю заявку пользователя и дату"""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, user_id, username, clan_choice, description, level, ingame_name, 
               skills, timezone, age, timestamp, status
        FROM applications WHERE user_id = ? ORDER BY id DESC LIMIT 1
    ''', (user_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        app = {
            "id": row[0],
            "user_id": row[1],
            "username": row[2],
            "clan_choice": row[3],
            "answers": {
                "описание": row[4],
                "уровень": row[5],
                "имя": row[6],
                "навыки": row[7],
                "часовой пояс": row[8],
                "возраст": row[9]
            },
            "timestamp": row[10],
            "status": row[11]
        }
        last_date = datetime.strptime(app["timestamp"], "%Y-%m-%d %H:%M:%S")
        return app, last_date
    return None, None

def can_submit_application(user_id):
    """Проверяет, может ли пользователь подать новую заявку"""
    last_app, last_date = get_user_last_application(user_id)
    
    if last_app is None:
        return True, None
    
    days_passed = (datetime.now() - last_date).days
    
    if days_passed >= COOLDOWN_DAYS:
        return True, None
    else:
        days_left = COOLDOWN_DAYS - days_passed
        return False, days_left

def get_statistics():
    """Получает статистику по заявкам"""
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
    tir_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM applications WHERE clan_choice = "Academia"')
    academia_count = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        "total": total,
        "pending": pending,
        "accepted": accepted,
        "rejected": rejected,
        "tir": tir_count,
        "academia": academia_count
    }

# ========== ФУНКЦИЯ ДЛЯ ЭКРАНИРОВАНИЯ MARKDOWN ==========
def escape_markdown(text):
    """Экранирует специальные символы Markdown"""
    special_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(r'([{}])'.format(re.escape(special_chars)), r'\\\1', str(text))

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
        try:
            await message.edit_text(menu_text, reply_markup=reply_markup, parse_mode="Markdown")
        except:
            await message.reply_text(menu_text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(menu_text, reply_markup=reply_markup, parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_temp.pop(user_id, None)
    admin_reply_temp.pop(user_id, None)
    await main_menu(update, context)

# ========== ПРОВЕРКА СТАТУСА ЗАЯВКИ ==========
async def my_application(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает пользователю статус его последней заявки"""
    user_id = update.effective_user.id
    last_app, last_date = get_user_last_application(user_id)
    
    if last_app is None:
        await update.message.reply_text(
            "📭 *У вас нет отправленных заявок.*\n\n"
            "Нажмите /start и выберите 'Вступить в Tir' или 'Вступить в Academia'",
            parse_mode="Markdown"
        )
        return
    
    status_emoji = {
        "pending": "⏳",
        "accepted": "✅",
        "rejected": "❌"
    }.get(last_app["status"], "❓")
    
    status_text = {
        "pending": "Ожидает рассмотрения",
        "accepted": "✅ ПРИНЯТА! Лидер свяжется с вами",
        "rejected": "❌ ОТКЛОНЕНА"
    }.get(last_app["status"], "Неизвестно")
    
    can_submit, days_left = can_submit_application(user_id)
    
    next_attempt = ""
    if not can_submit and last_app["status"] in ["rejected", "pending"]:
        next_attempt = f"\n\n📅 Следующая попытка: через {days_left} дн."
    
    description = escape_markdown(last_app['answers']['описание'])
    name = escape_markdown(last_app['answers']['имя'])
    skills = escape_markdown(last_app['answers']['навыки'])
    timezone = escape_markdown(last_app['answers']['часовой пояс'])
    
    message = f"""
{status_emoji} *Статус вашей заявки*

📋 *Заявка #{last_app['id']}*
🏰 Клан: {escape_markdown(last_app['clan_choice'])}
📅 Дата: {escape_markdown(last_app['timestamp'])}
📊 Статус: {status_text}

📝 *Ваши данные:*
• Описание: {description}
• Уровень: {last_app['answers']['уровень']}
• Имя в игре: {name}
• Навыки: {skills}
• Часовой пояс: {timezone}
• Возраст: {last_app['answers']['возраст']}
{next_attempt}
"""
    
    keyboard = [[InlineKeyboardButton("◀️ Вернуться в меню", callback_data="back_to_menu")]]
    await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# ========== ИНФОРМАЦИОННЫЕ КНОПКИ ==========
async def about_us_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    about_text = """
🏰 **О клане Tir** 🏰

*Мы не просто клан — мы братство воинов, объединённых одной целью: стать легендой!*

⚡ **Наш путь** ⚡
Мы прошли через огонь и воду, через сотни битв и тысячи побед. Tir — это не название, это клеймо на сердце каждого из нас.

🎯 **Наша принципы** 🎯
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
Топ-10 кланов по PvP | 3-кратные победители клановых турниров | Более 50 совместных рейдов

*Стань частью истории. Стань частью TIR!* 🐉
"""
    keyboard = [[InlineKeyboardButton("◀️ Вернуться в меню", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(about_text, reply_markup=reply_markup, parse_mode="Markdown")
    except:
        await query.message.reply_text(about_text, reply_markup=reply_markup, parse_mode="Markdown")

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

📚 **ACADEMIA — НОВОБРАНЦЫ** 📚

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
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(diff_text, reply_markup=reply_markup, parse_mode="Markdown")
    except:
        await query.message.reply_text(diff_text, reply_markup=reply_markup, parse_mode="Markdown")

# ========== НАЧАЛО АНКЕТЫ ==========
async def join_tir_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    can_submit, days_left = can_submit_application(user_id)
    
    if not can_submit:
        keyboard = [[InlineKeyboardButton("◀️ Вернуться в меню", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(
                f"⏰ *Вы не можете подать заявку так часто!*\n\n"
                f"Ваша предыдущая заявка ещё рассматривается или была отклонена.\n\n"
                f"📅 *Следующую заявку можно подать через {days_left} дн.*\n\n"
                f"Чтобы узнать статус заявки, отправьте команду /myapp",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        except:
            await query.message.reply_text(
                f"⏰ Вы не можете подать заявку так часто!\n\nСледующая попытка через {days_left} дн.",
                reply_markup=reply_markup
            )
        return
    
    user_data_temp[user_id] = {"clan": "Tir", "step": ASK_DESCRIPTION}
    
    try:
        await query.edit_message_text(
            "⚔️ *Ты выбрал клан Tir!* ⚔️\n\n"
            "Это путь сильнейших. Расскажи о себе подробнее.\n\n"
            "📝 *Напиши ОПИСАНИЕ о себе:*\n"
            "(Кратко расскажи, кто ты, чем занимаешься в игре, какой у тебя опыт)",
            parse_mode="Markdown"
        )
    except:
        await query.message.reply_text(
            "⚔️ Ты выбрал клан Tir!\n\n📝 Напиши ОПИСАНИЕ о себе:"
        )

async def join_academia_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    can_submit, days_left = can_submit_application(user_id)
    
    if not can_submit:
        keyboard = [[InlineKeyboardButton("◀️ Вернуться в меню", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(
                f"⏰ *Вы не можете подать заявку так часто!*\n\n"
                f"Ваша предыдущая заявка ещё рассматривается или была отклонена.\n\n"
                f"📅 *Следующую заявку можно подать через {days_left} дн.*\n\n"
                f"Чтобы узнать статус заявки, отправьте команду /myapp",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        except:
            await query.message.reply_text(
                f"⏰ Вы не можете подать заявку так часто!\n\nСледующая попытка через {days_left} дн.",
                reply_markup=reply_markup
            )
        return
    
    user_data_temp[user_id] = {"clan": "Academia", "step": ASK_DESCRIPTION}
    
    try:
        await query.edit_message_text(
            "📚 *Ты выбрал Academia!* 📚\n\n"
            "Это старт твоего пути к величию. Расскажи о себе.\n\n"
            "📝 *Напиши ОПИСАНИЕ о себе:*\n"
            "(Кто ты, какой у тебя опыт, чего хочешь достичь)",
            parse_mode="Markdown"
        )
    except:
        await query.message.reply_text(
            "📚 Ты выбрал Academia!\n\n📝 Напиши ОПИСАНИЕ о себе:"
        )

# ========== ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    
    if user_id in user_data_temp:
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
            await update.message.reply_text("⚔️ *Опишите свои НАВЫКИ:*\n(Класс, роль в команде, что умеете)", parse_mode="Markdown")
        
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
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"✅ *Заявка #{app_id} отправлена!*\n\n"
                "Ожидайте ответа лидера или зама.\n"
                "Спасибо, что выбрали наш клан! 🙌\n\n"
                "Статус заявки можно проверить командой /myapp",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        
        return
    
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
                f"✅ *Сообщение отправлено!*\n\n"
                f"Пользователь: @{escape_markdown(username)}\n"
                f"ID заявки: #{app_id}",
                parse_mode="Markdown"
            )
            
            del admin_reply_temp[user_id]
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при отправке: {escape_markdown(str(e))}")
        
        return

# ========== АДМИН-ПАНЕЛЬ ==========
async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if user_id != ADMIN_ID:
        keyboard = [[InlineKeyboardButton("◀️ Вернуться в меню", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(
                "⛔ *Доступ запрещён!*\n\nЭта панель доступна только лидерам и замам клана Tir.",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        except:
            await query.message.reply_text("⛔ Доступ запрещён!")
        return
    
    stats = get_statistics()
    
    admin_text = (
        "👑 *Админ-панель клана Tir* 👑\n\n"
        f"📊 *Статистика:*\n"
        f"• Всего заявок: `{stats['total']}`\n"
        f"• Ожидают рассмотрения: `{stats['pending']}`\n"
        f"• Подтверждённые: `{stats['accepted']}`\n"
        f"• Отклонённые: `{stats['rejected']}`\n"
        f"• В Tir: `{stats['tir']}` | В Academia: `{stats['academia']}`\n"
        f"• КД между заявками: `{COOLDOWN_DAYS} дн.`\n\n"
        "Выберите действие:"
    )
    
    keyboard = [
        [InlineKeyboardButton("📋 Список всех заявок", callback_data="admin_view_all")],
        [InlineKeyboardButton("⏳ Только новые (ожидают)", callback_data="admin_view_pending")],
        [InlineKeyboardButton("✅ Подтверждённые", callback_data="admin_view_accepted")],
        [InlineKeyboardButton("❌ Отклонённые", callback_data="admin_view_rejected")],
        [InlineKeyboardButton("🗑️ Удалить заявку", callback_data="admin_delete_menu")],
        [InlineKeyboardButton("💬 Написать пользователю", callback_data="admin_write_user")],
        [InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(admin_text, reply_markup=reply_markup, parse_mode="Markdown")
    except:
        await query.message.reply_text(admin_text, reply_markup=reply_markup)

# ========== ФУНКЦИИ УДАЛЕНИЯ ЗАЯВОК ==========
async def admin_delete_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню выбора заявки для удаления"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    apps = load_applications()
    
    if not apps:
        await query.edit_message_text(
            "📭 Нет заявок для удаления.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")
            ]])
        )
        return
    
    keyboard = []
    for app in apps[:20]:
        status_emoji = "⏳" if app["status"] == "pending" else "✅" if app["status"] == "accepted" else "❌"
        username = app['username'] if app['username'] else "нет_username"
        keyboard.append([
            InlineKeyboardButton(
                f"{status_emoji} #{app['id']} - @{username} ({app['clan_choice']})",
                callback_data=f"admin_delete_confirm_{app['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("🗑️ Выберите заявку для удаления:", reply_markup=reply_markup)

async def admin_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение удаления заявки"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    app_id = int(query.data.split("_")[3])
    app = get_application_by_id(app_id)
    
    if not app:
        await query.edit_message_text("❌ Заявка не найдена!")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"admin_delete_execute_{app_id}"),
            InlineKeyboardButton("❌ Нет, отмена", callback_data="admin_delete_menu")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🗑️ ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ\n\n"
        f"Вы действительно хотите удалить заявку #{app_id}?\n\n"
        f"📋 Информация о заявке:\n"
        f"👤 Пользователь: @{app['username']}\n"
        f"🏰 Клан: {app['clan_choice']}\n"
        f"📊 Статус: {app['status']}\n"
        f"📅 Дата: {app['timestamp']}\n\n"
        f"⚠️ Это действие необратимо!",
        reply_markup=reply_markup
    )

async def admin_delete_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполняет удаление заявки"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    app_id = int(query.data.split("_")[3])
    app = get_application_by_id(app_id)
    
    if not app:
        await query.edit_message_text("❌ Заявка не найдена!")
        return
    
    username = app['username'] if app['username'] else "пользователь"
    clan = app['clan_choice']
    user_id = app['user_id']
    
    delete_application(app_id)
    
    await query.edit_message_text(
        f"✅ Заявка #{app_id} успешно удалена!\n\nПользователь: @{username}\nКлан: {clan}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="admin_panel")
        ]])
    )
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🗑️ Ваша заявка #{app_id} в клан {clan} была удалена администрацией.\n\n"
                 f"Если у вас есть вопросы, обратитесь к лидеру клана.\n\n"
                 f"Вы можете подать новую заявку через /start"
        )
    except:
        pass

# ========== ПРОСМОТР ЗАЯВОК ==========
async def admin_view_applications(update: Update, context: ContextTypes.DEFAULT_TYPE, status_filter=None):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        return
    
    apps = load_applications(status_filter)
    
    if not apps:
        status_text = {
            "pending": "новых",
            "accepted": "подтверждённых",
            "rejected": "отклонённых"
        }.get(status_filter, "") if status_filter else ""
        
        await query.edit_message_text(
            f"📭 Нет {status_text} заявок.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data="admin_panel")
            ]])
        )
        return
    
    page = context.user_data.get("admin_page", 0)
    per_page = 5
    total_pages = (len(apps) + per_page - 1) // per_page
    
    if page >= total_pages:
        page = 0
        context.user_data["admin_page"] = 0
    
    start_idx = page * per_page
    end_idx = min(start_idx + per_page, len(apps))
    
    context.user_data["admin_filter"] = status_filter
    context.user_data["admin_apps"] = apps
    
    message_text = f"📋 ЗАЯВКИ ({page+1}/{total_pages}):\n\n"
    
    for i, app in enumerate(apps[start_idx:end_idx], start=1):
        username = app['username'] if app['username'] else "нет_username"
        message_text += (
            f"{start_idx + i}. Заявка #{app['id']}\n"
            f"👤 @{username} | {app['clan_choice']}\n"
            f"⏰ {app['timestamp']}\n"
            f"📊 Статус: {app['status']}\n"
            f"🎮 Имя: {app['answers']['имя']}\n"
            f"✨ Уровень: {app['answers']['уровень']}\n"
            "—————————————\n"
        )
    
    keyboard = []
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data="admin_prev_page"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Вперёд ▶️", callback_data="admin_next_page"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    if apps:
        current_app = apps[start_idx]
        keyboard.append([
            InlineKeyboardButton("✅ Принять", callback_data=f"admin_accept_{current_app['id']}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"admin_reject_{current_app['id']}")
        ])
        keyboard.append([
            InlineKeyboardButton("🗑️ Удалить", callback_data=f"admin_delete_confirm_{current_app['id']}"),
            InlineKeyboardButton("💬 Написать", callback_data=f"admin_reply_to_{current_app['user_id']}_{current_app['id']}")
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="admin_panel")])
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.edit_message_text(message_text, reply_markup=reply_markup)
    except:
        await query.message.reply_text(message_text, reply_markup=reply_markup)

async def admin_change_page(update: Update, context: ContextTypes.DEFAULT_TYPE, direction):
    query = update.callback_query
    await query.answer()
    
    current_page = context.user_data.get("admin_page", 0)
    if direction == "next":
        context.user_data["admin_page"] = current_page + 1
    else:
        context.user_data["admin_page"] = current_page - 1
    
    status_filter = context.user_data.get("admin_filter")
    await admin_view_applications(update, context, status_filter)

async def admin_handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE, app_id, action):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    app = get_application_by_id(app_id)
    if not app:
        await query.edit_message_text("❌ Заявка не найдена!")
        return
    
    new_status = "accepted" if action == "accept" else "rejected"
    update_application_status(app_id, new_status)
    
    status_emoji = "✅" if action == "accept" else "❌"
    status_text = "принята" if action == "accept" else "отклонена"
    
    try:
        user_message = f"{status_emoji} *Ваша заявка в клан {escape_markdown(app['clan_choice'])} была {status_text}!*\n\n"
        if action == "accept":
            user_message += "🎉 Поздравляем! Лидер свяжется с вами для дальнейших инструкций.\n\nДобро пожаловать в семью Tir! 💪"
        else:
            user_message += f"😔 К сожалению, мы не можем принять вас сейчас.\n\nНовую заявку можно подать через {COOLDOWN_DAYS} дней."
        
        await context.bot.send_message(chat_id=app["user_id"], text=user_message, parse_mode="Markdown")
        await query.edit_message_text(
            f"{status_emoji} Заявка #{app_id} {status_text}!\nПользователю отправлено уведомление.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="admin_panel")
            ]])
        )
    except Exception as e:
        await query.edit_message_text(
            f"{status_emoji} Заявка #{app_id} {status_text}!\n⚠️ Уведомление не отправлено.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="admin_panel")
            ]])
        )

# ========== ОТПРАВКА СООБЩЕНИЙ ==========
async def admin_write_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return
    
    apps = load_applications()
    if not apps:
        await query.edit_message_text(
            "📭 Нет пользователей для связи.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="admin_panel")
            ]])
        )
        return
    
    keyboard = []
    for app in apps[:15]:
        username = app['username'] if app['username'] else "нет_username"
        keyboard.append([
            InlineKeyboardButton(
                f"@{username} (заявка #{app['id']})", 
                callback_data=f"admin_reply_to_{app['user_id']}_{app['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="admin_panel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text("💬 Выберите пользователя для отправки сообщения:", reply_markup=reply_markup)

async def admin_start_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id != ADMIN_ID:
        return
    
    parts = query.data.split("_")
    target_user_id = int(parts[3])
    app_id = int(parts[4])
    
    admin_reply_temp[user_id] = {"target_user_id": target_user_id, "app_id": app_id}
    
    await query.edit_message_text(
        "💬 РЕЖИМ ОТПРАВКИ СООБЩЕНИЯ\n\n"
        "Напишите сообщение, которое хотите отправить пользователю.\n\n"
        "Сообщение придёт ОТ ИМЕНИ БОТА.\n\n"
        "Для отмены напишите /cancel"
    )

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
async def back_to_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data_temp.pop(user_id, None)
    admin_reply_temp.pop(user_id, None)
    context.user_data.pop("admin_page", None)
    context.user_data.pop("admin_filter", None)
    context.user_data.pop("admin_apps", None)
    
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

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ Неизвестная команда.\n\n"
        "Доступные команды:\n"
        "/start - Главное меню\n"
        "/myapp - Статус моей заявки\n"
        "/cancel - Отмена текущего действия"
    )

# ========== ЗАПУСК БОТА ==========
async def run_bot():
    """Запускает Telegram бота"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("myapp", my_application))
    application.add_handler(CommandHandler("cancel", cancel_command))
    
    # Callback-обработчики главного меню
    application.add_handler(CallbackQueryHandler(join_tir_callback, pattern="^join_tir$"))
    application.add_handler(CallbackQueryHandler(join_academia_callback, pattern="^join_academia$"))
    application.add_handler(CallbackQueryHandler(about_us_callback, pattern="^about_us$"))
    application.add_handler(CallbackQueryHandler(difference_callback, pattern="^difference$"))
    application.add_handler(CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$"))
    application.add_handler(CallbackQueryHandler(back_to_menu_callback, pattern="^back_to_menu$"))
    
    # Админские обработчики просмотра
    application.add_handler(CallbackQueryHandler(lambda u,c: admin_view_applications(u,c, None), pattern="^admin_view_all$"))
    application.add_handler(CallbackQueryHandler(lambda u,c: admin_view_applications(u,c, "pending"), pattern="^admin_view_pending$"))
    application.add_handler(CallbackQueryHandler(lambda u,c: admin_view_applications(u,c, "accepted"), pattern="^admin_view_accepted$"))
    application.add_handler(CallbackQueryHandler(lambda u,c: admin_view_applications(u,c, "rejected"), pattern="^admin_view_rejected$"))
    
    # Пагинация
    application.add_handler(CallbackQueryHandler(lambda u,c: admin_change_page(u,c, "next"), pattern="^admin_next_page$"))
    application.add_handler(CallbackQueryHandler(lambda u,c: admin_change_page(u,c, "prev"), pattern="^admin_prev_page$"))
    
    # Принятие/отклонение заявок
    application.add_handler(CallbackQueryHandler(lambda u,c: admin_handle_action(u,c, int(c.matches[0].group(1)), "accept"), pattern=r"^admin_accept_(\d+)$"))
    application.add_handler(CallbackQueryHandler(lambda u,c: admin_handle_action(u,c, int(c.matches[0].group(1)), "reject"), pattern=r"^admin_reject_(\d+)$"))
    
    # Удаление заявок
    application.add_handler(CallbackQueryHandler(admin_delete_menu, pattern="^admin_delete_menu$"))
    application.add_handler(CallbackQueryHandler(admin_delete_confirm, pattern=r"^admin_delete_confirm_(\d+)$"))
    application.add_handler(CallbackQueryHandler(admin_delete_execute, pattern=r"^admin_delete_execute_(\d+)$"))
    
    # Отправка сообщений
    application.add_handler(CallbackQueryHandler(admin_write_user_list, pattern="^admin_write_user$"))
    application.add_handler(CallbackQueryHandler(admin_start_reply, pattern=r"^admin_reply_to_\d+_\d+$"))
    
    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.COMMAND, unknown))
    
    print("✅ Telegram бот запущен!")
    print(f"👑 Администратор: {ADMIN_ID}")
    print(f"⏰ КД между заявками: {COOLDOWN_DAYS} дней")
    print(f"💾 База данных: {DATABASE_FILE}")
    
    # Запускаем бота с polling
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Держим бота запущенным
    while True:
        await asyncio.sleep(3600)

# ========== FLASK ДЛЯ HEALTHCHECK ==========
@flask_app.route('/')
@flask_app.route('/health')
def health():
    return jsonify({"status": "ok", "message": "Bot is running"}), 200

def run_flask():
    """Запускает Flask-сервер для Render healthcheck"""
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

# ========== ОСНОВНОЙ ЗАПУСК ==========
if __name__ == "__main__":
    import asyncio
    
    # Инициализируем базу данных
    init_database()
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print("✅ Flask сервер запущен на порту", os.environ.get("PORT", 5000))
    
    # Запускаем бота
    asyncio.run(run_bot())
