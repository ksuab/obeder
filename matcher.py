#!/usr/bin/env python3
import json
import csv
import argparse
import sys
from datetime import datetime, time, timedelta
from typing import List, Dict, Tuple, Optional, Set
from itertools import combinations


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
    Находит общий временной слот, учитывая, что:
    - У каждого пользователя есть временные окна.
    - Группа должна уложиться в самое короткое доступное время (max_lunch_duration).
    """
    if any(not u["parameters"]["time_slots"] for u in users):
        return ("12:00", "13:00")  # fallback

    # Преобразуем слоты в объекты time
    user_time_slots = []
    for user in users:
        slots = []
        for s in user["parameters"]["time_slots"]:
            start_t = parse_time(s[0])
            end_t = parse_time(s[1])
            if start_t < end_t:
                slots.append((start_t, end_t))
        user_time_slots.append(slots)

    # Пересекаем слоты всех пользователей
    common = user_time_slots[0]
    for user_slots in user_time_slots[1:]:
        new_common = []
        for s1 in common:
            for s2 in user_slots:
                if s1[0] < s2[1] and s2[0] < s1[1]:  # есть пересечение
                    start = max(s1[0], s2[0])
                    end = min(s1[1], s2[1])
                    if start < end:
                        new_common.append((start, end))
        common = new_common
        if not common:
            return None

    # Максимальная длительность, которую может себе позволить самый "занятой" участник
    max_allowed_duration = min(u["parameters"]["max_lunch_duration"] for u in users)
    max_duration_td = timedelta(minutes=max_allowed_duration)

    # Ищем самое раннее окно, которое помещается в max_allowed_duration
    for start, end in sorted(common):
        slot_duration = datetime.combine(datetime.today(), end) - datetime.combine(datetime.today(), start)
        if slot_duration >= max_duration_td:
            # Используем ровно max_duration минут, начиная с `start`
            optimal_end = (datetime.combine(datetime.today(), start) + max_duration_td).time()
            if optimal_end <= end:
                return (start.strftime("%H:%M"), optimal_end.strftime("%H:%M"))

    return None


def is_team_size_compatible(users: List[Dict], team_size: int) -> bool:
    for user in users:
        allowed = user["parameters"]["team_size_lst"]
        fits = False
        if team_size == 2 and "2" in allowed:
            fits = True
        if 3 <= team_size <= 5 and "3-5" in allowed:
            fits = True
        if team_size >= 6 and "6+" in allowed:
            fits = True
        if not fits:
            return False
    return True


def find_compatible_places(users: List[Dict], places: List[Dict]) -> List[Dict]:
    """Находит места, которые НРАВЯТСЯ ВСЕМ (входят в favourite_places каждого) и не запрещены."""
    office = users[0]["parameters"]["office"]
    team_size = len(users)

    # Проверка офиса
    if any(user["parameters"]["office"] != office for user in users):
        return []

    # Проверка размера группы
    if not is_team_size_compatible(users, team_size):
        return []

    # Находим ОБЩИЕ любимые места
    common_fav = None
    for user in users:
        fav_set = set(user["parameters"]["favourite_places"])
        common_fav = fav_set if common_fav is None else common_fav & fav_set
    if not common_fav:
        return []  # Нет общего любимого — нет группы

    # Фильтруем места: только в общих любимых, правильный офис, размер стола
    compatible = []
    for place in places:
        if place["office_name"] != office:
            continue
        if place["name"] not in common_fav:
            continue
        if place["max_table_size"] < team_size:
            continue
        # Дополнительно: убедимся, что никто не запрещает это место
        if any(place["name"] in user["parameters"]["non_desirable_places"] for user in users):
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
    """Сопоставляет группу пользователей для обеда."""
    if len(users) == 1:
        return {
            "participants": [users[0]["login"]],
            "lunch_time": None,
            "place": None,
            "maps_link": None
        }

    common_slot = find_common_time_slot(users)
    if common_slot is None:
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
    if len(users) == 1:
        match = match_lunch_group(users, places)
        return [match] if match else []

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
    """Основная функция: мэтчит людей для обеда."""
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

        # Замена: duration_min → max_lunch_duration
        for user in data:
            if "duration_min" in user["parameters"]:
                user["parameters"]["max_lunch_duration"] = user["parameters"].pop("duration_min")
            print(f"   - {user['login']} (max_lunch_duration={user['parameters']['max_lunch_duration']} мин)")

        result = match_lunch(data, args.places)

        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"✅ Найдено {len(result)} групп на обед. Результат сохранён в {args.output}")

    except Exception as e:
        print(f"❌ Ошибка выполнения: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()