from datetime import date, datetime

LANG_NAMES = {"ru": "Русский", "kk": "Қазақша", "en": "English"}

WEEKDAYS = {
    "ru": ["пн", "вт", "ср", "чт", "пт", "сб", "вс"],
    "kk": ["дс", "сс", "ср", "бс", "жм", "сн", "жс"],
    "en": ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
}

MONTHS = {
    "ru": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"],
    "kk": ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}

UNITS = {
    "ru": ("мин", "ч"),
    "kk": ("мин", "сағ"),
    "en": ("min", "h"),
}

TEXTS: dict[str, dict[str, str]] = {
    "ru": {
        "menu": "<b>{name}</b>\n\nЗдесь можно записаться, перенести или отменить визит.",
        "btn_book": "📅 Записаться",
        "btn_my": "🗂 Мои записи",
        "btn_services": "💈 Услуги и цены",
        "btn_address": "📍 Адрес и контакты",
        "btn_support": "💬 Написать администратору",
        "btn_lang": "🌐 Язык",
        "btn_back": "‹ Назад",
        "btn_menu": "🏠 В меню",
        "lang_choose": "Выберите язык:",
        "choose_service": "Выберите услугу:",
        "choose_staff": "<b>{service}</b>\n\nВыберите мастера:",
        "any_staff": "Любой свободный",
        "choose_date": "<b>{service}</b>\nМастер: {staff}\n\nВыберите день:",
        "choose_time": "<b>{service}</b>\nМастер: {staff}\n{day}\n\nВыберите время:",
        "no_days": "В ближайшие {days} дн. свободного времени нет. Попробуйте другого мастера или напишите администратору.",
        "no_times": "На этот день свободного времени уже нет. Выберите другой день.",
        "ask_name": "Как вас зовут?",
        "use_name": "Оставить «{name}»",
        "bad_name": "Напишите имя текстом, до 60 символов.",
        "ask_phone": "Отправьте номер телефона кнопкой ниже или напишите его сообщением.",
        "send_contact": "📱 Отправить мой номер",
        "bad_phone": "Не похоже на номер телефона. Пример: +7 701 123 45 67",
        "contact_saved": "Спасибо, {name}.",
        "confirm_title": "Проверьте запись:",
        "btn_confirm": "✅ Записаться",
        "booked": "✅ <b>Вы записаны</b>",
        "booked_hint": "Напомним за день и за пару часов до визита.",
        "slot_taken": "Это время только что заняли. Выберите другое.",
        "limit_reached": "У вас уже есть активные записи: {n}. Отмените одну из них или напишите администратору.",
        "my_title": "Ваши записи:",
        "my_empty": "У вас нет предстоящих записей.",
        "btn_reschedule": "🔁 Перенести",
        "btn_cancel_booking": "❌ Отменить запись",
        "cancel_ask": "Отменить эту запись?",
        "btn_yes_cancel": "Да, отменить",
        "cancelled": "Запись отменена.",
        "too_late": "До визита меньше {time}. Изменить запись может только администратор.",
        "not_found": "Запись не найдена или уже неактивна.",
        "resched_date": "Перенос записи. Выберите новый день:",
        "resched_time": "Перенос записи, {day}. Выберите время:",
        "resched_confirm": "Перенести запись?",
        "btn_resched_ok": "✅ Перенести",
        "rescheduled": "🔁 <b>Запись перенесена</b>",
        "remind_first": "🔔 Напоминаем о записи:",
        "remind_ask": "Вы придёте?",
        "btn_coming": "👍 Приду",
        "remind_second": "🔔 Ждём вас через {time}:",
        "confirmed_thanks": "Отлично, ждём вас.",
        "services_title": "<b>Услуги и цены</b>",
        "support_ask": "Напишите сообщение, и я передам его администратору.",
        "support_sent": "Сообщение передано. Ответ придёт сюда.",
        "support_reply": "💬 <b>Администратор:</b>",
        "admin_cancelled": "Администратор отменил вашу запись:",
        "master": "Мастер",
        "unknown_command": "Выберите действие в меню.",
        "adm_help": (
            "<b>Команды администратора</b>\n\n"
            "/today — записи на сегодня\n/tomorrow — на завтра\n/week — на 7 дней\n"
            "/add — записать клиента вручную\n/block — закрыть время мастера\n/blocks — закрытое время\n"
            "/export — выгрузка в CSV\n/stats — статистика\n\n"
            "Чтобы ответить клиенту, ответьте реплаем на его сообщение."
        ),
        "adm_new": "🆕 <b>Новая запись</b>",
        "adm_new_manual": "🆕 <b>Запись создана администратором</b>",
        "adm_cancelled": "❌ <b>Клиент отменил запись</b>",
        "adm_moved": "🔁 <b>Клиент перенёс запись</b>",
        "adm_was": "Было: {when}",
        "adm_day_empty": "записей нет",
        "adm_pick": "Нажмите на запись, чтобы изменить её:",
        "adm_btn_cancel": "❌ Отменить",
        "adm_btn_noshow": "🚫 Не пришёл",
        "adm_done_cancel": "Запись отменена, клиент уведомлён.",
        "adm_done_noshow": "Отмечено: клиент не пришёл.",
        "adm_add_ask": "Отправьте имя и телефон клиента одним сообщением.\nПример: Айгерим +7 701 123 45 67",
        "adm_add_bad": "Нужны имя и телефон. Пример: Айгерим +7 701 123 45 67",
        "adm_add_for": "Запись для: <b>{name}</b>, {phone}",
        "adm_block_staff": "Кому закрыть время?",
        "adm_block_date": "<b>{staff}</b>\nВыберите день:",
        "adm_block_start": "<b>{staff}</b>, {day}\nС какого времени закрыть?",
        "adm_block_whole": "Весь день",
        "adm_block_end": "<b>{staff}</b>, {day}, с {start}\nДо какого времени?",
        "adm_block_done": "🔒 Закрыто: <b>{staff}</b>, {when}",
        "adm_block_warn": "⚠️ На это время уже есть записи: {n}. Они остались в силе, отмените их вручную.",
        "adm_day_off": "В этот день мастер не работает.",
        "adm_blocks_title": "Закрытое время. Нажмите, чтобы открыть:",
        "adm_blocks_empty": "Закрытого времени нет.",
        "adm_block_deleted": "Время снова открыто.",
        "adm_export": "Записи с {start} по {end}: {n}",
        "adm_stats": (
            "<b>Статистика</b>\n\n"
            "<b>7 дней</b>\nвизитов: {w_done} · отмен: {w_cancel} · неявок: {w_noshow}\nвыручка: {w_money}\n\n"
            "<b>30 дней</b>\nвизитов: {m_done} · отмен: {m_cancel} · неявок: {m_noshow}\nвыручка: {m_money}\n\n"
            "<b>Впереди</b>: {upcoming}\n\n<b>Визиты по мастерам за 30 дней</b>\n{by_staff}"
        ),
        "adm_support_from": "✉️ <b>{name}</b> {phone}\nОтветьте реплаем на это сообщение.",
        "adm_reply_sent": "Ответ отправлен.",
        "adm_reply_failed": "Не удалось отправить: клиент заблокировал бота.",
        "adm_closed": "закрыто",
        "adm_confirmed": "подтвердил",
        "adm_manual": "вручную",
        "status_active": "активна",
        "status_done": "состоялась",
        "status_cancelled": "отменена",
        "status_noshow": "не пришёл",
    },
    "kk": {
        "menu": "<b>{name}</b>\n\nМұнда жазылуға, уақытты ауыстыруға немесе жазылудан бас тартуға болады.",
        "btn_book": "📅 Жазылу",
        "btn_my": "🗂 Менің жазылуларым",
        "btn_services": "💈 Қызметтер мен бағалар",
        "btn_address": "📍 Мекенжай мен байланыс",
        "btn_support": "💬 Әкімшіге жазу",
        "btn_lang": "🌐 Тіл",
        "btn_back": "‹ Артқа",
        "btn_menu": "🏠 Мәзірге",
        "lang_choose": "Тілді таңдаңыз:",
        "choose_service": "Қызметті таңдаңыз:",
        "choose_staff": "<b>{service}</b>\n\nШеберді таңдаңыз:",
        "any_staff": "Кез келген бос шебер",
        "choose_date": "<b>{service}</b>\nШебер: {staff}\n\nКүнді таңдаңыз:",
        "choose_time": "<b>{service}</b>\nШебер: {staff}\n{day}\n\nУақытты таңдаңыз:",
        "no_days": "Алдағы {days} күнде бос уақыт жоқ. Басқа шеберді таңдаңыз немесе әкімшіге жазыңыз.",
        "no_times": "Бұл күні бос уақыт қалмады. Басқа күнді таңдаңыз.",
        "ask_name": "Есіміңіз кім?",
        "use_name": "«{name}» деп қалдыру",
        "bad_name": "Есіміңізді мәтінмен жазыңыз, 60 таңбаға дейін.",
        "ask_phone": "Телефон нөміріңізді төмендегі түймемен жіберіңіз немесе хабарламамен жазыңыз.",
        "send_contact": "📱 Нөмірімді жіберу",
        "bad_phone": "Бұл телефон нөміріне ұқсамайды. Мысалы: +7 701 123 45 67",
        "contact_saved": "Рақмет, {name}.",
        "confirm_title": "Жазылуды тексеріңіз:",
        "btn_confirm": "✅ Жазылу",
        "booked": "✅ <b>Сіз жазылдыңыз</b>",
        "booked_hint": "Бір күн бұрын және келуден екі сағат бұрын еске саламыз.",
        "slot_taken": "Бұл уақыт жаңа ғана алынды. Басқасын таңдаңыз.",
        "limit_reached": "Сізде белсенді жазылулар бар: {n}. Біреуінен бас тартыңыз немесе әкімшіге жазыңыз.",
        "my_title": "Сіздің жазылуларыңыз:",
        "my_empty": "Алдағы жазылуларыңыз жоқ.",
        "btn_reschedule": "🔁 Ауыстыру",
        "btn_cancel_booking": "❌ Бас тарту",
        "cancel_ask": "Осы жазылудан бас тартасыз ба?",
        "btn_yes_cancel": "Иә, бас тартамын",
        "cancelled": "Жазылу жойылды.",
        "too_late": "Келуге {time} аз уақыт қалды. Жазылуды тек әкімші өзгерте алады.",
        "not_found": "Жазылу табылмады немесе белсенді емес.",
        "resched_date": "Жазылуды ауыстыру. Жаңа күнді таңдаңыз:",
        "resched_time": "Жазылуды ауыстыру, {day}. Уақытты таңдаңыз:",
        "resched_confirm": "Жазылуды ауыстырамыз ба?",
        "btn_resched_ok": "✅ Ауыстыру",
        "rescheduled": "🔁 <b>Жазылу ауыстырылды</b>",
        "remind_first": "🔔 Жазылуыңызды еске саламыз:",
        "remind_ask": "Келесіз бе?",
        "btn_coming": "👍 Келемін",
        "remind_second": "🔔 Сізді {time} кейін күтеміз:",
        "confirmed_thanks": "Тамаша, сізді күтеміз.",
        "services_title": "<b>Қызметтер мен бағалар</b>",
        "support_ask": "Хабарламаңызды жазыңыз, мен оны әкімшіге жеткіземін.",
        "support_sent": "Хабарлама жіберілді. Жауап осында келеді.",
        "support_reply": "💬 <b>Әкімші:</b>",
        "admin_cancelled": "Әкімші сіздің жазылуыңызды жойды:",
        "master": "Шебер",
        "unknown_command": "Мәзірден әрекетті таңдаңыз.",
        "adm_help": (
            "<b>Әкімші командалары</b>\n\n"
            "/today — бүгінгі жазылулар\n/tomorrow — ертеңгі\n/week — 7 күнге\n"
            "/add — клиентті қолмен жазу\n/block — шебердің уақытын жабу\n/blocks — жабық уақыт\n"
            "/export — CSV файлына шығару\n/stats — статистика\n\n"
            "Клиентке жауап беру үшін оның хабарламасына жауап (reply) жазыңыз."
        ),
        "adm_new": "🆕 <b>Жаңа жазылу</b>",
        "adm_new_manual": "🆕 <b>Жазылуды әкімші жасады</b>",
        "adm_cancelled": "❌ <b>Клиент жазылудан бас тартты</b>",
        "adm_moved": "🔁 <b>Клиент жазылуды ауыстырды</b>",
        "adm_was": "Бұрын: {when}",
        "adm_day_empty": "жазылу жоқ",
        "adm_pick": "Өзгерту үшін жазылуды басыңыз:",
        "adm_btn_cancel": "❌ Жою",
        "adm_btn_noshow": "🚫 Келмеді",
        "adm_done_cancel": "Жазылу жойылды, клиентке хабарланды.",
        "adm_done_noshow": "Белгіленді: клиент келмеді.",
        "adm_add_ask": "Клиенттің есімі мен телефонын бір хабарламамен жіберіңіз.\nМысалы: Айгерім +7 701 123 45 67",
        "adm_add_bad": "Есім мен телефон қажет. Мысалы: Айгерім +7 701 123 45 67",
        "adm_add_for": "Кімге: <b>{name}</b>, {phone}",
        "adm_block_staff": "Кімнің уақытын жабамыз?",
        "adm_block_date": "<b>{staff}</b>\nКүнді таңдаңыз:",
        "adm_block_start": "<b>{staff}</b>, {day}\nҚай уақыттан бастап жабамыз?",
        "adm_block_whole": "Күні бойы",
        "adm_block_end": "<b>{staff}</b>, {day}, {start} бастап\nҚай уақытқа дейін?",
        "adm_block_done": "🔒 Жабылды: <b>{staff}</b>, {when}",
        "adm_block_warn": "⚠️ Бұл уақытта жазылулар бар: {n}. Олар күшінде қалды, қолмен жойыңыз.",
        "adm_day_off": "Бұл күні шебер жұмыс істемейді.",
        "adm_blocks_title": "Жабық уақыт. Ашу үшін басыңыз:",
        "adm_blocks_empty": "Жабық уақыт жоқ.",
        "adm_block_deleted": "Уақыт қайта ашылды.",
        "adm_export": "{start} – {end} аралығындағы жазылулар: {n}",
        "adm_stats": (
            "<b>Статистика</b>\n\n"
            "<b>7 күн</b>\nкелгендер: {w_done} · бас тартқандар: {w_cancel} · келмегендер: {w_noshow}\nтүсім: {w_money}\n\n"
            "<b>30 күн</b>\nкелгендер: {m_done} · бас тартқандар: {m_cancel} · келмегендер: {m_noshow}\nтүсім: {m_money}\n\n"
            "<b>Алда</b>: {upcoming}\n\n<b>30 күндегі шеберлер бойынша</b>\n{by_staff}"
        ),
        "adm_support_from": "✉️ <b>{name}</b> {phone}\nОсы хабарламаға жауап (reply) жазыңыз.",
        "adm_reply_sent": "Жауап жіберілді.",
        "adm_reply_failed": "Жіберілмеді: клиент ботты бұғаттаған.",
        "adm_closed": "жабық",
        "adm_confirmed": "растады",
        "adm_manual": "қолмен",
        "status_active": "белсенді",
        "status_done": "өтті",
        "status_cancelled": "жойылды",
        "status_noshow": "келмеді",
    },
    "en": {
        "menu": "<b>{name}</b>\n\nBook a visit, move it or cancel it here.",
        "btn_book": "📅 Book a visit",
        "btn_my": "🗂 My bookings",
        "btn_services": "💈 Services and prices",
        "btn_address": "📍 Address and contacts",
        "btn_support": "💬 Message the admin",
        "btn_lang": "🌐 Language",
        "btn_back": "‹ Back",
        "btn_menu": "🏠 Menu",
        "lang_choose": "Choose a language:",
        "choose_service": "Choose a service:",
        "choose_staff": "<b>{service}</b>\n\nChoose a specialist:",
        "any_staff": "Anyone available",
        "choose_date": "<b>{service}</b>\nSpecialist: {staff}\n\nChoose a day:",
        "choose_time": "<b>{service}</b>\nSpecialist: {staff}\n{day}\n\nChoose a time:",
        "no_days": "No free time in the next {days} days. Try another specialist or message the admin.",
        "no_times": "No free time left on this day. Choose another day.",
        "ask_name": "What is your name?",
        "use_name": "Keep “{name}”",
        "bad_name": "Send your name as text, up to 60 characters.",
        "ask_phone": "Send your phone number with the button below or type it.",
        "send_contact": "📱 Send my number",
        "bad_phone": "That does not look like a phone number. Example: +7 701 123 45 67",
        "contact_saved": "Thanks, {name}.",
        "confirm_title": "Check your booking:",
        "btn_confirm": "✅ Book",
        "booked": "✅ <b>You are booked</b>",
        "booked_hint": "We will remind you a day and a couple of hours before the visit.",
        "slot_taken": "This time was just taken. Choose another one.",
        "limit_reached": "You already have {n} active bookings. Cancel one or message the admin.",
        "my_title": "Your bookings:",
        "my_empty": "You have no upcoming bookings.",
        "btn_reschedule": "🔁 Move",
        "btn_cancel_booking": "❌ Cancel booking",
        "cancel_ask": "Cancel this booking?",
        "btn_yes_cancel": "Yes, cancel",
        "cancelled": "Booking cancelled.",
        "too_late": "Less than {time} left before the visit. Only the admin can change it now.",
        "not_found": "Booking not found or no longer active.",
        "resched_date": "Moving the booking. Choose a new day:",
        "resched_time": "Moving the booking, {day}. Choose a time:",
        "resched_confirm": "Move the booking?",
        "btn_resched_ok": "✅ Move",
        "rescheduled": "🔁 <b>Booking moved</b>",
        "remind_first": "🔔 A reminder about your booking:",
        "remind_ask": "Will you come?",
        "btn_coming": "👍 I will come",
        "remind_second": "🔔 See you in {time}:",
        "confirmed_thanks": "Great, see you then.",
        "services_title": "<b>Services and prices</b>",
        "support_ask": "Write your message and I will pass it to the admin.",
        "support_sent": "Message sent. The reply will come here.",
        "support_reply": "💬 <b>Admin:</b>",
        "admin_cancelled": "The admin cancelled your booking:",
        "master": "Specialist",
        "unknown_command": "Choose an action in the menu.",
        "adm_help": (
            "<b>Admin commands</b>\n\n"
            "/today — bookings for today\n/tomorrow — for tomorrow\n/week — for 7 days\n"
            "/add — book a client by hand\n/block — close a specialist's time\n/blocks — closed time\n"
            "/export — CSV export\n/stats — statistics\n\n"
            "To answer a client, reply to their message."
        ),
        "adm_new": "🆕 <b>New booking</b>",
        "adm_new_manual": "🆕 <b>Booking created by an admin</b>",
        "adm_cancelled": "❌ <b>The client cancelled a booking</b>",
        "adm_moved": "🔁 <b>The client moved a booking</b>",
        "adm_was": "Was: {when}",
        "adm_day_empty": "no bookings",
        "adm_pick": "Tap a booking to change it:",
        "adm_btn_cancel": "❌ Cancel",
        "adm_btn_noshow": "🚫 No-show",
        "adm_done_cancel": "Booking cancelled, the client was notified.",
        "adm_done_noshow": "Marked as a no-show.",
        "adm_add_ask": "Send the client's name and phone in one message.\nExample: Aigerim +7 701 123 45 67",
        "adm_add_bad": "Name and phone are required. Example: Aigerim +7 701 123 45 67",
        "adm_add_for": "Booking for: <b>{name}</b>, {phone}",
        "adm_block_staff": "Whose time should be closed?",
        "adm_block_date": "<b>{staff}</b>\nChoose a day:",
        "adm_block_start": "<b>{staff}</b>, {day}\nClose from what time?",
        "adm_block_whole": "Whole day",
        "adm_block_end": "<b>{staff}</b>, {day}, from {start}\nUntil what time?",
        "adm_block_done": "🔒 Closed: <b>{staff}</b>, {when}",
        "adm_block_warn": "⚠️ There are {n} bookings in this time. They stay active, cancel them by hand.",
        "adm_day_off": "The specialist does not work on this day.",
        "adm_blocks_title": "Closed time. Tap to reopen:",
        "adm_blocks_empty": "No closed time.",
        "adm_block_deleted": "The time is open again.",
        "adm_export": "Bookings from {start} to {end}: {n}",
        "adm_stats": (
            "<b>Statistics</b>\n\n"
            "<b>7 days</b>\nvisits: {w_done} · cancelled: {w_cancel} · no-shows: {w_noshow}\nrevenue: {w_money}\n\n"
            "<b>30 days</b>\nvisits: {m_done} · cancelled: {m_cancel} · no-shows: {m_noshow}\nrevenue: {m_money}\n\n"
            "<b>Upcoming</b>: {upcoming}\n\n<b>Visits by specialist, 30 days</b>\n{by_staff}"
        ),
        "adm_support_from": "✉️ <b>{name}</b> {phone}\nReply to this message to answer.",
        "adm_reply_sent": "Reply sent.",
        "adm_reply_failed": "Not delivered: the client blocked the bot.",
        "adm_closed": "closed",
        "adm_confirmed": "confirmed",
        "adm_manual": "by hand",
        "status_active": "active",
        "status_done": "done",
        "status_cancelled": "cancelled",
        "status_noshow": "no-show",
    },
}


def guess_lang(code: str | None) -> str:
    code = (code or "").lower()[:2]
    return code if code in TEXTS else "ru"


def t(lang: str, key: str, **kwargs: object) -> str:
    text = TEXTS.get(lang, TEXTS["ru"]).get(key) or TEXTS["ru"][key]
    return text.format(**kwargs) if kwargs else text


def fmt_day(lang: str, day: date) -> str:
    lang = lang if lang in WEEKDAYS else "ru"
    return f"{WEEKDAYS[lang][day.weekday()]}, {day.day} {MONTHS[lang][day.month - 1]}"


def fmt_dt(lang: str, moment: datetime) -> str:
    return f"{fmt_day(lang, moment.date())} · {moment:%H:%M}"


def fmt_minutes(lang: str, minutes: int) -> str:
    minute_unit, hour_unit = UNITS.get(lang, UNITS["ru"])
    if minutes >= 60 and minutes % 60 == 0:
        return f"{minutes // 60} {hour_unit}"
    return f"{minutes} {minute_unit}"


def money(amount: int, currency: str) -> str:
    return f"{amount:,}".replace(",", " ") + f" {currency}"
