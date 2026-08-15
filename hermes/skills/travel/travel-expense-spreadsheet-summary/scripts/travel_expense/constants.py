from __future__ import annotations

CATEGORY_AIR = "Авиа"
CATEGORY_RAIL = "ЖД"
CATEGORY_HOTEL = "Проживание в отелях"
CATEGORY_UNKNOWN = "Unknown"
CATEGORY_TOTAL = "ИТОГО"
CATEGORY_ORDER = [CATEGORY_AIR, CATEGORY_RAIL, CATEGORY_HOTEL, CATEGORY_UNKNOWN]
VALID_CATEGORIES = set(CATEGORY_ORDER)

CANON_DATE = "date"
CANON_COMMENT = "comment"
CANON_CARRIER = "carrier"
CANON_DETAILS = "details"
CANON_AMOUNT = "amount"
CANONICAL_COLUMNS = [CANON_DATE, CANON_COMMENT, CANON_CARRIER, CANON_DETAILS, CANON_AMOUNT]
REQUIRED_COLUMNS = [CANON_CARRIER, CANON_DETAILS, CANON_AMOUNT]

COLUMN_HINTS: dict[str, list[str]] = {
    CANON_DATE: ["дата", "дата покупки", "дата бронирования", "дата заказа", "дата операции", "дата оформления"],
    CANON_COMMENT: ["комментарий", "сотрудник", "приказ", "заявка", "подразделение", "центр затрат"],
    CANON_CARRIER: ["перевозчик", "поставщик", "контрагент", "агент", "продавец", "сервис", "организация"],
    CANON_DETAILS: ["детали", "описание", "маршрут", "услуга", "назначение", "направление"],
    CANON_AMOUNT: ["сумма", "стоимость", "цена", "итого", "оплата", "руб"],
}

# Specific airline names and distinctive fragments. Generic words like
# `авиа` / `air` are deliberately not used as standalone detail markers.
KNOWN_AIRLINES = [
    "аэрофлот", "aeroflot",
    "победа",
    "уральские авиалинии", "уральские",
    "ютэйр", "utair",
    "ювт аэро", "ювтаэро",
    "ред вингс", "red wings",
    "s7", "с7",
    "air serbia",
    "turkish airlines", "turkish",
    "qatar airways", "qatar",
    "indigo",
    "air china",
    "china eastern", "china southern", "china united",
    "hainan", "tianjin", "spring",
    "nordstar", "нордстар",
    "nordwind", "нордвинд",
    "emirates", "etihad", "fly dubai", "flydubai",
    "belavia", "северсталь",
    "oman air", "oman",
    "air india", "india",
]

RAIL_CARRIER_MARKERS = ["ржд", "ж/д", "железнодорож", "гранд сервис", "гранд сервис экспресс"]
RAIL_DETAIL_MARKERS = [
    "ржд", "ж/д", "жд", "железнодорож", "поезд", "вагон", "сапсан", "купе", "плацкарт",
    "гранд сервис", "гранд сервис экспресс",
]

# Legacy report keeps ground transport inside ЖД unless the user asks for a
# separate category. These are confirmed service markers, not review signals.
GROUND_MARKERS = ["аэроэкспресс", "аэроэскпресс", "трансфер", "автобус"]

# Mixed vendors cannot be classified by carrier alone.
MIXED_SERVICE_VENDOR_MARKERS = [
    "trip.com", "trip com", "trip", "вайт тревел", "яндекс", "дубльгис",
]

HOTEL_VENDOR_MARKERS = [
    "комфорт букинг", "центр бронирования", "гостиниц", "гостиница", "отель", "hotel", "booking",
]

# Strong lodging markers. These mean the service itself is lodging.
EXPLICIT_LODGING_DETAILS = [
    "прожив", "апартамент", "поздний выезд", "ранний заезд",
]

# Softer hints: useful only with additional structure/vendor context.
SOFT_LODGING_DETAILS = ["гостиница", "гостиниц", "отель", "hotel", "inn", "residence", "apart", "апарт"]
