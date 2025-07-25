# test_matcher.py

import json
import csv
import os
from datetime import time, datetime, timedelta
from matcher import match_lunch, load_places, parse_time

# Пути к тестовым файлам
USERS_FILE = "test/users_to_match.json"
PLACES_FILE = "test/places.csv"
OUTPUT_FILE = "test/output.json"

def load_users():
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_result(result):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

def parse_time_str(t: str) -> time:
    return datetime.strptime(t, "%H:%M").time()

def time_diff(end: str, start: str) -> int:
    """Разница в минутах между двумя временами."""
    t_end = parse_time_str(end)
    t_start = parse_time_str(start)
    delta = timedelta(hours=t_end.hour, minutes=t_end.minute) - timedelta(hours=t_start.hour, minutes=t_start.minute)
    return int(delta.total_seconds() // 60)

def run_tests():
    print("📥 Загружаем тестовые данные...")
    users = load_users()
    print(f"✅ Загружено {len(users)} пользователей")

    # Прямой вызов match_lunch
    print("🔍 Запускаем мэтчинг...")
    result = match_lunch(users, PLACES_FILE)
    save_result(result)
    print(f"✅ Результат сохранён в {OUTPUT_FILE}")

    # === Тест 1: Все пользователи должны быть в результатах
    all_logins = {u["login"] for u in users}
    matched_logins = set()
    for group in result:
        matched_logins.update(group["participants"])
    assert matched_logins == all_logins, f"❌ Пропущены пользователи: {all_logins - matched_logins}"

    # === Тест 2: Нет дублирования пользователей
    seen = set()
    for group in result:
        for p in group["participants"]:
            assert p not in seen, f"❌ Пользователь {p} в нескольких группах"
            seen.add(p)

    # === Тест 3: Все группы с 2+ человек — имеют время и место
    solo_count = 0
    for group in result:
        participants = group["participants"]
        if len(participants) == 1:
            solo_count += 1
            continue
        assert group["lunch_time"] is not None, f"❌ Группа {participants} без времени"
        assert group["place"] is not None, f"❌ Группа {participants} без места"
        start, end = group["lunch_time"]
        duration = time_diff(end, start)
        # Проверим, что длительность не превышает max_lunch_duration любого участника
        user_dict = {u["login"]: u for u in users}
        participant_users = [user_dict[login] for login in participants]
        min_max_duration = min(u["parameters"]["max_lunch_duration"] for u in participant_users)
        assert duration <= min_max_duration, f"❌ Группа {participants} превысила время: {duration} > {min_max_duration} мин"

    print(f"✅ Проверка времени и длительности пройдена. Одиночки: {solo_count}")

    # === Тест 4: Проверка любимых и нежелательных мест
    places_data = load_places(PLACES_FILE)
    places_dict = {p["name"]: p for p in places_data}

    for group in result:
        if len(group["participants"]) == 1:
            continue
        place_name = group["place"]
        assert place_name in places_dict, f"❌ Место {place_name} не найдено в places.csv"

        # Проверим, что место нравится всем
        user_dict = {u["login"]: u for u in users}
        for login in group["participants"]:
            user = user_dict[login]
            fav = user["parameters"]["favourite_places"]
            non_des = user["parameters"]["non_desirable_places"]
            assert place_name in fav, f"❌ {login} не любит {place_name}"
            assert place_name not in non_des, f"❌ {login} НЕ ЛЮБИТ {place_name}"

    print("✅ Проверка предпочтений пройдена")

    # === Тест 5: Размер группы совместим с team_size_lst
    size_map = {
        2: ["2", "3-5", "6+"],
        3: ["3-5", "6+"],
        4: ["3-5", "6+"],
        5: ["3-5", "6+"],
        6: ["6+"],
        7: ["6+"],
        8: ["6+"],
        9: ["6+"],
        10: ["6+"],
    }

    for group in result:
        if len(group["participants"]) == 1:
            continue
        team_size = len(group["participants"])
        allowed_sizes = size_map.get(team_size, [])
        for login in group["participants"]:
            user = next(u for u in users if u["login"] == login)
            user_allowed = user["parameters"]["team_size_lst"]
            assert any(sz in allowed_sizes for sz in user_allowed), \
                f"❌ {login} не разрешает группу из {team_size} человек (разрешено: {user_allowed})"

    print("✅ Проверка размера группы пройдена")

    # === Тест 6: Проверка, что группа не пересекается по времени (внутри группы — не нужно, т.к. общий слот)
    # Но если бы была глобальная шедулинг-логика — проверяли бы между группами. Пока пропускаем.

    # === Тест 7: Минимизация одиночек — желательно, чтобы было < 5 одиночек
    assert solo_count <= 5, f"❌ Слишком много одиночек: {solo_count}. Цель — минимизировать."

    print(f"🎉 Все тесты пройдены! Найдено {len(result)} групп, одиночек: {solo_count}")

if __name__ == "__main__":
    run_tests()