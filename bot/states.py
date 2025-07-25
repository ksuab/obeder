from aiogram.fsm.state import State, StatesGroup

# Состояния для анкеты
class Form(StatesGroup):
    office = State()
    select_time_start = State()
    select_time_end = State()
    add_more_slots = State()
    lunch_duration = State()
    favorite_places = State()
    disliked_places = State()
    company_size = State()
    confirmation = State()

# Состояния для главного меню
class MainMenu(StatesGroup):
    main = State()
    lunch_preference = State()
    lunch_time_start = State()
    lunch_time_end = State()
    lunch_time_add_more = State()
    lunch_duration = State()
    lunch_place = State()
    lunch_company_size = State()
    lunch_confirmation = State()
    edit_profile = State()
    edit_field = State()
