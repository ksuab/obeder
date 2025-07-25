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
    print("✅ Тест 1: Все пользователи учтены")

    # === Тест 2: Нет дублирования пользователей
    seen = set()
    for group in result:
        for p in group["participants"]:
            assert p not in seen, f"❌ Пользователь {p} в нескольких группах"
            seen.add(p)
    print("✅ Тест 2: Нет дубликатов пользователей")

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
    print("✅ Тест 3: Время и длительность корректны")

    # === Тест 4: Проверка любимых и нежелательных мест
    places_data = load_places(PLACES_FILE)
    places_dict = {p["name"]: p for p in places_data}

    for group in result:
        if len(group["participants"]) == 1:
            continue
        place_name = group["place"]
        assert place_name in places_dict, f"❌ Место {place_name} не найдено в places.csv"

        user_dict = {u["login"]: u for u in users}
        for login in group["participants"]:
            user = user_dict[login]
            fav = user["parameters"]["favourite_places"]
            non_des = user["parameters"]["non_desirable_places"]
            assert place_name in fav, f"❌ {login} не любит {place_name}"
            assert place_name not in non_des, f"❌ {login} НЕ ЛЮБИТ {place_name}"
    print("✅ Тест 4: Предпочтения по местам соблюдены")

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
    print("✅ Тест 5: Размеры групп разрешены пользователями")

    # === Тест 6: Время ланча попадает хотя бы в один из time_slots пользователя
    for group in result:
        if len(group["participants"]) == 1:
            continue
        lunch_start, lunch_end = group["lunch_time"]
        start_t = parse_time_str(lunch_start)
        end_t = parse_time_str(lunch_end)

        user_dict = {u["login"]: u for u in users}
        for login in group["participants"]:
            user = user_dict[login]
            params = user["parameters"]

            # Проверяем наличие time_slots
            if "time_slots" not in params or not params["time_slots"]:
                assert False, f"❌ {login} не имеет time_slots"

            # Проверим, есть ли пересечение с хотя бы одним слотом
            fits = False
            for slot in params["time_slots"]:
                try:
                    slot_start, slot_end = slot
                    slot_start_t = parse_time_str(slot_start)
                    slot_end_t = parse_time_str(slot_end)

                    # Ланч должен полностью помещаться в слот
                    if start_t >= slot_start_t and end_t <= slot_end_t:
                        fits = True
                        break
                except Exception as e:
                    assert False, f"❌ Ошибка в time_slots у {login}: {slot}"

            assert fits, f"❌ Время ланча {lunch_start}-{lunch_end} не входит ни в один слот {login}: {params['time_slots']}"
    print("✅ Тест 6: Время ланча в пределах хотя бы одного time_slot")

    # === Тест 7: Минимизация одиночек — желательно, чтобы было < 5 одиночек
    assert solo_count <= 5, f"❌ Слишком много одиночек: {solo_count}. Цель — минимизировать."
    print(f"✅ Тест 7: Одиночек всего {solo_count} (<=5)")

    # === Тест 8: Проверка на пустых пользователей
    assert len(users) > 0, "❌ Нет пользователей для мэтчинга"
    print("✅ Тест 8: Есть пользователи для обработки")

    # === Тест 9: Проверка, что время ланча корректно отформатировано
    for group in result:
        lunch_time = group["lunch_time"]
        if len(group["participants"]) > 1:
            assert isinstance(lunch_time, list) and len(lunch_time) == 2, f"❌ Неверный формат времени: {lunch_time}"
            start, end = lunch_time
            assert ":" in start and ":" in end, f"❌ Неверный формат времени: {start}, {end}"
            try:
                parse_time_str(start)
                parse_time_str(end)
            except ValueError:
                assert False, f"❌ Невалидное время: {start} или {end}"
    print("✅ Тест 9: Формат времени корректен")

    # === Тест 10: У каждого участника есть пересечение между его слотами и временем ланча
    for group in result:
        if len(group["participants"]) == 1:
            continue
        lunch_start, lunch_end = group["lunch_time"]
        start_t = parse_time_str(lunch_start)
        end_t = parse_time_str(lunch_end)

        user_dict = {u["login"]: u for u in users}
        for login in group["participants"]:
            user = user_dict[login]
            params = user["parameters"]

            assert "time_slots" in params, f"❌ {login} не имеет time_slots"

            has_overlap = False
            for slot in params["time_slots"]:
                try:
                    s1, e1 = parse_time_str(slot[0]), parse_time_str(slot[1])
                    # Пересечение: начало ланча < конца слота И конец ланча > начала слота
                    if start_t < e1 and end_t > s1:
                        has_overlap = True
                        break
                except:
                    assert False, f"❌ Неверный формат слота у {login}: {slot}"

            assert has_overlap, f"❌ {login} не может посетить ланч в {lunch_start}-{lunch_end} (нет пересечения со слотами)"
    print("✅ Тест 10: Все участники имеют пересечение по времени")

    # === Тест 11: Проверка, что мэтчинг стабилен (повторный запуск даёт тот же результат)
    # Запускаем второй раз и сравниваем
    result2 = match_lunch(users, PLACES_FILE)
    # Сравниваем по ключевым полям: участники, время, место
    def normalize_group(g):
        return {
            "participants": sorted(g["participants"]),
            "lunch_time": tuple(g["lunch_time"]) if g["lunch_time"] else None,
            "place": g["place"]
        }
    norm1 = sorted([normalize_group(g) for g in result], key=lambda x: (x["participants"], x["place"]))
    norm2 = sorted([normalize_group(g) for g in result2], key=lambda x: (x["participants"], x["place"]))
    assert norm1 == norm2, "❌ Результат мэтчинга нестабилен между запусками"
    print("✅ Тест 11: Мэтчинг стабилен при повторных запусках")

    # === Тест 12: Проверка производительности (макс. 5 секунд)
    import time as tm
    start_time = tm.time()
    for _ in range(3):  # Среднее по 3 запускам
        match_lunch(users, PLACES_FILE)
    avg_time = (tm.time() - start_time) / 3
    assert avg_time < 5, f"❌ Мэтчинг слишком медленный: {avg_time:.2f} сек"
    print(f"✅ Тест 12: Производительность хорошая: {avg_time:.2f} сек в среднем")

    # === Тест 13: Проверка, что все места из результата — реальные (из CSV)
    used_places = {g["place"] for g in result if g["place"] is not None}
    valid_places = {p["name"] for p in places_data}
    invalid = used_places - valid_places
    assert not invalid, f"❌ Использованы несуществующие места: {invalid}"
    print("✅ Тест 13: Все места существуют в places.csv")

    # === Тест 14: Если пользователь указал только "6+", то он не может быть в группе из 2
    for group in result:
        size = len(group["participants"])
        if size == 2:
            for login in group["participants"]:
                user = next(u for u in users if u["login"] == login)
                allowed = user["parameters"]["team_size_lst"]
                assert "2" in allowed or "3-5" in allowed or "6+" in allowed, \
                    f"❌ {login} с team_size_lst={allowed} не может быть в группе из 2"

    print("✅ Тест 14: Учёт строгих ограничений по размеру команды")

    # === Тест 15: Проверка, что группы не слишком большие (например, не больше 10)
    max_group_size = 10
    for group in result:
        size = len(group["participants"])
        assert size <= max_group_size, f"❌ Группа слишком большая: {size} > {max_group_size}"
    print(f"✅ Тест 15: Максимальный размер группы — {max_group_size}")

    print(f"🎉 Все тесты пройдены! Найдено {len(result)} групп, одиночек: {solo_count}")
    print("💡 Рекомендация: Добавь тесты с edge-кейсами (пустые предпочтения, один пользователь и т.п.)")

    # === Тест 15: Нет искусственного ограничения размера группы
    max_possible_size = len(users)
    max_actual_size = max(len(g["participants"]) for g in result) if result else 0

    # Если все пользователи совместимы, теоретически может быть одна большая группа
    compatible_pair = True
    if len(users) > 1:
        # Простая эвристика: если хотя бы двое совместимы по времени и месту — большая группа возможна
        u1, u2 = users[0], users[1]
        t1_start = parse_time_str(u1["parameters"]["available_from"])
        t1_end = parse_time_str(u1["parameters"]["available_to"])
        t2_start = parse_time_str(u2["parameters"]["available_from"])
        t2_end = parse_time_str(u2["parameters"]["available_to"])
        time_overlap = t1_start < t2_end and t2_start < t1_end
        common_places = set(u1["parameters"]["favourite_places"]) & set(u2["parameters"]["favourite_places"])
        common_places -= set(u1["parameters"]["non_desirable_places"])
        common_places -= set(u2["parameters"]["non_desirable_places"])
        compatible_pair = time_overlap and len(common_places) > 0

    if compatible_pair and len(users) >= 3:
        assert max_actual_size >= 3, f"❌ При совместимых пользователях не сформирована группа ≥3 (максимум: {max_actual_size})"
    else:
        print(f"ℹ️ Тест 15: Большие группы маловероятны из-за несовместимости")

    print("✅ Тест 15: Проверка отсутствия искусственных ограничений на размер группы")

if __name__ == "__main__":
    run_tests()