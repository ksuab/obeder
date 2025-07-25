import csv
import os
import re
import json
from datetime import datetime, time
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен вашего бота
API_TOKEN = bottoken

# Пути к файлам CSV и JSON
USERS_CSV = 'users_data.csv'
PLACES_CSV = 'places.csv'
USERS_TO_MATCH_JSON = 'users_to_match.json'

# Список офисов
OFFICES = ["Аврора", "Сити: Нева", "Сити: Око", "Красная роза", "Лотте", "Бенуа"]

# Глобальные переменные для хранения данных из CSV
PLACES = []
PLACES_BY_OFFICE = {}

# Варианты времени для выбора
TIME_OPTIONS = [
    "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", 
    "14:00", "14:30", "15:00", "15:30", "16:00", "16:30",
]

# Обновленные размеры компании
COMPANY_SIZES = ["1", "2", "3-5", "6+"]

# Определение длительности обеда
LUNCH_DURATIONS = ["30", "45", "60", "90"]

# Определение состояний FSM для основного меню и анкеты
class Form(StatesGroup):
    office = State()
    select_time_start = State()
    select_time_end = State()
    add_more_slots = State()
    lunch_duration = State()
    favorite_places = State()
    disliked_places = State()
    company_size = State()
    confirmation = State()

# Состояния для главного меню и записи на обед
class MainMenu(StatesGroup):
    main = State()
    lunch_booking = State()
    lunch_preference = State()
    lunch_time_start = State()
    lunch_time_end = State()
    lunch_place = State()
    lunch_company_size = State()
    lunch_confirmation = State()
    edit_profile = State()
    edit_field = State()

# Загрузка мест для обеда из CSV-файла
def load_places():
    global PLACES, PLACES_BY_OFFICE
    
    if not os.path.exists(PLACES_CSV):
        logging.error(f"Файл с местами {PLACES_CSV} не найден!")
        return []
    
    all_places = []
    places_by_office = {}
    
    try:
        with open(PLACES_CSV, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                all_places.append(row)
                
                # Группируем места по офисам
                office = row.get('office_name', 'Unknown')
                if office not in places_by_office:
                    places_by_office[office] = []
                places_by_office[office].append(row)
    except Exception as e:
        logging.error(f"Ошибка при чтении файла мест: {e}")
        return []
    
    # Создаем список только с названиями для использования в выборе мест
    place_names = [place['name'] for place in all_places]
    logging.info(f"Загружено {len(all_places)} мест из файла: {', '.join(place_names)}")
    
    PLACES = place_names
    PLACES_BY_OFFICE = places_by_office
    
    return place_names

# Функция для проверки существования файла CSV и его создания при необходимости
def ensure_csv_exists():
    if not os.path.exists(USERS_CSV):
        with open(USERS_CSV, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['user_id', 'username', 'office', 'time_slots', 'lunch_duration', 
                            'favorite_places', 'disliked_places', 'company_size', 'last_updated'])

# Функция для проверки существования JSON файла для матчинга
def ensure_json_exists():
    if not os.path.exists(USERS_TO_MATCH_JSON):
        with open(USERS_TO_MATCH_JSON, 'w', encoding='utf-8') as file:
            json.dump([], file, ensure_ascii=False, indent=2)

# Функция для сохранения/обновления данных пользователя в CSV
def save_user_data(user_id, username, data):
    ensure_csv_exists()
    
    # Преобразование данных в строки для CSV
    time_slots_str = ';'.join([f"{start}-{end}" for start, end in data['time_slots']])
    favorite_places_str = ';'.join(data['favorite_places'])
    disliked_places_str = ';'.join(data['disliked_places'])
    company_size_str = ';'.join(data['company_size'])
    
    # Чтение существующих данных
    rows = []
    user_exists = False
    if os.path.exists(USERS_CSV):
        with open(USERS_CSV, 'r', newline='', encoding='utf-8') as file:
            reader = csv.reader(file)
            header = next(reader)  # Сохраняем заголовок
            for row in reader:
                if row and row[0] == str(user_id):
                    # Обновляем существующую запись
                    row = [str(user_id), username, data['office'], time_slots_str, data['lunch_duration'],
                          favorite_places_str, disliked_places_str, company_size_str,
                          datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")]
                    user_exists = True
                rows.append(row)
    
    # Если пользователь новый, добавляем его
    if not user_exists:
        new_row = [str(user_id), username, data['office'], time_slots_str, data['lunch_duration'],
                  favorite_places_str, disliked_places_str, company_size_str,
                  datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")]
        rows.append(new_row)
    
    # Записываем все данные обратно в файл
    with open(USERS_CSV, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['user_id', 'username', 'office', 'time_slots', 'lunch_duration', 
                        'favorite_places', 'disliked_places', 'company_size', 'last_updated'])
        writer.writerows(rows)

# Функция для получения данных пользователя из CSV
def get_user_data(user_id):
    if not os.path.exists(USERS_CSV):
        return None
    
    with open(USERS_CSV, 'r', newline='', encoding='utf-8') as file:
        reader = csv.reader(file)
        header = next(reader)  # Пропускаем заголовок
        for row in reader:
            if row and row[0] == str(user_id):
                # Преобразуем строки обратно в списки
                time_slots = [slot.split('-') for slot in row[3].split(';')] if row[3] else []
                favorite_places = row[5].split(';') if row[5] else []
                disliked_places = row[6].split(';') if row[6] else []
                company_size = row[7].split(';') if row[7] else []
                
                return {
                    'office': row[2],
                    'time_slots': time_slots,
                    'lunch_duration': row[4],
                    'favorite_places': favorite_places,
                    'disliked_places': disliked_places,
                    'company_size': company_size,
                    'last_updated': row[8]
                }
    
    return None

# Функция для обновления данных пользователя в файле users_to_match.json
def update_user_to_match(username, parameters):
    ensure_json_exists()
    
    users = []
    user_exists = False
    
    # Читаем существующие данные
    if os.path.exists(USERS_TO_MATCH_JSON):
        with open(USERS_TO_MATCH_JSON, 'r', encoding='utf-8') as file:
            try:
                users = json.load(file)
            except json.JSONDecodeError:
                users = []
    
    # Ищем пользователя и обновляем его данные
    for user in users:
        if user.get('login') == username:
            user['parameters'] = parameters
            user_exists = True
            break
    
    # Если пользователя нет, добавляем его
    if not user_exists:
        users.append({
            "login": username,
            "parameters": parameters
        })
    
    # Записываем обновленные данные
    with open(USERS_TO_MATCH_JSON, 'w', encoding='utf-8') as file:
        json.dump(users, file, ensure_ascii=False, indent=2)

# Получение списка мест для конкретного офиса
def get_places_for_office(office):
    # Если места не сгруппированы по офисам или офис не найден, возвращаем все места
    if office not in PLACES_BY_OFFICE:
        return PLACES
    
    # Возвращаем только места для указанного офиса
    return [place['name'] for place in PLACES_BY_OFFICE[office]]

# Проверка валидности временного интервала
def is_valid_time_interval(start_time, end_time):
    try:
        start_h, start_m = map(int, start_time.split(':'))
        end_h, end_m = map(int, end_time.split(':'))
        
        start = time(hour=start_h, minute=start_m)
        end = time(hour=end_h, minute=end_m)
        
        return start < end
    except:
        return False

# Конвертация данных пользователя в формат для users_to_match.json
def convert_to_match_format(data, username):
    return {
        "office": data.get('office', ''),
        "time_slots": data.get('time_slots', []),
        "duration_min": int(data.get('lunch_duration', 30)),
        "favourite_places": data.get('favorite_places', []),
        "non_desirable_places": data.get('disliked_places', []),
        "team_size_lst": data.get('company_size', [])
    }

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Хендлер для команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    
    # Проверяем, заполнял ли пользователь анкету ранее
    user_data = get_user_data(user_id)
    
    if user_data:
        # Если пользователь уже заполнял анкету, показываем главное меню
        await show_main_menu(message, user_data)
        await state.set_state(MainMenu.main)
    else:
        # Если пользователь новый, начинаем заполнение анкеты
        await start_profile_creation(message, state)

# Функция для отображения главного меню
async def show_main_menu(message, user_data=None):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Записаться на обед сегодня", callback_data="menu:book_lunch")],
        [InlineKeyboardButton(text="Изменить настройки профиля", callback_data="menu:edit_profile")],
        [InlineKeyboardButton(text="Показать мой профиль", callback_data="menu:show_profile")]
    ])
    
    await message.answer("Главное меню:", reply_markup=keyboard)

# Функция для начала создания профиля
async def start_profile_creation(message, state):
    # Очищаем предыдущее состояние
    await state.clear()
    
    # Создаем инлайн-клавиатуру для выбора офиса
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=office, callback_data=f"office:{office}")] for office in OFFICES
    ])
    
    await message.answer("Давайте заполним ваш профиль для подбора компании на обед. Для начала, выберите ваш офис:", reply_markup=keyboard)
    await state.set_state(Form.office)

# Обработчик для главного меню
@dp.callback_query(F.data.startswith("menu:"), MainMenu.main)
async def process_main_menu(callback_query: CallbackQuery, state: FSMContext):
    action = callback_query.data.split(':')[1]
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username or f"user{user_id}"
    user_data = get_user_data(user_id)
    
    if action == "book_lunch":
        # Начинаем процесс записи на обед
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="По моим настройкам из анкеты", callback_data="lunch:by_profile")],
            [InlineKeyboardButton(text="Изменить настройки для сегодня", callback_data="lunch:custom")]
        ])
        
        await callback_query.message.edit_text(
            "Как вы хотите найти компанию на обед?",
            reply_markup=keyboard
        )
        
        await state.set_state(MainMenu.lunch_preference)
    
    elif action == "edit_profile":
        # Начинаем процесс редактирования профиля
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Офис", callback_data="edit:office")],
            [InlineKeyboardButton(text="Временные слоты", callback_data="edit:time_slots")],
            [InlineKeyboardButton(text="Длительность обеда", callback_data="edit:duration")],
            [InlineKeyboardButton(text="Любимые места", callback_data="edit:favorite_places")],
            [InlineKeyboardButton(text="Нелюбимые места", callback_data="edit:disliked_places")],
            [InlineKeyboardButton(text="Размер компании", callback_data="edit:company_size")],
            [InlineKeyboardButton(text="Вернуться в главное меню", callback_data="edit:back")]
        ])
        
        await callback_query.message.edit_text(
            "Выберите, какие настройки вы хотите изменить:",
            reply_markup=keyboard
        )
        
        await state.set_state(MainMenu.edit_field)
    
    elif action == "show_profile":
        # Показываем текущий профиль пользователя
        if user_data:
            time_slots_formatted = ", ".join([f"{start}-{end}" for start, end in user_data.get('time_slots', [])])
            
            profile_text = (
                "Ваш текущий профиль:\n"
                f"- Офис: {user_data.get('office', 'Не выбран')}\n"
                f"- Слоты времени: {time_slots_formatted}\n"
                f"- Длительность обеда: {user_data.get('lunch_duration', 'Не выбрана')} минут\n"
                f"- Любимые места: {', '.join(user_data.get('favorite_places', ['Не выбраны']))}\n"
                f"- Нелюбимые места: {', '.join(user_data.get('disliked_places', ['Не выбраны']))}\n"
                f"- Размер компании: {', '.join(user_data.get('company_size', ['Не выбран']))}\n"
                f"- Последнее обновление: {user_data.get('last_updated', '')}"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Вернуться в главное меню", callback_data="menu:back")]
            ])
            
            await callback_query.message.edit_text(
                profile_text,
                reply_markup=keyboard
            )
        else:
            await callback_query.message.edit_text(
                "У вас еще нет профиля. Давайте создадим его!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Создать профиль", callback_data="menu:create_profile")]
                ])
            )
    
    elif action == "back" or action == "create_profile":
        # Возвращаемся в главное меню или начинаем создание профиля
        if action == "create_profile":
            await start_profile_creation(callback_query.message, state)
        else:
            await show_main_menu(callback_query.message, user_data)
            await state.set_state(MainMenu.main)
    
    await callback_query.answer()

# Обработчик для выбора предпочтений обеда
@dp.callback_query(F.data.startswith("lunch:"), MainMenu.lunch_preference)
async def process_lunch_preference(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username or f"user{user_id}"
    user_data = get_user_data(user_id)
    
    if choice == "by_profile":
        # Пользователь хочет использовать свои настройки из профиля
        if user_data:
            # Конвертируем данные в формат для матчинга и сохраняем
            match_params = convert_to_match_format(user_data, username)
            update_user_to_match(username, match_params)
            
            await callback_query.message.edit_text(
                "Отлично! Мы используем ваши настройки из профиля для подбора компании на обед сегодня.\n"
                "Когда найдется подходящая компания, мы вас оповестим.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Вернуться в главное меню", callback_data="menu:back")]
                ])
            )
            
            await state.set_state(MainMenu.main)
        else:
            await callback_query.message.edit_text(
                "У вас еще нет профиля. Давайте сначала заполним его.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Заполнить профиль", callback_data="menu:create_profile")]
                ])
            )
    
    elif choice == "custom":
        # Пользователь хочет изменить настройки для сегодняшнего обеда
        # Начинаем с выбора времени
        await state.update_data(custom_lunch_data={})
        
        # Создаем клавиатуру для выбора времени начала
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=time_opt, callback_data=f"lunch_time_start:{time_opt}")] for time_opt in TIME_OPTIONS
        ])
        
        await callback_query.message.edit_text(
            "Выберите начало временного слота для сегодняшнего обеда:",
            reply_markup=keyboard
        )
        
        await state.set_state(MainMenu.lunch_time_start)
    
    await callback_query.answer()

# Обработчик выбора времени начала для обеда
@dp.callback_query(F.data.startswith("lunch_time_start:"), MainMenu.lunch_time_start)
async def process_lunch_time_start(callback_query: CallbackQuery, state: FSMContext):
    start_time = callback_query.data.split(':')[1]
    
    # Сохраняем выбранное время начала
    await state.update_data(lunch_start_time=start_time)
    
    # Создаем клавиатуру для выбора времени конца
    # Показываем только времена, которые идут после выбранного начала
    filtered_times = [t for t in TIME_OPTIONS if t > start_time]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=time_opt, callback_data=f"lunch_time_end:{time_opt}")] for time_opt in filtered_times
    ])
    
    await callback_query.message.edit_text(
        f"Выбрано начало: {start_time}\n\nТеперь выберите конец временного слота для обеда:",
        reply_markup=keyboard
    )
    
    # Переходим к следующему состоянию
    await state.set_state(MainMenu.lunch_time_end)
    
    await callback_query.answer()

# Обработчик выбора времени окончания для обеда
@dp.callback_query(F.data.startswith("lunch_time_end:"), MainMenu.lunch_time_end)
async def process_lunch_time_end(callback_query: CallbackQuery, state: FSMContext):
    end_time = callback_query.data.split(':')[1]
    
    # Получаем данные из состояния
    data = await state.get_data()
    start_time = data.get('lunch_start_time')
    
    # Проверяем валидность интервала
    if is_valid_time_interval(start_time, end_time):
        # Обновляем данные
        custom_lunch_data = data.get('custom_lunch_data', {})
        custom_lunch_data['time_slots'] = [[start_time, end_time]]
        await state.update_data(custom_lunch_data=custom_lunch_data)
        
        # Получаем данные пользователя
        user_id = callback_query.from_user.id
        user_data = get_user_data(user_id)
        office = user_data.get('office') if user_data else None
        
        if office:
            # Если есть офис, предлагаем выбор места
            places_for_office = get_places_for_office(office)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=place, callback_data=f"lunch_place:{place}")] for place in places_for_office
            ] + [[InlineKeyboardButton(text="Пропустить (использовать настройки профиля)", callback_data="lunch_place:skip")]])
            
            await callback_query.message.edit_text(
                f"Выбран временной слот: {start_time} - {end_time}\n\nВыберите место для обеда сегодня:",
                reply_markup=keyboard
            )
            
            await state.set_state(MainMenu.lunch_place)
        else:
            # Если офиса нет, пропускаем выбор места и переходим к размеру компании
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=size, callback_data=f"lunch_company:{size}")] for size in COMPANY_SIZES
            ] + [[InlineKeyboardButton(text="Пропустить (использовать настройки профиля)", callback_data="lunch_company:skip")]])
            
            await callback_query.message.edit_text(
                f"Выбран временной слот: {start_time} - {end_time}\n\nВыберите предпочтительный размер компании для обеда сегодня:",
                reply_markup=keyboard
            )
            
            await state.set_state(MainMenu.lunch_company_size)
    else:
        # Если интервал невалидный, возвращаемся к выбору начала
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=time_opt, callback_data=f"lunch_time_start:{time_opt}")] for time_opt in TIME_OPTIONS
        ])
        
        await callback_query.message.edit_text(
            "Ошибка: время окончания должно быть позже времени начала.\nПожалуйста, выберите начало временного слота:",
            reply_markup=keyboard
        )
        
        await state.set_state(MainMenu.lunch_time_start)
    
    await callback_query.answer()

# Обработчик выбора места для обеда
@dp.callback_query(F.data.startswith("lunch_place:"), MainMenu.lunch_place)
async def process_lunch_place(callback_query: CallbackQuery, state: FSMContext):
    place = callback_query.data.split(':')[1]
    
    # Получаем текущие данные
    data = await state.get_data()
    custom_lunch_data = data.get('custom_lunch_data', {})
    
    if place != "skip":
        # Сохраняем выбранное место
        custom_lunch_data['favourite_places'] = [place]
    
    await state.update_data(custom_lunch_data=custom_lunch_data)
    
    # Переходим к выбору размера компании
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=size, callback_data=f"lunch_company:{size}")] for size in COMPANY_SIZES
    ] + [[InlineKeyboardButton(text="Пропустить (использовать настройки профиля)", callback_data="lunch_company:skip")]])
    
    await callback_query.message.edit_text(
        "Выберите предпочтительный размер компании для обеда сегодня:",
        reply_markup=keyboard
    )
    
    await state.set_state(MainMenu.lunch_company_size)
    
    await callback_query.answer()

# Обработчик выбора размера компании для обеда
@dp.callback_query(F.data.startswith("lunch_company:"), MainMenu.lunch_company_size)
async def process_lunch_company(callback_query: CallbackQuery, state: FSMContext):
    company_size = callback_query.data.split(':')[1]
    
    # Получаем текущие данные
    data = await state.get_data()
    custom_lunch_data = data.get('custom_lunch_data', {})
    
    if company_size != "skip":
        # Сохраняем выбранный размер компании
        custom_lunch_data['team_size_lst'] = [company_size]
    
    await state.update_data(custom_lunch_data=custom_lunch_data)
    
    # Формируем сводку и переходим к подтверждению
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username or f"user{user_id}"
    user_data = get_user_data(user_id)
    
    # Подготавливаем параметры для записи
    if user_data:
        # Берем базовые параметры из профиля
        match_params = convert_to_match_format(user_data, username)
        
        # Обновляем их кастомными данными на сегодня
        if 'time_slots' in custom_lunch_data:
            match_params['time_slots'] = custom_lunch_data['time_slots']
        if 'favourite_places' in custom_lunch_data:
            match_params['favourite_places'] = custom_lunch_data['favourite_places']
        if 'team_size_lst' in custom_lunch_data:
            match_params['team_size_lst'] = custom_lunch_data['team_size_lst']
        
        # Формируем текст с параметрами
        time_slots_formatted = ", ".join([f"{start}-{end}" for start, end in match_params['time_slots']])
        
        summary = (
            "Параметры для подбора обеда сегодня:\n"
            f"- Офис: {match_params.get('office', 'Не выбран')}\n"
            f"- Слот времени: {time_slots_formatted}\n"
            f"- Длительность обеда: {match_params.get('duration_min', 'Не выбрана')} минут\n"
            f"- Предпочитаемые места: {', '.join(match_params.get('favourite_places', ['Не выбраны']))}\n"
            f"- Нежелательные места: {', '.join(match_params.get('non_desirable_places', ['Не указаны']))}\n"
            f"- Размер компании: {', '.join(match_params.get('team_size_lst', ['Не выбран']))}"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подтвердить", callback_data="lunch_confirm:yes")],
            [InlineKeyboardButton(text="Отменить и вернуться в меню", callback_data="lunch_confirm:no")]
        ])
        
        await callback_query.message.edit_text(
            f"{summary}\n\nПодтвердите запись на обед с этими параметрами:",
            reply_markup=keyboard
        )
        
        await state.set_state(MainMenu.lunch_confirmation)
    
    await callback_query.answer()

# # Обработчик подтверждения записи на обед
@dp.callback_query(F.data.startswith("lunch_confirm:"), MainMenu.lunch_confirmation)
async def process_lunch_confirmation(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    
    if choice == "yes":
        # Получаем все необходимые данные
        data = await state.get_data()
        custom_lunch_data = data.get('custom_lunch_data', {})
        
        user_id = callback_query.from_user.id
        username = callback_query.from_user.username or f"user{user_id}"
        user_data = get_user_data(user_id)
        
        if user_data:
            # Берем базовые параметры из профиля
            match_params = convert_to_match_format(user_data, username)
            
            # Обновляем их кастомными данными на сегодня
            if 'time_slots' in custom_lunch_data:
                match_params['time_slots'] = custom_lunch_data['time_slots']
            if 'favourite_places' in custom_lunch_data:
                match_params['favourite_places'] = custom_lunch_data['favourite_places']
            if 'team_size_lst' in custom_lunch_data:
                match_params['team_size_lst'] = custom_lunch_data['team_size_lst']
            
            # Сохраняем данные для матчинга
            update_user_to_match(username, match_params)
            
            await callback_query.message.edit_text(
                "Вы успешно записаны на обед! Когда найдется подходящая компания, мы вас оповестим.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Вернуться в главное меню", callback_data="menu:back")]
                ])
            )
        else:
            await callback_query.message.edit_text(
                "Ошибка: не удалось найти ваш профиль. Пожалуйста, заполните анкету сначала.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Заполнить анкету", callback_data="menu:create_profile")]
                ])
            )
    else:
        # Отмена и возврат в главное меню
        await callback_query.message.edit_text(
            "Запись на обед отменена.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Вернуться в главное меню", callback_data="menu:back")]
            ])
        )
    
    await state.set_state(MainMenu.main)
    await callback_query.answer()

# Обработчик выбора поля для редактирования профиля
@dp.callback_query(F.data.startswith("edit:"), MainMenu.edit_field)
async def process_edit_field(callback_query: CallbackQuery, state: FSMContext):
    field = callback_query.data.split(':')[1]
    
    if field == "office":
        # Редактирование офиса
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=office, callback_data=f"office:{office}")] for office in OFFICES
        ])
        
        await callback_query.message.edit_text(
            "Выберите ваш офис:",
            reply_markup=keyboard
        )
        
        await state.set_state(Form.office)
    
    elif field == "time_slots":
        # Редактирование временных слотов
        # Сначала очищаем предыдущие слоты
        await state.update_data(time_slots=[])
        
        # Создаем клавиатуру для выбора времени начала
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=time_opt, callback_data=f"time_start:{time_opt}")] for time_opt in TIME_OPTIONS
        ])
        
        await callback_query.message.edit_text(
            "Выберите начало временного слота для обеда:",
            reply_markup=keyboard
        )
        
        await state.set_state(Form.select_time_start)
    
    elif field == "duration":
        # Редактирование длительности обеда
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{duration} минут", callback_data=f"duration:{duration}")] for duration in LUNCH_DURATIONS
        ])
        
        await callback_query.message.edit_text(
            "Выберите предпочтительную длительность обеда:",
            reply_markup=keyboard
        )
        
        await state.set_state(Form.lunch_duration)
    
    elif field == "favorite_places":
        # Редактирование любимых мест
        user_id = callback_query.from_user.id
        user_data = get_user_data(user_id)
        office = user_data.get('office') if user_data else None
        favorite_places = user_data.get('favorite_places', []) if user_data else []
        
        if office:
            places_for_office = get_places_for_office(office)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"{'✅ ' if place in favorite_places else ''}{place}", callback_data=f"fav_place:{place}")] for place in places_for_office
            ] + [[InlineKeyboardButton(text="Готово", callback_data="fav_place:done")]])
            
            await callback_query.message.edit_text(
                "Выберите места, которые вам нравятся:",
                reply_markup=keyboard
            )
            
            await state.set_state(Form.favorite_places)
        else:
            await callback_query.message.edit_text(
                "Сначала выберите офис.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Выбрать офис", callback_data="edit:office")]
                ])
            )
    
    elif field == "disliked_places":
        # Редактирование нелюбимых мест
        user_id = callback_query.from_user.id
        user_data = get_user_data(user_id)
        office = user_data.get('office') if user_data else None
        disliked_places = user_data.get('disliked_places', []) if user_data else []
        
        if office:
            places_for_office = get_places_for_office(office)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"{'✅ ' if place in disliked_places else ''}{place}", callback_data=f"dis_place:{place}")] for place in places_for_office
            ] + [[InlineKeyboardButton(text="Готово", callback_data="dis_place:done")]])
            
            await callback_query.message.edit_text(
                "Выберите места, которые вам не нравятся:",
                reply_markup=keyboard
            )
            
            await state.set_state(Form.disliked_places)
        else:
            await callback_query.message.edit_text(
                "Сначала выберите офис.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Выбрать офис", callback_data="edit:office")]
                ])
            )
    
    elif field == "company_size":
        # Редактирование размера компании
        user_id = callback_query.from_user.id
        user_data = get_user_data(user_id)
        company_size = user_data.get('company_size', []) if user_data else []
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{'✅ ' if size in company_size else ''}{size}", callback_data=f"size:{size}")] for size in COMPANY_SIZES
        ] + [[InlineKeyboardButton(text="Готово", callback_data="size:done")]])
        
        await callback_query.message.edit_text(
            "Выберите предпочтительный размер компании для обеда:",
            reply_markup=keyboard
        )
        
        await state.set_state(Form.company_size)
    
    elif field == "back":
        # Возврат в главное меню
        user_id = callback_query.from_user.id
        user_data = get_user_data(user_id)
        
        await show_main_menu(callback_query.message, user_data)
        await state.set_state(MainMenu.main)
    
    await callback_query.answer()

# Обработчик выбора офиса
@dp.callback_query(F.data.startswith("office:"), Form.office)
async def process_office(callback_query: CallbackQuery, state: FSMContext):
    office = callback_query.data.split(':')[1]
    
    # Сохраняем выбор офиса
    await state.update_data(office=office)
    
    # Проверяем, редактирование это или создание нового профиля
    current_state = await state.get_state()
    
    if current_state == Form.office.state:
        # Это первоначальное создание профиля
        # Инициализируем пустой список слотов
        await state.update_data(time_slots=[])
        
        # Создаем клавиатуру для выбора времени начала
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=time_opt, callback_data=f"time_start:{time_opt}")] for time_opt in TIME_OPTIONS
        ])
        
        await callback_query.message.edit_text(
            f"Отлично! Вы выбрали офис: {office}\n\nТеперь выберите начало временного слота для обеда:",
            reply_markup=keyboard
        )
        
        # Переходим к следующему состоянию
        await state.set_state(Form.select_time_start)
    else:
        # Это редактирование профиля
        # Сохраняем изменения и возвращаемся в меню редактирования
        user_id = callback_query.from_user.id
        username = callback_query.from_user.username or f"user{user_id}"
        user_data = get_user_data(user_id) or {}
        
        # Обновляем офис
        user_data['office'] = office
        
        # Сохраняем изменения
        save_user_data(user_id, username, user_data)
        
        # Показываем сообщение об успешном обновлении
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Продолжить редактирование", callback_data="menu:edit_profile")],
            [InlineKeyboardButton(text="Вернуться в главное меню", callback_data="menu:back")]
        ])
        
        await callback_query.message.edit_text(
            f"Офис успешно обновлен на: {office}",
            reply_markup=keyboard
        )
        
        await state.set_state(MainMenu.main)
    
    await callback_query.answer()

# Обработчик выбора времени начала слота
@dp.callback_query(F.data.startswith("time_start:"), Form.select_time_start)
async def process_time_start(callback_query: CallbackQuery, state: FSMContext):
    start_time = callback_query.data.split(':')[1]
    
    # Сохраняем выбранное время начала
    await state.update_data(current_start_time=start_time)
    
    # Создаем клавиатуру для выбора времени конца
    # Показываем только времена, которые идут после выбранного начала
    filtered_times = [t for t in TIME_OPTIONS if t > start_time]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=time_opt, callback_data=f"time_end:{time_opt}")] for time_opt in filtered_times
    ])
    
    await callback_query.message.edit_text(
        f"Выбрано начало: {start_time}\n\nТеперь выберите конец временного слота:",
        reply_markup=keyboard
    )
    
    # Переходим к следующему состоянию
    await state.set_state(Form.select_time_end)
    
    await callback_query.answer()

# Обработчик выбора времени конца слота
@dp.callback_query(F.data.startswith("time_end:"), Form.select_time_end)
async def process_time_end(callback_query: CallbackQuery, state: FSMContext):
    end_time = callback_query.data.split(':')[1]
    
    # Получаем данные из состояния
    data = await state.get_data()
    start_time = data.get('current_start_time')
    time_slots = data.get('time_slots', [])
    
    # Проверяем валидность интервала
    if is_valid_time_interval(start_time, end_time):
        # Добавляем слот
        time_slots.append([start_time, end_time])
        await state.update_data(time_slots=time_slots)
        
        # Создаем клавиатуру для выбора добавления еще одного слота
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Да", callback_data="add_slot:yes"), 
             InlineKeyboardButton(text="Нет", callback_data="add_slot:no")]
        ])
        
        await callback_query.message.edit_text(
            f"Добавлен слот: {start_time} - {end_time}\nХотите добавить еще один временной слот?",
            reply_markup=keyboard
        )
        
        await state.set_state(Form.add_more_slots)
    else:
        # Если интервал невалидный, возвращаемся к выбору начала
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=time_opt, callback_data=f"time_start:{time_opt}")] for time_opt in TIME_OPTIONS
        ])
        
        await callback_query.message.edit_text(
            "Ошибка: время окончания должно быть позже времени начала.\nПожалуйста, выберите начало временного слота:",
            reply_markup=keyboard
        )
        
        await state.set_state(Form.select_time_start)
    
    await callback_query.answer()

# Обработчик выбора добавления дополнительного слота
@dp.callback_query(F.data.startswith("add_slot:"), Form.add_more_slots)
async def process_add_more_slots(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    
    if choice == "yes":
        # Создаем клавиатуру для выбора времени начала нового слота
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=time_opt, callback_data=f"time_start:{time_opt}")] for time_opt in TIME_OPTIONS
        ])
        
        await callback_query.message.edit_text(
            "Выберите начало нового временного слота:",
            reply_markup=keyboard
        )
        
        await state.set_state(Form.select_time_start)
    else:
        # Проверяем, это новый профиль или редактирование
        user_id = callback_query.from_user.id
        user_data = get_user_data(user_id)
        
        if user_data:
            # Это редактирование - сохраняем новые слоты и возвращаемся в меню редактирования
            data = await state.get_data()
            time_slots = data.get('time_slots', [])
            
            user_data['time_slots'] = time_slots
            username = callback_query.from_user.username or f"user{user_id}"
            
            save_user_data(user_id, username, user_data)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Продолжить редактирование", callback_data="menu:edit_profile")],
                [InlineKeyboardButton(text="Вернуться в главное меню", callback_data="menu:back")]
            ])
            
            await callback_query.message.edit_text(
                "Временные слоты успешно обновлены.",
                reply_markup=keyboard
            )
            
            await state.set_state(MainMenu.main)
        else:
            # Это новый профиль - продолжаем заполнение
            # Создаем клавиатуру для выбора длительности обеда
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"{duration} минут", callback_data=f"duration:{duration}")] for duration in LUNCH_DURATIONS
            ])
            
            await callback_query.message.edit_text(
                "Понял. Какую длительность обеда вы предпочитаете?",
                reply_markup=keyboard
            )
            await state.set_state(Form.lunch_duration)
    
    await callback_query.answer()

# Обработчик выбора длительности обеда
@dp.callback_query(F.data.startswith("duration:"), Form.lunch_duration)
async def process_lunch_duration(callback_query: CallbackQuery, state: FSMContext):
    duration = callback_query.data.split(':')[1]
    
    # Сохраняем выбранную длительность
    await state.update_data(lunch_duration=duration)
    
    # Проверяем, это новый профиль или редактирование
    user_id = callback_query.from_user.id
    user_data = get_user_data(user_id)
    
    if user_data:
        # Это редактирование - сохраняем новую длительность и возвращаемся в меню редактирования
        user_data['lunch_duration'] = duration
        username = callback_query.from_user.username or f"user{user_id}"
        
        save_user_data(user_id, username, user_data)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Продолжить редактирование", callback_data="menu:edit_profile")],
            [InlineKeyboardButton(text="Вернуться в главное меню", callback_data="menu:back")]
        ])
        
        await callback_query.message.edit_text(
            f"Длительность обеда успешно обновлена на: {duration} минут",
            reply_markup=keyboard
        )
        
        await state.set_state(MainMenu.main)
    else:
        # Это новый профиль - продолжаем заполнение
        # Получаем офис пользователя для фильтрации мест
        data = await state.get_data()
        office = data.get('office')
        
        # Получаем места для выбранного офиса
        places_for_office = get_places_for_office(office)
        favorite_places = data.get('favorite_places', [])
        
        # Создаем клавиатуру для выбора любимых мест
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{'✅ ' if place in favorite_places else ''}{place}", callback_data=f"fav_place:{place}")] for place in places_for_office
        ] + [[InlineKeyboardButton(text="Готово", callback_data="fav_place:done")]])
        
        await callback_query.message.edit_text(
            "Теперь выберите места, которые вам нравятся. Можно выбрать несколько. Когда закончите, нажмите 'Готово'.",
            reply_markup=keyboard
        )
        
        await state.set_state(Form.favorite_places)
    
    await callback_query.answer()

# Обработчик выбора любимых мест
@dp.callback_query(F.data.startswith("fav_place:"), Form.favorite_places)
async def process_favorite_places(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    
    # Получаем текущие данные
    data = await state.get_data()
    office = data.get('office')
    favorite_places = data.get('favorite_places', [])
    
    if choice == "done":
        # Проверяем, это новый профиль или редактирование
        user_id = callback_query.from_user.id
        user_data = get_user_data(user_id)
        
        if user_data and 'time_slots' not in data:
            # Это редактирование - сохраняем новые любимые места и возвращаемся в меню редактирования
            user_data['favorite_places'] = favorite_places
            username = callback_query.from_user.username or f"user{user_id}"
            
            save_user_data(user_id, username, user_data)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Продолжить редактирование", callback_data="menu:edit_profile")],
                [InlineKeyboardButton(text="Вернуться в главное меню", callback_data="menu:back")]
            ])
            
            await callback_query.message.edit_text(
                "Любимые места успешно обновлены.",
                reply_markup=keyboard
            )
            
            await state.set_state(MainMenu.main)
        else:
            # Это новый профиль или полное редактирование - продолжаем
            # Получаем места для выбранного офиса
            places_for_office = get_places_for_office(office)
            disliked_places = data.get('disliked_places', [])
            
            # Создаем клавиатуру для выбора нелюбимых мест
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"{'✅ ' if place in disliked_places else ''}{place}", callback_data=f"dis_place:{place}")] for place in places_for_office
            ] + [[InlineKeyboardButton(text="Готово", callback_data="dis_place:done")]])
            
            await callback_query.message.edit_text(
                "А теперь выберите места, которые вам не нравятся (чтобы мы их избегали):",
                reply_markup=keyboard
            )
            
            await state.set_state(Form.disliked_places)
    else:
        # Обновляем список любимых мест
        if choice in favorite_places:
            favorite_places.remove(choice)
        else:
            favorite_places.append(choice)
        
        await state.update_data(favorite_places=favorite_places)
        
        # Получаем места для выбранного офиса и обновляем клавиатуру
        places_for_office = get_places_for_office(office)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{'✅ ' if place in favorite_places else ''}{place}", callback_data=f"fav_place:{place}")] for place in places_for_office
        ] + [[InlineKeyboardButton(text="Готово", callback_data="fav_place:done")]])
        
        await callback_query.message.edit_text(
            "Теперь выберите места, которые вам нравятся. Можно выбрать несколько. Когда закончите, нажмите 'Готово'.",
            reply_markup=keyboard
        )
    
    await callback_query.answer()

# Обработчик выбора нелюбимых мест
@dp.callback_query(F.data.startswith("dis_place:"), Form.disliked_places)
async def process_disliked_places(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    
    # Получаем текущие данные
    data = await state.get_data()
    office = data.get('office')
    disliked_places = data.get('disliked_places', [])
    
    if choice == "done":
        # Проверяем, это новый профиль или редактирование
        user_id = callback_query.from_user.id
        user_data = get_user_data(user_id)
        
        if user_data and 'time_slots' not in data:
            # Это редактирование - сохраняем новые нелюбимые места и возвращаемся в меню редактирования
            user_data['disliked_places'] = disliked_places
            username = callback_query.from_user.username or f"user{user_id}"
            
            save_user_data(user_id, username, user_data)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Продолжить редактирование", callback_data="menu:edit_profile")],
                [InlineKeyboardButton(text="Вернуться в главное меню", callback_data="menu:back")]
            ])
            
            await callback_query.message.edit_text(
                "Нелюбимые места успешно обновлены.",
                reply_markup=keyboard
            )
            
            await state.set_state(MainMenu.main)
        else:
            # Это новый профиль или полное редактирование - продолжаем
            # Создаем клавиатуру для выбора размера компании
            company_size = data.get('company_size', [])
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"{'✅ ' if size in company_size else ''}{size}", callback_data=f"size:{size}")] for size in COMPANY_SIZES
            ] + [[InlineKeyboardButton(text="Готово", callback_data="size:done")]])
            
            await callback_query.message.edit_text(
                "Почти готово! Укажите предпочитаемый размер компании для обеда (можно выбрать несколько):",
                reply_markup=keyboard
            )
            
            await state.set_state(Form.company_size)
    else:
        # Обновляем список нелюбимых мест
        if choice in disliked_places:
            disliked_places.remove(choice)
        else:
            disliked_places.append(choice)
        
        await state.update_data(disliked_places=disliked_places)
        
        # Получаем места для выбранного офиса и обновляем клавиатуру
        places_for_office = get_places_for_office(office)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{'✅ ' if place in disliked_places else ''}{place}", callback_data=f"dis_place:{place}")] for place in places_for_office
        ] + [[InlineKeyboardButton(text="Готово", callback_data="dis_place:done")]])
        
        await callback_query.message.edit_text(
            "А теперь выберите места, которые вам не нравятся (чтобы мы их избегали):",
            reply_markup=keyboard
        )
    
    await callback_query.answer()

# Обработчик выбора размера компании
@dp.callback_query(F.data.startswith("size:"), Form.company_size)
async def process_company_size(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    
    # Получаем текущие данные
    data = await state.get_data()
    company_size = data.get('company_size', [])
    
    if choice == "done":
        # Проверяем, это новый профиль или редактирование
        user_id = callback_query.from_user.id
        user_data = get_user_data(user_id)
        
        if user_data and 'time_slots' not in data:
            # Это редактирование - сохраняем новый размер компании и возвращаемся в меню редактирования
            user_data['company_size'] = company_size
            username = callback_query.from_user.username or f"user{user_id}"
            
            save_user_data(user_id, username, user_data)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Продолжить редактирование", callback_data="menu:edit_profile")],
                [InlineKeyboardButton(text="Вернуться в главное меню", callback_data="menu:back")]
            ])
            
            await callback_query.message.edit_text(
                "Размер компании успешно обновлен.",
                reply_markup=keyboard
            )
            
            await state.set_state(MainMenu.main)
        else:
            # Это новый профиль или полное редактирование - формируем сводку и переходим к подтверждению
            time_slots_formatted = ", ".join([f"{start}-{end}" for start, end in data.get('time_slots', [])])
            
            summary = (
                "Давайте проверим вашу анкету:\n"
                f"- Офис: {data.get('office', 'Не выбран')}\n"
                f"- Слоты времени: {time_slots_formatted}\n"
                f"- Длительность обеда: {data.get('lunch_duration', 'Не выбрана')} минут\n"
                                f"- Любимые места: {', '.join(data.get('favorite_places', ['Не выбраны']))}\n"
                f"- Нелюбимые места: {', '.join(data.get('disliked_places', ['Не выбраны']))}\n"
                f"- Размер компании: {', '.join(data.get('company_size', ['Не выбран']))}"
            )
            
            # Создаем клавиатуру для подтверждения
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Всё верно", callback_data="confirm:yes"), 
                 InlineKeyboardButton(text="Заполнить заново", callback_data="confirm:no")]
            ])
            
            await callback_query.message.edit_text(
                summary,
                reply_markup=keyboard
            )
            
            await state.set_state(Form.confirmation)
    else:
        # Обновляем список размеров компании
        if choice in company_size:
            company_size.remove(choice)
        else:
            company_size.append(choice)
        
        await state.update_data(company_size=company_size)
        
        # Обновляем клавиатуру
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"{'✅ ' if size in company_size else ''}{size}", callback_data=f"size:{size}")] for size in COMPANY_SIZES
        ] + [[InlineKeyboardButton(text="Готово", callback_data="size:done")]])
        
        await callback_query.message.edit_text(
            "Почти готово! Укажите предпочитаемый размер компании для обеда (можно выбрать несколько):",
            reply_markup=keyboard
        )
    
    await callback_query.answer()

# Обработчик подтверждения анкеты
@dp.callback_query(F.data.startswith("confirm:"), Form.confirmation)
async def process_confirmation(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    
    if choice == "yes":
        # Сохраняем данные пользователя в CSV
        user_id = callback_query.from_user.id
        username = callback_query.from_user.username or f"user{user_id}"
        data = await state.get_data()
        
        # Проверка, что все необходимые ключи существуют
        if not data.get('favorite_places'):
            data['favorite_places'] = []
        if not data.get('disliked_places'):
            data['disliked_places'] = []
        if not data.get('company_size'):
            data['company_size'] = []
        
        save_user_data(user_id, username, data)
        
        # Сохраняем также данные для матчинга
        match_params = convert_to_match_format(data, username)
        update_user_to_match(username, match_params)
        
        # Показываем главное меню
        await callback_query.message.edit_text(
            "Спасибо! Ваша анкета сохранена. Теперь вы можете записаться на обед или изменить настройки."
        )
        
        await show_main_menu(callback_query.message, data)
        
        # Очищаем состояние пользователя и переходим в главное меню
        await state.clear()
        await state.set_state(MainMenu.main)
    else:
        # Начинаем заполнение анкеты заново
        await callback_query.message.edit_text(
            "Хорошо, давайте заполним анкету заново."
        )
        
        # Очищаем состояние и возвращаемся к началу
        await state.clear()
        
        # Создаем инлайн-клавиатуру для выбора офиса
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=office, callback_data=f"office:{office}")] for office in OFFICES
        ])
        
        await callback_query.message.answer(
            "Для начала, выберите ваш офис:",
            reply_markup=keyboard
        )
        
        await state.set_state(Form.office)
    
    await callback_query.answer()

# Запуск бота
async def main():
    # Проверяем и создаем файлы для хранения данных, если их нет
    ensure_csv_exists()
    ensure_json_exists()
    
    # Загружаем список мест для обеда
    load_places()
    
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())