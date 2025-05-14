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
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from aiogram.client.session.aiohttp import AiohttpSession
from datetime import datetime

# Configuration
API_TOKEN = '7840291905:AAEm7jpF8FQw9FxV-7EkF7kPVlHIZtyQhIU'
# Замените на ID вашего аккаунта в Telegram
ADMIN_ID = 6547570784  # Замените на реальный ID администратора
logging.basicConfig(level=logging.INFO)

# Set up data storage
DB_FILE = 'suppliers.db'
EXPORT_FILE = 'suppliers_export.xlsx'
QR_FOLDER = 'qr_codes'

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
    suppliers = get_suppliers_from_db()
    if not suppliers:
        return False
    
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
    
    # Сохраняем сначала без изображений в Excel
    df.to_excel(EXPORT_FILE, index=False)
    
    # Теперь добавляем изображения с помощью openpyxl
    workbook = openpyxl.load_workbook(EXPORT_FILE)
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
    
    # Обрабатываем каждого поставщика
    for i, supplier in enumerate(suppliers, start=2):  # start=2 потому что первая строка - заголовки
        # Скачиваем QR-коды
        wechat_path = os.path.join(temp_folder, f"wechat_{supplier['id']}.jpg")
        wegoo_path = os.path.join(temp_folder, f"wegoo_{supplier['id']}.jpg")
        
        await download_telegram_file(bot, supplier['qr_wechat'], wechat_path)
        await download_telegram_file(bot, supplier['qr_wegoo'], wegoo_path)
        
        # Добавляем изображения в Excel
        if os.path.exists(wechat_path):
            img_wechat = XLImage(wechat_path)
            # Масштабируем изображение
            img_wechat.width = 100
            img_wechat.height = 100
            sheet.row_dimensions[i].height = 80
            sheet.add_image(img_wechat, f'B{i}')
        
        if os.path.exists(wegoo_path):
            img_wegoo = XLImage(wegoo_path)
            # Масштабируем изображение
            img_wegoo.width = 100
            img_wegoo.height = 100
            sheet.row_dimensions[i].height = 80
            sheet.add_image(img_wegoo, f'C{i}')
    
    # Сохраняем файл
    workbook.save(EXPORT_FILE)
    
    return True

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
    selecting_categories = State()  # New state for multiple category selection

@dp.message(Command('start'))
async def cmd_start(message: Message):
    markup = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Добавить поставщика")],
        [KeyboardButton(text="Список поставщиков")]
    ], resize_keyboard=True)
    
    # Для администратора показываем дополнительные команды
    if message.from_user.id == ADMIN_ID:
        markup.keyboard.append([KeyboardButton(text="Экспорт в Excel")])
    
    await message.answer("Добро пожаловать! Выберите действие.", reply_markup=markup)

@dp.message(Command('export'))
async def cmd_export(message: Message):
    # Проверяем, является ли пользователь администратором
    if message.from_user.id != ADMIN_ID:
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
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет доступа к этой функции.")
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

@dp.message(F.text == "Добавить поставщика")
async def add_supplier(message: Message, state: FSMContext):
    await message.answer("Пожалуйста, отправьте QR код для WeChat.")
    await state.set_state(SupplierForm.qr_wechat)

@dp.message(SupplierForm.qr_wechat, F.photo)
async def process_qr_wechat(message: Message, state: FSMContext):
    qr_wechat_file = message.photo[-1].file_id
    await state.update_data(qr_wechat=qr_wechat_file)
    await message.answer("Теперь отправьте QR код для WEGoo.")
    await state.set_state(SupplierForm.qr_wegoo)

@dp.message(SupplierForm.qr_wegoo, F.photo)
async def process_qr_wegoo(message: Message, state: FSMContext):
    qr_wegoo_file = message.photo[-1].file_id
    await state.update_data(qr_wegoo=qr_wegoo_file)
    await message.answer("Напишите комментарий о поставщике.")
    await state.set_state(SupplierForm.comment)

@dp.message(SupplierForm.comment)
async def process_comment(message: Message, state: FSMContext):
    comment = message.text
    await state.update_data(comment=comment)
    await state.update_data(selected_categories=[])  # Initialize empty list for selected categories
    await message.answer("Выберите категории продукта (можно выбрать несколько):", reply_markup=categories_selection_keyboard([]))
    await state.set_state(SupplierForm.selecting_categories)

def categories_selection_keyboard(selected_categories):
    categories = ["Обувь", "Одежда", "Аксессуары", "Сумки", "Украшения"]
    
    # Create rows with buttons (1 category per row for clarity)
    rows = []
    for category in categories:
        # Show checkbox status for each category
        prefix = "☑️ " if category in selected_categories else "⬜ "
        rows.append([KeyboardButton(text=f"{prefix}{category}")])
    
    # Add Done button at the bottom
    rows.append([KeyboardButton(text="✅ Готово")])
    
    markup = ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
    return markup

@dp.message(SupplierForm.selecting_categories)
async def process_category_selection(message: Message, state: FSMContext):
    if message.text == "✅ Готово":
        # User is done selecting categories
        data = await state.get_data()
        selected_categories = data.get('selected_categories', [])
        
        if not selected_categories:
            await message.answer("Пожалуйста, выберите хотя бы одну категорию.")
            return
            
        # Join selected categories with comma for storage
        main_category = ", ".join(selected_categories)
        await state.update_data(main_category=main_category)
        
        # Move to next step - level selection
        markup = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Топ")],
                [KeyboardButton(text="Средний")], 
                [KeyboardButton(text="Улитка")]
            ],
            resize_keyboard=True
        )
        
        await message.answer("Выберите уровень товара:", reply_markup=markup)
        await state.set_state(SupplierForm.level_category)
    else:
        # Process category selection/deselection
        data = await state.get_data()
        selected_categories = data.get('selected_categories', [])
        
        # Extract category name from button text (remove checkbox)
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
    level_category = message.text
    await state.update_data(level_category=level_category)
    
    # После выбора уровня предлагаем выбрать пол
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Мужское"), KeyboardButton(text="Женское")],
            [KeyboardButton(text="Унисекс")]
        ],
        resize_keyboard=True
    )
    
    await message.answer("Выберите для кого товар:", reply_markup=markup)
    await state.set_state(SupplierForm.gender_category)

@dp.message(SupplierForm.gender_category)
async def process_gender_category(message: Message, state: FSMContext):
    gender_category = message.text
    await state.update_data(gender_category=gender_category)
    
    # Просим ввести бренд
    await message.answer("Напишите название бренда:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(SupplierForm.brand)

@dp.message(SupplierForm.brand)
async def process_brand(message: Message, state: FSMContext):
    brand = message.text
    await state.update_data(brand=brand)

    user_data = await state.get_data()
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
    
    # Сохраняем QR-коды локально
    wechat_path = os.path.join(QR_FOLDER, f"wechat_{supplier_id}.jpg")
    wegoo_path = os.path.join(QR_FOLDER, f"wegoo_{supplier_id}.jpg")
    
    await download_telegram_file(bot, qr_wechat, wechat_path)
    await download_telegram_file(bot, qr_wegoo, wegoo_path)

    # Отправляем фото QR-кодов и информацию о поставщике
    await message.answer_photo(
        photo=qr_wechat,
        caption="QR код WeChat"
    )
    
    await message.answer_photo(
        photo=qr_wegoo,
        caption="QR код WEGoo"
    )

    # Escape special characters for MarkdownV2
    comment_escaped = comment.replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
    main_category_escaped = main_category.replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
    level_category_escaped = level_category.replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
    gender_category_escaped = gender_category.replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
    brand_escaped = brand.replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')

    post_text = f"📦 **Новый поставщик добавлен:**\n\n" \
                f"💬 Комментарий: {comment_escaped}\n" \
                f"📂 Категория: {main_category_escaped} / {level_category_escaped} / {gender_category_escaped}\n" \
                f"🏷️ Бренд: {brand_escaped}\n\n" \
                f"✅ Данные сохранены в базу"

    # Возвращаем основную клавиатуру
    markup = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Добавить поставщика")],
        [KeyboardButton(text="Список поставщиков")]
    ], resize_keyboard=True)
    
    if message.from_user.id == ADMIN_ID:
        markup.keyboard.append([KeyboardButton(text="Экспорт в Excel")])

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
        main_category_escaped = supplier['main_category'].replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
        level_category_escaped = supplier['level_category'].replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
        gender_category_escaped = supplier['gender_category'].replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
        brand_escaped = supplier['brand'].replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
        comment_escaped = supplier['comment'].replace('.', '\\.').replace('-', '\\-').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('~', '\\~').replace('`', '\\`').replace('>', '\\>').replace('#', '\\#').replace('+', '\\+').replace('=', '\\=').replace('|', '\\|').replace('{', '\\{').replace('}', '\\}').replace('!', '\\!')
        
        response += f"{i}\\. *{main_category_escaped} / {level_category_escaped} / {gender_category_escaped}*\n"
        response += f"   🏷️ Бренд: {brand_escaped}\n"
        response += f"   💬 Комментарий: {comment_escaped}\n\n"
    
    await message.answer(response, parse_mode="MarkdownV2")
    
    # Также отправим несколько последних QR-кодов
    if len(suppliers) > 0:
        for i, supplier in enumerate(suppliers[:3]):  # Первые 3 поставщика
            # WeChat QR
            await message.answer_photo(
                photo=supplier['qr_wechat'],
                caption=f"Поставщик {i+1}: QR WeChat ({supplier['main_category']} - {supplier['level_category']} - {supplier['gender_category']} - {supplier['brand']})"
            )
            
            # WEGoo QR
            await message.answer_photo(
                photo=supplier['qr_wegoo'],
                caption=f"Поставщик {i+1}: QR WEGoo ({supplier['main_category']} - {supplier['level_category']} - {supplier['gender_category']} - {supplier['brand']})"
            )

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
