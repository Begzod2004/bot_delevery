import logging
import os
import asyncio
import sqlite3
import pandas as pd
import openpyxl
from openpyxl.drawing.image import Image as XLImage
from io import BytesIO
import aiohttp
import aiofiles
import shutil
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.client.session.aiohttp import AiohttpSession
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env')  # Explicitly specify .env file

# Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in environment variables")

ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id]
if not ADMIN_IDS:
    raise ValueError("ADMIN_IDS not found in environment variables")

logging.basicConfig(level=logging.INFO)
logging.info(f"Bot token loaded: {BOT_TOKEN[:10]}...")  # Log first 10 chars of token for verification

# Set up data storage
DB_FILE = 'suppliers.db'
EXPORT_FILE = 'suppliers_export.xlsx'
QR_FOLDER = 'qr_codes'
BRANDS_FILE = 'popular_brands.json'

# Initialize bot and dispatcher with default session
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Bot configuration with increased timeout
BOT_CONFIG = {
    'timeout': 30,  # Increase timeout to 30 seconds
    'connect_timeout': 30,
    'read_timeout': 30,
    'write_timeout': 30
}

# Создаем папку для QR-кодов, если её нет
if not os.path.exists(QR_FOLDER):
    os.makedirs(QR_FOLDER)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Создаем таблицу для поставщиков если она не существует
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        qr_wechat TEXT NULL,
        qr_wegoo TEXT NULL,
        comment TEXT NULL,
        main_category TEXT NULL,
        level_category TEXT NULL,
        gender_category TEXT NULL,
        brand TEXT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()
    logging.info("База данных инициализирована")
    
    # Initialize brands file if it doesn't exist
    if not os.path.exists(BRANDS_FILE):
        # Brand categories with luxury brands
        popular_brands = {
            "top_fashion": [
                "Louis Vuitton", "Chanel", "Gucci", "Hermès", "Prada", 
                "Dior", "Balenciaga", "Saint Laurent", "Fendi", "Valentino"
            ],
            "premium_fashion": [
                "Givenchy", "Bottega Veneta", "Burberry", "Versace", "Celine",
                "Loewe", "Tom Ford", "Alexander McQueen", "Maison Margiela", "Off-White"
            ],
            "luxury_shoes": [
                "Christian Louboutin", "Jimmy Choo", "Manolo Blahnik", "Salvatore Ferragamo",
                "Gianvito Rossi", "Roger Vivier", "Berluti"
            ],
            "jewelry_watches": [
                "Cartier", "Van Cleef & Arpels", "Bvlgari", "Chopard", "Tiffany & Co.",
                "Piaget", "Graff", "Patek Philippe", "Audemars Piguet", "Rolex"
            ],
            "niche_brands": [
                "Amiri", "Fear of God", "Issey Miyake", "Yohji Yamamoto", "Comme des Garçons",
                "Delvaux", "Goyard", "Moynat", "Etro", "Ermenegildo Zegna"
            ],
            "custom": []
        }
        save_brands(popular_brands)
        logging.info("Файл с брендами создан")

# Load brands from JSON file
def load_brands():
    if os.path.exists(BRANDS_FILE):
        try:
            with open(BRANDS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            # Return default if file is corrupted
            return {
                "top_fashion": [
                    "Louis Vuitton", "Chanel", "Gucci", "Hermès", "Prada", 
                    "Dior", "Balenciaga", "Saint Laurent", "Fendi", "Valentino"
                ],
                "premium_fashion": [
                    "Givenchy", "Bottega Veneta", "Burberry", "Versace", "Celine",
                    "Loewe", "Tom Ford", "Alexander McQueen", "Maison Margiela", "Off-White"
                ],
                "luxury_shoes": [
                    "Christian Louboutin", "Jimmy Choo", "Manolo Blahnik", "Salvatore Ferragamo",
                    "Gianvito Rossi", "Roger Vivier", "Berluti"
                ],
                "jewelry_watches": [
                    "Cartier", "Van Cleef & Arpels", "Bvlgari", "Chopard", "Tiffany & Co.",
                    "Piaget", "Graff", "Patek Philippe", "Audemars Piguet", "Rolex"
                ],
                "niche_brands": [
                    "Amiri", "Fear of God", "Issey Miyake", "Yohji Yamamoto", "Comme des Garçons",
                    "Delvaux", "Goyard", "Moynat", "Etro", "Ermenegildo Zegna"
                ],
                "custom": []
            }
    else:
        # Create default brands file with the full list
        brands = {
            "top_fashion": [
                "Louis Vuitton", "Chanel", "Gucci", "Hermès", "Prada", 
                "Dior", "Balenciaga", "Saint Laurent", "Fendi", "Valentino"
            ],
            "premium_fashion": [
                "Givenchy", "Bottega Veneta", "Burberry", "Versace", "Celine",
                "Loewe", "Tom Ford", "Alexander McQueen", "Maison Margiela", "Off-White"
            ],
            "luxury_shoes": [
                "Christian Louboutin", "Jimmy Choo", "Manolo Blahnik", "Salvatore Ferragamo",
                "Gianvito Rossi", "Roger Vivier", "Berluti"
            ],
            "jewelry_watches": [
                "Cartier", "Van Cleef & Arpels", "Bvlgari", "Chopard", "Tiffany & Co.",
                "Piaget", "Graff", "Patek Philippe", "Audemars Piguet", "Rolex"
            ],
            "niche_brands": [
                "Amiri", "Fear of God", "Issey Miyake", "Yohji Yamamoto", "Comme des Garçons",
                "Delvaux", "Goyard", "Moynat", "Etro", "Ermenegildo Zegna"
            ],
            "custom": []
        }
        save_brands(brands)
        return brands

# Save brands to JSON file
def save_brands(brands_data):
    with open(BRANDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(brands_data, f, ensure_ascii=False, indent=2)

# Add a new custom brand if it doesn't exist
def add_custom_brand(brand_name):
    brands = load_brands()
    
    # Skip if already in any of the brand categories
    for category in brands:
        if brand_name in brands[category]:
            return
    
    # Add to custom brands list and save
    brands["custom"].append(brand_name)
    save_brands(brands)
    logging.info(f"Добавлен новый бренд: {brand_name}")

# Сохранение поставщика в БД
def save_supplier_to_db(data):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Convert empty strings to None
    for key in data:
        if data[key] == "":
            data[key] = None
    
    cursor.execute(
        "INSERT INTO suppliers (qr_wechat, qr_wegoo, comment, main_category, level_category, gender_category, brand) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (data['qr_wechat'], data['qr_wegoo'], data['comment'], data['main_category'], data['level_category'], data['gender_category'], data['brand'])
    )
    
    supplier_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return supplier_id

# Получение всех поставщиков из БД
def get_suppliers_from_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # Получаем результаты как словари
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM suppliers ORDER BY created_at DESC")
    suppliers = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return suppliers

# Скачивание файла из Telegram
async def download_telegram_file(bot, file_id, destination):
    file = await bot.get_file(file_id)
    file_path = file.file_path
    
    # Получаем URL для скачивания
    file_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_path}"
    
    # Скачиваем файл
    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            if resp.status == 200:
                content = await resp.read()
                # Сохраняем файл
                async with aiofiles.open(destination, 'wb') as f:
                    await f.write(content)
                return True
    return False

# Экспорт в Excel с изображениями
async def export_to_excel_with_images(bot):
    try:
        logging.info("Starting Excel export process")
        suppliers = get_suppliers_from_db()
        if not suppliers:
            logging.warning("No suppliers found in database for export")
            return False
        
        logging.info(f"Found {len(suppliers)} suppliers to export")
        
        # Create absolute path for export file
        export_path = os.path.abspath(EXPORT_FILE)
        logging.info(f"Excel will be saved to: {export_path}")
        
        # Создаем DataFrame из данных поставщиков
        df = pd.DataFrame(suppliers)
        
        # Переименовываем столбцы для лучшей читаемости
        df = df.rename(columns={
            'id': 'ID',
            'qr_wechat': 'QR WeChat',
            'qr_wegoo': 'QR WEGoo',
            'comment': 'Комментарий',
            'main_category': 'Основная категория',
            'level_category': 'Уровень',
            'gender_category': 'Пол',
            'brand': 'Бренд',
            'created_at': 'Дата создания'
        })
        
        try:
            # Сохраняем сначала без изображений в Excel
            df.to_excel(export_path, index=False)
            logging.info("Base Excel file created without images")
        except Exception as e:
            logging.error(f"Error creating Excel file: {str(e)}")
            return False
        
        try:
            # Теперь добавляем изображения с помощью openpyxl
            workbook = openpyxl.load_workbook(export_path)
            sheet = workbook.active
            
            # Увеличиваем высоту строк для изображений
            sheet.row_dimensions[1].height = 20  # Заголовок
            
            # Увеличиваем ширину колонок с QR-кодами
            sheet.column_dimensions['B'].width = 30  # QR WeChat
            sheet.column_dimensions['C'].width = 30  # QR WEGoo
            
            # Создаем временную папку для изображений
            temp_folder = os.path.join(QR_FOLDER, 'temp')
            if os.path.exists(temp_folder):
                shutil.rmtree(temp_folder)
            os.makedirs(temp_folder)
            logging.info(f"Created temp folder for images: {temp_folder}")
            
            # Обрабатываем каждого поставщика
            for i, supplier in enumerate(suppliers, start=2):  # start=2 потому что первая строка - заголовки
                try:
                    # Скачиваем QR-коды
                    wechat_path = os.path.join(temp_folder, f"wechat_{supplier['id']}.jpg")
                    wegoo_path = os.path.join(temp_folder, f"wegoo_{supplier['id']}.jpg")
                    
                    wechat_success = await download_telegram_file(bot, supplier['qr_wechat'], wechat_path)
                    wegoo_success = await download_telegram_file(bot, supplier['qr_wegoo'], wegoo_path)
                    
                    if not wechat_success:
                        logging.warning(f"Failed to download WeChat QR for supplier {supplier['id']}")
                    if not wegoo_success:
                        logging.warning(f"Failed to download WEGoo QR for supplier {supplier['id']}")
                    
                    # Добавляем изображения в Excel
                    if os.path.exists(wechat_path) and os.path.getsize(wechat_path) > 0:
                        img_wechat = XLImage(wechat_path)
                        # Масштабируем изображение
                        img_wechat.width = 100
                        img_wechat.height = 100
                        sheet.row_dimensions[i].height = 80
                        sheet.add_image(img_wechat, f'B{i}')
                    
                    if os.path.exists(wegoo_path) and os.path.getsize(wegoo_path) > 0:
                        img_wegoo = XLImage(wegoo_path)
                        # Масштабируем изображение
                        img_wegoo.width = 100
                        img_wegoo.height = 100
                        sheet.row_dimensions[i].height = 80
                        sheet.add_image(img_wegoo, f'C{i}')
                except Exception as e:
                    logging.error(f"Error processing supplier {supplier['id']}: {str(e)}")
                    # Continue with other suppliers even if one fails
                    continue
            
            # Сохраняем файл
            try:
                workbook.save(export_path)
                logging.info(f"Excel file with images saved successfully at {export_path}")
                
                # Verify file exists and has content
                if os.path.exists(export_path) and os.path.getsize(export_path) > 0:
                    logging.info(f"Excel file verified: {os.path.getsize(export_path)} bytes")
                    return True
                else:
                    logging.error("Excel file was not created properly")
                    return False
            except Exception as e:
                logging.error(f"Error saving Excel file: {str(e)}")
                return False
            
        except Exception as e:
            logging.error(f"Error adding images to Excel: {str(e)}")
            # If we can't add images, at least return the basic Excel file
            return os.path.exists(export_path) and os.path.getsize(export_path) > 0
    
    except Exception as e:
        logging.error(f"Unexpected error in export_to_excel_with_images: {str(e)}")
        return False

# Получение поставщика по ID
def get_supplier_by_id(supplier_id):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
    supplier = cursor.fetchone()
    
    conn.close()
    return dict(supplier) if supplier else None

# Получение статистики по поставщикам
def get_suppliers_stats():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Общее количество поставщиков
    cursor.execute("SELECT COUNT(*) FROM suppliers")
    total_count = cursor.fetchone()[0]
    
    # Количество поставщиков по категориям
    cursor.execute("SELECT main_category, COUNT(*) FROM suppliers GROUP BY main_category")
    categories_stats = cursor.fetchall()
    
    # Количество поставщиков по уровням
    cursor.execute("SELECT level_category, COUNT(*) FROM suppliers GROUP BY level_category")
    levels_stats = cursor.fetchall()
    
    # Количество поставщиков за последние 24 часа
    yesterday = datetime.now() - timedelta(days=1)
    cursor.execute("SELECT COUNT(*) FROM suppliers WHERE datetime(created_at) > datetime(?)", 
                  (yesterday.strftime('%Y-%m-%d %H:%M:%S'),))
    last_24h_count = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        "total": total_count,
        "categories": categories_stats,
        "levels": levels_stats,
        "last_24h": last_24h_count
    }

# Определение состояний для формы
class SupplierForm(StatesGroup):
    qr_wechat = State()
    qr_wegoo = State()
    comment = State()
    main_category = State()
    level_category = State()
    gender_category = State()
    brand = State()
    selecting_categories = State()
    search_id = State()
    edit_mode = State()  # For tracking if user is editing previous entries

# Form step names for progress indication
FORM_STEPS = {
    "qr_wechat": "1. QR WeChat",
    "qr_wegoo": "2. QR WEGoo",
    "comment": "3. Комментарий",
    "selecting_categories": "4. Категории",
    "level_category": "5. Уровень",
    "gender_category": "6. Пол",
    "brand": "7. Бренд"
}

# Special keyboard for navigation and cancelation
def get_nav_keyboard(include_back=True, include_cancel=True, include_skip=False):
    buttons = []
    
    # Create the row based on which buttons to include
    row = []
    if include_back:
        row.append(KeyboardButton(text="◀️ Назад"))
    if include_cancel:
        row.append(KeyboardButton(text="❌ Отмена"))
    if include_skip:
        row.append(KeyboardButton(text="⏭️ Пропустить"))
    
    if row:
        buttons.append(row)
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=False)

# Get a keyboard with progress indication
def get_form_progress_keyboard(current_state, include_back=True, include_cancel=True, include_skip=False):
    # Create the base navigation keyboard
    keyboard = get_nav_keyboard(include_back, include_cancel, include_skip)
    
    # Add progress indicator to keyboard
    if current_state in FORM_STEPS:
        # Get all step names
        steps = list(FORM_STEPS.values())
        current_step_name = FORM_STEPS[current_state]
        current_step_index = steps.index(current_step_name)
        
        # Add progress text (e.g., "Step 3/7")
        progress_text = f"Шаг {current_step_index + 1}/{len(steps)}: {current_step_name}"
        keyboard.keyboard.insert(0, [KeyboardButton(text=progress_text)])
    
    return keyboard

def categories_selection_keyboard(selected_categories):
    categories = ["Обувь", "Одежда", "Аксессуары", "Сумки", "Украшения"]
    
    # Create rows with buttons (1 category per row for clarity)
    rows = []
    for category in categories:
        # Show checkbox status for each category
        prefix = "☑️ " if category in selected_categories else "⬜ "
        rows.append([KeyboardButton(text=f"{prefix}{category}")])
    
    # Add navigation buttons
    nav_row = []
    nav_row.append(KeyboardButton(text="◀️ Назад"))
    nav_row.append(KeyboardButton(text="✅ Готово"))
    nav_row.append(KeyboardButton(text="❌ Отмена"))
    rows.append(nav_row)
    
    markup = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
    return markup

def brands_selection_keyboard(selected_brands, current_category="top_fashion"):
    """Keyboard for multi-brand selection with checkboxes"""
    # Load all brands
    brands_data = load_brands()
    # Get the brands from current category
    category_brands = brands_data.get(current_category, [])
    # Create keyboard with checkboxes for each brand
    rows = []
    # Add category title and navigation
    category_names = {
        "top_fashion": "👑 ТОП БРЕНДЫ",
        "premium_fashion": "🌟 ПРЕМИУМ",
        "luxury_shoes": "👠 ОБУВЬ",
        "jewelry_watches": "💎 УКРАШЕНИЯ",
        "niche_brands": "⭐ НИШЕВЫЕ",
        "custom": "🔖 ДОБАВЛЕННЫЕ"
    }
    # Get ordered category list for navigation
    categories = ["top_fashion", "premium_fashion", "luxury_shoes", "jewelry_watches", "niche_brands", "custom"]
    current_index = categories.index(current_category)
    # Add category navigation bar
    nav_row = []
    if current_index > 0:
        nav_row.append(KeyboardButton(text="◀️"))
    nav_row.append(KeyboardButton(text=f"📚 {category_names[current_category]} ({current_index+1}/{len(categories)})"))
    if current_index < len(categories) - 1:
        nav_row.append(KeyboardButton(text="▶️"))
    rows.append(nav_row)
    # Add brands with checkboxes
    for brand in category_brands:
        # Mark selected brands with checkboxes
        prefix = "✅ " if brand in selected_brands else "⬜ "
        rows.append([KeyboardButton(text=f"{prefix}{brand}")])
    # Add control buttons at the bottom
    control_row = []
    control_row.append(KeyboardButton(text="🔍 ПОИСК"))
    control_row.append(KeyboardButton(text="➕ ДОБАВИТЬ"))
    rows.append(control_row)
    # Add navigation buttons
    nav_row = []
    nav_row.append(KeyboardButton(text="◀️ НАЗАД"))
    nav_row.append(KeyboardButton(text="✅ ГОТОВО"))
    nav_row.append(KeyboardButton(text="❌ ОТМЕНА"))
    rows.append(nav_row)
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

@dp.message(Command('start'))
async def cmd_start(message: Message):
    markup = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Добавить поставщика")],
        [KeyboardButton(text="🔍 Найти поставщика")]
    ], resize_keyboard=True)
    
    # Для администратора показываем дополнительные команды
    if message.from_user.id in ADMIN_IDS:
        markup.keyboard.append([
            KeyboardButton(text="📊 Статистика"),
            KeyboardButton(text="Экспорт в Excel")
        ])
    
    await message.answer("Добро пожаловать! Выберите действие.", reply_markup=markup)

@dp.message(Command('supplier', 'find'))
async def cmd_find_supplier(message: Message, command: CommandObject):
    """Find supplier by ID using command like /supplier 123 or /find 123"""
    if not command.args:
        await message.answer("Пожалуйста, укажите ID поставщика. Например: /supplier 123")
        return
        
    try:
        supplier_id = int(command.args)
        supplier = get_supplier_by_id(supplier_id)
        
        if not supplier:
            await message.answer(f"Поставщик с ID {supplier_id} не найден.")
            return
            
        await show_supplier_card(message, supplier)
    except ValueError:
        await message.answer("ID поставщика должен быть числом. Например: /supplier 123")

@dp.message(F.text == "🔍 Найти поставщика")
async def search_supplier_start(message: Message, state: FSMContext):
    await message.answer("Введите ID поставщика для поиска:")
    await state.set_state(SupplierForm.search_id)

@dp.message(SupplierForm.search_id)
async def search_supplier_process(message: Message, state: FSMContext):
    try:
        supplier_id = int(message.text)
        supplier = get_supplier_by_id(supplier_id)
        
        if not supplier:
            await message.answer(f"Поставщик с ID {supplier_id} не найден.")
        else:
            await show_supplier_card(message, supplier)
            
        await state.clear()
    except ValueError:
        await message.answer("ID поставщика должен быть числом. Пожалуйста, введите корректный ID.")

@dp.message(F.text == "📊 Статистика")
async def show_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет доступа к этой функции.")
        return
        
    stats = get_suppliers_stats()
    
    # Форматируем статистику
    response = "📊 **Статистика по поставщикам:**\n\n"
    response += f"📌 Всего поставщиков: **{stats['total']}**\n"
    response += f"🆕 Добавлено за 24 часа: **{stats['last_24h']}**\n\n"
    
    # Статистика по категориям
    response += "📂 **По категориям:**\n"
    for category, count in stats['categories']:
        category_name = category or "Без категории"
        response += f"  • {category_name}: {count}\n"
    
    # Статистика по уровням
    response += "\n🔝 **По уровням:**\n"
    for level, count in stats['levels']:
        level_name = level or "Без уровня"
        response += f"  • {level_name}: {count}\n"
    
    # Кнопки для дополнительных действий
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Экспорт в Excel", callback_data="export_excel")],
        [InlineKeyboardButton(text="📋 Последние добавленные", callback_data="latest_suppliers")]
    ])
    
    await message.answer(response, parse_mode="Markdown", reply_markup=markup)

@dp.callback_query(F.data == "export_excel")
async def callback_export_excel(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет доступа к этой функции.")
        return
        
    await callback.answer("Начинаю экспорт...")
    
    # Use the existing export_button handler but with message object
    await export_button(callback.message)

@dp.callback_query(F.data == "latest_suppliers")
async def callback_latest_suppliers(callback: CallbackQuery):
    await callback.answer("Показываю последних поставщиков...")
    
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM suppliers ORDER BY created_at DESC LIMIT 5")
    latest_suppliers = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    if not latest_suppliers:
        await callback.message.answer("Пока нет добавленных поставщиков.")
        return
        
    response = "🆕 **Последние добавленные поставщики:**\n\n"
    
    for supplier in latest_suppliers:
        supplier_id = supplier['id']
        brand = supplier['brand'] or "Бренд не указан"
        created_at = supplier['created_at'].split('.')[0] if '.' in supplier['created_at'] else supplier['created_at']
        
        response += f"📌 ID: {supplier_id} - {brand}\n"
        response += f"   📆 Добавлен: {created_at}\n\n"
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Открыть ID: {s['id']}", callback_data=f"show_supplier_{s['id']}")]
        for s in latest_suppliers
    ])
    
    await callback.message.answer(response, parse_mode="Markdown", reply_markup=markup)

@dp.callback_query(F.data.startswith("show_supplier_"))
async def callback_show_supplier(callback: CallbackQuery):
    await callback.answer()
    supplier_id = int(callback.data.split("_")[2])
    supplier = get_supplier_by_id(supplier_id)
    
    if supplier:
        await show_supplier_card(callback.message, supplier)
    else:
        await callback.message.answer(f"Поставщик с ID {supplier_id} не найден.")

async def show_supplier_card(message, supplier):
    """Show detailed supplier card with QR codes and inline buttons"""
    supplier_id = supplier['id']
    main_category = supplier['main_category'] or ""
    level_category = supplier['level_category'] or ""
    gender_category = supplier['gender_category'] or ""
    brand = supplier['brand'] or ""
    comment = supplier['comment'] or ""
    created_at = supplier['created_at']
    
    # Prepare a nice formatted card
    card_text = f"🆔 **Поставщик #{supplier_id}**\n\n"
    card_text += f"🏷️ **Бренд:** {brand}\n"
    card_text += f"📂 **Категория:** {main_category}\n"
    card_text += f"📊 **Уровень:** {level_category}\n"
    card_text += f"👥 **Пол:** {gender_category}\n"
    card_text += f"📝 **Комментарий:** {comment}\n"
    card_text += f"📅 **Добавлен:** {created_at}\n"
    
    # Create inline buttons for actions
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📱 QR WeChat", callback_data=f"qr_wechat_{supplier_id}"),
            InlineKeyboardButton(text="🌐 QR WEGoo", callback_data=f"qr_wegoo_{supplier_id}")
        ]
    ])
    
    await message.answer(card_text, parse_mode="Markdown", reply_markup=markup)

@dp.callback_query(F.data.startswith("qr_wechat_"))
async def show_wechat_qr(callback: CallbackQuery):
    await callback.answer()
    supplier_id = int(callback.data.split("_")[2])
    supplier = get_supplier_by_id(supplier_id)
    
    if supplier:
        await callback.message.answer_photo(
            photo=supplier['qr_wechat'],
            caption=f"QR WeChat для поставщика ID: {supplier_id}"
        )
    else:
        await callback.message.answer(f"Поставщик с ID {supplier_id} не найден.")

@dp.callback_query(F.data.startswith("qr_wegoo_"))
async def show_wegoo_qr(callback: CallbackQuery):
    await callback.answer()
    supplier_id = int(callback.data.split("_")[2])
    supplier = get_supplier_by_id(supplier_id)
    
    if supplier:
        await callback.message.answer_photo(
            photo=supplier['qr_wegoo'],
            caption=f"QR WEGoo для поставщика ID: {supplier_id}"
        )
    else:
        await callback.message.answer(f"Поставщик с ID {supplier_id} не найден.")

@dp.message(F.text.startswith("#id"))
async def quick_find_supplier(message: Message):
    """Quick supplier search using #id123 format"""
    try:
        # Extract ID from message text (#id123 -> 123)
        supplier_id = int(message.text.replace("#id", "").strip())
        supplier = get_supplier_by_id(supplier_id)
        
        if supplier:
            await show_supplier_card(message, supplier)
        else:
            await message.answer(f"Поставщик с ID {supplier_id} не найден.")
    except ValueError:
        await message.answer("Некорректный формат. Используйте #id123 где 123 - ID поставщика.")

@dp.message(F.text == "Добавить поставщика")
async def add_supplier(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data({
        'edit_mode': False,
        'selected_categories': [],
        'selected_brands': []
    })
    await message.answer(
        "Начинаем добавление нового поставщика.\n\n"
        "Шаг 1/7: Пожалуйста, отправьте QR код для WeChat или нажмите '⏭️ Пропустить'.",
        reply_markup=get_form_progress_keyboard("qr_wechat", include_back=False, include_skip=True)
    )
    await state.set_state(SupplierForm.qr_wechat)

@dp.message(SupplierForm.qr_wechat)
async def process_qr_wechat(message: Message, state: FSMContext):
    if message.text == "⏭️ Пропустить":
        await state.update_data(qr_wechat=None)
        await message.answer(
            "✅ QR WeChat пропущен.\n\n"
            "Шаг 2/7: Теперь отправьте QR код для WEGoo или нажмите '⏭️ Пропустить'.",
            reply_markup=get_form_progress_keyboard("qr_wegoo", include_skip=True)
        )
        await state.set_state(SupplierForm.qr_wegoo)
        return
        
    if not message.photo:
        await message.answer(
            "❌ Ошибка! Пожалуйста, отправьте фотографию QR-кода WeChat или нажмите '⏭️ Пропустить'.",
            reply_markup=get_form_progress_keyboard("qr_wechat", include_back=False, include_skip=True)
        )
        return
        
    qr_wechat_file = message.photo[-1].file_id
    await state.update_data(qr_wechat=qr_wechat_file)
    await message.answer(
        "✅ QR WeChat получен.\n\n"
        "Шаг 2/7: Теперь отправьте QR код для WEGoo или нажмите '⏭️ Пропустить'.",
        reply_markup=get_form_progress_keyboard("qr_wegoo", include_skip=True)
    )
    await state.set_state(SupplierForm.qr_wegoo)

@dp.message(SupplierForm.qr_wegoo)
async def process_qr_wegoo(message: Message, state: FSMContext):
    if message.text == "⏭️ Пропустить":
        await state.update_data(qr_wegoo=None)
        await message.answer(
            "✅ QR WEGoo пропущен.\n\n"
            "Шаг 3/7: Напишите комментарий о поставщике или нажмите '⏭️ Пропустить'.",
            reply_markup=get_form_progress_keyboard("comment", include_skip=True)
        )
        await state.set_state(SupplierForm.comment)
        return
        
    if not message.photo:
        await message.answer(
            "❌ Ошибка! Пожалуйста, отправьте фотографию QR-кода WEGoo или нажмите '⏭️ Пропустить'.",
            reply_markup=get_form_progress_keyboard("qr_wegoo", include_skip=True)
        )
        return
        
    qr_wegoo_file = message.photo[-1].file_id
    await state.update_data(qr_wegoo=qr_wegoo_file)
    await message.answer(
        "✅ QR WEGoo получен.\n\n"
        "Шаг 3/7: Напишите комментарий о поставщике или нажмите '⏭️ Пропустить'.",
        reply_markup=get_form_progress_keyboard("comment", include_skip=True)
    )
    await state.set_state(SupplierForm.comment)

@dp.message(SupplierForm.comment)
async def process_comment(message: Message, state: FSMContext):
    if message.text == "⏭️ Пропустить":
        await state.update_data(comment=None)
        await state.update_data(selected_categories=[])
        await message.answer(
            "✅ Комментарий пропущен.\n\n"
            "Шаг 4/7: Выберите категории продукта (можно выбрать несколько):",
            reply_markup=categories_selection_keyboard([])
        )
        await state.set_state(SupplierForm.selecting_categories)
        return
        
    comment = message.text
    await state.update_data(comment=comment)
    await state.update_data(selected_categories=[])
    await message.answer(
        "✅ Комментарий сохранен.\n\n"
        "Шаг 4/7: Выберите категории продукта (можно выбрать несколько):",
        reply_markup=categories_selection_keyboard([])
    )
    await state.set_state(SupplierForm.selecting_categories)

@dp.message(SupplierForm.selecting_categories)
async def process_category_selection(message: Message, state: FSMContext):
    if message.text == "⏭️ Пропустить":
        await state.update_data(main_category=None)
        markup = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Топ")],
                [KeyboardButton(text="Средний")], 
                [KeyboardButton(text="Улитка")],
                [KeyboardButton(text="⏭️ Пропустить")],
                [KeyboardButton(text="◀️ Назад"), KeyboardButton(text="❌ Отмена")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "✅ Категории пропущены.\n\n"
            "Шаг 5/7: Выберите уровень товара или нажмите '⏭️ Пропустить':", 
            reply_markup=markup
        )
        await state.set_state(SupplierForm.level_category)
        return
        
    if message.text == "✅ Готово":
        data = await state.get_data()
        selected_categories = data.get('selected_categories', [])
        
        if not selected_categories:
            await message.answer("Пожалуйста, выберите хотя бы одну категорию или нажмите '⏭️ Пропустить'.")
            return
            
        main_category = ", ".join(selected_categories)
        await state.update_data(main_category=main_category)
        
        markup = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Топ")],
                [KeyboardButton(text="Средний")], 
                [KeyboardButton(text="Улитка")],
                [KeyboardButton(text="⏭️ Пропустить")],
                [KeyboardButton(text="◀️ Назад"), KeyboardButton(text="❌ Отмена")]
            ],
            resize_keyboard=True
        )
        
        await message.answer(
            "✅ Категории сохранены.\n\n"
            "Шаг 5/7: Выберите уровень товара или нажмите '⏭️ Пропустить':", 
            reply_markup=markup
        )
        await state.set_state(SupplierForm.level_category)
    elif message.text in ["◀️ Назад", "❌ Отмена"]:
        return
    else:
        data = await state.get_data()
        selected_categories = data.get('selected_categories', [])
        
        if message.text.startswith("⬜ "):
            category = message.text[2:]
            if category not in selected_categories:
                selected_categories.append(category)
        elif message.text.startswith("☑️ "):
            category = message.text[2:]
            if category in selected_categories:
                selected_categories.remove(category)
        
        await state.update_data(selected_categories=selected_categories)
        await message.answer(
            f"Выбрано категорий: {len(selected_categories)}\nПродолжайте выбор или нажмите '✅ Готово' когда закончите.",
            reply_markup=categories_selection_keyboard(selected_categories)
        )

@dp.message(SupplierForm.level_category)
async def process_level_category(message: Message, state: FSMContext):
    if message.text == "⏭️ Пропустить":
        await state.update_data(level_category=None)
        markup = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Мужское"), KeyboardButton(text="Женское")],
                [KeyboardButton(text="Унисекс")],
                [KeyboardButton(text="⏭️ Пропустить")],
                [KeyboardButton(text="◀️ Назад"), KeyboardButton(text="❌ Отмена")]
            ],
            resize_keyboard=True
        )
        await message.answer(
            "✅ Уровень пропущен.\n\n"
            "Шаг 6/7: Выберите для кого товар или нажмите '⏭️ Пропустить':", 
            reply_markup=markup
        )
        await state.set_state(SupplierForm.gender_category)
        return
        
    if message.text in ["◀️ Назад", "❌ Отмена"]:
        return
        
    level_category = message.text
    await state.update_data(level_category=level_category)
    
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Мужское"), KeyboardButton(text="Женское")],
            [KeyboardButton(text="Унисекс")],
            [KeyboardButton(text="⏭️ Пропустить")],
            [KeyboardButton(text="◀️ Назад"), KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "✅ Уровень сохранен.\n\n"
        "Шаг 6/7: Выберите для кого товар или нажмите '⏭️ Пропустить':", 
        reply_markup=markup
    )
    await state.set_state(SupplierForm.gender_category)

@dp.message(SupplierForm.gender_category)
async def process_gender_category(message: Message, state: FSMContext):
    if message.text == "⏭️ Пропустить":
        await state.update_data(gender_category=None)
        await state.update_data(brand_category="top_fashion")
        await message.answer(
            "✅ Категория пола пропущена.\n\n"
            "Шаг 7/7: Выберите бренд или нажмите '⏭️ Пропустить':"
        )
        await show_brand_category(message, state, "top_fashion")
        return
        
    if message.text in ["◀️ Назад", "❌ Отмена"]:
        return
        
    gender_category = message.text
    await state.update_data(gender_category=gender_category)
    await state.update_data(brand_category="top_fashion")
    
    await message.answer(
        "✅ Категория пола сохранена.\n\n"
        "Шаг 7/7: Выберите бренд или нажмите '⏭️ Пропустить':"
    )
    await show_brand_category(message, state, "top_fashion")

# Helper function to show brands by category
async def show_brand_category(message, state, category_name):
    brands = load_brands()
    await state.update_data(brand_category=category_name)
    
    # Create category navigation buttons
    categories_row = []
    category_names = {
        "top_fashion": "👑 Топ бренды",
        "premium_fashion": "🌟 Премиум",
        "luxury_shoes": "👠 Обувь",
        "jewelry_watches": "💎 Украшения",
        "niche_brands": "⭐ Нишевые",
        "custom": "🔖 Пользовательские"
    }
    
    # Create category navigation (scrollable with indicators)
    active_categories = list(category_names.keys())
    current_index = active_categories.index(category_name)
    
    # Create navigation with current category highlighted
    nav_row = []
    if current_index > 0:
        nav_row.append(KeyboardButton(text="◀️"))
    nav_row.append(KeyboardButton(text=f"📚 {category_names[category_name]} ({current_index+1}/{len(active_categories)})"))
    if current_index < len(active_categories) - 1:
        nav_row.append(KeyboardButton(text="▶️"))
    
    # Generate keyboard with brands from current category
    keyboard = [nav_row]
    
    # Add brands (3 per row for better UI)
    current_brands = brands[category_name]
    for i in range(0, len(current_brands), 3):
        row = []
        for brand in current_brands[i:i+3]:
            row.append(KeyboardButton(text=brand))
        keyboard.append(row)
    
    # Add search and custom options at the bottom
    keyboard.append([
        KeyboardButton(text="🔍 Поиск"),
        KeyboardButton(text="➕ Добавить новый")
    ])
    
    markup = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    
    await message.answer(
        f"Выберите бренд из категории {category_names[category_name]}, "
        "переключайте категории стрелками или добавьте новый:",
        reply_markup=markup
    )
    await state.set_state(SupplierForm.brand)

@dp.message(SupplierForm.brand)
async def process_brand_selection(message: Message, state: FSMContext):
    """Handle brand selection with multi-selection support and save to database"""
    logging.info(f"Brand selection received: '{message.text}'")
    # Check for special buttons first
    special_buttons = ["◀️ Назад", "❌ Отмена", "🔄 Начать сначала", 
                      "◀️ НАЗАД", "❌ ОТМЕНА", "🔄 НАЧАТЬ СНАЧАЛА"]
    if message.text in special_buttons:
        logging.info(f"Brand selection: detected special button: {message.text}")
        await handle_special_buttons(message, state)
        return
    user_data = await state.get_data()
    current_category = user_data.get("brand_category", "top_fashion")
    selected_brands = user_data.get("selected_brands", [])
    # Handle navigation and control buttons
    if message.text in ["✅ Готово", "✅ ГОТОВО"]:
        # Complete brand selection if at least one brand is selected
        if not selected_brands:
            await message.answer(
                "❌ Пожалуйста, выберите хотя бы один бренд или добавьте новый.",
                reply_markup=brands_selection_keyboard(selected_brands, current_category)
            )
            return
        # Join brands with comma for storage
        brand = ", ".join(selected_brands)
        await state.update_data(brand=brand)
        logging.info(f"Brand selection complete with brands: {brand}")
        # --- SAVE SUPPLIER TO DATABASE ---
        user_data = await state.get_data()
        qr_wechat = user_data.get('qr_wechat')
        qr_wegoo = user_data.get('qr_wegoo')
        comment = user_data.get('comment')
        main_category = user_data.get('main_category')
        level_category = user_data.get('level_category')
        gender_category = user_data.get('gender_category')
        brand = user_data.get('brand')
        supplier_data = {
            'qr_wechat': qr_wechat,
            'qr_wegoo': qr_wegoo,
            'comment': comment,
            'main_category': main_category,
            'level_category': level_category,
            'gender_category': gender_category,
            'brand': brand
        }
        supplier_id = save_supplier_to_db(supplier_data)
        # Confirmation message
        await message.answer(f"✅ Поставщик успешно добавлен в базу!\nID: {supplier_id}\nБренды: {brand}", reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Добавить поставщика")],
                [KeyboardButton(text="🔍 Найти поставщика")]
            ], resize_keyboard=True
        ))
        await state.clear()
        return
    elif message.text == "◀️":
        # Navigate to previous brand category
        categories = ["top_fashion", "premium_fashion", "luxury_shoes", "jewelry_watches", "niche_brands", "custom"]
        current_index = categories.index(current_category)
        if current_index > 0:
            new_category = categories[current_index - 1]
            await state.update_data(brand_category=new_category)
            await message.answer(
                f"Переход к категории брендов: {new_category}",
                reply_markup=brands_selection_keyboard(selected_brands, new_category)
            )
        return
    elif message.text == "▶️":
        # Navigate to next brand category
        categories = ["top_fashion", "premium_fashion", "luxury_shoes", "jewelry_watches", "niche_brands", "custom"]
        current_index = categories.index(current_category)
        if current_index < len(categories) - 1:
            new_category = categories[current_index + 1]
            await state.update_data(brand_category=new_category)
            await message.answer(
                f"Переход к категории брендов: {new_category}",
                reply_markup=brands_selection_keyboard(selected_brands, new_category)
            )
        return
    elif message.text.startswith("📚 "):
        # Ignore category header clicks
        return
    elif message.text in ["🔍 Поиск", "🔍 ПОИСК"]:
        markup = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="↩️ ВЕРНУТЬСЯ К ВЫБОРУ БРЕНДОВ")]
        ], resize_keyboard=True)
        await message.answer(
            "🔍 Введите часть названия бренда для поиска:",
            reply_markup=markup
        )
        await state.update_data(awaiting_brand_search=True)
        return
    elif "вернуться к выбору брендов" in message.text.lower():
        await message.answer(
            "Возвращаемся к выбору брендов:",
            reply_markup=brands_selection_keyboard(selected_brands, current_category)
        )
        await state.update_data(awaiting_brand_search=False)
        await state.update_data(awaiting_custom_brand=False)
        return
    elif message.text in ["➕ Добавить", "➕ ДОБАВИТЬ"]:
        markup = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="↩️ ВЕРНУТЬСЯ К ВЫБОРУ БРЕНДОВ")]
        ], resize_keyboard=True)
        await message.answer(
            "➕ Введите название нового бренда:",
            reply_markup=markup
        )
        await state.update_data(awaiting_custom_brand=True)
        return
    # Handle brand search results
    if user_data.get("awaiting_brand_search"):
        await state.update_data(awaiting_brand_search=False)
        search_query = message.text.lower()
        brands_data = load_brands()
        search_results = []
        for category, brand_list in brands_data.items():
            for brand in brand_list:
                if search_query in brand.lower():
                    search_results.append(brand)
        if search_results:
            rows = []
            rows.append([KeyboardButton(text="📝 Результаты поиска:")])
            for brand in search_results:
                prefix = "☑️ " if brand in selected_brands else "⬜ "
                rows.append([KeyboardButton(text=f"{prefix}{brand}")])
            rows.append([KeyboardButton(text="↩️ Вернуться к выбору брендов")])
            markup = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
            await message.answer(
                f"🔍 Найдено {len(search_results)} брендов по запросу '{message.text}'.\n"
                "Нажмите на бренд, чтобы выбрать/отменить его:",
                reply_markup=markup
            )
        else:
            await message.answer(
                f"🔍 По запросу '{message.text}' ничего не найдено.\n"
                "Попробуйте другой запрос или добавьте новый бренд:",
                reply_markup=brands_selection_keyboard(selected_brands, current_category)
            )
        return
    # Handle adding new brand
    if user_data.get("awaiting_custom_brand"):
        await state.update_data(awaiting_custom_brand=False)
        new_brand = message.text.strip()
        if len(new_brand) < 2:
            await message.answer(
                "❌ Название бренда должно содержать минимум 2 символа. Попробуйте ещё раз:",
                reply_markup=ReplyKeyboardMarkup(keyboard=[
                    [KeyboardButton(text="↩️ Вернуться к выбору брендов")]
                ], resize_keyboard=True)
            )
            await state.update_data(awaiting_custom_brand=True)
            return
        add_custom_brand(new_brand)
        if new_brand not in selected_brands:
            selected_brands.append(new_brand)
            await state.update_data(selected_brands=selected_brands)
        await message.answer(
            f"✅ Бренд '{new_brand}' добавлен и выбран!",
            reply_markup=brands_selection_keyboard(selected_brands, "custom")
        )
        await state.update_data(brand_category="custom")
        return
    # Handle regular brand selection/deselection (when user clicks on a brand)
    if message.text.startswith("⬜ ") or message.text.startswith("☑️ "):
        brand = message.text[2:]
        if message.text.startswith("⬜ "):
            if brand not in selected_brands:
                selected_brands.append(brand)
        else:
            if brand in selected_brands:
                selected_brands.remove(brand)
        await state.update_data(selected_brands=selected_brands)
        await message.answer(
            f"Выбрано брендов: {len(selected_brands)}. Продолжайте выбор или нажмите '✅ Готово' когда закончите.",
            reply_markup=brands_selection_keyboard(selected_brands, current_category)
        )
        return
    # Fallback for unrecognized input
    await message.answer(
        "❓ Не понимаю эту команду. Пожалуйста, используйте кнопки для выбора брендов.",
        reply_markup=brands_selection_keyboard(selected_brands, current_category)
    )

@dp.message(F.text == "Список поставщиков")
async def list_suppliers(message: Message):
    suppliers = get_suppliers_from_db()
    
    if not suppliers:
        await message.answer("Список поставщиков пуст.")
        return
    
    # Create a list of suppliers
    response = "📋 **Список поставщиков:**\n\n"
    
    for i, supplier in enumerate(suppliers, 1):
        # Include supplier ID in the listing
        supplier_id = supplier['id']
        
        # Safely handle potential None values in any field
        main_category = supplier['main_category'] or ""
        level_category = supplier['level_category'] or ""
        gender_category = supplier['gender_category'] or ""
        brand = supplier['brand'] or ""
        comment = supplier['comment'] or ""
        
        # Now escape the strings safely
        main_category_escaped = main_category.replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
        level_category_escaped = level_category.replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
        gender_category_escaped = gender_category.replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
        brand_escaped = brand.replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
        comment_escaped = comment.replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
        
        response += f"{i}\\. *ID: {supplier_id}* \\- *{main_category_escaped} / {level_category_escaped} / {gender_category_escaped}*\n"
        response += f"   🏷️ Бренд: {brand_escaped}\n"
        response += f"   💬 Комментарий: {comment_escaped}\n\n"
    
    await message.answer(response, parse_mode="MarkdownV2")
    
    # Также отправим несколько последних QR-кодов
    if len(suppliers) > 0:
        for i, supplier in enumerate(suppliers[:3]):  # Первые 3 поставщика
            # Handle potential None values for captions too
            main_category = supplier['main_category'] or ""
            level_category = supplier['level_category'] or ""
            gender_category = supplier['gender_category'] or ""
            brand = supplier['brand'] or ""
            
            # WeChat QR
            await message.answer_photo(
                photo=supplier['qr_wechat'],
                caption=f"Поставщик ID: {supplier['id']} - QR WeChat ({main_category} - {level_category} - {gender_category} - {brand})"
            )
            
            # WEGoo QR
            await message.answer_photo(
                photo=supplier['qr_wegoo'],
                caption=f"Поставщик ID: {supplier['id']} - QR WEGoo ({main_category} - {level_category} - {gender_category} - {brand})"
            )

@dp.message(Command('export'))
async def cmd_export(message: Message):
    # Проверяем, является ли пользователь администратором
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет доступа к этой команде.")
        return
    
    # Отправляем сообщение о начале экспорта
    await message.answer("Начинаю экспорт данных в Excel с изображениями...")
    
    # Экспортируем данные в Excel с изображениями
    success = await export_to_excel_with_images(bot)
    
    if success:
        # Отправляем файл администратору
        excel_file = FSInputFile(EXPORT_FILE)
        await message.answer_document(excel_file, caption="Экспорт поставщиков с QR-кодами")
    else:
        await message.answer("Нет данных для экспорта.")

@dp.message(F.text == "Экспорт в Excel")
async def export_button(message: Message):
    # Проверяем, является ли пользователь администратором
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет доступа к этой функции.")
        return
        
    # Отправляем сообщение о начале экспорта
    status_message = await message.answer("Начинаю экспорт данных в Excel с изображениями...")
    
    try:
        # Экспортируем данные в Excel с изображениями
        success = await export_to_excel_with_images(bot)
        
        if success:
            # Проверяем, существует ли файл
            if os.path.exists(EXPORT_FILE) and os.path.getsize(EXPORT_FILE) > 0:
                try:
                    # Отправляем файл администратору
                    excel_file = FSInputFile(EXPORT_FILE)
                    await message.answer_document(excel_file, caption="Экспорт поставщиков с QR-кодами")
                    await status_message.edit_text("✅ Экспорт успешно завершен и файл отправлен!")
                except Exception as e:
                    logging.error(f"Error sending Excel file: {str(e)}")
                    await status_message.edit_text(f"❌ Ошибка при отправке файла: {str(e)}")
            else:
                logging.error(f"Excel file not found or empty at path: {os.path.abspath(EXPORT_FILE)}")
                await status_message.edit_text("❌ Файл Excel не был создан или пуст. Проверьте журналы.")
        else:
            await status_message.edit_text("❌ Ошибка при создании Excel-файла или нет данных для экспорта.")
    except Exception as e:
        logging.error(f"Unexpected error in export_button: {str(e)}")
        await status_message.edit_text(f"❌ Произошла непредвиденная ошибка: {str(e)}")

@dp.message(Command('help'))
async def cmd_help(message: Message):
    """Display bot help information"""
    help_text = "🤖 **Справка по боту поставщиков**\n\n"
    
    help_text += "**Основные команды:**\n"
    help_text += "• /start - Начало работы с ботом\n"
    help_text += "• /help - Вывод этой справки\n"
    help_text += "• /find ID - Поиск поставщика по ID\n"
    help_text += "• #idXXX - Быстрый поиск (например #id123)\n\n"
    
    help_text += "**Кнопки управления:**\n"
    help_text += "• Добавить поставщика - Начать процесс добавления\n"
    help_text += "• 🔍 Найти поставщика - Поиск по ID\n\n"
    
    if message.from_user.id in ADMIN_IDS:
        help_text += "**Команды администратора:**\n"
        help_text += "• 📊 Статистика - Общая статистика поставщиков\n"
        help_text += "• Экспорт в Excel - Выгрузка данных в Excel\n"
        help_text += "• /export - Альтернативная команда для экспорта\n"

    await message.answer(help_text, parse_mode="Markdown")

@dp.message(Command('today'))
async def cmd_today_activity(message: Message):
    """Show today's activity summary"""
    # Get today's date
    today = datetime.now().date()
    today_start = datetime.combine(today, datetime.min.time())
    
    # Connect to database
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Count today's new suppliers
    cursor.execute(
        "SELECT COUNT(*) FROM suppliers WHERE date(created_at) = date(?)",
        (today_start.strftime('%Y-%m-%d'),)
    )
    today_count = cursor.fetchone()[0]
    
    # Get most active categories today
    cursor.execute(
        "SELECT main_category, COUNT(*) as count FROM suppliers WHERE date(created_at) = date(?) GROUP BY main_category ORDER BY count DESC LIMIT 3",
        (today_start.strftime('%Y-%m-%d'),)
    )
    top_categories = cursor.fetchall()
    
    conn.close()
    
    # Format the message
    response = f"📅 **Активность за {today.strftime('%d.%m.%Y')}**\n\n"
    
    if today_count > 0:
        response += f"• Добавлено поставщиков: **{today_count}**\n\n"
        
        if top_categories:
            response += "**Популярные категории:**\n"
            for category in top_categories:
                cat_name = category['main_category'] or "Без категории"
                response += f"• {cat_name}: {category['count']} поставщика(ов)\n"
    else:
        response += "Сегодня еще не было добавлено ни одного поставщика."
    
    await message.answer(response, parse_mode="Markdown")

@dp.message(F.text == "❌ Отмена")
async def cancel_form(message: Message, state: FSMContext):
    """Handle form cancellation from any step"""
    current_state = await state.get_state()
    if current_state is None:
        return
        
    await state.clear()
    await message.answer(
        "✅ Процесс добавления поставщика отменен. Все введенные данные удалены.",
        reply_markup=ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="Добавить поставщика")],
            [KeyboardButton(text="🔍 Найти поставщика")]
        ], resize_keyboard=True)
    )

@dp.message(F.text == "◀️ Назад")
async def back_step(message: Message, state: FSMContext):
    """Handle going back to previous step"""
    current_state = await state.get_state()
    if current_state is None:
        return
        
    # Define the step sequence
    form_sequence = [
        "qr_wechat", "qr_wegoo", "comment", 
        "selecting_categories", "level_category", "gender_category", "brand"
    ]
    
    # Find current position in sequence
    try:
        current_index = form_sequence.index(current_state.split(':')[1])
    except (ValueError, IndexError):
        await message.answer("Невозможно вернуться назад из текущего состояния.")
        return
    
    # Go back one step if possible
    if current_index > 0:
        prev_state = form_sequence[current_index - 1]
        
        # Set flag that we're in edit mode
        await state.update_data(edit_mode=True)
        
        # Go to previous state
        await state.set_state(getattr(SupplierForm, prev_state))
        
        # Show appropriate prompt for the previous step
        if prev_state == "qr_wechat":
            await message.answer(
                "🔄 Вернулись к шагу загрузки QR WeChat. Пожалуйста, отправьте изображение QR-кода:",
                reply_markup=get_form_progress_keyboard("qr_wechat", include_back=False)
            )
        elif prev_state == "qr_wegoo":
            await message.answer(
                "🔄 Вернулись к шагу загрузки QR WEGoo. Пожалуйста, отправьте изображение QR-кода:",
                reply_markup=get_form_progress_keyboard("qr_wegoo")
            )
        elif prev_state == "comment":
            await message.answer(
                "🔄 Вернулись к шагу добавления комментария. Пожалуйста, введите комментарий:",
                reply_markup=get_form_progress_keyboard("comment")
            )
        elif prev_state == "selecting_categories":
            data = await state.get_data()
            selected_categories = data.get('selected_categories', [])
            await message.answer(
                "🔄 Вернулись к выбору категорий. Выберите категории продукта:",
                reply_markup=categories_selection_keyboard(selected_categories)
            )
        elif prev_state == "level_category":
            markup = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Топ")],
                    [KeyboardButton(text="Средний")], 
                    [KeyboardButton(text="Улитка")],
                    [KeyboardButton(text="◀️ Назад"), KeyboardButton(text="❌ Отмена")]
                ],
                resize_keyboard=True
            )
            await message.answer(
                "🔄 Вернулись к выбору уровня товара. Пожалуйста, выберите уровень:",
                reply_markup=markup
            )
        elif prev_state == "gender_category":
            markup = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="Мужское"), KeyboardButton(text="Женское")],
                    [KeyboardButton(text="Унисекс")],
                    [KeyboardButton(text="◀️ Назад"), KeyboardButton(text="❌ Отмена")]
                ],
                resize_keyboard=True
            )
            await message.answer(
                "🔄 Вернулись к выбору пола. Пожалуйста, выберите для кого товар:",
                reply_markup=markup
            )
    else:
        await message.answer(
            "Это первый шаг, невозможно вернуться назад. Вы можете отменить процесс кнопкой '❌ Отмена'."
        )

@dp.message(F.text == "⏭️ Пропустить")
async def skip_step(message: Message, state: FSMContext):
    """Handle skipping optional fields"""
    current_state = await state.get_state()
    if current_state is None:
        return
        
    # Only comment can be skipped for now
    if current_state == "SupplierForm:comment":
        await state.update_data(comment="")
        await state.update_data(selected_categories=[])
        await message.answer("Комментарий пропущен. Выберите категории продукта:", 
                             reply_markup=categories_selection_keyboard([]))
        await state.set_state(SupplierForm.selecting_categories)
    else:
        await message.answer("Этот шаг нельзя пропустить.")

async def main():
    # Инициализируем базу данных
    init_db()
    
    try:
        # Delete webhook before starting polling
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("Webhook deleted successfully")
        
        # Start polling with error handling
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Error starting bot: {str(e)}")
        # Try to reconnect after delay
        await asyncio.sleep(5)
        await main()  # Retry connection

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")











