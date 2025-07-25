from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import OFFICES, TIME_OPTIONS, LUNCH_DURATIONS, COMPANY_SIZES

# Клавиатура выбора офиса
def get_office_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=office, callback_data=f"office:{office}")] for office in OFFICES
    ])

# Клавиатура выбора времени начала
def get_time_start_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=(time_opt if ':' in time_opt else f"{int(time_opt):02d}:00"), callback_data=f"time_start:{(time_opt if ':' in time_opt else f'{int(time_opt):02d}:00')}" )] for time_opt in TIME_OPTIONS
    ])

# Клавиатура выбора времени конца
def get_time_end_keyboard(start_time):
    filtered_times = [t for t in TIME_OPTIONS if t > start_time]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=(time_opt if ':' in time_opt else f"{int(time_opt):02d}:00"), callback_data=f"time_end:{(time_opt if ':' in time_opt else f'{int(time_opt):02d}:00')}" )] for time_opt in filtered_times
    ])

# Клавиатура добавления еще одного слота
def get_add_slot_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да", callback_data="add_slot:yes"), 
         InlineKeyboardButton(text="Нет", callback_data="add_slot:no")]
    ])

# Клавиатура выбора длительности обеда
def get_lunch_duration_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{duration} минут", callback_data=f"duration:{duration}")] for duration in LUNCH_DURATIONS
    ])

# Клавиатура выбора любимых мест
def get_favorite_places_keyboard(places, selected_places):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{'✅ ' if place in selected_places else ''}{place}", callback_data=f"fav_place:{place}")] for place in places
    ] + [[InlineKeyboardButton(text="Готово", callback_data="fav_place:done")]])

# Клавиатура выбора нелюбимых мест
def get_disliked_places_keyboard(places, selected_places):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{'✅ ' if place in selected_places else ''}{place}", callback_data=f"dis_place:{place}")] for place in places
    ] + [[InlineKeyboardButton(text="Готово", callback_data="dis_place:done")]])

# Клавиатура выбора размера компании
def get_company_size_keyboard(selected_sizes):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{'✅ ' if size in selected_sizes else ''}{size}", callback_data=f"size:{size}")] for size in COMPANY_SIZES
    ] + [[InlineKeyboardButton(text="Готово", callback_data="size:done")]])

# Клавиатура подтверждения
def get_confirmation_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Всё верно", callback_data="confirm:yes"), 
         InlineKeyboardButton(text="Заполнить заново", callback_data="confirm:no")]
    ])

# Главное меню
def get_main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Записаться на обед сегодня", callback_data="menu:book_lunch")],
        [InlineKeyboardButton(text="Изменить настройки профиля", callback_data="menu:edit_profile")],
        [InlineKeyboardButton(text="Показать мой профиль", callback_data="menu:show_profile")]
    ])

# Меню редактирования
def get_edit_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Офис", callback_data="edit:office")],
        [InlineKeyboardButton(text="Временные слоты", callback_data="edit:time_slots")],
        [InlineKeyboardButton(text="Длительность обеда", callback_data="edit:duration")],
        [InlineKeyboardButton(text="Любимые места", callback_data="edit:favorite_places")],
        [InlineKeyboardButton(text="Нелюбимые места", callback_data="edit:disliked_places")],
        [InlineKeyboardButton(text="Размер компании", callback_data="edit:company_size")],
        [InlineKeyboardButton(text="Вернуться в главное меню", callback_data="edit:back")]
    ])

# Клавиатура выбора типа записи на обед
def get_lunch_preference_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="По моим настройкам из анкеты", callback_data="lunch:by_profile")],
        [InlineKeyboardButton(text="Изменить настройки для сегодня", callback_data="lunch:custom")]
    ])

# Другие клавиатуры...
def get_back_to_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Вернуться в главное меню", callback_data="menu:back")]
    ])

def get_lunch_place_keyboard(places):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=place, callback_data=f"lunch_place:{place}")] for place in places
    ] + [[InlineKeyboardButton(text="Пропустить", callback_data="lunch_place:skip")]])

def get_lunch_company_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=size, callback_data=f"lunch_company:{size}")] for size in COMPANY_SIZES
    ] + [[InlineKeyboardButton(text="Пропустить", callback_data="lunch_company:skip")]])

def get_lunch_confirm_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить", callback_data="lunch_confirm:yes")],
        [InlineKeyboardButton(text="Отменить", callback_data="lunch_confirm:no")]
    ])

def get_after_edit_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Продолжить редактирование", callback_data="menu:edit_profile")],
        [InlineKeyboardButton(text="Вернуться в главное меню", callback_data="menu:back")]
    ])
