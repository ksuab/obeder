import csv
import os
import re
import json
from datetime import datetime, time
import logging
import subprocess
from filelock import FileLock
import asyncio

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
    time_slots_str = ';'.join([f"{start}-{end}" for start, end in data['time_slots']])
    favorite_places_str = ';'.join(data['favorite_places'])
    disliked_places_str = ';'.join(data['disliked_places'])
    company_size_str = ';'.join(data['company_size'])
    lock_path = USERS_CSV + '.lock'
    with FileLock(lock_path, timeout=10):
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
    lock_path = USERS_TO_MATCH_JSON + '.lock'
    import logging
    with FileLock(lock_path, timeout=10):
        users = []
        user_exists = False
        if os.path.exists(USERS_TO_MATCH_JSON):
            with open(USERS_TO_MATCH_JSON, 'r', encoding='utf-8') as file:
                try:
                    users = json.load(file)
                except json.JSONDecodeError:
                    users = []
        # Проверяем, есть ли уже такой пользователь
        for user in users:
            if user.get('login') == username:
                user['parameters'] = parameters
                user_exists = True
                logging.info(f"[update_user_to_match] Обновлен пользователь: {username}")
                break
        if not user_exists:
            users.append({
                "login": username,
                "parameters": parameters
            })
            logging.info(f"[update_user_to_match] Добавлен новый пользователь: {username}")
        # Сохраняем всех пользователей обратно
        with open(USERS_TO_MATCH_JSON, 'w', encoding='utf-8') as file:
            json.dump(users, file, ensure_ascii=False, indent=2)
        logging.info(f"[update_user_to_match] Всего пользователей: {len(users)}")

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

# Запуск matcher.py и получение результата для пользователя

def run_matcher_and_get_result(user_login, users_file, places_file, output_file):
    print("=== DEBUG: run_matcher_and_get_result вызван ===")
    import logging
    logging.info("=== DEBUG: run_matcher_and_get_result вызван ===")
    log_path = 'logs/bot.log'
    matcher_path = os.path.abspath('matcher.py')
    logging.info(f"[DEBUG] run_matcher_and_get_result вызван для {user_login}, matcher_path={matcher_path}")
    with open(log_path, 'a', encoding='utf-8') as log_file:
        log_file.write(f"\n[run_matcher_and_get_result] Запуск matcher.py для {user_login} (matcher_path={matcher_path})\n")
        try:
            result = subprocess.run([
                "python3", matcher_path,
                "-i", users_file,
                "-p", places_file,
                "-o", output_file
            ], check=True, capture_output=True, text=True)
            log_file.write(f"[matcher.py stdout]\n{result.stdout}\n")
            log_file.write(f"[matcher.py stderr]\n{result.stderr}\n")
            logging.info(f"[DEBUG] matcher.py успешно завершён для {user_login}")
        except subprocess.CalledProcessError as e:
            log_file.write(f"[matcher.py ERROR] {e}\n[stdout]\n{e.stdout}\n[stderr]\n{e.stderr}\n")
            logging.error(f"[DEBUG] matcher.py завершился с ошибкой для {user_login}: {e}")
            raise
        except Exception as e:
            log_file.write(f"[matcher.py UNEXPECTED ERROR] {e}\n")
            logging.error(f"[DEBUG] matcher.py неожиданная ошибка для {user_login}: {e}")
            raise
    with open(output_file, "r", encoding="utf-8") as f:
        results = json.load(f)
    for group in results:
        if user_login in group["participants"]:
            return group
    return None

async def run_matcher_and_get_result_async(user_login, users_file, places_file, output_file):
    import sys
    import logging
    logging.info("=== DEBUG: run_matcher_and_get_result_async вызван ===")
    matcher_path = os.path.abspath('matcher.py')
    proc = await asyncio.create_subprocess_exec(
        sys.executable, matcher_path,
        "-i", users_file,
        "-p", places_file,
        "-o", output_file,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    logging.info(f"[matcher.py stdout]\n{stdout.decode()}")
    logging.info(f"[matcher.py stderr]\n{stderr.decode()}")
    with open(output_file, "r", encoding="utf-8") as f:
        results = json.load(f)
    for group in results:
        if user_login in group["participants"]:
            return group
    return None

NOTIFIED_GROUPS_JSON = os.path.join('data', 'notified_groups.json')

def read_notified_groups():
    if not os.path.exists(NOTIFIED_GROUPS_JSON):
        return {}
    try:
        with open(NOTIFIED_GROUPS_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def write_notified_groups(data):
    with open(NOTIFIED_GROUPS_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_user_notified(username, group_key):
    notified = read_notified_groups()
    return notified.get(username) == group_key

def mark_user_notified(username, group_key):
    notified = read_notified_groups()
    notified[username] = group_key
    write_notified_groups(notified)
