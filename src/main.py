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

# Configuration
API_TOKEN = '7840291905:AAEm7jpF8FQw9FxV-7EkF7kPVlHIZtyQhIU'
# Замените на ID вашего аккаунта в Telegram
ADMIN_IDS = [6547570784, 1835816946]  # Список ID администраторов
logging.basicConfig(level=logging.INFO)

# Set up data storage
DB_FILE = 'suppliers.db'
EXPORT_FILE = 'suppliers_export.xlsx'
QR_FOLDER = 'qr_codes'
BRANDS_FILE = 'popular_brands.json'

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
        qr_wechat TEXT,
        qr_wegoo TEXT,
        comment TEXT,
        main_category TEXT,
        level_category TEXT,
        gender_category TEXT,
        brand TEXT,
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

# Initialize bot and dispatcher
session = AiohttpSession()
bot = Bot(token=API_TOKEN, session=session)
dp = Dispatcher()

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
    selecting_brands = State()  # New state for multi-brand selection
    search_id = State()
    edit_mode = State()

# Form step names for progress indication
FORM_STEPS = {
    "qr_wechat": "1. QR WeChat",
    "qr_wegoo": "2. QR WEGoo",
    "comment": "3. Комментарий",
    "selecting_categories": "4. Категории",
    "level_category": "5. Уровень",
    "gender_category": "6. Пол",
    "selecting_brands": "7. Бренды"
}

# Special keyboard for navigation and cancelation
def get_nav_keyboard(include_back=True, include_cancel=True, include_skip=False, include_restart=False):
    buttons = []
    
    # Create the row based on which buttons to include
    row = []
    if include_back:
        row.append(KeyboardButton(text="◀️ НАЗАД"))
    if include_cancel:
        row.append(KeyboardButton(text="❌ ОТМЕНА"))
    if include_skip:
        row.append(KeyboardButton(text="⏭️ ПРОПУСТИТЬ"))
    if include_restart:
        row.append(KeyboardButton(text="🔄 НАЧАТЬ СНАЧАЛА"))
    
    if row:
        buttons.append(row)
    
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, one_time_keyboard=False)

# Get a keyboard with progress indication
def get_form_progress_keyboard(current_state, include_back=True, include_cancel=True, include_skip=False, include_restart=False):
    # Create the base navigation keyboard
    keyboard = get_nav_keyboard(include_back, include_cancel, include_skip, include_restart)
    
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
    # Define categories with emojis for better visibility
    categories_with_emojis = [
        ("Обувь", "👞"),
        ("Одежда", "👕"),
        ("Аксессуары", "👓"),
        ("Сумки", "👜"),
        ("Украшения", "💍")
    ]
    
    # Create rows with buttons (1 category per row for clarity)
    rows = []
    
    # Add header
    rows.append([KeyboardButton(text="📋 ВЫБЕРИТЕ КАТЕГОРИИ")])
    
    for category, emoji in categories_with_emojis:
        # Show checkbox status for each category with emoji
        if category in selected_categories:
            # Selected - use a more visible checkmark and emoji
            prefix = f"✅ {emoji} "
        else:
            # Not selected - use a more visible empty box and emoji
            prefix = f"⬜ {emoji} "
        rows.append([KeyboardButton(text=f"{prefix}{category.upper()}")])
    
    # Add selection status
    rows.append([KeyboardButton(text=f"📊 ВЫБРАНО: {len(selected_categories)}/{len(categories_with_emojis)}")])
    
    # Add navigation buttons
    nav_row = []
    nav_row.append(KeyboardButton(text="◀️ НАЗАД"))
    nav_row.append(KeyboardButton(text="✅ ГОТОВО"))
    nav_row.append(KeyboardButton(text="❌ ОТМЕНА"))
    rows.append(nav_row)
    
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

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

@dp.message(F.text == "Добавить поставщика")
async def add_supplier(message: Message, state: FSMContext):
    await state.clear()
    # Initialize empty form data
    await state.update_data({
        'edit_mode': False,
        'selected_categories': [],
        'selected_brands': []
    })
    await message.answer(
        "Начинаем добавление нового поставщика.\n\n"
        "Шаг 1/7: Пожалуйста, отправьте QR код для WeChat.",
        reply_markup=get_form_progress_keyboard("qr_wechat", include_back=False)
    )
    await state.set_state(SupplierForm.qr_wechat)

@dp.message(SupplierForm.qr_wechat, F.photo)
async def process_qr_wechat(message: Message, state: FSMContext):
    qr_wechat_file = message.photo[-1].file_id
    await state.update_data(qr_wechat=qr_wechat_file)
    await message.answer(
        "✅ QR WeChat получен.\n\n"
        "Шаг 2/7: Теперь отправьте QR код для WEGoo.",
        reply_markup=get_form_progress_keyboard("qr_wegoo")
    )
    await state.set_state(SupplierForm.qr_wegoo)

@dp.message(SupplierForm.qr_wechat)
async def invalid_qr_wechat(message: Message):
    """Handle non-photo input for WeChat QR"""
    # Ignore clicks on the progress indicator
    if message.text and message.text.startswith("Шаг"):
        return
        
    if message.text == "🔄 Начать сначала":
        # Special button that restarts the whole form
        await message.answer("Начинаем заново!")
        await add_supplier(message, message.bot.fsm_storage)
        return
        
    await message.answer(
        "❌ Ошибка! Пожалуйста, отправьте фотографию QR-кода WeChat.\n"
        "Если хотите отменить добавление, нажмите '❌ Отмена'.\n"
        "Чтобы начать весь процесс заново, нажмите '🔄 Начать сначала'.",
        reply_markup=get_form_progress_keyboard("qr_wechat", include_back=False, include_restart=True)
    )

@dp.message(SupplierForm.qr_wegoo, F.photo)
async def process_qr_wegoo(message: Message, state: FSMContext):
    qr_wegoo_file = message.photo[-1].file_id
    await state.update_data(qr_wegoo=qr_wegoo_file)
    
    # Create keyboard without skip button for comments
    comment_keyboard = get_form_progress_keyboard("comment", include_skip=False)
    
    await message.answer(
        "✅ QR WEGoo получен.\n\n"
        "Шаг 3/7: Напишите комментарий о поставщике.",
        reply_markup=comment_keyboard
    )
    await state.set_state(SupplierForm.comment)

@dp.message(SupplierForm.qr_wegoo)
async def invalid_qr_wegoo(message: Message):
    """Handle non-photo input for WEGoo QR"""
    # Ignore clicks on the progress indicator
    if message.text and message.text.startswith("Шаг"):
        return
        
    if message.text == "🔄 Начать сначала":
        # Special button that restarts the whole form
        await message.answer("Начинаем заново!")
        await add_supplier(message, message.bot.fsm_storage)
        return
        
    await message.answer(
        "❌ Ошибка! Пожалуйста, отправьте фотографию QR-кода WEGoo.\n"
        "Вы можете вернуться на предыдущий шаг с кнопкой '◀️ Назад', отменить добавление с '❌ Отмена',\n"
        "или начать весь процесс заново с кнопкой '🔄 Начать сначала'.",
        reply_markup=get_form_progress_keyboard("qr_wegoo", include_restart=True)
    )

@dp.message()
async def handle_special_buttons(message: Message, state: FSMContext):
    """Global handler for special button texts that should take precedence"""
    # Check both uppercase and regular case versions
    back_buttons = ["◀️ Назад", "◀️ НАЗАД"]
    skip_buttons = ["⏭️ Пропустить", "⏭️ ПРОПУСТИТЬ"]
    cancel_buttons = ["❌ Отмена", "❌ ОТМЕНА"]
    restart_buttons = ["🔄 Начать сначала", "🔄 НАЧАТЬ СНАЧАЛА"]
    
    if message.text in back_buttons:
        # Call the back_step handler directly
        logging.info(f"Global handler: processing back button '{message.text}'")
        await back_step(message, state)
        return True
    elif message.text in skip_buttons:
        # Call the skip_step handler directly
        logging.info(f"Global handler: processing skip button '{message.text}'")
        await skip_step(message, state)
        return True
    elif message.text in cancel_buttons:
        # Call the cancel_form handler directly
        logging.info(f"Global handler: processing cancel button '{message.text}'")
        await cancel_form(message, state)
        return True
    elif message.text in restart_buttons:
        # Call the restart_form handler directly
        logging.info(f"Global handler: processing restart button '{message.text}'")
        await restart_form(message, state)
        return True
    
    # If not a special button, continue with regular handlers
    return False

@dp.message(SupplierForm.comment)
async def process_comment(message: Message, state: FSMContext):
    """Handle comments for the supplier"""
    # Debug logging
    logging.info(f"Comment received: '{message.text}'")
    
    # Check for other special buttons
    if message.text in ["◀️ Назад", "❌ Отмена", "🔄 Начать сначала", 
                      "◀️ НАЗАД", "❌ ОТМЕНА", "🔄 НАЧАТЬ СНАЧАЛА"]:
        logging.info(f"Special button detected in comment section: {message.text}")
        await handle_special_buttons(message, state)
        return
    
    # Check for step indicators 
    if message.text and message.text.startswith("Шаг"):
        logging.info(f"Ignoring step indicator in comment: {message.text}")
        return
    
    # Handle regular comment text
    if message.text:
        logging.info(f"Processing regular comment: {message.text}")
        comment = message.text
        
        # Save to state
        await state.update_data(comment=comment)
        await state.update_data(selected_categories=[])
        
        # Confirm and move to category selection
        logging.info(f"Moving to category selection after saving comment: {comment}")
        
        # Create category selection keyboard
        keyboard = categories_selection_keyboard([])
        
        # Send confirmation and show category selection
        await message.answer(
            f"✅ Комментарий сохранен: «{comment}»\n\n"
            "Шаг 4/7: Выберите категории продукта (можно выбрать несколько):",
            reply_markup=keyboard
        )
        
        # Set the state to category selection
        await state.set_state(SupplierForm.selecting_categories)
        logging.info("State set to selecting_categories")
    else:
        # If no text provided, show error message
        await message.answer(
            "❌ Пожалуйста, введите комментарий о поставщике.",
            reply_markup=get_form_progress_keyboard("comment", include_skip=False)
        )

@dp.message(SupplierForm.selecting_categories)
async def process_category_selection(message: Message, state: FSMContext):
    """Handle category selection with improved detection and logging"""
    # Debug logging
    logging.info(f"Category selection: received text: '{message.text}'")
    
    if message.text is None:
        logging.warning("Empty message in category selection")
        return
    
    # Check for special buttons first (using exact matching)
    special_buttons = ["◀️ Назад", "❌ Отмена", "🔄 Начать сначала", 
                       "◀️ НАЗАД", "❌ ОТМЕНА", "🔄 НАЧАТЬ СНАЧАЛА"]
    
    if message.text in special_buttons:
        logging.info(f"Category selection: detected special button: {message.text}")
        await handle_special_buttons(message, state)
        return
    
    # Handle the Done button - case sensitive check
    if message.text in ["✅ Готово", "✅ ГОТОВО"]:
        # User is done selecting categories
        data = await state.get_data()
        selected_categories = data.get('selected_categories', [])
        logging.info(f"Categories completed with: {selected_categories}")
        
        if not selected_categories:
            await message.answer(
                "Пожалуйста, выберите хотя бы одну категорию.",
                reply_markup=categories_selection_keyboard(selected_categories)
            )
            return
            
        # Join selected categories with comma for storage
        main_category = ", ".join(selected_categories)
        await state.update_data(main_category=main_category)
        
        # Move to next step - level selection
        markup = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="ТОП")],
                [KeyboardButton(text="СРЕДНИЙ")], 
                [KeyboardButton(text="УЛИТКА")],
                [KeyboardButton(text="◀️ НАЗАД"), KeyboardButton(text="❌ ОТМЕНА")]
            ],
            resize_keyboard=True
        )
        
        await message.answer(
            f"✅ Выбранные категории: {main_category}\n\n"
            "Шаг 5/7: Выберите уровень товара:", 
            reply_markup=markup
        )
        await state.set_state(SupplierForm.level_category)
        return
    
    # Ignore service/information messages in keyboard
    if (message.text.startswith("📋") or 
        message.text.startswith("📊") or 
        message.text.startswith("Шаг")):
        logging.info(f"Ignoring service message: {message.text}")
        return
    
    # Get current selected categories
    data = await state.get_data()
    selected_categories = data.get('selected_categories', [])
    logging.info(f"Current selected categories: {selected_categories}")
    
    # Define the categories
    categories_with_emojis = [
        ("Обувь", "👞"),
        ("Одежда", "👕"),
        ("Аксессуары", "👓"),
        ("Сумки", "👜"),
        ("Украшения", "💍")
    ]
    
    categories = [item[0] for item in categories_with_emojis]
    
    # Clean up message text
    clean_text = message.text
    for prefix in ["✅ ", "⬜ ", "👞 ", "👕 ", "👓 ", "👜 ", "💍 "]:
        if prefix in clean_text:
            clean_text = clean_text.replace(prefix, "")
    
    clean_text = clean_text.strip().upper()
    
    # Match with known categories
    detected_category = None
    for cat in categories:
        if cat.upper() in clean_text:
            detected_category = cat
            logging.info(f"Detected category: {detected_category} from cleaned text: {clean_text}")
            break
    
    if detected_category:
        # Toggle the category selection
        if detected_category in selected_categories:
            selected_categories.remove(detected_category)
            logging.info(f"Removed category: {detected_category}")
            action_text = "❌ Удалено"
        else:
            selected_categories.append(detected_category)
            logging.info(f"Added category: {detected_category}")
            action_text = "✅ Добавлено"
            
        # Update state with selected categories
        await state.update_data(selected_categories=selected_categories)
        
        # Immediately show confirmation and update keyboard
        await message.answer(
            f"{action_text}: {detected_category}\n"
            f"Выбрано категорий: {len(selected_categories)}/{len(categories)}\n"
            f"Продолжайте выбор или нажмите '✅ ГОТОВО' когда закончите.",
            reply_markup=categories_selection_keyboard(selected_categories)
        )
    else:
        # No category detected - show help message
        logging.warning(f"No category detected in message: '{message.text}'")
        
        # Don't re-show the keyboard for messages we don't understand
        await message.answer(
            f"❓ Команда '{message.text}' не распознана.\n\n"
            "Пожалуйста, выберите категорию, нажав на одну из кнопок с названиями категорий.\n"
            "После выбора всех нужных категорий нажмите '✅ ГОТОВО'.",
            reply_markup=categories_selection_keyboard(selected_categories)
        )

@dp.message(SupplierForm.level_category)
async def process_level_category(message: Message, state: FSMContext):
    # First check if this is a special command that's already handled
    if await handle_special_buttons(message, state):
        return
    
    # Convert input to uppercase for consistency
    level_category = message.text
    logging.info(f"Level category selected: {level_category}")
    await state.update_data(level_category=level_category)
    
    # After level selection, move to gender selection
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="МУЖСКОЕ"), KeyboardButton(text="ЖЕНСКОЕ")],
            [KeyboardButton(text="УНИСЕКС")],
            [KeyboardButton(text="◀️ НАЗАД"), KeyboardButton(text="❌ ОТМЕНА")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"✅ Уровень сохранен: {level_category}\n\n"
        "Шаг 6/7: Выберите для кого товар:", 
        reply_markup=markup
    )
    await state.set_state(SupplierForm.gender_category)

@dp.message(SupplierForm.gender_category)
async def process_gender_category(message: Message, state: FSMContext):
    # First check if this is a special command that's already handled
    if await handle_special_buttons(message, state):
        return
    
    gender_category = message.text
    logging.info(f"Gender category selected: {gender_category}")
    await state.update_data(gender_category=gender_category)
    
    # Initialize empty brand selection
    await state.update_data(selected_brands=[])
    await state.update_data(brand_category="top_fashion")
    
    # Show progress and move to brand selection
    await message.answer(
        f"✅ Категория пола сохранена: {gender_category}\n\n"
        "Шаг 7/7: Выберите бренды товара (можно выбрать несколько):",
        reply_markup=brands_selection_keyboard([], "top_fashion")
    )
    await state.set_state(SupplierForm.selecting_brands)

@dp.message(SupplierForm.selecting_brands)
async def process_brand_selection(message: Message, state: FSMContext):
    """Handle brand selection with multi-selection support"""
    # Debug logging 
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
        
        # Process the final supplier data
        await process_final_supplier_data(message, state)
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
        # Handle brand search
        markup = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="↩️ ВЕРНУТЬСЯ К ВЫБОРУ БРЕНДОВ")]
        ], resize_keyboard=True)
        await message.answer(
            "🔍 Введите часть названия бренда для поиска:",
            reply_markup=markup
        )
        await state.update_data(awaiting_brand_search=True)
        return
        
    # Check for both uppercase and lowercase "return to brands" buttons
    elif "вернуться к выбору брендов" in message.text.lower():
        # Return to brand selection
        await message.answer(
            "Возвращаемся к выбору брендов:",
            reply_markup=brands_selection_keyboard(selected_brands, current_category)
        )
        await state.update_data(awaiting_brand_search=False)
        await state.update_data(awaiting_custom_brand=False)
        return
        
    elif message.text in ["➕ Добавить", "➕ ДОБАВИТЬ"]:
        # Add custom brand
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
        
        # Search across all brand categories
        brands_data = load_brands()
        search_results = []
        
        for category, brand_list in brands_data.items():
            for brand in brand_list:
                if search_query in brand.lower():
                    search_results.append(brand)
        
        if search_results:
            # Found results - display them with checkboxes
            rows = []
            rows.append([KeyboardButton(text="📝 Результаты поиска:")])
            
            for brand in search_results:
                prefix = "☑️ " if brand in selected_brands else "⬜ "
                rows.append([KeyboardButton(text=f"{prefix}{brand}")])
                
            # Add navigation button
            rows.append([KeyboardButton(text="↩️ Вернуться к выбору брендов")])
            markup = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
            
            await message.answer(
                f"🔍 Найдено {len(search_results)} брендов по запросу '{message.text}'.\n"
                "Нажмите на бренд, чтобы выбрать/отменить его:",
                reply_markup=markup
            )
        else:
            # No results
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
        
        # Validate brand name
        if len(new_brand) < 2:
            await message.answer(
                "❌ Название бренда должно содержать минимум 2 символа. Попробуйте ещё раз:",
                reply_markup=ReplyKeyboardMarkup(keyboard=[
                    [KeyboardButton(text="↩️ Вернуться к выбору брендов")]
                ], resize_keyboard=True)
            )
            await state.update_data(awaiting_custom_brand=True)
            return
            
        # Add to custom brands and selected brands
        add_custom_brand(new_brand)
        if new_brand not in selected_brands:
            selected_brands.append(new_brand)
            await state.update_data(selected_brands=selected_brands)
        
        # Show confirmation and return to selection
        await message.answer(
            f"✅ Бренд '{new_brand}' добавлен и выбран!",
            reply_markup=brands_selection_keyboard(selected_brands, "custom")
        )
        await state.update_data(brand_category="custom")
        return
    
    # Handle regular brand selection/deselection (when user clicks on a brand)
    if message.text.startswith("⬜ ") or message.text.startswith("☑️ "):
        # Extract brand name from the button text
        brand = message.text[2:]  # Remove the checkbox prefix
        
        if message.text.startswith("⬜ "):
            # Add to selected brands if not already there
            if brand not in selected_brands:
                selected_brands.append(brand)
        else:
            # Remove from selected brands
            if brand in selected_brands:
                selected_brands.remove(brand)
        
        # Update state with new selection
        await state.update_data(selected_brands=selected_brands)
        
        # Show updated keyboard
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

async def process_final_supplier_data(message: Message, state: FSMContext):
    """Process final supplier data after brand selection"""
    user_data = await state.get_data()
    
    # Get all the collected data
    qr_wechat = user_data['qr_wechat']
    qr_wegoo = user_data['qr_wegoo']
    comment = user_data['comment']
    main_category = user_data['main_category']
    level_category = user_data['level_category']
    gender_category = user_data['gender_category']
    brand = user_data['brand']
    
    # Save supplier data to database
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
    
    # Save QR codes locally
    wechat_path = os.path.join(QR_FOLDER, f"wechat_{supplier_id}.jpg")
    wegoo_path = os.path.join(QR_FOLDER, f"wegoo_{supplier_id}.jpg")
    
    await download_telegram_file(bot, qr_wechat, wechat_path)
    await download_telegram_file(bot, qr_wegoo, wegoo_path)
    
    # Show confirmation with QR codes
    await message.answer_photo(
        photo=qr_wechat,
        caption="QR код WeChat"
    )
    
    await message.answer_photo(
        photo=qr_wegoo,
        caption="QR код WEGoo"
    )
    
    # Escape special characters for MarkdownV2
    comment_escaped = (comment or "").replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
    main_category_escaped = main_category.replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
    level_category_escaped = level_category.replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
    gender_category_escaped = gender_category.replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
    brand_escaped = brand.replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
    
    post_text = f"📦 **Новый поставщик добавлен:**\n\n" \
                f"💬 Комментарий: {comment_escaped}\n" \
                f"📂 Категория: {main_category_escaped} / {level_category_escaped} / {gender_category_escaped}\n" \
                f"🏷️ Бренд: {brand_escaped}\n\n" \
                f"✅ Данные сохранены в базу"
    
    # Return to main menu
    markup = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Добавить поставщика")],
        [KeyboardButton(text="🔍 Найти поставщика")]
    ], resize_keyboard=True)
    
    if message.from_user.id in ADMIN_IDS:
        markup.keyboard.append([
            KeyboardButton(text="📊 Статистика"),
            KeyboardButton(text="Экспорт в Excel")
        ])
    
    await message.answer(post_text, parse_mode="MarkdownV2", reply_markup=markup)
    await state.clear()

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

@dp.message(F.text.in_({"❌ Отмена", "❌ ОТМЕНА"}))
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

@dp.message(F.text.in_({"◀️ Назад", "◀️ НАЗАД"}))
async def back_step(message: Message, state: FSMContext):
    """Handle going back to previous step"""
    current_state = await state.get_state()
    logging.info(f"Back button pressed. Current state: {current_state}")
    
    if current_state is None:
        logging.warning("No active state found when Back button was pressed")
        return
        
    # Define the step sequence
    form_sequence = [
        "qr_wechat", "qr_wegoo", "comment", 
        "selecting_categories", "level_category", "gender_category", "selecting_brands"
    ]
    
    # Find current position in sequence
    try:
        current_state_name = current_state.split(':')[1]
        logging.info(f"Current state parsed: {current_state_name}")
        current_index = form_sequence.index(current_state_name)
        logging.info(f"Current index in sequence: {current_index}")
    except (ValueError, IndexError) as e:
        logging.error(f"Error parsing state: {e}")
        await message.answer("Невозможно вернуться назад из текущего состояния.")
        return
    
    # Go back one step if possible
    if current_index > 0:
        prev_state = form_sequence[current_index - 1]
        logging.info(f"Going back to previous state: {prev_state}")
        
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
                reply_markup=get_form_progress_keyboard("comment", include_skip=True)
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
                    [KeyboardButton(text="ТОП")],
                    [KeyboardButton(text="СРЕДНИЙ")], 
                    [KeyboardButton(text="УЛИТКА")],
                    [KeyboardButton(text="◀️ НАЗАД"), KeyboardButton(text="❌ ОТМЕНА")]
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
                    [KeyboardButton(text="◀️ НАЗАД"), KeyboardButton(text="❌ ОТМЕНА")]
                ],
                resize_keyboard=True
            )
            await message.answer(
                "🔄 Вернулись к выбору пола. Пожалуйста, выберите для кого товар:",
                reply_markup=markup
            )
    else:
        logging.info("Already at first step, can't go back further")
        await message.answer(
            "Это первый шаг, невозможно вернуться назад. Вы можете отменить процесс кнопкой '❌ ОТМЕНА'."
        )

@dp.message(F.text.in_({"🔄 Начать сначала", "🔄 НАЧАТЬ СНАЧАЛА"}))
async def restart_form(message: Message, state: FSMContext):
    """Handle form restart from any step"""
    current_state = await state.get_state()
    if current_state is None:
        return
        
    await state.clear()
    await message.answer("🔄 Начинаем процесс добавления поставщика заново.")
    
    # Call the add_supplier function to start over
    await add_supplier(message, state)

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

@dp.message(F.text.in_({"⏭️ Пропустить", "⏭️ ПРОПУСТИТЬ"}))
async def skip_step(message: Message, state: FSMContext):
    """Handle skipping optional fields"""
    current_state = await state.get_state()
    logging.info(f"Global skip button pressed. Current state: {current_state}")
    
    if current_state is None:
        logging.warning("No active state found when Skip button was pressed")
        return
    
    # Handle skipping based on current state
    if current_state == "SupplierForm:comment":
        logging.info("Skipping comment step via global handler")
        # Set empty comment
        await state.update_data(comment="")
        
        # Initialize empty category selection
        await state.update_data(selected_categories=[])
        
        # Show category selection screen
        await message.answer(
            "✅ Комментарий пропущен.\n\n"
            "Шаг 4/7: Выберите категории продукта (можно выбрать несколько):", 
            reply_markup=categories_selection_keyboard([])
        )
        await state.set_state(SupplierForm.selecting_categories)
    else:
        logging.info(f"Skip not allowed for state: {current_state}")
        await message.answer("Этот шаг нельзя пропустить.")

async def main():
    # Инициализируем базу данных
    init_db()
    
    # Delete webhook before starting polling
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Webhook deleted successfully")
    
    # Start polling
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
