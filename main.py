import csv
import os
import re
from datetime import datetime
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
API_TOKEN = '8069233462:AAETcgqI5kUYkeg3gCXCnmGXAzXbLMgYjoY'

# Пути к файлам CSV
USERS_CSV = 'users_data.csv'
PLACES_CSV = 'places.csv'

# Список офисов
OFFICES = ["Аврора", "Сити: Нева", "Сити: Око", "Красная роза", "Лотте", "Бенуа"]

# Глобальные переменные для хранения данных из CSV
PLACES = []
PLACES_BY_OFFICE = {}

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

# Определение длительности обеда и размеров компании
LUNCH_DURATIONS = ["30", "45", "60", "90"]
COMPANY_SIZES = ["1", "2", "3", "4", "5+"]

# Определение состояний FSM
class Form(StatesGroup):
    office = State()
    time_slots = State()
    add_more_slots = State()
    lunch_duration = State()
    favorite_places = State()
    disliked_places = State()
    company_size = State()
    confirmation = State()

# Функция для проверки существования файла CSV и его создания при необходимости
def ensure_csv_exists():
    if not os.path.exists(USERS_CSV):
        with open(USERS_CSV, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['user_id', 'username', 'office', 'time_slots', 'lunch_duration', 
                            'favorite_places', 'disliked_places', 'company_size', 'last_updated'])

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

# Получение списка мест для конкретного офиса
def get_places_for_office(office):
    # Если места не сгруппированы по офисам или офис не найден, возвращаем все места
    if office not in PLACES_BY_OFFICE:
        return PLACES
    
    # Возвращаем только места для указанного офиса
    return [place['name'] for place in PLACES_BY_OFFICE[office]]

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Хендлер для команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    
    # Очищаем предыдущее состояние
    await state.clear()
    
    # Создаем инлайн-клавиатуру для выбора офиса
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=office, callback_data=f"office:{office}")] for office in OFFICES
    ])
    
    await message.answer("Привет! Давайте заполним ваш профиль для подбора компании на обед. Для начала, выберите ваш офис:", reply_markup=keyboard)
    await state.set_state(Form.office)

# Обработчик выбора офиса
@dp.callback_query(F.data.startswith("office:"), Form.office)
async def process_office(callback_query: CallbackQuery, state: FSMContext):
    office = callback_query.data.split(':')[1]
    
    # Сохраняем выбор офиса
    await state.update_data(office=office)
    
    # Редактируем сообщение и просим ввести временной слот
    await callback_query.message.edit_text(
        f"Отлично! Вы выбрали офис: {office}\n\nТеперь укажите удобные для вас временные слоты для обеда. Отправьте время в формате ЧЧ:ММ - ЧЧ:ММ, например, 13:00 - 14:30."
    )
    
    # Инициализируем пустой список слотов
    await state.update_data(time_slots=[])
    
    # Переходим к следующему состоянию
    await state.set_state(Form.time_slots)
    
    # Обязательно отвечаем на callback_query
    await callback_query.answer()

# Обработчик ввода временного слота
@dp.message(Form.time_slots)
async def process_time_slot(message: types.Message, state: FSMContext):
    # Регулярное выражение для проверки формата времени
    pattern = r'^([01]\d|2[0-3]):([0-5]\d)\s*-\s*([01]\d|2[0-3]):([0-5]\d)$'
    
    if re.match(pattern, message.text):
        # Если формат верный, извлекаем время начала и конца
        start_time, end_time = message.text.replace(' ', '').split('-')
        
        # Получаем текущие слоты
        data = await state.get_data()
        time_slots = data.get('time_slots', [])
        
        # Добавляем новый слот
        time_slots.append([start_time, end_time])
        await state.update_data(time_slots=time_slots)
        
        # Создаем клавиатуру для выбора добавления еще одного слота
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Да", callback_data="add_slot:yes"), 
             InlineKeyboardButton(text="Нет", callback_data="add_slot:no")]
        ])
        
        await message.answer("Слот добавлен. Хотите добавить еще один?", reply_markup=keyboard)
        await state.set_state(Form.add_more_slots)
    else:
        await message.answer("Неверный формат. Пожалуйста, введите время в формате ЧЧ:ММ - ЧЧ:ММ, например, 13:00 - 14:30.")

# Обработчик выбора добавления дополнительного слота
@dp.callback_query(F.data.startswith("add_slot:"), Form.add_more_slots)
async def process_add_more_slots(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    
    if choice == "yes":
        await callback_query.message.edit_text("Введите следующий слот:")
        await state.set_state(Form.time_slots)
    else:
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
        # Форматируем временные слоты для отображения
        time_slots_formatted = ", ".join([f"{start}-{end}" for start, end in data.get('time_slots', [])])
        
        # Создаем текст сводки
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
        username = callback_query.from_user.username or "No username"
        data = await state.get_data()
        
        # Проверка, что все необходимые ключи существуют
        if not data.get('favorite_places'):
            data['favorite_places'] = []
        if not data.get('disliked_places'):
            data['disliked_places'] = []
        if not data.get('company_size'):
            data['company_size'] = []
        
        save_user_data(user_id, username, data)
        
        await callback_query.message.edit_text(
            "Спасибо! Ваша анкета сохранена."
        )
        
        # Очищаем состояние пользователя
        await state.clear()
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
    # Проверяем и создаем файл для хранения данных пользователей, если его нет
    ensure_csv_exists()
    
    # Загружаем список мест для обеда
    load_places()
    
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
