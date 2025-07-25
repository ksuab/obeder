import os
def get_bot_token():
    try:
        with open('data/bottoken.txt', 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.error("Файл с токеном не найден! Создайте файл data/bottoken с токеном бота")
        exit(1)

BOT_TOKEN = get_bot_token()

# Пути к файлам данных
DATA_DIR = 'data'
USERS_CSV = os.path.join(DATA_DIR, 'users_data.csv')
PLACES_CSV = os.path.join(DATA_DIR, 'places.csv')
USERS_TO_MATCH_JSON = os.path.join(DATA_DIR, 'users_to_match.json')

# Создаем папку data, если ее нет
os.makedirs(DATA_DIR, exist_ok=True)

# Список офисов
OFFICES = ["Аврора", "Сити: Нева", "Сити: Око", "Красная роза", "Лотте", "Бенуа"]

# Варианты времени для выбора
TIME_OPTIONS = [
    "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", 
    "14:00", "14:30", "15:00", "15:30", "16:00", "16:30",
]

# Размеры компании
COMPANY_SIZES = ["1", "2", "3-5", "6+", "18+"]

# Длительность обеда
LUNCH_DURATIONS = ["30", "45", "60", "90"]
