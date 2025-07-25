#!/usr/bin/env python3
import json
import csv
import argparse
import sys
from datetime import datetime, time, timedelta
from typing import List, Dict, Tuple, Optional, Set
from itertools import combinations
import logging
import os

# === Диагностика запуска matcher.py ===
import os
os.makedirs('logs', exist_ok=True)
with open('logs/matcher.log', 'a', encoding='utf-8') as f:
    f.write('=== matcher.py: запуск скрипта ===\n')
print('=== matcher.py: запуск скрипта ===', flush=True)
print('=== DEBUG: matcher.py действительно запускается ===', flush=True)

# Настройка логирования matcher.py
os.makedirs('logs', exist_ok=True)
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('logs/matcher.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logging.info('=== LOGGING CONFIGURED ===')
print('=== LOGGING CONFIGURED PRINT ===', flush=True)


def validate_input(data: List[Dict]) -> None:
    """Проверяет, что входные данные не пустые."""
    if not data:
        raise ValueError("Входной JSON пуст.")
    if not isinstance(data, list):
        raise ValueError("Ожидается список пользователей.")
    for i, user in enumerate(data):
        if "login" not in user or "parameters" not in user:
            raise ValueError(f"Неверный формат данных у пользователя {i}")
        params = user["parameters"]
        required = ["office", "time_slots", "max_lunch_duration", "favourite_places", "non_desirable_places", "team_size_lst"]
        for key in required:
            if key not in params:
                raise ValueError(f"Не хватает параметра '{key}' у пользователя {user['login']}")


def parse_time(time_str: str) -> time:
    """Парсит строку времени в объект time."""
    return datetime.strptime(time_str, "%H:%M").time()


def is_valid_time_slot(start: str, end: str) -> bool:
    """Проверяет, что начало слота раньше конца."""
    try:
        start_time = parse_time(start)
        end_time = parse_time(end)
        return start_time < end_time
    except ValueError:
        return False


def clean_time_slots(slots: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Очищает и объединяет пересекающиеся временные слоты."""
    valid_slots = [s for s in slots if is_valid_time_slot(s[0], s[1])]
    if not valid_slots:
        return []
    intervals = [(parse_time(s[0]), parse_time(s[1])) for s in valid_slots]
    intervals.sort()
    merged = [intervals[0]]
    for current in intervals[1:]:
        last = merged[-1]
        if current[0] <= last[1]:
            merged[-1] = (last[0], max(last[1], current[1]))
        else:
            merged.append(current)
    return [(t[0].strftime("%H:%M"), t[1].strftime("%H:%M")) for t in merged]


def clean_preferences(user: Dict) -> None:
    """Исключает нежелательные места из любимых."""
    fav = set(user["parameters"]["favourite_places"])
    non_des = set(user["parameters"]["non_desirable_places"])
    cleaned = fav - non_des
    user["parameters"]["favourite_places"] = list(cleaned)


def load_places(filename: str) -> List[Dict]:
    """Загружает список мест из CSV."""
    try:
        with open(filename, mode='r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            places = []
            for row in reader:
                row["time_to_go_min"] = int(row["time_to_go_min"])
                row["max_table_size"] = int(row["max_table_size"])
                row["avg_bill"] = float(row["avg_bill"])
                row["min_time_to_eat"] = int(row["min_time_to_eat"])
                places.append(row)
        return places
    except Exception as e:
        print(f"❌ Ошибка загрузки places.csv: {e}")
        sys.exit(1)


def find_common_time_slot(users: List[Dict]) -> Optional[Tuple[str, str]]:
    """
    Находит общий временной слот, который начинается не раньше, чем через 5 минут от текущего времени.
    """
    if any(not u["parameters"]["time_slots"] for u in users):
        return ("12:00", "13:00")  # fallback

    user_time_slots = []
    for user in users:
        slots = []
        for s in user["parameters"]["time_slots"]:
            start_t = parse_time(s[0])
            end_t = parse_time(s[1])
            if start_t < end_t:
                slots.append((start_t, end_t))
        user_time_slots.append(slots)

    common = user_time_slots[0]
    for user_slots in user_time_slots[1:]:
        new_common = []
        for s1 in common:
            for s2 in user_slots:
                if s1[0] < s2[1] and s2[0] < s1[1]:
                    start = max(s1[0], s2[0])
                    end = min(s1[1], s2[1])
                    if start < end:
                        new_common.append((start, end))
        common = new_common
        if not common:
            return None

    max_allowed_duration = min(u["parameters"]["max_lunch_duration"] for u in users)
    max_duration_td = timedelta(minutes=max_allowed_duration)

    now = datetime.now().time()
    min_start = (datetime.combine(datetime.today(), now) + timedelta(minutes=5)).time()

    for start, end in sorted(common):
        if start < min_start:
            continue  # пропускаем слоты, которые уже прошли или слишком близко
        slot_duration = datetime.combine(datetime.today(), end) - datetime.combine(datetime.today(), start)
        if slot_duration >= max_duration_td:
            optimal_end = (datetime.combine(datetime.today(), start) + max_duration_td).time()
            if optimal_end <= end:
                return (start.strftime("%H:%M"), optimal_end.strftime("%H:%M"))

    return None


def is_team_size_compatible(users: List[Dict], team_size: int) -> bool:
    """
    Проверяет, что размер группы (team_size) разрешён КАЖДЫМ пользователем.
    Каждый пользователь может указать несколько форматов: ["2", "6+", "18+"] и т.д.
    Достаточно, чтобы ХОТЯ БЫ ОДИН из форматов разрешал данный размер.
    """
    for user in users:
        allowed = False
        for size_range in user["parameters"]["team_size_lst"]:
            if size_range == "2":
                if team_size == 2:
                    allowed = True
                    break
            elif size_range == "3-5":
                if 3 <= team_size <= 5:
                    allowed = True
                    break
            elif size_range.endswith("+"):
                try:
                    min_size = int(size_range.replace("+", ""))
                    if team_size >= min_size:
                        allowed = True
                        break
                except ValueError:
                    continue  # игнорируем некорректные форматы
            # Если формат не распознан — пропускаем
        if not allowed:
            return False  # если хоть один пользователь не разрешает размер — всё
    return True


def find_compatible_places(users: List[Dict], places: List[Dict]) -> List[Dict]:
    debug_msg = f"DEBUG: find_compatible_places: users={users}, places_office={[p['name'] for p in places if p['office_name'].strip().lower()==users[0]['parameters']['office'].strip().lower()]}"
    print(debug_msg, flush=True)
    with open('logs/matcher_debug.log', 'a', encoding='utf-8') as dbg:
        dbg.write(debug_msg + '\n')
    office = users[0]["parameters"]["office"].strip().lower()
    team_size = len(users)

    # Проверка офиса
    if any(user["parameters"]["office"].strip().lower() != office for user in users):
        return []

    # Проверка размера группы
    if not is_team_size_compatible(users, team_size):
        return []

    # --- Изменено: если одиночка, подбирать любое место офиса, кроме non_desirable_places ---
    if len(users) == 1:
        non_des = set(users[0]["parameters"].get("non_desirable_places", []))
        compatible = []
        for place in places:
            if place["office_name"].strip().lower() != office:
                continue
            if place["name"] in non_des:
                continue
            if place["max_table_size"] < team_size:
                continue
            compatible.append(place)
        print(f"DEBUG: одиночка, подходящие места: {[p['name'] for p in compatible]}", flush=True)
        with open('logs/matcher_debug.log', 'a', encoding='utf-8') as dbg:
            dbg.write(f"DEBUG: одиночка, подходящие места: {[p['name'] for p in compatible]}\n")
        return compatible

    # Находим ОБЩИЕ любимые места
    common_fav = None
    for user in users:
        fav_set = set(user["parameters"]["favourite_places"])
        common_fav = fav_set if common_fav is None else common_fav & fav_set
    compatible = []
    for place in places:
        if place["office_name"].strip().lower() != office:
            continue
        if place["max_table_size"] < team_size:
            continue
        # Если есть общие любимые места — только они
        if common_fav and place["name"] not in common_fav:
            continue
        # Если нет общих любимых — брать любые, кроме нелюбимых
        if not common_fav:
            skip = False
            for user in users:
                if place["name"] in user["parameters"].get("non_desirable_places", []):
                    skip = True
                    break
            if skip:
                continue
        compatible.append(place)
    print(f"DEBUG: совместимые места: {[p['name'] for p in compatible]}", flush=True)
    with open('logs/matcher_debug.log', 'a', encoding='utf-8') as dbg:
        dbg.write(f"DEBUG: совместимые места: {[p['name'] for p in compatible]}\n")
    return compatible


def process_users(users: List[Dict]) -> List[Dict]:
    """Очищает и нормализует данные пользователей."""
    for user in users:
        user["parameters"]["time_slots"] = clean_time_slots(user["parameters"]["time_slots"])
        clean_preferences(user)
    return users


def match_lunch_group(users: List[Dict], places: List[Dict]) -> Optional[Dict]:
    debug_msg = f"DEBUG: match_lunch_group: users={users}"
    print(debug_msg, flush=True)
    with open('logs/matcher_debug.log', 'a', encoding='utf-8') as dbg:
        dbg.write(debug_msg + '\n')
    common_slot = find_common_time_slot(users)
    print(f"DEBUG: common_slot={common_slot}", flush=True)
    with open('logs/matcher_debug.log', 'a', encoding='utf-8') as dbg:
        dbg.write(f"DEBUG: common_slot={common_slot}\n")
    if common_slot is None:
        print("DEBUG: common_slot is None, return None", flush=True)
        with open('logs/matcher_debug.log', 'a', encoding='utf-8') as dbg:
            dbg.write("DEBUG: common_slot is None, return None\n")
        return None

    compatible_places = find_compatible_places(users, places)
    print(f"DEBUG: compatible_places={[p['name'] for p in compatible_places]}", flush=True)
    with open('logs/matcher_debug.log', 'a', encoding='utf-8') as dbg:
        dbg.write(f"DEBUG: compatible_places={[p['name'] for p in compatible_places]}\n")
    if not compatible_places:
        print("DEBUG: compatible_places is empty, return None", flush=True)
        with open('logs/matcher_debug.log', 'a', encoding='utf-8') as dbg:
            dbg.write("DEBUG: compatible_places is empty, return None\n")
        return None

    best_place = min(compatible_places, key=lambda p: p["time_to_go_min"])
    return {
        "participants": sorted(u["login"] for u in users),
        "lunch_time": common_slot,
        "place": best_place["name"],
        "maps_link": best_place["maps_link"]
    }


def find_all_lunch_groups(users: List[Dict], places: List[Dict]) -> List[Dict]:
    if len(users) == 1:
        team_size_lst = users[0]["parameters"].get("team_size_lst", [])
        if "1" in team_size_lst:
            match = match_lunch_group(users, places)
            return [match] if match else []
        else:
            return []

    for user in users:
        if "duration_min" in user["parameters"]:
            user["parameters"]["max_lunch_duration"] = user["parameters"].pop("duration_min")

    result = []
    used = set()

    # Сортируем: сначала "гибкие", потом "жёсткие"
    users_sorted = sorted(
        users,
        key=lambda u: (
            len(u["parameters"]["time_slots"]) if u["parameters"]["time_slots"] else 0,
            -u["parameters"]["max_lunch_duration"],
            len(u["parameters"]["favourite_places"])
        )
    )

    all_candidates = []

    # Сначала пары
    for combo in combinations(users_sorted, 2):
        match = match_lunch_group(list(combo), places)
        if match:
            all_candidates.append(match)

    # Потом тройки
    for combo in combinations(users_sorted, 3):
        match = match_lunch_group(list(combo), places)
        if match:
            all_candidates.append(match)

    # Потом 4, 5, 6
    for size in [4, 5, 6]:
        for combo in combinations(users_sorted, size):
            match = match_lunch_group(list(combo), places)
            if match:
                all_candidates.append(match)

    # Новый ключ: приоритет по "жёсткости" участников
    def sort_key(group):
        urgency = 0
        for login in group["participants"]:
            user = next(u for u in users if u["login"] == login)
            num_slots = len(user["parameters"]["time_slots"]) if user["parameters"]["time_slots"] else 0
            urgency += (3 - num_slots) * 2
            urgency += (3 - len(user["parameters"]["favourite_places"]))
        size = len(group["participants"])
        time_start = parse_time(group["lunch_time"][0]) if group["lunch_time"] else time(23, 59)
        return (-urgency, -size, time_start)

    all_candidates.sort(key=sort_key)

    # Жадный выбор
    for group in all_candidates:
        if used.intersection(group["participants"]):
            continue
        result.append(group)
        used.update(group["participants"])

    # Одиночки
    for user in users:
        if user["login"] not in used:
            single = match_lunch_group([user], places)
            if single:
                result.append(single)

    return result


def match_lunch(data: List[Dict], places_file: str) -> List[Dict]:
    print('=== DEBUG: match_lunch вызван ===', flush=True)
    import logging
    logging.info('=== DEBUG: match_lunch вызван ===')
    validate_input(data)
    places = load_places(places_file)
    print(f"DEBUG: loaded places: {[(p['office_name'], p['name']) for p in places]}", flush=True)
    processed_users = process_users(data)
    result = find_all_lunch_groups(processed_users, places)
    return result if result else []


def main():
    parser = argparse.ArgumentParser(description="Сопоставление пользователей для обеда.")
    parser.add_argument("-i", "--input", required=True, help="Путь к JSON-файлу с пользователями")
    parser.add_argument("-p", "--places", required=True, help="Путь к CSV-файлу с местами")
    parser.add_argument("-o", "--output", required=True, help="Путь к выходному JSON-файлу")
    args = parser.parse_args()

    logging.info(f"matcher.py ЗАПУЩЕН: input={args.input}, places={args.places}, output={args.output}")
    try:
        print(f"📥 Загружаем пользователей из {args.input}")
        with open(args.input, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logging.info(f"matcher.py: Загружено {len(data)} пользователей из {args.input}")

        # Замена: duration_min → max_lunch_duration
        for user in data:
            if "duration_min" in user["parameters"]:
                user["parameters"]["max_lunch_duration"] = user["parameters"].pop("duration_min")
            print(f"   - {user['login']} (max_lunch_duration={user['parameters']['max_lunch_duration']} мин)")

        result = match_lunch(data, args.places)

        print(f"DEBUG: FINAL RESULT = {result}", flush=True)
        logging.info(f"DEBUG: FINAL RESULT = {result}")

        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logging.info(f"matcher.py: Найдено {len(result)} групп. Результат сохранён в {args.output}")

        print(f"✅ Найдено {len(result)} групп на обед. Результат сохранён в {args.output}")

    except Exception as e:
        logging.error(f"matcher.py: Ошибка выполнения: {e}")
        print(f"❌ Ошибка выполнения: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()