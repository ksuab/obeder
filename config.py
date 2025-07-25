# Чтение токена из файла
def get_bot_token():
    try:
        with open('bottoken', 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        print("ОШИБКА: Файл bottoken не найден. Создайте файл с токеном вашего бота.")
        exit(1)

# Токен бота
API_TOKEN = get_bot_token()

# Пути к файлам данных
USERS_CSV = 'users_data.csv'
PLACES_CSV = 'places.csv'
USERS_TO_MATCH_JSON = 'users_to_match.json'

# Список офисов
OFFICES = ["Аврора", "Сити: Нева", "Сити: Око", "Красная роза", "Лотте", "Бенуа"]

# Варианты времени для выбора
TIME_OPTIONS = [
    "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", 
    "14:00", "14:30", "15:00", "15:30", "16:00", "16:30",
]

# Размеры компании
COMPANY_SIZES = ["1", "2", "3-5", "6+"]

# Длительность обеда
LUNCH_DURATIONS = ["30", "45", "60", "90"]
