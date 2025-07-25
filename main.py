import csv
import os
import re
from datetime import datetime
import logging
from aiogram import Bot, Dispatcher, types, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен вашего бота (вам нужно заменить на свой)
API_TOKEN = '8069233462:AAETcgqI5kUYkeg3gCXCnmGXAzXbLMgYjoY'

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Пути к файлам CSV
USERS_CSV = 'users_data.csv'
PLACES_CSV = 'places.csv'

# Предварительная настройка данных
# Список офисов
OFFICES = ["Аврора", "Сити: Нева", "Сити: Око", "Красная роза", "Лотте", "Бенуа"]

# Список мест для обеда (предполагается, что они уже определены в places_data.csv)
def load_places():
    if not os.path.exists(PLACES_CSV):
        # Создаем файл с демо-данными, если он не существует
        with open(PLACES_CSV, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['id', 'name', 'location'])
            places = [
                [1, 'Кафе 1', 'Москва, Сити'],
                [2, 'Столовая 2', 'Москва, Сити'],
                [3, 'Фастфуд 3', 'Москва, Центр'],
                [4, 'Ресторан 4', 'Москва, Центр'],
                [5, 'Ресторан 5', 'Санкт-Петербург'],
                [6, 'Кафе 6', 'Новосибирск']
            ]
            for place in places:
                writer.writerow(place)
    
    places = []
    with open(PLACES_CSV, 'r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            places.append(row['name'])
    return places

PLACES = load_places()

# Определение длительности обеда
LUNCH_DURATIONS = ["30", "45", "60", "90"]

# Определение размеров компании
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

# Команда /start - начало взаимодействия
@dp.message_handler(commands=['start'], state='*')
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    
    # Очищаем предыдущее состояние
    await state.finish()
    
    # Создаем инлайн-клавиатуру для выбора офиса
    keyboard = InlineKeyboardMarkup(row_width=1)
    for office in OFFICES:
        keyboard.add(InlineKeyboardButton(office, callback_data=f"office:{office}"))
    
    await message.answer("Привет! Давайте заполним ваш профиль для подбора компании на обед. Для начала, выберите ваш офис:", reply_markup=keyboard)
    await Form.office.set()

# Обработчик выбора офиса
@dp.callback_query_handler(lambda c: c.data.startswith('office:'), state=Form.office)
async def process_office(callback_query: CallbackQuery, state: FSMContext):
    office = callback_query.data.split(':')[1]
    
    # Сохраняем выбор офиса
    await state.update_data(office=office)
    
    # Редактируем сообщение и просим ввести временной слот
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text=f"Отлично! Вы выбрали офис: {office}\n\nТеперь укажите удобные для вас временные слоты для обеда. Отправьте время в формате ЧЧ:ММ - ЧЧ:ММ, например, 13:00 - 14:30."
    )
    
    # Инициализируем пустой список слотов
    await state.update_data(time_slots=[])
    
    # Переходим к следующему состоянию
    await Form.time_slots.set()

# Обработчик ввода временного слота
@dp.message_handler(state=Form.time_slots)
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
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("Да", callback_data="add_slot:yes"),
            InlineKeyboardButton("Нет", callback_data="add_slot:no")
        )
        
        await message.answer("Слот добавлен. Хотите добавить еще один?", reply_markup=keyboard)
        await Form.add_more_slots.set()
    else:
        await message.answer("Неверный формат. Пожалуйста, введите время в формате ЧЧ:ММ - ЧЧ:ММ, например, 13:00 - 14:30.")

# Обработчик выбора добавления дополнительного слота
@dp.callback_query_handler(lambda c: c.data.startswith('add_slot:'), state=Form.add_more_slots)
async def process_add_more_slots(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    
    if choice == "yes":
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="Введите следующий слот:"
        )
        await Form.time_slots.set()
    else:
        # Создаем клавиатуру для выбора длительности обеда
        keyboard = InlineKeyboardMarkup(row_width=2)
        for duration in LUNCH_DURATIONS:
            keyboard.add(InlineKeyboardButton(f"{duration} минут", callback_data=f"duration:{duration}"))
        
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="Понял. Какую длительность обеда вы предпочитаете?",
            reply_markup=keyboard
        )
        await Form.lunch_duration.set()

# Обработчик выбора длительности обеда
@dp.callback_query_handler(lambda c: c.data.startswith('duration:'), state=Form.lunch_duration)
async def process_lunch_duration(callback_query: CallbackQuery, state: FSMContext):
    duration = callback_query.data.split(':')[1]
    
    # Сохраняем выбранную длительность
    await state.update_data(lunch_duration=duration)
    
    # Создаем клавиатуру для выбора любимых мест
    keyboard = InlineKeyboardMarkup(row_width=1)
    data = await state.get_data()
    favorite_places = data.get('favorite_places', [])
    
    for place in PLACES:
        if place in favorite_places:
            keyboard.add(InlineKeyboardButton(f"✅ {place}", callback_data=f"fav_place:{place}"))
        else:
            keyboard.add(InlineKeyboardButton(place, callback_data=f"fav_place:{place}"))
    
    keyboard.add(InlineKeyboardButton("Готово", callback_data="fav_place:done"))
    
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="Теперь выберите места, которые вам нравятся. Можно выбрать несколько. Когда закончите, нажмите 'Готово'.",
        reply_markup=keyboard
    )
    
    await Form.favorite_places.set()

# Обработчик выбора любимых мест
@dp.callback_query_handler(lambda c: c.data.startswith('fav_place:'), state=Form.favorite_places)
async def process_favorite_places(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    
    if choice == "done":
        # Создаем клавиатуру для выбора нелюбимых мест
        keyboard = InlineKeyboardMarkup(row_width=1)
        data = await state.get_data()
        disliked_places = data.get('disliked_places', [])
        
        for place in PLACES:
            if place in disliked_places:
                keyboard.add(InlineKeyboardButton(f"✅ {place}", callback_data=f"dis_place:{place}"))
            else:
                keyboard.add(InlineKeyboardButton(place, callback_data=f"dis_place:{place}"))
        
        keyboard.add(InlineKeyboardButton("Готово", callback_data="dis_place:done"))
        
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="А теперь выберите места, которые вам не нравятся (чтобы мы их избегали):",
            reply_markup=keyboard
        )
        
        await Form.disliked_places.set()
    else:
        # Обновляем список любимых мест
        data = await state.get_data()
        favorite_places = data.get('favorite_places', [])
        
        if choice in favorite_places:
            favorite_places.remove(choice)
        else:
            favorite_places.append(choice)
        
        await state.update_data(favorite_places=favorite_places)
        
        # Обновляем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)
        for place in PLACES:
            if place in favorite_places:
                keyboard.add(InlineKeyboardButton(f"✅ {place}", callback_data=f"fav_place:{place}"))
            else:
                keyboard.add(InlineKeyboardButton(place, callback_data=f"fav_place:{place}"))
        
        keyboard.add(InlineKeyboardButton("Готово", callback_data="fav_place:done"))
        
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="Теперь выберите места, которые вам нравятся. Можно выбрать несколько. Когда закончите, нажмите 'Готово'.",
            reply_markup=keyboard
        )

# Обработчик выбора нелюбимых мест
@dp.callback_query_handler(lambda c: c.data.startswith('dis_place:'), state=Form.disliked_places)
async def process_disliked_places(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    
    if choice == "done":
        # Создаем клавиатуру для выбора размера компании
        keyboard = InlineKeyboardMarkup(row_width=2)
        data = await state.get_data()
        company_size = data.get('company_size', [])
        
        for size in COMPANY_SIZES:
            if size in company_size:
                keyboard.add(InlineKeyboardButton(f"✅ {size}", callback_data=f"size:{size}"))
            else:
                keyboard.add(InlineKeyboardButton(size, callback_data=f"size:{size}"))
        
        keyboard.add(InlineKeyboardButton("Готово", callback_data="size:done"))
        
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="Почти готово! Укажите предпочитаемый размер компании для обеда (можно выбрать несколько):",
            reply_markup=keyboard
        )
        
        await Form.company_size.set()
    else:
        # Обновляем список нелюбимых мест
        data = await state.get_data()
        disliked_places = data.get('disliked_places', [])
        
        if choice in disliked_places:
            disliked_places.remove(choice)
        else:
            disliked_places.append(choice)
        
        await state.update_data(disliked_places=disliked_places)
        
        # Обновляем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=1)
        for place in PLACES:
            if place in disliked_places:
                keyboard.add(InlineKeyboardButton(f"✅ {place}", callback_data=f"dis_place:{place}"))
            else:
                keyboard.add(InlineKeyboardButton(place, callback_data=f"dis_place:{place}"))
        
        keyboard.add(InlineKeyboardButton("Готово", callback_data="dis_place:done"))
        
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="А теперь выберите места, которые вам не нравятся (чтобы мы их избегали):",
            reply_markup=keyboard
        )

# Обработчик выбора размера компании
@dp.callback_query_handler(lambda c: c.data.startswith('size:'), state=Form.company_size)
async def process_company_size(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    
    if choice == "done":
        # Получаем все данные и формируем сводку
        data = await state.get_data()
        
        # Форматируем временные слоты
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
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("Всё верно", callback_data="confirm:yes"),
            InlineKeyboardButton("Заполнить заново", callback_data="confirm:no")
        )
        
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text=summary,
            reply_markup=keyboard
        )
        
        await Form.confirmation.set()
    else:
        # Обновляем список размеров компании
        data = await state.get_data()
        company_size = data.get('company_size', [])
        
        if choice in company_size:
            company_size.remove(choice)
        else:
            company_size.append(choice)
        
        await state.update_data(company_size=company_size)
        
        # Обновляем клавиатуру
        keyboard = InlineKeyboardMarkup(row_width=2)
        for size in COMPANY_SIZES:
            if size in company_size:
                keyboard.add(InlineKeyboardButton(f"✅ {size}", callback_data=f"size:{size}"))
            else:
                keyboard.add(InlineKeyboardButton(size, callback_data=f"size:{size}"))
        
        keyboard.add(InlineKeyboardButton("Готово", callback_data="size:done"))
        
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="Почти готово! Укажите предпочитаемый размер компании для обеда (можно выбрать несколько):",
            reply_markup=keyboard
        )

# Обработчик подтверждения анкеты
@dp.callback_query_handler(lambda c: c.data.startswith('confirm:'), state=Form.confirmation)
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
        
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="Спасибо! Ваша анкета сохранена."
        )
        
        # Очищаем состояние пользователя
        await state.finish()
    else:
        # Начинаем заполнение анкеты заново
        await bot.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.message_id,
            text="Хорошо, давайте заполним анкету заново."
        )
        
        # Очищаем состояние и возвращаемся к началу
        await state.finish()
        
        # Создаем инлайн-клавиатуру для выбора офиса
        keyboard = InlineKeyboardMarkup(row_width=1)
        for office in OFFICES:
            keyboard.add(InlineKeyboardButton(office, callback_data=f"office:{office}"))
        
        await bot.send_message(
            chat_id=callback_query.message.chat.id,
            text="Для начала, выберите ваш офис:",
            reply_markup=keyboard
        )
        
        await Form.office.set()

# Запуск бота
if __name__ == '__main__':
    ensure_csv_exists()
    load_places()
    executor.start_polling(dp, skip_updates=True)
