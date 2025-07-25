import csv
import os
import re
import json
from datetime import datetime, time
import logging

from config import USERS_CSV, PLACES_CSV, USERS_TO_MATCH_JSON

# Глобальные переменные для хранения данных
PLACES = []
PLACES_BY_OFFICE = {}

# Загрузка мест для обеда из CSV
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
    
    # Создаем список только с названиями мест
    place_names = [place['name'] for place in all_places]
    logging.info(f"Загружено {len(all_places)} мест из файла")
    
    PLACES = place_names
    PLACES_BY_OFFICE = places_by_office
    
    return place_names

# Проверка и создание CSV-файла
def ensure_csv_exists():
    if not os.path.exists(USERS_CSV):
        with open(USERS_CSV, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['user_id', 'username', 'office', 'time_slots', 'lunch_duration', 
                            'favorite_places', 'disliked_places', 'company_size', 'last_updated'])

# Проверка и создание JSON-файла
def ensure_json_exists():
    if not os.path.exists(USERS_TO_MATCH_JSON):
        with open(USERS_TO_MATCH_JSON, 'w', encoding='utf-8') as file:
            json.dump([], file, ensure_ascii=False, indent=2)

# Сохранение данных пользователя
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

# Получение данных пользователя
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

# Обновление данных пользователя для матчинга
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

# Получение списка мест для офиса
def get_places_for_office(office):
    if office not in PLACES_BY_OFFICE:
        return PLACES
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

# Конвертация данных в формат для матчинга
def convert_to_match_format(data, username):
    return {
        "office": data.get('office', ''),
        "time_slots": data.get('time_slots', []),
        "max_lunch_duration": int(data.get('lunch_duration', 30)),
        "favourite_places": data.get('favorite_places', []),
        "non_desirable_places": data.get('disliked_places', []),
        "team_size_lst": data.get('company_size', [])
    }
