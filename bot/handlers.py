from aiogram import F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import logging

from .states import Form, MainMenu
from .utils import (
    get_user_data, save_user_data, update_user_to_match, 
    get_places_for_office, is_valid_time_interval, convert_to_match_format
)
from .keyboards import (
    get_office_keyboard, get_time_start_keyboard, get_time_end_keyboard,
    get_add_slot_keyboard, get_lunch_duration_keyboard, get_favorite_places_keyboard,
    get_disliked_places_keyboard, get_company_size_keyboard, get_confirmation_keyboard,
    get_main_menu_keyboard, get_edit_menu_keyboard, get_lunch_preference_keyboard,
    get_back_to_menu_keyboard, get_lunch_favorite_places_keyboard, get_lunch_company_keyboard,
    get_lunch_confirm_keyboard, get_after_edit_keyboard,
    get_lunch_time_start_keyboard, get_lunch_time_end_keyboard
)

logger = logging.getLogger(__name__)

# Базовые функции
async def show_main_menu(message, user_data=None):
    keyboard = get_main_menu_keyboard()
    await message.answer("Главное меню:", reply_markup=keyboard)

async def start_profile_creation(message, state):
    await state.clear()
    keyboard = get_office_keyboard()
    await message.answer("Давайте заполним ваш профиль для подбора компании на обед. Для начала, выберите ваш офис:", reply_markup=keyboard)
    await state.set_state(Form.office)

# Команда /start
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or "No username"
    
    user_data = get_user_data(user_id)
    
    if user_data:
        await show_main_menu(message, user_data)
        await state.set_state(MainMenu.main)
    else:
        await start_profile_creation(message, state)

# Обработчик для главного меню
async def process_main_menu(callback_query: CallbackQuery, state: FSMContext):
    action = callback_query.data.split(':')[1]
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username or f"user{user_id}"
    user_data = get_user_data(user_id)
    
    if action == "book_lunch":
        keyboard = get_lunch_preference_keyboard()
        await callback_query.message.edit_text(
            "Как вы хотите найти компанию на обед?",
            reply_markup=keyboard
        )
        await state.set_state(MainMenu.lunch_preference)
    
    elif action == "edit_profile":
        keyboard = get_edit_menu_keyboard()
        await callback_query.message.edit_text(
            "Выберите, какие настройки вы хотите изменить:",
            reply_markup=keyboard
        )
        await state.set_state(MainMenu.edit_field)
    
    elif action == "show_profile":
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
            
            keyboard = get_back_to_menu_keyboard()
            await callback_query.message.edit_text(profile_text, reply_markup=keyboard)
        else:
            await callback_query.message.edit_text(
                "У вас еще нет профиля. Давайте создадим его!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Создать профиль", callback_data="menu:create_profile")]
                ])
            )
    
    elif action == "back" or action == "create_profile":
        if action == "create_profile":
            await start_profile_creation(callback_query.message, state)
        else:
            await show_main_menu(callback_query.message, user_data)
            await state.set_state(MainMenu.main)
    
    await callback_query.answer()

# Обработчик для выбора предпочтений обеда
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
                reply_markup=get_back_to_menu_keyboard()
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
        keyboard = get_lunch_time_start_keyboard()
        
        await callback_query.message.edit_text(
            "Выберите начало временного слота для сегодняшнего обеда:",
            reply_markup=keyboard
        )
        
        await state.set_state(MainMenu.lunch_time_start)
    
    await callback_query.answer()

# В custom lunch используем отдельные клавиатуры и callback_data
async def process_lunch_time_start(callback_query: CallbackQuery, state: FSMContext):
    start_time = callback_query.data.split(':', 1)[1]
    await state.update_data(lunch_start_time=start_time)
    keyboard = get_lunch_time_end_keyboard(start_time)
    await callback_query.message.edit_text(
        f"Выбрано начало: {start_time}\n\nТеперь выберите конец временного слота:",
        reply_markup=keyboard
    )
    await state.set_state(MainMenu.lunch_time_end)
    await callback_query.answer()

async def process_lunch_time_end(callback_query: CallbackQuery, state: FSMContext):
    end_time = callback_query.data.split(':', 1)[1]
    data = await state.get_data()
    start_time = data.get('lunch_start_time')
    custom_lunch_data = data.get('custom_lunch_data', {})
    time_slots = custom_lunch_data.get('time_slots', [])
    if is_valid_time_interval(start_time, end_time):
        time_slots.append([start_time, end_time])
        custom_lunch_data['time_slots'] = time_slots
        await state.update_data(custom_lunch_data=custom_lunch_data)
        keyboard = get_add_slot_keyboard()
        await callback_query.message.edit_text(
            f"Добавлен слот: {start_time} - {end_time}\nХотите добавить еще один временной слот?",
            reply_markup=keyboard
        )
        await state.set_state(MainMenu.lunch_time_add_more)
    else:
        keyboard = get_lunch_time_start_keyboard()
        await callback_query.message.edit_text(
            "Ошибка: время окончания должно быть позже времени начала.\nПожалуйста, выберите начало временного слота:",
            reply_markup=keyboard
        )
        await state.set_state(MainMenu.lunch_time_start)
    await callback_query.answer()

async def process_lunch_time_add_more(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    if choice == "yes":
        keyboard = get_lunch_time_start_keyboard()
        await callback_query.message.edit_text(
            "Выберите начало следующего временного слота:",
            reply_markup=keyboard
        )
        await state.set_state(MainMenu.lunch_time_start)
    else:
        data = await state.get_data()
        user_id = callback_query.from_user.id
        user_data = get_user_data(user_id)
        office = user_data.get('office') if user_data else None
        places_for_office = get_places_for_office(office)
        custom_lunch_data = data.get('custom_lunch_data', {})
        fav_places = custom_lunch_data.get('favourite_places', [])
        keyboard = get_lunch_favorite_places_keyboard(places_for_office, fav_places)
        await callback_query.message.edit_text(
            "Выберите места, которые вам нравятся для обеда сегодня. Можно выбрать несколько. Когда закончите, нажмите 'Готово'.",
            reply_markup=keyboard
        )
        await state.set_state(MainMenu.lunch_place)
    await callback_query.answer()

async def process_lunch_place(callback_query: CallbackQuery, state: FSMContext):
    place = callback_query.data.split(':')[1]
    data = await state.get_data()
    custom_lunch_data = data.get('custom_lunch_data', {})
    fav_places = custom_lunch_data.get('favourite_places', [])
    if place == "done":
        selected_sizes = custom_lunch_data.get('team_size_lst', [])
        keyboard = get_lunch_company_keyboard(selected_sizes)
        await callback_query.message.edit_text(
            "Выберите предпочтительный размер компании для обеда сегодня:",
            reply_markup=keyboard
        )
        await state.set_state(MainMenu.lunch_company_size)
    else:
        if place in fav_places:
            fav_places.remove(place)
        else:
            fav_places.append(place)
        custom_lunch_data['favourite_places'] = fav_places
        await state.update_data(custom_lunch_data=custom_lunch_data)
        user_id = callback_query.from_user.id
        user_data = get_user_data(user_id)
        office = user_data.get('office') if user_data else None
        places_for_office = get_places_for_office(office)
        keyboard = get_lunch_favorite_places_keyboard(places_for_office, fav_places)
        await callback_query.message.edit_text(
            "Выберите места, которые вам нравятся для обеда сегодня. Можно выбрать несколько. Когда закончите, нажмите 'Готово'.",
            reply_markup=keyboard
        )
    await callback_query.answer()

async def process_lunch_company(callback_query: CallbackQuery, state: FSMContext):
    company_size = callback_query.data.split(':')[1]
    data = await state.get_data()
    custom_lunch_data = data.get('custom_lunch_data', {})
    sizes = custom_lunch_data.get('team_size_lst', [])
    if company_size == "done":
        user_id = callback_query.from_user.id
        username = callback_query.from_user.username or f"user{user_id}"
        user_data = get_user_data(user_id)
        match_params = convert_to_match_format(user_data, username)
        if 'time_slots' in custom_lunch_data:
            match_params['time_slots'] = custom_lunch_data['time_slots']
        if 'favourite_places' in custom_lunch_data:
            match_params['favourite_places'] = custom_lunch_data['favourite_places']
        if 'team_size_lst' in custom_lunch_data:
            match_params['team_size_lst'] = custom_lunch_data['team_size_lst']
        time_slots_formatted = ", ".join([f"{start}-{end}" for start, end in match_params['time_slots']])
        summary = (
            "Проверьте ваши параметры для подбора обеда сегодня:\n"
            f"- Офис: {match_params.get('office', 'Не выбран')}\n"
            f"- Слоты времени: {time_slots_formatted}\n"
            f"- Длительность обеда: {match_params.get('duration_min', 'Не выбрана')} минут\n"
            f"- Любимые места: {', '.join(match_params.get('favourite_places', ['Не выбраны']))}\n"
            f"- Размер компании: {', '.join(match_params.get('team_size_lst', ['Не выбран']))}"
        )
        keyboard = get_lunch_confirm_keyboard()
        await callback_query.message.edit_text(
            f"{summary}\n\nПодтвердите запись на обед с этими параметрами:",
            reply_markup=keyboard
        )
        await state.set_state(MainMenu.lunch_confirmation)
    else:
        if company_size in sizes:
            sizes.remove(company_size)
        else:
            sizes.append(company_size)
        custom_lunch_data['team_size_lst'] = sizes
        await state.update_data(custom_lunch_data=custom_lunch_data)
        keyboard = get_lunch_company_keyboard(sizes)
        await callback_query.message.edit_text(
            "Выберите предпочтительный размер компании для обеда сегодня:",
            reply_markup=keyboard
        )
    await callback_query.answer()

# Обработчик подтверждения записи на обед
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
                "Вы успешно записаны на обед! Мы оповестим вас о найденной компании в ближайшее время.",
                reply_markup=get_back_to_menu_keyboard()
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
            reply_markup=get_back_to_menu_keyboard()
        )
    
    await state.set_state(MainMenu.main)
    await callback_query.answer()

# Обработчик выбора поля для редактирования профиля
async def process_edit_field(callback_query: CallbackQuery, state: FSMContext):
    field = callback_query.data.split(':')[1]
    
    if field == "office":
        # Редактирование офиса
        keyboard = get_office_keyboard()
        
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
        keyboard = get_time_start_keyboard()
        
        await callback_query.message.edit_text(
            "Выберите начало временного слота для обеда:",
            reply_markup=keyboard
        )
        
        await state.set_state(Form.select_time_start)
    
    elif field == "duration":
        # Редактирование длительности обеда
        keyboard = get_lunch_duration_keyboard()
        
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
            
            keyboard = get_favorite_places_keyboard(places_for_office, favorite_places)
            
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
            
            keyboard = get_disliked_places_keyboard(places_for_office, disliked_places)
            
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
        
        keyboard = get_company_size_keyboard(company_size)
        
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
        keyboard = get_time_start_keyboard()
        
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
        keyboard = get_after_edit_keyboard()
        
        await callback_query.message.edit_text(
            f"Офис успешно обновлен на: {office}",
            reply_markup=keyboard
        )
        
        await state.set_state(MainMenu.main)
    
    await callback_query.answer()

# Обработчик выбора времени начала слота
async def process_time_start(callback_query: CallbackQuery, state: FSMContext):
    start_time = callback_query.data.split(':', 1)[1]
    logger.info(f"[DEBUG] Выбрано начало слота: {start_time}")
    await state.update_data(current_start_time=start_time)
    keyboard = get_time_end_keyboard(start_time)
    await callback_query.message.edit_text(
        f"Выбрано начало: {start_time}\n\nТеперь выберите конец временного слота:",
        reply_markup=keyboard
    )
    await state.set_state(Form.select_time_end)
    await callback_query.answer()

# Обработчик выбора времени конца слота
async def process_time_end(callback_query: CallbackQuery, state: FSMContext):
    end_time = callback_query.data.split(':', 1)[1]
    data = await state.get_data()
    start_time = data.get('current_start_time')
    logger.info(f"[DEBUG] Проверка интервала: start_time={start_time}, end_time={end_time}")
    time_slots = data.get('time_slots', [])
    if is_valid_time_interval(start_time, end_time):
        time_slots.append([start_time, end_time])
        await state.update_data(time_slots=time_slots)
        keyboard = get_add_slot_keyboard()
        await callback_query.message.edit_text(
            f"Добавлен слот: {start_time} - {end_time}\nХотите добавить еще один временной слот?",
            reply_markup=keyboard
        )
        await state.set_state(Form.add_more_slots)
    else:
        keyboard = get_time_start_keyboard()
        await callback_query.message.edit_text(
            "Ошибка: время окончания должно быть позже времени начала.\nПожалуйста, выберите начало временного слота:",
            reply_markup=keyboard
        )
        await state.set_state(Form.select_time_start)
    await callback_query.answer()

# Обработчик выбора добавления дополнительного слота
async def process_add_more_slots(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    
    if choice == "yes":
        # Создаем клавиатуру для выбора времени начала нового слота
        keyboard = get_time_start_keyboard()
        
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
            
            keyboard = get_after_edit_keyboard()
            
            await callback_query.message.edit_text(
                "Временные слоты успешно обновлены.",
                reply_markup=keyboard
            )
            
            await state.set_state(MainMenu.main)
        else:
            # Это новый профиль - продолжаем заполнение
            # Создаем клавиатуру для выбора длительности обеда
            keyboard = get_lunch_duration_keyboard()
            
            await callback_query.message.edit_text(
                "Понял. Какую длительность обеда вы предпочитаете?",
                reply_markup=keyboard
            )
            await state.set_state(Form.lunch_duration)
    
    await callback_query.answer()

# Обработчик выбора длительности обеда
async def process_lunch_duration(callback_query: CallbackQuery, state: FSMContext):
    duration = callback_query.data.split(':')[1]
    
    # Сохраняем выбранную длительность
    await state.update_data(lunch_duration=duration)
    
    # Проверяем, это новый профиль или редактирование
    user_id = callback_query.from_user.id
    user_data = get_user_data(user_id)
    
    if user_data and 'time_slots' not in await state.get_data():
        # Это редактирование - сохраняем новую длительность и возвращаемся в меню редактирования
        user_data['lunch_duration'] = duration
        username = callback_query.from_user.username or f"user{user_id}"
        
        save_user_data(user_id, username, user_data)
        
        keyboard = get_after_edit_keyboard()
        
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
        keyboard = get_favorite_places_keyboard(places_for_office, favorite_places)
        
        await callback_query.message.edit_text(
            "Теперь выберите места, которые вам нравятся. Можно выбрать несколько. Когда закончите, нажмите 'Готово'.",
            reply_markup=keyboard
        )
        
        await state.set_state(Form.favorite_places)
    
    await callback_query.answer()

# Обработчик выбора любимых мест
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
            
            keyboard = get_after_edit_keyboard()
            
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
            keyboard = get_disliked_places_keyboard(places_for_office, disliked_places)
            
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
        keyboard = get_favorite_places_keyboard(places_for_office, favorite_places)
        
        await callback_query.message.edit_text(
            "Теперь выберите места, которые вам нравятся. Можно выбрать несколько. Когда закончите, нажмите 'Готово'.",
            reply_markup=keyboard
        )
    
    await callback_query.answer()

# Обработчик выбора нелюбимых мест
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
            
            keyboard = get_after_edit_keyboard()
            
            await callback_query.message.edit_text(
                "Нелюбимые места успешно обновлены.",
                reply_markup=keyboard
            )
            
            await state.set_state(MainMenu.main)
        else:
            # Это новый профиль или полное редактирование - продолжаем
            # Создаем клавиатуру для выбора размера компании
            company_size = data.get('company_size', [])
            keyboard = get_company_size_keyboard(company_size)
            
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
        keyboard = get_disliked_places_keyboard(places_for_office, disliked_places)
        
        await callback_query.message.edit_text(
            "А теперь выберите места, которые вам не нравятся (чтобы мы их избегали):",
            reply_markup=keyboard
        )
    
    await callback_query.answer()

# Обработчик выбора размера компании
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
            
            keyboard = get_after_edit_keyboard()
            
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
            keyboard = get_confirmation_keyboard()
            
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
        keyboard = get_company_size_keyboard(company_size)
        
        await callback_query.message.edit_text(
            "Почти готово! Укажите предпочитаемый размер компании для обеда (можно выбрать несколько):",
            reply_markup=keyboard
        )
    
    await callback_query.answer()

# Обработчик подтверждения анкеты
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
        keyboard = get_office_keyboard()
        
        await callback_query.message.answer(
            "Для начала, выберите ваш офис:",
            reply_markup=keyboard
        )
        
        await state.set_state(Form.office)
    
    await callback_query.answer()

# Регистрация всех обработчиков
def register_all_handlers(dp):
    # Регистрация обработчиков команд
    dp.message.register(cmd_start, Command("start"))
    
    # Регистрация обработчиков для главного меню
    dp.callback_query.register(process_main_menu, F.data.startswith("menu:"), MainMenu.main)
    
    # Регистрация обработчиков для анкеты
    dp.callback_query.register(process_office, F.data.startswith("office:"), Form.office)
    dp.callback_query.register(process_time_start, F.data.startswith("time_start:"), Form.select_time_start)
    dp.callback_query.register(process_time_end, F.data.startswith("time_end:"), Form.select_time_end)
    dp.callback_query.register(process_add_more_slots, F.data.startswith("add_slot:"), Form.add_more_slots)
    dp.callback_query.register(process_lunch_duration, F.data.startswith("duration:"), Form.lunch_duration)
    dp.callback_query.register(process_favorite_places, F.data.startswith("fav_place:"), Form.favorite_places)
    dp.callback_query.register(process_disliked_places, F.data.startswith("dis_place:"), Form.disliked_places)
    dp.callback_query.register(process_company_size, F.data.startswith("size:"), Form.company_size)
    dp.callback_query.register(process_confirmation, F.data.startswith("confirm:"), Form.confirmation)
    
    # Регистрация обработчиков для записи на обед
    dp.callback_query.register(process_lunch_preference, F.data.startswith("lunch:"), MainMenu.lunch_preference)
    dp.callback_query.register(process_lunch_time_start, F.data.startswith("lunch_time_start:"), MainMenu.lunch_time_start)
    dp.callback_query.register(process_lunch_time_end, F.data.startswith("lunch_time_end:"), MainMenu.lunch_time_end)
    dp.callback_query.register(process_lunch_time_add_more, F.data.startswith("add_slot:"), MainMenu.lunch_time_add_more)
    dp.callback_query.register(process_lunch_place, F.data.startswith("lunch_place:"), MainMenu.lunch_place)
    dp.callback_query.register(process_lunch_company, F.data.startswith("lunch_company:"), MainMenu.lunch_company_size)
    dp.callback_query.register(process_lunch_confirmation, F.data.startswith("lunch_confirm:"), MainMenu.lunch_confirmation)
    
    # Регистрация обработчиков для редактирования профиля
    dp.callback_query.register(process_edit_field, F.data.startswith("edit:"), MainMenu.edit_field)