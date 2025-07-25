#!/usr/bin/env python3

import json
import csv
import argparse
import sys
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Set, Any
from itertools import combinations
from datetime import timedelta

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
        required = ["office", "time_slots", "duration_min", "favourite_places", "non_desirable_places", "team_size_lst"]
        for key in required:
            if key not in params:
                raise ValueError(f"Не хватает параметра '{key}' у пользователя {user['login']}")


def parse_time(time_str: str) -> datetime.time:
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
    """Удаляет невалидные слоты и объединяет пересекающиеся."""
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


def time_overlap(slot1: Tuple[str, str], slot2: Tuple[str, str]) -> bool:
    """Проверяет пересечение двух временных слотов."""
    start1, end1 = parse_time(slot1[0]), parse_time(slot1[1])
    start2, end2 = parse_time(slot2[0]), parse_time(slot2[1])
    return start1 < end2 and start2 < end1


def find_common_time_slot(users: List[Dict]) -> Optional[Tuple[str, str]]:
    """Находит общий временной слот и возвращает оптимальное окно обеда (start, end), с учётом duration_min."""
    if any(not u["parameters"]["time_slots"] for u in users):
        # Если у кого-то нет слотов — подходит любое время, например, 12:00–13:00
        return ("12:00", "13:00")

    slots = [u["parameters"]["time_slots"] for u in users]
    common = slots[0]
    for user_slots in slots[1:]:
        new_common = []
        for s1 in common:
            for s2 in user_slots:
                if time_overlap(s1, s2):
                    start = max(parse_time(s1[0]), parse_time(s2[0]))
                    end = min(parse_time(s1[1]), parse_time(s2[1]))
                    if start < end:
                        new_common.append((start, end))
        common = new_common
        if not common:
            return None

    # Теперь ищем оптимальное время с учётом минимальной длительности
    min_duration = max(u["parameters"]["duration_min"] for u in users)  # Берём максимум, чтобы удовлетворить всех
    min_duration_td = timedelta(minutes=min_duration)

    for start, end in sorted(common):  # Сортируем, чтобы взять самое раннее подходящее
        if datetime.combine(datetime.today(), end) - datetime.combine(datetime.today(), start) >= min_duration_td:
            optimal_start = start
            optimal_end = (datetime.combine(datetime.today(), start) + min_duration_td).time()
            # Обрезаем по доступному окну
            if optimal_end > end:
                continue  # Не влезает
            return (optimal_start.strftime("%H:%M"), optimal_end.strftime("%H:%M"))

    return None  # Не найдено подходящее время


def is_team_size_compatible(users: List[Dict], team_size: int) -> bool:
    """Проверяет, что размер группы разрешён всеми пользователями."""
    allowed_sizes = set()
    for user in users:
        for size in user["parameters"]["team_size_lst"]:
            if size == "2":
                allowed_sizes.add(2)
            elif size == "3-5":
                allowed_sizes.update({3, 4, 5})
            elif size == "6+":
                allowed_sizes.update(range(6, 20))
    return team_size in allowed_sizes


def find_compatible_places(users: List[Dict], places: List[Dict]) -> List[Dict]:
    """Находит места, подходящие всем пользователям."""
    office = users[0]["parameters"]["office"]
    team_size = len(users)

    # Проверка офисов
    if any(user["parameters"]["office"] != office for user in users):
        return []

    # Проверка размера группы
    if not is_team_size_compatible(users, team_size):
        return []

    # Общие любимые места
    common_fav = None
    for user in users:
        fav_set = set(user["parameters"]["favourite_places"])
        common_fav = fav_set if common_fav is None else common_fav & fav_set
    if not common_fav:
        return []

    # Совместимые места
    compatible = []
    for place in places:
        if place["office_name"] != office:
            continue
        if place["name"] not in common_fav:
            continue
        if place["max_table_size"] < team_size:
            continue
        compatible.append(place)
    return compatible


def process_users(users: List[Dict]) -> List[Dict]:
    """Очищает и нормализует данные пользователей."""
    for user in users:
        user["parameters"]["time_slots"] = clean_time_slots(user["parameters"]["time_slots"])
        clean_preferences(user)
    return users


def match_lunch_group(users: List[Dict], places: List[Dict]) -> Optional[Dict]:
    """Сопоставляет группу для обеда, если возможно."""
    if len(users) == 1:
        return {
            "participants": [users[0]["login"]],
            "lunch_time": None,
            "place": None,
            "maps_link": None
        }

    common_slot = find_common_time_slot(users)
    if common_slot is None and any(u["parameters"]["time_slots"] for u in users):
        return None

    compatible_places = find_compatible_places(users, places)
    if not compatible_places:
        return None

    best_place = min(compatible_places, key=lambda p: p["time_to_go_min"])

    return {
        "participants": sorted(u["login"] for u in users),
        "lunch_time": common_slot,
        "place": best_place["name"],
        "maps_link": best_place["maps_link"]
    }


def find_all_lunch_groups(users: List[Dict], places: List[Dict]) -> List[Dict]:
    """Ищет все возможные непересекающиеся группы для обеда."""
    if len(users) == 1:
        match = match_lunch_group(users, places)
        return [match] if match else []

    # Сортируем по количеству слотов, чтобы сначала брать "жёстких"
    users_sorted = sorted(users, key=lambda u: len(u["parameters"]["time_slots"]) if u["parameters"]["time_slots"] else 999)

    all_matches = []
    used = set()

    # Сначала пробуем группы по 2, потом по 3 и т.д., но не больше 6
    for size in range(2, min(7, len(users) + 1)):
        for group in combinations([u for u in users_sorted if u["login"] not in used], size):
            group_list = list(group)
            match = match_lunch_group(group_list, places)
            if match:
                all_matches.append(match)
                for u in group_list:
                    used.add(u["login"])

    # Добавляем одиночек
    for user in users:
        if user["login"] not in used:
            single_match = match_lunch_group([user], places)
            if single_match:
                all_matches.append(single_match)

    return all_matches


def match_lunch(data: List[Dict], places_file: str) -> List[Dict]:
    """Основная функция: мэтчит людей для обеда (включая несколько групп)."""
    validate_input(data)
    places = load_places(places_file)
    processed_users = process_users(data)

    result = find_all_lunch_groups(processed_users, places)
    return result if result else []


def main():
    parser = argparse.ArgumentParser(description="Сопоставление пользователей для обеда.")
    parser.add_argument("-i", "--input", required=True, help="Путь к JSON-файлу с пользователями")
    parser.add_argument("-p", "--places", required=True, help="Путь к CSV-файлу с местами")
    parser.add_argument("-o", "--output", required=True, help="Путь к выходному JSON-файлу")

    args = parser.parse_args()

    try:
        print(f"📥 Загружаем пользователей из {args.input}")
        with open(args.input, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print(f"🔍 Найдено {len(data)} пользователей")
        for user in data:
            print(f"   - {user['login']}")

        result = match_lunch(data, args.places)

        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"✅ Найдено {len(result)} групп на обед. Результат сохранён в {args.output}")

    except Exception as e:
        print(f"❌ Ошибка выполнения: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()