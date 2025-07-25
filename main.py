import csv
import os
import re
from datetime import datetime
import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен вашего бота (вам нужно заменить на свой)
API_TOKEN = '8069233462:AAETcgqI5kUYkeg3gCXCnmGXAzXbLMgYjoY'

# Пути к файлам CSV
USERS_CSV = 'users_data.csv'
PLACES_CSV = 'places.csv'

# Предварительная настройка данных
# Список офисов
OFFICES = ["Аврора", "Сити: Нева", "Сити: Око", "Красная роза", "Лотте", "Бенуа"]

# Список мест для обеда (предполагается, что они уже определены в places_data.csv)
def load_places():
    if not os.path.exists(PLACES_CSV):
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

LUNCH_DURATIONS = ["30", "45", "60", "90"]
COMPANY_SIZES = ["1", "2", "3", "4", "5+"]

class Form(StatesGroup):
    office = State()
    time_slots = State()
    add_more_slots = State()
    lunch_duration = State()
    favorite_places = State()
    disliked_places = State()
    company_size = State()
    confirmation = State()

def ensure_csv_exists():
    if not os.path.exists(USERS_CSV):
        with open(USERS_CSV, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['user_id', 'username', 'office', 'time_slots', 'lunch_duration', \
                            'favorite_places', 'disliked_places', 'company_size', 'last_updated'])

def save_user_data(user_id, username, data):
    ensure_csv_exists()
    time_slots_str = ';'.join([f"{start}-{end}" for start, end in data['time_slots']])
    favorite_places_str = ';'.join(data['favorite_places'])
    disliked_places_str = ';'.join(data['disliked_places'])
    company_size_str = ';'.join(data['company_size'])
    rows = []
    user_exists = False
    if os.path.exists(USERS_CSV):
        with open(USERS_CSV, 'r', newline='', encoding='utf-8') as file:
            reader = csv.reader(file)
            header = next(reader)
            for row in reader:
                if row and row[0] == str(user_id):
                    row = [str(user_id), username, data['office'], time_slots_str, data['lunch_duration'],
                          favorite_places_str, disliked_places_str, company_size_str,
                          datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")]
                    user_exists = True
                rows.append(row)
    if not user_exists:
        new_row = [str(user_id), username, data['office'], time_slots_str, data['lunch_duration'],
                  favorite_places_str, disliked_places_str, company_size_str,
                  datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")]
        rows.append(new_row)
    with open(USERS_CSV, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['user_id', 'username', 'office', 'time_slots', 'lunch_duration', \
                        'favorite_places', 'disliked_places', 'company_size', 'last_updated'])
        writer.writerows(rows)

# --- Хендлеры ---
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    await state.clear()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=office, callback_data=f"office:{office}")] for office in OFFICES
    ])
    await message.answer("Привет! Давайте заполним ваш профиль для подбора компании на обед. Для начала, выберите ваш офис:", reply_markup=keyboard)
    await state.set_state(Form.office)

async def process_office(callback_query: CallbackQuery, state: FSMContext):
    office = callback_query.data.split(':')[1]
    await state.update_data(office=office)
    await callback_query.message.edit_text(
        f"Отлично! Вы выбрали офис: {office}\n\nТеперь укажите удобные для вас временные слоты для обеда. Отправьте время в формате ЧЧ:ММ - ЧЧ:ММ, например, 13:00 - 14:30."
    )
    await state.update_data(time_slots=[])
    await state.set_state(Form.time_slots)

async def process_time_slot(message: types.Message, state: FSMContext):
    pattern = r'^([01]\d|2[0-3]):([0-5]\d)\s*-\s*([01]\d|2[0-3]):([0-5]\d)$'
    if re.match(pattern, message.text):
        start_time, end_time = message.text.replace(' ', '').split('-')
        data = await state.get_data()
        time_slots = data.get('time_slots', [])
        time_slots.append([start_time, end_time])
        await state.update_data(time_slots=time_slots)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("Да", callback_data="add_slot:yes"), InlineKeyboardButton("Нет", callback_data="add_slot:no")]
        ])
        await message.answer("Слот добавлен. Хотите добавить еще один?", reply_markup=keyboard)
        await state.set_state(Form.add_more_slots)
    else:
        await message.answer("Неверный формат. Пожалуйста, введите время в формате ЧЧ:ММ - ЧЧ:ММ, например, 13:00 - 14:30.")

async def process_add_more_slots(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    if choice == "yes":
        await callback_query.message.edit_text("Введите следующий слот:")
        await state.set_state(Form.time_slots)
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(f"{duration} минут", callback_data=f"duration:{duration}")] for duration in LUNCH_DURATIONS
        ])
        await callback_query.message.edit_text(
            "Понял. Какую длительность обеда вы предпочитаете?",
            reply_markup=keyboard
        )
        await state.set_state(Form.lunch_duration)

async def process_lunch_duration(callback_query: CallbackQuery, state: FSMContext):
    duration = callback_query.data.split(':')[1]
    await state.update_data(lunch_duration=duration)
    data = await state.get_data()
    favorite_places = data.get('favorite_places', [])
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(f"{'✅ ' if place in favorite_places else ''}{place}", callback_data=f"fav_place:{place}")] for place in PLACES
    ] + [[InlineKeyboardButton("Готово", callback_data="fav_place:done")]])
    await callback_query.message.edit_text(
        "Теперь выберите места, которые вам нравятся. Можно выбрать несколько. Когда закончите, нажмите 'Готово'.",
        reply_markup=keyboard
    )
    await state.set_state(Form.favorite_places)

async def process_favorite_places(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    data = await state.get_data()
    favorite_places = data.get('favorite_places', [])
    if choice == "done":
        disliked_places = data.get('disliked_places', [])
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(f"{'✅ ' if place in disliked_places else ''}{place}", callback_data=f"dis_place:{place}")] for place in PLACES
        ] + [[InlineKeyboardButton("Готово", callback_data="dis_place:done")]])
        await callback_query.message.edit_text(
            "А теперь выберите места, которые вам не нравятся (чтобы мы их избегали):",
            reply_markup=keyboard
        )
        await state.set_state(Form.disliked_places)
    else:
        if choice in favorite_places:
            favorite_places.remove(choice)
        else:
            favorite_places.append(choice)
        await state.update_data(favorite_places=favorite_places)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(f"{'✅ ' if place in favorite_places else ''}{place}", callback_data=f"fav_place:{place}")] for place in PLACES
        ] + [[InlineKeyboardButton("Готово", callback_data="fav_place:done")]])
        await callback_query.message.edit_text(
            "Теперь выберите места, которые вам нравятся. Можно выбрать несколько. Когда закончите, нажмите 'Готово'.",
            reply_markup=keyboard
        )

async def process_disliked_places(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    data = await state.get_data()
    disliked_places = data.get('disliked_places', [])
    if choice == "done":
        company_size = data.get('company_size', [])
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(f"{'✅ ' if size in company_size else ''}{size}", callback_data=f"size:{size}")] for size in COMPANY_SIZES
        ] + [[InlineKeyboardButton("Готово", callback_data="size:done")]])
        await callback_query.message.edit_text(
            "Почти готово! Укажите предпочитаемый размер компании для обеда (можно выбрать несколько):",
            reply_markup=keyboard
        )
        await state.set_state(Form.company_size)
    else:
        if choice in disliked_places:
            disliked_places.remove(choice)
        else:
            disliked_places.append(choice)
        await state.update_data(disliked_places=disliked_places)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(f"{'✅ ' if place in disliked_places else ''}{place}", callback_data=f"dis_place:{place}")] for place in PLACES
        ] + [[InlineKeyboardButton("Готово", callback_data="dis_place:done")]])
        await callback_query.message.edit_text(
            "А теперь выберите места, которые вам не нравятся (чтобы мы их избегали):",
            reply_markup=keyboard
        )

async def process_company_size(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    data = await state.get_data()
    company_size = data.get('company_size', [])
    if choice == "done":
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
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("Всё верно", callback_data="confirm:yes"), InlineKeyboardButton("Заполнить заново", callback_data="confirm:no")]
        ])
        await callback_query.message.edit_text(
            summary,
            reply_markup=keyboard
        )
        await state.set_state(Form.confirmation)
    else:
        if choice in company_size:
            company_size.remove(choice)
        else:
            company_size.append(choice)
        await state.update_data(company_size=company_size)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(f"{'✅ ' if size in company_size else ''}{size}", callback_data=f"size:{size}")] for size in COMPANY_SIZES
        ] + [[InlineKeyboardButton("Готово", callback_data="size:done")]])
        await callback_query.message.edit_text(
            "Почти готово! Укажите предпочитаемый размер компании для обеда (можно выбрать несколько):",
            reply_markup=keyboard
        )

async def process_confirmation(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    if choice == "yes":
        user_id = callback_query.from_user.id
        username = callback_query.from_user.username or "No username"
        data = await state.get_data()
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
        await state.clear()
    else:
        await callback_query.message.edit_text(
            "Хорошо, давайте заполним анкету заново."
        )
        await state.clear()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=office, callback_data=f"office:{office}")] for office in OFFICES
        ])
        await callback_query.message.answer(
            "Для начала, выберите ваш офис:",
            reply_markup=keyboard
        )
        await state.set_state(Form.office)

async def main():
    ensure_csv_exists()
    load_places()
    bot = Bot(token=API_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.register(cmd_start, commands={"start"})
    dp.callback_query.register(process_office, lambda c, state: c.data.startswith('office:'), Form.office)
    dp.message.register(process_time_slot, Form.time_slots)
    dp.callback_query.register(process_add_more_slots, lambda c, state: c.data.startswith('add_slot:'), Form.add_more_slots)
    dp.callback_query.register(process_lunch_duration, lambda c, state: c.data.startswith('duration:'), Form.lunch_duration)
    dp.callback_query.register(process_favorite_places, lambda c, state: c.data.startswith('fav_place:'), Form.favorite_places)
    dp.callback_query.register(process_disliked_places, lambda c, state: c.data.startswith('dis_place:'), Form.disliked_places)
    dp.callback_query.register(process_company_size, lambda c, state: c.data.startswith('size:'), Form.company_size)
    dp.callback_query.register(process_confirmation, lambda c, state: c.data.startswith('confirm:'), Form.confirmation)
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
