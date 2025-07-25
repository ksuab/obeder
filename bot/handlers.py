from aiogram import F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import logging
import os
from config import USERS_TO_MATCH_JSON, PLACES_CSV
from aiogram.exceptions import TelegramBadRequest

from .states import Form, MainMenu
from .utils import (
    get_user_data, save_user_data, update_user_to_match, 
    get_places_for_office, is_valid_time_interval, convert_to_match_format,
    run_matcher_and_get_result, read_notified_groups, write_notified_groups, is_user_notified, mark_user_notified
)
from .keyboards import (
    get_office_keyboard, get_time_start_keyboard, get_time_end_keyboard,
    get_add_slot_keyboard, get_lunch_duration_keyboard, get_favorite_places_keyboard,
    get_disliked_places_keyboard, get_company_size_keyboard, get_confirmation_keyboard,
    get_main_menu_keyboard, get_edit_menu_keyboard, get_lunch_preference_keyboard,
    get_back_to_menu_keyboard, get_lunch_favorite_places_keyboard, get_lunch_company_keyboard,
    get_lunch_confirm_keyboard, get_after_edit_keyboard,
    get_lunch_time_start_keyboard, get_lunch_time_end_keyboard, get_duration_keyboard
)
from aiogram import Bot
from aiogram import Router, F, types

logger = logging.getLogger(__name__)

# --- Переместить notify_all_new_groups выше ---
async def notify_all_new_groups(bot: Bot, output_file: str):
    import json
    import logging
    print("notify_all_new_groups CALLED", flush=True)
    logging.info("notify_all_new_groups CALLED")
    notified = read_notified_groups()
    with open(output_file, 'r', encoding='utf-8') as f:
        groups = json.load(f)
    # Получим всех пользователей, участвующих в подборе (users_to_match.json)
    with open('data/users_to_match.json', 'r', encoding='utf-8') as f:
        users_to_match = json.load(f)
    match_usernames = set(u['login'] for u in users_to_match)
    # Получим user_id для этих пользователей из users_data.csv
    import csv
    user_id_map = {}
    try:
        with open('data/users_data.csv', 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if row['username'] in match_usernames:
                    user_id_map[row['username']] = int(row['user_id'])
    except Exception as e:
        logging.error(f"Ошибка при чтении users_data.csv: {e}")
    # Соберём всех пользователей, для которых нашлась группа
    users_with_group = set()
    for group in groups:
        if group.get("lunch_time") and group.get("place"):
            users_with_group.update(group["participants"])
    # Отправим сообщение тем, у кого нет группы
    for username in match_usernames - users_with_group:
        user_id = user_id_map.get(username)
        logging.info(f"[notify_all_new_groups] Нет группы для {username} (user_id={user_id})")
        if user_id:
            try:
                await bot.send_message(user_id, 'Сегодня больше нет подходящих слотов для обеда. Попробуйте завтра!')
                logging.info(f"[notify_all_new_groups] Сообщение 'нет слотов' отправлено {username} (user_id={user_id})")
            except Exception as e:
                logging.warning(f"Не удалось отправить уведомление {username} ({user_id}): {e}")
    # Стандартная логика для найденных групп
    for group in groups:
        group_key = f"{sorted(group['participants'])}_{group.get('lunch_time')}_{group.get('place')}"
        for username in group['participants']:
            if not is_user_notified(username, group_key):
                user_id = user_id_map.get(username)
                logging.info(f"[notify_all_new_groups] Группа: {group}, username={username}, user_id={user_id}")
                if user_id:
                    if group["lunch_time"] and group["place"]:
                        partners = [p for p in group["participants"] if p != username]
                        partners_str = ", ".join(partners) if partners else "Вы обедаете в одиночку."
                        lunch_time = f"{group['lunch_time'][0]}–{group['lunch_time'][1]}"
                        place = group["place"]
                        maps_link = group.get("maps_link", "")
                        msg = (
                            f"🍽 Ваш обед:\n"
                            f"Время: {lunch_time}\n"
                            f"Место: {place}\n"
                            f"Ссылка: {maps_link}\n"
                            f"Партнеры: {partners_str}"
                        )
                    else:
                        msg = "Пока что мы не смогли подобрать вам пару или компанию для обеда, но обязательно подберём!"
                    logging.info(f"[notify_all_new_groups] Пытаюсь отправить сообщение {username} (user_id={user_id}): {msg}")
                    try:
                        await bot.send_message(user_id, msg)
                        logging.info(f"[notify_all_new_groups] Сообщение отправлено {username} (user_id={user_id})")
                    except Exception as e:
                        logging.warning(f"Не удалось отправить уведомление {username} ({user_id}): {e}")
                else:
                    logging.warning(f"[notify_all_new_groups] Не найден user_id для {username}")
                mark_user_notified(username, group_key)

# Заменить все вызовы edit_text на безопасный вариант с обработкой TelegramBadRequest
async def safe_edit_text(message, text, **kwargs):
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        if 'message is not modified' in str(e):
            logging.info(f'[safe_edit_text] Попытка изменить сообщение на тот же текст: "{text[:40]}..."')
        else:
            logging.error(f'[safe_edit_text] TelegramBadRequest: {e}')
            raise

# Базовые функции
async def show_main_menu(message, user_data=None):
    keyboard = get_main_menu_keyboard()
    # Корректно различаем Message и CallbackQuery.message
    if isinstance(message, Message):
        await message.answer("Главное меню:", reply_markup=keyboard)
    else:
        await safe_edit_text(message, "Главное меню:", reply_markup=keyboard)

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

async def cmd_notify_groups(message: types.Message):
    await notify_all_new_groups(message.bot, "data/output.json")
    await message.answer("Рассылка по группам из output.json выполнена.")

router = Router()

# Обработчик для главного меню
async def process_main_menu(callback_query: CallbackQuery, state: FSMContext):
    action = callback_query.data.split(':')[1]
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username or f"user{user_id}"
    user_data = get_user_data(user_id)
    
    if action == "book_lunch":
        # --- ДОБАВЛЕНО: автозаполнение users_to_match.json из профиля ---
        if user_data:
            from .utils import update_user_to_match, run_matcher_and_get_result_async, convert_to_match_format
            import asyncio
            import json
            import logging
            import os
            match_params = convert_to_match_format(user_data, username)
            update_user_to_match(username, match_params)
            # Проверяем, сколько пользователей сейчас в users_to_match.json
            with open("data/users_to_match.json", "r", encoding="utf-8") as f:
                users_to_match = json.load(f)
            if len(users_to_match) >= 2:
                # Очищаем notified_groups.json перед подбором
                notified_path = os.path.join("data", "notified_groups.json")
                if os.path.exists(notified_path):
                    os.remove(notified_path)
                from config import USERS_TO_MATCH_JSON, PLACES_CSV
                output_file = os.path.join("data", "output.json")
                await run_matcher_and_get_result_async(username, USERS_TO_MATCH_JSON, PLACES_CSV, output_file)
                logging.info("BEFORE notify_all_new_groups")
                print("BEFORE notify_all_new_groups", flush=True)
                try:
                    await notify_all_new_groups(callback_query.bot, output_file)
                except Exception as e:
                    logging.error(f"notify_all_new_groups ERROR: {e}")
                    print(f"notify_all_new_groups ERROR: {e}", flush=True)
                logging.info("AFTER notify_all_new_groups")
                print("AFTER notify_all_new_groups", flush=True)
                await safe_edit_text(callback_query.message,
                    "Компания на обед подбирается! Когда найдется подходящая компания, мы вас оповестим!",
                    reply_markup=get_back_to_menu_keyboard()
                )
            else:
                await safe_edit_text(callback_query.message,
                    "Вы записаны, ждите компанию! Как только кто-то ещё запишется, мы подберём группу.",
                    reply_markup=get_back_to_menu_keyboard()
                )
            await state.set_state(MainMenu.main)
            await callback_query.answer()
            return
        keyboard = get_lunch_preference_keyboard()
        await safe_edit_text(callback_query.message,
            "Как вы хотите найти компанию на обед?",
            reply_markup=keyboard
        )
        await state.set_state(MainMenu.lunch_preference)
    
    elif action == "edit_profile":
        keyboard = get_edit_menu_keyboard()
        await safe_edit_text(callback_query.message,
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
            await safe_edit_text(callback_query.message, profile_text, reply_markup=keyboard)
            await state.set_state(MainMenu.main)
        else:
            await safe_edit_text(callback_query.message,
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
            
            await safe_edit_text(callback_query.message,
                "Отлично! Мы используем ваши настройки из профиля для подбора компании на обед сегодня.\n"
                "Когда найдется подходящая компания, мы вас оповестим.",
                reply_markup=get_back_to_menu_keyboard()
            )
            
            await state.set_state(MainMenu.main)
        else:
            await safe_edit_text(callback_query.message,
                "У вас еще нет профиля. Давайте сначала заполним его.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Заполнить профиль", callback_data="menu:create_profile")]
                ])
            )
    
    elif choice == "custom":
        # Пользователь хочет изменить настройки для сегодняшнего обеда
        # Начинаем с выбора времени
        await state.update_data(custom_lunch_data={})
        
        # Сначала выбор офиса
        keyboard = get_office_keyboard()
        await safe_edit_text(callback_query.message,
            "Выберите офис, из которого вы сегодня обедаете:",
            reply_markup=keyboard
        )
        await state.set_state(MainMenu.lunch_office)
    
    await callback_query.answer()

# --- ДОБАВИТЬ: обработчик выбора офиса для custom lunch ---
async def process_lunch_office(callback_query: CallbackQuery, state: FSMContext):
    office = callback_query.data.split(':', 1)[1]
    custom_lunch_data = (await state.get_data()).get('custom_lunch_data', {})
    custom_lunch_data['office'] = office
    await state.update_data(custom_lunch_data=custom_lunch_data)
    # Переход к выбору времени
    keyboard = get_lunch_time_start_keyboard()
    await safe_edit_text(callback_query.message,
        f"Офис выбран: {office}\nТеперь выберите начало временного слота для сегодняшнего обеда:",
        reply_markup=keyboard
    )
    await state.set_state(MainMenu.lunch_time_start)
    await callback_query.answer()

# В custom lunch используем отдельные клавиатуры и callback_data
async def process_lunch_time_start(callback_query: CallbackQuery, state: FSMContext):
    start_time = callback_query.data.split(':', 1)[1]
    await state.update_data(lunch_start_time=start_time)
    keyboard = get_lunch_time_end_keyboard(start_time)
    await safe_edit_text(callback_query.message,
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
        await safe_edit_text(callback_query.message,
            f"Добавлен слот: {start_time} - {end_time}\nХотите добавить еще один временной слот?",
            reply_markup=keyboard
        )
        await state.set_state(MainMenu.lunch_time_add_more)
    else:
        keyboard = get_lunch_time_start_keyboard()
        await safe_edit_text(callback_query.message,
            "Ошибка: время окончания должно быть позже времени начала.\nПожалуйста, выберите начало временного слота:",
            reply_markup=keyboard
        )
        await state.set_state(MainMenu.lunch_time_start)
    await callback_query.answer()

async def process_lunch_time_add_more(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    if choice == "yes":
        keyboard = get_lunch_time_start_keyboard()
        await safe_edit_text(callback_query.message,
            "Выберите начало следующего временного слота:",
            reply_markup=keyboard
        )
        await state.set_state(MainMenu.lunch_time_start)
    else:
        # После выбора всех временных слотов — выбор длительности обеда
        keyboard = get_lunch_duration_keyboard()
        await safe_edit_text(callback_query.message,
            "Выберите длительность обеда на сегодня:",
            reply_markup=keyboard
        )
        await state.set_state(MainMenu.lunch_duration)
    await callback_query.answer()

# Новый обработчик для выбора длительности обеда в custom lunch
async def process_lunch_custom_duration(callback_query: CallbackQuery, state: FSMContext):
    duration = callback_query.data.split(':')[1]
    data = await state.get_data()
    custom_lunch_data = data.get('custom_lunch_data', {})
    custom_lunch_data['max_lunch_duration'] = int(duration)
    await state.update_data(custom_lunch_data=custom_lunch_data)
    office = custom_lunch_data.get('office')
    places_for_office = get_places_for_office(office)
    fav_places = custom_lunch_data.get('favourite_places', [])
    keyboard = get_lunch_favorite_places_keyboard(places_for_office, fav_places)
    await safe_edit_text(callback_query.message,
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
        await safe_edit_text(callback_query.message,
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
        await safe_edit_text(callback_query.message,
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
        if 'max_lunch_duration' in custom_lunch_data:
            match_params['max_lunch_duration'] = custom_lunch_data['max_lunch_duration']
        time_slots_formatted = ", ".join([f"{start}-{end}" for start, end in match_params['time_slots']])
        summary = (
            "Проверьте ваши параметры для подбора обеда сегодня:\n"
            f"- Офис: {match_params.get('office', 'Не выбран')}\n"
            f"- Слоты времени: {time_slots_formatted}\n"
            f"- Длительность обеда: {match_params.get('max_lunch_duration', 'Не выбрана')} минут\n"
            f"- Любимые места: {', '.join(match_params.get('favourite_places', ['Не выбраны']))}\n"
            f"- Размер компании: {', '.join(match_params.get('team_size_lst', ['Не выбран']))}"
        )
        keyboard = get_lunch_confirm_keyboard()
        await safe_edit_text(callback_query.message,
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
        await safe_edit_text(callback_query.message,
            "Выберите предпочтительный размер компании для обеда сегодня:",
            reply_markup=keyboard
        )
    await callback_query.answer()

# Обработчик подтверждения записи на обед
async def process_lunch_confirmation(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username or f"user{user_id}"
    logging.info(f'[DEBUG] process_lunch_confirmation start for {username}')
    choice = callback_query.data.split(':')[1]
    logging.info(f'[DEBUG] process_lunch_confirmation: choice={choice} для {username}')
    
    if choice == "yes":
        logging.info(f'[DEBUG] process_lunch_confirmation: внутри if choice==yes для {username}')
        # Получаем все необходимые данные
        data = await state.get_data()
        logging.info(f'[DEBUG] process_lunch_confirmation: получил state.get_data для {username}')
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
            if 'max_lunch_duration' in custom_lunch_data:
                match_params['max_lunch_duration'] = custom_lunch_data['max_lunch_duration']
            
            # Сохраняем данные для матчинга
            update_user_to_match(username, match_params)
            
            # Запускаем matcher.py и отправляем результат пользователю
            output_file = os.path.join("data", "output.json")
            try:
                logging.info(f'[DEBUG] about to call run_matcher_and_get_result for {username}')
                group = run_matcher_and_get_result(
                    username,
                    USERS_TO_MATCH_JSON,
                    PLACES_CSV,
                    output_file
                )
                logging.info(f'[DEBUG] run_matcher_and_get_result успешно вызван для {username}')
                if group:
                    if group["lunch_time"] and group["place"]:
                        partners = [p for p in group["participants"] if p != username]
                        partners_str = ", ".join(partners) if partners else "Вы обедаете в одиночку."
                        lunch_time = f"{group['lunch_time'][0]}–{group['lunch_time'][1]}"
                        place = group["place"]
                        maps_link = group.get("maps_link", "")
                        msg = (
                            f"🍽 Ваш обед:\n"
                            f"Время: {lunch_time}\n"
                            f"Место: {place}\n"
                            f"Ссылка: {maps_link}\n"
                            f"Партнеры: {partners_str}"
                        )
                    else:
                        # --- ДОБАВЛЕНО: обработка одиночного обеда ---
                        user_data_check = get_user_data(user_id)
                        if user_data_check and user_data_check.get('company_size') == ['1']:
                            msg = "Вы успешно записаны на обед в одиночку! Приятного аппетита :)"
                        else:
                            msg = "Пока что мы не смогли подобрать вам пару или компанию для обеда, но обязательно подберём!"
                else:
                    msg = "Пока что мы не смогли подобрать вам пару или компанию для обеда, но обязательно подберём!"
                await callback_query.message.answer(msg)
                logging.info(f'[DEBUG] сообщение пользователю отправлено для {username}')
                await notify_all_new_groups(callback_query.bot, output_file)
                logging.info(f'[DEBUG] notify_all_new_groups вызван для {username}')
            except Exception as e:
                logging.error(f'[DEBUG] Exception in process_lunch_confirmation for {username}: {e}')
                await callback_query.message.answer(f"Ошибка при подборе компании для обеда: {e}")
            
            await safe_edit_text(callback_query.message,
                "Вы успешно записаны на обед! Мы оповестим вас о найденной компании в ближайшее время.",
                reply_markup=get_back_to_menu_keyboard()
            )
        else:
            await safe_edit_text(callback_query.message,
                "Ошибка: не удалось найти ваш профиль. Пожалуйста, заполните анкету сначала.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Заполнить анкету", callback_data="menu:create_profile")]
                ])
            )
    else:
        logging.info(f'[DEBUG] process_lunch_confirmation: внутри else для {username}')
        # Отмена и возврат в главное меню
        await safe_edit_text(callback_query.message,
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
        
        await safe_edit_text(callback_query.message,
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
        
        await safe_edit_text(callback_query.message,
            "Выберите начало временного слота для обеда:",
            reply_markup=keyboard
        )
        
        await state.set_state(Form.select_time_start)
    
    elif field == "duration":
        # Редактирование длительности обеда
        keyboard = get_lunch_duration_keyboard()
        
        await safe_edit_text(callback_query.message,
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
            
            await safe_edit_text(callback_query.message,
                "Выберите места, которые вам нравятся:",
                reply_markup=keyboard
            )
            
            await state.set_state(Form.favorite_places)
        else:
            await safe_edit_text(callback_query.message,
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
            
            await safe_edit_text(callback_query.message,
                "Выберите места, которые вам не нравятся:",
                reply_markup=keyboard
            )
            
            await state.set_state(Form.disliked_places)
        else:
            await safe_edit_text(callback_query.message,
                "Сначала выберите офис.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Выбрать офис", callback_data="edit:office")]
                ])
            )
    
    elif field == "company_size":
        # Редактирование размера компании
        user_id = callback_query.from_user.id
        username = callback_query.from_user.username or f"user{user_id}"
        user_data = get_user_data(user_id)
        company_size = user_data.get('company_size', []) if user_data else []
        
        keyboard = get_company_size_keyboard(company_size)
        
        await safe_edit_text(callback_query.message,
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
        
        await safe_edit_text(callback_query.message,
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
        
        await safe_edit_text(callback_query.message,
            f"Офис успешно обновлен на: {office}",
            reply_markup=keyboard
        )
        
        await state.set_state(MainMenu.main)
    
    await callback_query.answer()

# --- Исправить вызовы клавиатур для обычной анкеты ---
async def process_time_start(callback_query: CallbackQuery, state: FSMContext):
    start_time = callback_query.data.split(':', 1)[1]
    logger.info(f"[DEBUG] Выбрано начало слота: {start_time}")
    await state.update_data(current_start_time=start_time)
    keyboard = get_time_end_keyboard(start_time)
    await safe_edit_text(callback_query.message,
        f"Выбрано начало: {start_time}\n\nТеперь выберите конец временного слота:",
        reply_markup=keyboard
    )
    await state.set_state(Form.select_time_end)
    await callback_query.answer()

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
        await safe_edit_text(callback_query.message,
            f"Добавлен слот: {start_time} - {end_time}\nХотите добавить еще один временной слот?",
            reply_markup=keyboard
        )
        await state.set_state(Form.add_more_slots)
    else:
        keyboard = get_time_start_keyboard()
        await safe_edit_text(callback_query.message,
            "Ошибка: время окончания должно быть позже времени начала.\nПожалуйста, выберите начало временного слота:",
            reply_markup=keyboard
        )
        await state.set_state(Form.select_time_start)
    await callback_query.answer()

async def process_add_more_slots(callback_query: CallbackQuery, state: FSMContext):
    choice = callback_query.data.split(':')[1]
    if choice == "yes":
        keyboard = get_time_start_keyboard()
        await safe_edit_text(callback_query.message,
            "Выберите начало нового временного слота:",
            reply_markup=keyboard
        )
        await state.set_state(Form.select_time_start)
    else:
        user_id = callback_query.from_user.id
        user_data = get_user_data(user_id)
        if user_data:
            data = await state.get_data()
            time_slots = data.get('time_slots', [])
            user_data['time_slots'] = time_slots
            username = callback_query.from_user.username or f"user{user_id}"
            save_user_data(user_id, username, user_data)
            keyboard = get_after_edit_keyboard()
            await safe_edit_text(callback_query.message,
                "Временные слоты успешно обновлены.",
                reply_markup=keyboard
            )
            await state.set_state(MainMenu.main)
        else:
            keyboard = get_duration_keyboard()
            await safe_edit_text(callback_query.message,
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
        # --- Запуск matcher.py и рассылка результата ---
        from config import USERS_TO_MATCH_JSON, PLACES_CSV
        import os
        output_file = os.path.join("data", "output.json")
        from .utils import run_matcher_and_get_result
        match_params = convert_to_match_format(user_data, username)
        update_user_to_match(username, match_params)
        try:
            group = run_matcher_and_get_result(
                username,
                USERS_TO_MATCH_JSON,
                PLACES_CSV,
                output_file
            )
            if group and group["lunch_time"] and group["place"]:
                partners = [p for p in group["participants"] if p != username]
                partners_str = ", ".join(partners) if partners else "Вы обедаете в одиночку."
                lunch_time = f"{group['lunch_time'][0]}–{group['lunch_time'][1]}"
                place = group["place"]
                maps_link = group.get("maps_link", "")
                msg = (
                    f"🍽 Ваш обед:\n"
                    f"Время: {lunch_time}\n"
                    f"Место: {place}\n"
                    f"Ссылка: {maps_link}\n"
                    f"Партнеры: {partners_str}"
                )
            else:
                msg = "Пока что мы не смогли подобрать вам пару или компанию для обеда, но обязательно подберём!"
            await callback_query.message.answer(msg)
            await notify_all_new_groups(callback_query.bot, output_file)
        except Exception as e:
            await callback_query.message.answer(f"Ошибка при подборе компании для обеда: {e}")
        keyboard = get_after_edit_keyboard()
        await safe_edit_text(callback_query.message,
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
        
        await safe_edit_text(callback_query.message,
            "Теперь выберите места, которые вам нравятся. Можно выбрать несколько. Когда закончите, нажмите 'Готово'.",
            reply_markup=keyboard
        )
        
        await state.set_state(Form.favorite_places)
    
    await callback_query.answer()

# Обработчик выбора любимых мест
async def process_favorite_places(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username or f"user{user_id}"
    choice = callback_query.data.split(':')[1]
    
    # Получаем текущие данные
    data = await state.get_data()
    office = data.get('office')
    favorite_places = data.get('favorite_places', [])
    
    if choice == "done":
        # Проверяем, это новый профиль или редактирование
        user_id = callback_query.from_user.id
        user_data = get_user_data(user_id)
        import logging
        logging.info(f'[DEBUG] user_id={user_id}, user_data={user_data} в process_favorite_places')
        if user_data:
            logging.info(f'[DEBUG] Ветка редактирования профиля для {username} в process_favorite_places')
            # Это редактирование - сохраняем новые любимые места и возвращаемся в меню редактирования
            user_data['favorite_places'] = favorite_places
            username = callback_query.from_user.username or f"user{user_id}"
            save_user_data(user_id, username, user_data)
            # --- Запуск matcher.py и рассылка результата ---
            from config import USERS_TO_MATCH_JSON, PLACES_CSV
            import os
            output_file = os.path.join("data", "output.json")
            from .utils import run_matcher_and_get_result
            match_params = convert_to_match_format(user_data, username)
            update_user_to_match(username, match_params)
            try:
                group = run_matcher_and_get_result(
                    username,
                    USERS_TO_MATCH_JSON,
                    PLACES_CSV,
                    output_file
                )
                if group and group["lunch_time"] and group["place"]:
                    partners = [p for p in group["participants"] if p != username]
                    partners_str = ", ".join(partners) if partners else "Вы обедаете в одиночку."
                    lunch_time = f"{group['lunch_time'][0]}–{group['lunch_time'][1]}"
                    place = group["place"]
                    maps_link = group.get("maps_link", "")
                    msg = (
                        f"🍽 Ваш обед:\n"
                        f"Время: {lunch_time}\n"
                        f"Место: {place}\n"
                        f"Ссылка: {maps_link}\n"
                        f"Партнеры: {partners_str}"
                    )
                else:
                    msg = "Пока что мы не смогли подобрать вам пару или компанию для обеда, но обязательно подберём!"
                await callback_query.message.answer(msg)
                await notify_all_new_groups(callback_query.bot, output_file)
            except Exception as e:
                await callback_query.message.answer(f"Ошибка при подборе компании для обеда: {e}")
            keyboard = get_after_edit_keyboard()
            await safe_edit_text(callback_query.message,
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
            
            await safe_edit_text(callback_query.message,
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
        
        await safe_edit_text(callback_query.message,
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
        import logging
        logging.info(f'[DEBUG] user_id={user_id}, user_data={user_data} в process_disliked_places')
        if user_data:
            logging.info(f'[DEBUG] Ветка редактирования профиля для {username} в process_disliked_places')
            # Это редактирование - сохраняем новые нелюбимые места и возвращаемся в меню редактирования
            user_data['disliked_places'] = disliked_places
            username = callback_query.from_user.username or f"user{user_id}"
            
            save_user_data(user_id, username, user_data)
            
            # --- Запуск matcher.py и рассылка результата ---
            from config import USERS_TO_MATCH_JSON, PLACES_CSV
            import os
            output_file = os.path.join("data", "output.json")
            from .utils import run_matcher_and_get_result
            match_params = convert_to_match_format(user_data, username)
            update_user_to_match(username, match_params)
            try:
                group = run_matcher_and_get_result(
                    username,
                    USERS_TO_MATCH_JSON,
                    PLACES_CSV,
                    output_file
                )
                if group and group["lunch_time"] and group["place"]:
                    partners = [p for p in group["participants"] if p != username]
                    partners_str = ", ".join(partners) if partners else "Вы обедаете в одиночку."
                    lunch_time = f"{group['lunch_time'][0]}–{group['lunch_time'][1]}"
                    place = group["place"]
                    maps_link = group.get("maps_link", "")
                    msg = (
                        f"🍽 Ваш обед:\n"
                        f"Время: {lunch_time}\n"
                        f"Место: {place}\n"
                        f"Ссылка: {maps_link}\n"
                        f"Партнеры: {partners_str}"
                    )
                else:
                    msg = "Пока что мы не смогли подобрать вам пару или компанию для обеда, но обязательно подберём!"
                await callback_query.message.answer(msg)
                await notify_all_new_groups(callback_query.bot, output_file)
            except Exception as e:
                await callback_query.message.answer(f"Ошибка при подборе компании для обеда: {e}")
            keyboard = get_after_edit_keyboard()
            await safe_edit_text(callback_query.message,
                "Нелюбимые места успешно обновлены.",
                reply_markup=keyboard
            )
            await state.set_state(MainMenu.main)
        else:
            # Это новый профиль или полное редактирование - продолжаем
            # Создаем клавиатуру для выбора размера компании
            company_size = data.get('company_size', [])
            keyboard = get_company_size_keyboard(company_size)
            
            await safe_edit_text(callback_query.message,
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
        
        await safe_edit_text(callback_query.message,
            "А теперь выберите места, которые вам не нравятся (чтобы мы их избегали):",
            reply_markup=keyboard
        )
    
    await callback_query.answer()

# Обработчик выбора размера компании
async def process_company_size(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username or f"user{user_id}"
    choice = callback_query.data.split(':')[1]
    # Получаем текущие данные
    data = await state.get_data()
    company_size = data.get('company_size', [])
    
    if choice == "done":
        # Проверяем, это новый профиль или редактирование
        user_id = callback_query.from_user.id
        user_data = get_user_data(user_id)
        import logging
        logging.info(f'[DEBUG] user_id={user_id}, user_data={user_data} в process_company_size')
        if user_data:
            logging.info(f'[DEBUG] Ветка редактирования профиля для {username} в process_company_size')
            # Это редактирование - сохраняем новый размер компании и возвращаемся в меню редактирования
            user_data['company_size'] = company_size
            username = callback_query.from_user.username or f"user{user_id}"
            
            save_user_data(user_id, username, user_data)
            
            # --- Запуск matcher.py и рассылка результата ---
            from config import USERS_TO_MATCH_JSON, PLACES_CSV
            import os
            output_file = os.path.join("data", "output.json")
            from .utils import run_matcher_and_get_result
            match_params = convert_to_match_format(user_data, username)
            update_user_to_match(username, match_params)
            try:
                group = run_matcher_and_get_result(
                    username,
                    USERS_TO_MATCH_JSON,
                    PLACES_CSV,
                    output_file
                )
                if group and group["lunch_time"] and group["place"]:
                    partners = [p for p in group["participants"] if p != username]
                    partners_str = ", ".join(partners) if partners else "Вы обедаете в одиночку."
                    lunch_time = f"{group['lunch_time'][0]}–{group['lunch_time'][1]}"
                    place = group["place"]
                    maps_link = group.get("maps_link", "")
                    msg = (
                        f"🍽 Ваш обед:\n"
                        f"Время: {lunch_time}\n"
                        f"Место: {place}\n"
                        f"Ссылка: {maps_link}\n"
                        f"Партнеры: {partners_str}"
                    )
                else:
                    msg = "Пока что мы не смогли подобрать вам пару или компанию для обеда, но обязательно подберём!"
                await callback_query.message.answer(msg)
                await notify_all_new_groups(callback_query.bot, output_file)
            except Exception as e:
                await callback_query.message.answer(f"Ошибка при подборе компании для обеда: {e}")
            keyboard = get_after_edit_keyboard()
            await safe_edit_text(callback_query.message,
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
            
            await safe_edit_text(callback_query.message,
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
        
        await safe_edit_text(callback_query.message,
            "Почти готово! Укажите предпочитаемый размер компании для обеда (можно выбрать несколько):",
            reply_markup=keyboard
        )
    
    await callback_query.answer()

# Обработчик подтверждения анкеты
async def process_confirmation(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username or f"user{user_id}"
    logging.info(f'[DEBUG] process_confirmation start for {username}')
    choice = callback_query.data.split(':')[1]
    logging.info(f'[DEBUG] process_confirmation: choice={choice} для {username}')
    if choice == "yes":
        logging.info(f'[DEBUG] process_confirmation: внутри if choice==yes для {username}')
        data = await state.get_data()
        logging.info(f'[DEBUG] process_confirmation: получил state.get_data для {username}')
        if not data.get('favorite_places'):
            data['favorite_places'] = []
        if not data.get('disliked_places'):
            data['disliked_places'] = []
        if not data.get('company_size'):
            data['company_size'] = []
        save_user_data(user_id, username, data)
        logging.info(f'[DEBUG] после save_user_data для {username}')
        match_params = convert_to_match_format(data, username)
        update_user_to_match(username, match_params)
        logging.info(f'[DEBUG] после update_user_to_match для {username}')
        output_file = os.path.join("data", "output.json")
        try:
            logging.info(f'[DEBUG] about to call run_matcher_and_get_result for {username}')
            group = run_matcher_and_get_result(
                username,
                USERS_TO_MATCH_JSON,
                PLACES_CSV,
                output_file
            )
            logging.info(f'[DEBUG] run_matcher_and_get_result успешно вызван для {username}')
            if group:
                if group["lunch_time"] and group["place"]:
                    partners = [p for p in group["participants"] if p != username]
                    partners_str = ", ".join(partners) if partners else "Вы обедаете в одиночку."
                    lunch_time = f"{group['lunch_time'][0]}–{group['lunch_time'][1]}"
                    place = group["place"]
                    maps_link = group.get("maps_link", "")
                    msg = (
                        f"🍽 Ваш обед:\n"
                        f"Время: {lunch_time}\n"
                        f"Место: {place}\n"
                        f"Ссылка: {maps_link}\n"
                        f"Партнеры: {partners_str}"
                    )
                else:
                    msg = "Пока что мы не смогли подобрать вам пару или компанию для обеда, но обязательно подберём!"
            else:
                msg = "Пока что мы не смогли подобрать вам пару или компанию для обеда, но обязательно подберём!"
            await callback_query.message.answer(msg)
            logging.info(f'[DEBUG] сообщение пользователю отправлено для {username}')
            await notify_all_new_groups(callback_query.bot, output_file)
            logging.info(f'[DEBUG] notify_all_new_groups вызван для {username}')
        except Exception as e:
            logging.error(f'[DEBUG] Exception in process_confirmation for {username}: {e}')
            await callback_query.message.answer(f"Ошибка при подборе компании для обеда: {e}")
        await safe_edit_text(callback_query.message,
            "Спасибо! Ваша анкета сохранена. Теперь вы можете записаться на обед или изменить настройки.")
        await show_main_menu(callback_query.message, data)
        await state.clear()
        await state.set_state(MainMenu.main)
    else:
        logging.info(f'[DEBUG] process_confirmation: внутри else для {username}')
        await safe_edit_text(callback_query.message,
            "Хорошо, давайте заполним анкету заново.")
        await state.clear()
        keyboard = get_office_keyboard()
        await callback_query.message.answer(
            "Для начала, выберите ваш офис:",
            reply_markup=keyboard
        )
        await state.set_state(Form.office)
    await callback_query.answer()

# Обработчик кнопки "Назад" на этапах анкетирования
async def process_back_in_form(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_state = await state.get_state()
    # Определяем куда возвращаться
    if current_state == Form.select_time_start.state:
        # Назад к выбору офиса
        keyboard = get_office_keyboard()
        await safe_edit_text(callback_query.message, "Выберите ваш офис:", reply_markup=keyboard)
        await state.set_state(Form.office)
    elif current_state == Form.select_time_end.state:
        # Назад к выбору начала слота
        keyboard = get_time_start_keyboard()
        await safe_edit_text(callback_query.message, "Выберите начало временного слота:", reply_markup=keyboard)
        await state.set_state(Form.select_time_start)
    elif current_state == Form.add_more_slots.state:
        # Назад к выбору конца слота
        last_slot = data.get('time_slots', [])[-1][0] if data.get('time_slots') else None
        keyboard = get_time_end_keyboard(last_slot) if last_slot else get_time_end_keyboard('11:00')
        await safe_edit_text(callback_query.message, "Выберите время окончания слота:", reply_markup=keyboard)
        await state.set_state(Form.select_time_end)
    elif current_state == Form.lunch_duration.state:
        # Назад к добавлению еще одного слота
        keyboard = get_add_slot_keyboard()
        await safe_edit_text(callback_query.message, "Добавить еще один временной слот?", reply_markup=keyboard)
        await state.set_state(Form.add_more_slots)
    elif current_state == Form.favorite_places.state:
        # Назад к выбору нелюбимых мест
        office = data.get('office')
        places_for_office = get_places_for_office(office)
        disliked_places = data.get('disliked_places', [])
        keyboard = get_disliked_places_keyboard(places_for_office, disliked_places)
        await safe_edit_text(callback_query.message, "Выберите нелюбимые места:", reply_markup=keyboard)
        await state.set_state(Form.disliked_places)
    elif current_state == Form.company_size.state:
        # Назад к выбору размера компании
        company_size = data.get('company_size', [])
        keyboard = get_company_size_keyboard(company_size)
        await safe_edit_text(callback_query.message, "Выберите предпочитаемый размер компании:", reply_markup=keyboard)
        await state.set_state(Form.company_size)
    elif current_state == Form.confirmation.state:
        # Назад к выбору размера компании
        company_size = data.get('company_size', [])
        keyboard = get_company_size_keyboard(company_size)
        await safe_edit_text(callback_query.message, "Выберите предпочитаемый размер компании:", reply_markup=keyboard)
        await state.set_state(Form.company_size)
    else:
        await callback_query.message.answer("Возврат невозможен на этом этапе.")
    await callback_query.answer()

# Обработчик кнопки "Назад" для custom lunch
async def process_back_in_custom_lunch(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_state = await state.get_state()
    custom_lunch_data = data.get('custom_lunch_data', {})
    if current_state == MainMenu.lunch_office.state:
        # Назад к меню выбора типа записи
        keyboard = get_lunch_preference_keyboard()
        await safe_edit_text(callback_query.message, "Выберите способ записи на обед:", reply_markup=keyboard)
        await state.set_state(MainMenu.lunch_preference)
    elif current_state == MainMenu.lunch_time_start.state:
        # Назад к выбору офиса
        keyboard = get_office_keyboard()
        await safe_edit_text(callback_query.message, "Выберите офис:", reply_markup=keyboard)
        await state.set_state(MainMenu.lunch_office)
    elif current_state == MainMenu.lunch_time_end.state:
        # Назад к выбору времени начала
        keyboard = get_lunch_time_start_keyboard()
        await safe_edit_text(callback_query.message, "Выберите начало временного слота:", reply_markup=keyboard)
        await state.set_state(MainMenu.lunch_time_start)
    elif current_state == MainMenu.lunch_time_add_more.state:
        # Назад к выбору времени конца
        last_slot = custom_lunch_data.get('time_slots', [])[-1][0] if custom_lunch_data.get('time_slots') else None
        keyboard = get_lunch_time_end_keyboard(last_slot) if last_slot else get_lunch_time_end_keyboard('11:00')
        await safe_edit_text(callback_query.message, "Выберите время окончания слота:", reply_markup=keyboard)
        await state.set_state(MainMenu.lunch_time_end)
    elif current_state == MainMenu.lunch_duration.state:
        # Назад к добавлению еще одного слота
        keyboard = get_lunch_duration_keyboard()
        await safe_edit_text(callback_query.message, "Выберите длительность обеда:", reply_markup=keyboard)
        await state.set_state(MainMenu.lunch_duration)
    elif current_state == MainMenu.lunch_place.state:
        # Назад к выбору любимых мест
        office = custom_lunch_data.get('office')
        places_for_office = get_places_for_office(office)
        fav_places = custom_lunch_data.get('favourite_places', [])
        keyboard = get_lunch_favorite_places_keyboard(places_for_office, fav_places)
        await safe_edit_text(callback_query.message, "Выберите любимые места:", reply_markup=keyboard)
        await state.set_state(MainMenu.lunch_place)
    elif current_state == MainMenu.lunch_company_size.state:
        # Назад к выбору размера компании
        sizes = custom_lunch_data.get('team_size_lst', [])
        keyboard = get_lunch_company_keyboard(sizes)
        await safe_edit_text(callback_query.message, "Выберите предпочитаемый размер компании:", reply_markup=keyboard)
        await state.set_state(MainMenu.lunch_company_size)
    elif current_state == MainMenu.lunch_confirmation.state:
        # Назад к выбору размера компании
        sizes = custom_lunch_data.get('team_size_lst', [])
        keyboard = get_lunch_company_keyboard(sizes)
        await safe_edit_text(callback_query.message, "Выберите предпочитаемый размер компании:", reply_markup=keyboard)
        await state.set_state(MainMenu.lunch_company_size)
    else:
        await callback_query.message.answer("Возврат невозможен на этом этапе.")
    await callback_query.answer()

# Регистрация всех обработчиков
def register_all_handlers(dp):
    # Регистрация обработчиков команд
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(cmd_notify_groups, Command("notify_groups"))

    # Регистрация обработчиков для главного меню
    dp.callback_query.register(process_main_menu, F.data.startswith("menu:"))
    
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
    dp.callback_query.register(process_back_in_form, F.data.startswith("back:"), Form.select_time_start, Form.select_time_end, Form.add_more_slots, Form.lunch_duration, Form.favorite_places, Form.disliked_places, Form.company_size, Form.confirmation)
    
    # Регистрация обработчиков для записи на обед
    dp.callback_query.register(process_lunch_preference, F.data.startswith("lunch:"), MainMenu.lunch_preference)
    dp.callback_query.register(process_lunch_office, F.data.startswith("office:"), MainMenu.lunch_office)
    dp.callback_query.register(process_lunch_time_start, F.data.startswith("lunch_time_start:"), MainMenu.lunch_time_start)
    dp.callback_query.register(process_lunch_time_end, F.data.startswith("lunch_time_end:"), MainMenu.lunch_time_end)
    dp.callback_query.register(process_lunch_time_add_more, F.data.startswith("add_slot:"), MainMenu.lunch_time_add_more)
    dp.callback_query.register(process_lunch_custom_duration, F.data.startswith("lunch_duration:"), MainMenu.lunch_duration)
    dp.callback_query.register(process_lunch_place, F.data.startswith("lunch_place:"), MainMenu.lunch_place)
    dp.callback_query.register(process_lunch_company, F.data.startswith("lunch_company:"), MainMenu.lunch_company_size)
    dp.callback_query.register(process_lunch_confirmation, F.data.startswith("lunch_confirm:"), MainMenu.lunch_confirmation)
    dp.callback_query.register(process_back_in_custom_lunch, F.data.startswith("back:"), MainMenu.lunch_office, MainMenu.lunch_time_start, MainMenu.lunch_time_end, MainMenu.lunch_time_add_more, MainMenu.lunch_duration, MainMenu.lunch_place, MainMenu.lunch_company_size, MainMenu.lunch_confirmation)
    
    # Регистрация обработчиков для редактирования профиля
    dp.callback_query.register(process_edit_field, F.data.startswith("edit:"), MainMenu.edit_field)