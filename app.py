"""
RusLearn Pro — Rus tilini o'rganish platformasi
Versiya: 1.0
Ishga tushirish: python app.py
"""
import os, sys, json, sqlite3, threading, hashlib, secrets, uuid
import webbrowser, subprocess, time, shutil
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps
from flask import (Flask, render_template, request, jsonify, session,
                   redirect, url_for, send_from_directory)

# ── Windows notification ──────────────────────────
try:
    from win10toast import ToastNotifier
    _toaster = ToastNotifier()
    NOTIF_AVAILABLE = True
except ImportError:
    NOTIF_AVAILABLE = False

def send_windows_notif(title, msg):
    """Windows tizim xabarnomasi"""
    if NOTIF_AVAILABLE:
        try:
            _toaster.show_toast(title, msg, duration=8, threaded=True)
            return
        except Exception:
            pass
    # Fallback: msg qutisi
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                ["powershell", "-WindowStyle", "Hidden", "-Command",
                 f'Add-Type -AssemblyName System.Windows.Forms;'
                 f'[System.Windows.Forms.MessageBox]::Show("{msg}", "{title}")'],
                creationflags=0x08000000
            )
    except Exception:
        pass

# ── PATHS ─────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
DB_PATH    = BASE_DIR / "data" / "ruslearn.db"
STATIC_DIR = BASE_DIR / "static"
DATA_DIR   = BASE_DIR / "data"

for d in [DATA_DIR, STATIC_DIR / "audio", STATIC_DIR / "css", STATIC_DIR / "js"]:
    d.mkdir(parents=True, exist_ok=True)

# ── FLASK ──────────────────────────────────────────
app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)



class Database:
    def __init__(self):
        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.Lock()
        self._create_tables()
        self._seed_data()

    def _create_tables(self):
        self.conn.executescript("""
        -- Sozlamalar
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT
        );

        -- O'quvchi profili
        CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY,
            name TEXT DEFAULT 'O''quvchi',
            level TEXT DEFAULT 'beginner',
            total_xp INTEGER DEFAULT 0,
            streak_days INTEGER DEFAULT 0,
            last_study_date TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );

        -- Lugat sozlar
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            russian TEXT NOT NULL,
            uzbek TEXT NOT NULL,
            pronunciation TEXT DEFAULT '',
            category TEXT DEFAULT 'general',
            level TEXT DEFAULT 'beginner',
            example_ru TEXT DEFAULT '',
            example_uz TEXT DEFAULT '',
            times_seen INTEGER DEFAULT 0,
            times_correct INTEGER DEFAULT 0,
            times_wrong INTEGER DEFAULT 0,
            next_review TEXT DEFAULT (datetime('now')),
            ease_factor REAL DEFAULT 2.5,
            interval_days INTEGER DEFAULT 1,
            is_downloaded INTEGER DEFAULT 0,
            edited_by_user INTEGER DEFAULT 0,
            added_at TEXT DEFAULT (datetime('now'))
        );

        -- Grammatika qoidalari
        CREATE TABLE IF NOT EXISTS grammar_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            level TEXT DEFAULT 'beginner',
            category TEXT DEFAULT 'general',
            examples_json TEXT DEFAULT '[]',
            exercises_json TEXT DEFAULT '[]',
            is_downloaded INTEGER DEFAULT 0,
            added_at TEXT DEFAULT (datetime('now'))
        );

        -- Dars jadvali
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            lesson_type TEXT DEFAULT 'vocabulary',
            scheduled_at TEXT NOT NULL,
            duration_min INTEGER DEFAULT 30,
            status TEXT DEFAULT 'pending',
            completed_at TEXT DEFAULT '',
            started_at TEXT DEFAULT '',
            score INTEGER DEFAULT 0,
            notified INTEGER DEFAULT 0
        );

        -- O'qish tarixi
        CREATE TABLE IF NOT EXISTS study_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_type TEXT NOT NULL,
            duration_sec INTEGER DEFAULT 0,
            score INTEGER DEFAULT 0,
            xp_earned INTEGER DEFAULT 0,
            details_json TEXT DEFAULT '{}',
            studied_at TEXT DEFAULT (datetime('now'))
        );

        -- O'yin natijalari
        CREATE TABLE IF NOT EXISTS game_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_type TEXT NOT NULL,
            score INTEGER DEFAULT 0,
            max_score INTEGER DEFAULT 0,
            time_sec INTEGER DEFAULT 0,
            played_at TEXT DEFAULT (datetime('now'))
        );

        -- Offline yuklamalar
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_type TEXT NOT NULL,
            content_id INTEGER NOT NULL,
            file_path TEXT DEFAULT '',
            size_kb INTEGER DEFAULT 0,
            downloaded_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_words_level    ON words(level);
        CREATE INDEX IF NOT EXISTS idx_words_review   ON words(next_review);
        CREATE INDEX IF NOT EXISTS idx_schedule_time  ON schedule(scheduled_at);
        CREATE INDEX IF NOT EXISTS idx_history_date   ON study_history(studied_at DESC);
        """)
        self.conn.commit()

    def _seed_data(self):
        """Boshlang'ich ma'lumotlarni yuklash"""
        # Profil
        if not self.conn.execute("SELECT id FROM profile").fetchone():
            self.conn.execute("INSERT INTO profile(id,name,level) VALUES(?,?,?)", (1, "O'quvchi", "beginner"))
            self.conn.commit()

        # Settings
        defaults = {
            "internet_allowed": "on",
            "daily_goal_min": "30",
            "notification_before_min": "30",
            "theme": "dark",
            "app_password": "",
            "ai_conversation_level": "beginner",
        }
        for k, v in defaults.items():
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
        self.conn.commit()

        # Boshlang'ich so'zlar (agar yo'q bo'lsa)
        cnt = self.conn.execute("SELECT COUNT(*) as c FROM words").fetchone()["c"]
        if cnt < 10:
            self._insert_starter_words()
            self._insert_grammar_rules()
        # Grammatika qoidalarini yangilash (yangi bosqichlar qo'shilsa)
        gr_cnt = self.conn.execute("SELECT COUNT(*) as c FROM grammar_rules").fetchone()["c"]
        if gr_cnt < 17:
            self._insert_grammar_rules()
        # Raqamlar to'liq ro'yxati (agar yo'q bo'lsa)

        # Cloze test boshlang'ich ma'lumotlar
        # AI panel boshlang'ich ma'lumotlar
    def _insert_starter_words(self):
        words = [
            # Salomlashish
            ("Привет", "Salom (norasmiy)", "Pree-vyet", "greeting", "beginner",
             "Привет, как дела?", "Salom, qanday ish?"),
            ("Здравствуйте", "Salom (rasmiy)", "Zdra-stvooy-tye", "greeting", "beginner",
             "Здравствуйте, меня зовут Иван.", "Salom, mening ismim Ivan."),
            ("До свидания", "Xayr", "Da svee-da-nya", "greeting", "beginner",
             "До свидания, до завтра!", "Xayr, ertaga ko'rishguncha!"),
            ("Спасибо", "Rahmat", "Spa-see-ba", "greeting", "beginner",
             "Большое спасибо!", "Katta rahmat!"),
            ("Пожалуйста", "Iltimos / Marhamat", "Pa-zha-lus-ta", "greeting", "beginner",
             "Пожалуйста, помогите мне.", "Iltimos, menga yordam bering."),
            # Raqamlar
            ("Один", "Bir", "A-deen", "numbers", "beginner",
             "У меня один брат.", "Menda bir aka bor."),
            ("Два", "Ikki", "Dva", "numbers", "beginner",
             "Два яблока.", "Ikki olma."),
            ("Три", "Uch", "Tree", "numbers", "beginner",
             "Три кошки.", "Uch mushuk."),
            ("Четыре", "To'rt", "Chye-tye-rye", "numbers", "beginner",
             "Четыре часа.", "To'rt soat."),
            ("Пять", "Besh", "Pyat'", "numbers", "beginner",
             "Пять минут.", "Besh daqiqa."),
            # Ranglar
            ("Красный", "Qizil", "Kras-niy", "colors", "beginner",
             "Красное яблоко.", "Qizil olma."),
            ("Синий", "Ko'k", "See-niy", "colors", "beginner",
             "Синее небо.", "Ko'k osmon."),
            ("Зелёный", "Yashil", "Zye-lyo-niy", "colors", "beginner",
             "Зелёная трава.", "Yashil o't."),
            ("Белый", "Oq", "Bye-liy", "colors", "beginner",
             "Белый снег.", "Oq qor."),
            ("Чёрный", "Qora", "Chyor-niy", "colors", "beginner",
             "Чёрная кошка.", "Qora mushuk."),
            # Oila
            ("Мама", "Ona", "Ma-ma", "family", "beginner",
             "Моя мама врач.", "Mening onam shifokor."),
            ("Папа", "Ota", "Pa-pa", "family", "beginner",
             "Мой папа работает.", "Mening otam ishlaydi."),
            ("Брат", "Aka/uka", "Brat", "family", "beginner",
             "У меня два брата.", "Menda ikki aka-uka bor."),
            ("Сестра", "Opa/singil", "Syes-tra", "family", "beginner",
             "Моя сестра студентка.", "Mening opam talaba."),
            ("Друг", "Do'st", "Drook", "family", "beginner",
             "Он мой лучший друг.", "U mening eng yaxshi do'stim."),
            # Oziq-ovqat
            ("Хлеб", "Non", "Khlyeb", "food", "beginner",
             "Свежий хлеб вкусный.", "Yangi non mazali."),
            ("Вода", "Suv", "Va-da", "food", "beginner",
             "Дайте мне воды.", "Menga suv bering."),
            ("Молоко", "Sut", "Ma-la-ko", "food", "beginner",
             "Я пью молоко.", "Men sut ichaman."),
            ("Яблоко", "Olma", "Yab-la-ka", "food", "beginner",
             "Яблоко красное.", "Olma qizil."),
            ("Чай", "Choy", "Chay", "food", "beginner",
             "Хотите чай?", "Choy ichasizmi?"),
            # O'rta daraja
            ("Работать", "Ishlash", "Ra-bo-tat'", "verbs", "intermediate",
             "Я работаю каждый день.", "Men har kuni ishlayman."),
            ("Учиться", "O'qish/o'rganish", "U-chit'-sya", "verbs", "intermediate",
             "Я учусь русскому языку.", "Men rus tilini o'rganaman."),
            ("Говорить", "Gapirish", "Ga-va-reet'", "verbs", "intermediate",
             "Она говорит по-русски.", "U rus tilida gapiradi."),
            ("Понимать", "Tushunish", "Pa-nee-mat'", "verbs", "intermediate",
             "Я не понимаю.", "Men tushunmayapman."),
            ("Хотеть", "Xohlamoq", "Kha-tyet'", "verbs", "intermediate",
             "Я хочу есть.", "Men yemoqchi edim."),

            # ── 100 ta o'rta darajali so'z ──────────────────────────────

            # Fe'llar (verbs)
            ("Читать",    "O'qimoq",       "chee-TAT'",      "verbs","intermediate","Я читаю книгу каждый день.","Men har kuni kitob o'qiyman."),
            ("Писать",    "Yozmoq",         "pee-SAT'",       "verbs","intermediate","Она пишет письмо.","U xat yozyapti."),
            ("Слушать",   "Tinglash",       "SLOOS-shat'",    "verbs","intermediate","Я слушаю музыку.","Men musiqa tinglayapman."),
            ("Смотреть",  "Qaramoq/ko'rmoq","smat-RYET'",     "verbs","intermediate","Мы смотрим фильм.","Biz film ko'rayapmiz."),
            ("Идти",      "Bormoq (yayov)", "eet-TEE",        "verbs","intermediate","Я иду в школу.","Men maktabga borayapman."),
            ("Ехать",     "Bormoq (transport)","YEH-khat'",   "verbs","intermediate","Он едет на работу.","U ishga ketyapti."),
            ("Знать",     "Bilmoq",         "znat'",          "verbs","intermediate","Я знаю русский язык.","Men rus tilini bilaman."),
            ("Думать",    "O'ylamoq",       "DOO-mat'",       "verbs","intermediate","Я думаю о тебе.","Men seni o'ylayapman."),
            ("Любить",    "Sevmoq",         "lyoo-BEET'",     "verbs","intermediate","Я люблю тебя.","Men seni sevaman."),
            ("Помочь",    "Yordam bermoq",  "pa-MOCH'",       "verbs","intermediate","Помогите мне, пожалуйста.","Iltimos, menga yordam bering."),
            ("Купить",    "Sotib olmoq",    "koo-PEET'",      "verbs","intermediate","Я хочу купить книгу.","Men kitob sotib olmoqchiman."),
            ("Продать",   "Sotmoq",         "pra-DAT'",       "verbs","intermediate","Он продаёт машину.","U mashina sotmoqda."),
            ("Открыть",   "Ochmoq",         "atk-RYT'",       "verbs","intermediate","Откройте окно.","Derazani oching."),
            ("Закрыть",   "Yopmoq",         "zak-RYT'",       "verbs","intermediate","Закройте дверь.","Eshikni yoping."),
            ("Начать",    "Boshlash",       "na-CHAT'",       "verbs","intermediate","Начнём урок.","Darsni boshlaymiz."),
            ("Кончить",   "Tugatmoq",       "KON-chit'",      "verbs","intermediate","Я закончил работу.","Men ishni tugatdim."),
            ("Ждать",     "Kutmoq",         "zhdat'",         "verbs","intermediate","Подождите меня.","Meni kuting."),
            ("Спросить",  "So'ramoq",       "spra-SEET'",     "verbs","intermediate","Можно спросить?","So'rasam bo'ladimi?"),
            ("Ответить",  "Javob bermoq",   "at-VYE-tit'",    "verbs","intermediate","Ответьте на вопрос.","Savolga javob bering."),
            ("Приехать",  "Kelmoq (transport)","pree-YEH-khat'","verbs","intermediate","Он приехал вчера.","U kecha keldi."),

            # Sifatlar (adjectives)
            ("Большой",   "Katta",          "bal'-SHOY",      "adjectives","intermediate","Это большой город.","Bu katta shahar."),
            ("Маленький", "Kichkina",       "MA-lyen'-keey",  "adjectives","intermediate","У неё маленький котёнок.","Uning kichkina mushukchasi bor."),
            ("Хороший",   "Yaxshi",         "kha-RO-shiy",    "adjectives","intermediate","Он хороший человек.","U yaxshi odam."),
            ("Плохой",    "Yomon",          "pla-KHOY",       "adjectives","intermediate","Погода плохая.","Ob-havo yomon."),
            ("Красивый",  "Chiroyli",       "kra-SEE-viy",    "adjectives","intermediate","Какая красивая девушка!","Qanday chiroyli qiz!"),
            ("Умный",     "Aqlli",          "OOM-niy",        "adjectives","intermediate","Он очень умный.","U juda aqlli."),
            ("Быстрый",   "Tez",            "BYST-riy",       "adjectives","intermediate","Он быстрый бегун.","U tez yuguruvchi."),
            ("Медленный", "Sekin",          "MYED-lyen-niy",  "adjectives","intermediate","Машина едет медленно.","Mashina sekin ketyapti."),
            ("Дорогой",   "Qimmat / Aziz",  "da-ra-GOY",      "adjectives","intermediate","Это слишком дорого.","Bu juda qimmat."),
            ("Дешёвый",   "Arzon",          "dye-SHYO-viy",   "adjectives","intermediate","Здесь дешёвые продукты.","Bu yerda arzon mahsulotlar."),
            ("Старый",    "Eski / Keksa",   "STA-riy",        "adjectives","intermediate","Это старый дом.","Bu eski uy."),
            ("Молодой",   "Yosh",           "ma-la-DOY",      "adjectives","intermediate","Он молодой врач.","U yosh shifokor."),
            ("Тяжёлый",   "Og'ir",          "tya-ZHYO-liy",   "adjectives","intermediate","Этот чемодан тяжёлый.","Bu chemodon og'ir."),
            ("Лёгкий",    "Yengil",         "LYOKH-keey",     "adjectives","intermediate","Задание лёгкое.","Vazifa yengil."),
            ("Горячий",   "Issiq",          "ga-RYA-cheey",   "adjectives","intermediate","Чай горячий.","Choy issiq."),
            ("Холодный",  "Sovuq",          "kha-LOD-niy",    "adjectives","intermediate","Погода холодная.","Ob-havo sovuq."),
            ("Интересный","Qiziqarli",      "in-tye-RYES-niy","adjectives","intermediate","Это интересная книга.","Bu qiziqarli kitob."),
            ("Скучный",   "Zerikali",       "SKOOCH-niy",     "adjectives","intermediate","Фильм скучный.","Film zerikarli."),
            ("Правильный","To'g'ri",        "PRA-vil'-niy",   "adjectives","intermediate","Это правильный ответ.","Bu to'g'ri javob."),
            ("Важный",    "Muhim",          "VAZH-niy",       "adjectives","intermediate","Это важное решение.","Bu muhim qaror."),

            # Ot (nouns) — shahar, joy, vaqt
            ("Город",     "Shahar",         "GO-rat",         "travel","intermediate","Мы живём в большом городе.","Biz katta shaharda yashaymiz."),
            ("Улица",     "Ko'cha",         "OO-lee-tsa",     "travel","intermediate","Он живёт на этой улице.","U shu ko'chada yashaydi."),
            ("Дорога",    "Yo'l",           "da-RO-ga",       "travel","intermediate","Дорога длинная.","Yo'l uzun."),
            ("Магазин",   "Do'kon",         "ma-ga-ZEEN",     "travel","intermediate","Я иду в магазин.","Men do'konga ketyapman."),
            ("Рынок",     "Bozor",          "RY-nak",         "travel","intermediate","На рынке много людей.","Bozorda ko'p odam bor."),
            ("Больница",  "Kasalxona",      "bal'-NEE-tsa",   "health","intermediate","Он в больнице.","U kasalxonada."),
            ("Аптека",    "Dorixona",       "ap-TYE-ka",      "health","intermediate","Аптека рядом.","Dorixona yaqinda."),
            ("Станция",   "Bekat/stansiya", "STAN-tsiy-ya",   "travel","intermediate","Где станция метро?","Metro bekati qayerda?"),
            ("Самолёт",   "Samolyot",       "sa-ma-LYOT",     "travel","intermediate","Самолёт летит быстро.","Samolyot tez uchadi."),
            ("Поезд",     "Poyezd",         "PO-yezd",        "travel","intermediate","Поезд опоздал.","Poyezd kechikdi."),
            ("Билет",     "Chipta",         "bee-LYET",       "travel","intermediate","Купите билет заранее.","Chiptani oldindan sotib oling."),
            ("Паспорт",   "Pasport",        "PAS-port",       "travel","intermediate","Покажите паспорт.","Pasportingizni ko'rsating."),
            ("Гостиница", "Mehmonxona",     "gas-TEE-nee-tsa","travel","intermediate","Мы живём в гостинице.","Biz mehmonxonada yashaymiz."),
            ("Ресторан",  "Restoran",       "ryes-ta-RAN",    "food","intermediate","Давайте пойдём в ресторан.","Keling, restoranga boraylik."),
            ("Завтрак",   "Nonushta",       "ZAV-trak",       "food","intermediate","Завтрак готов.","Nonushta tayyor."),
            ("Обед",      "Tushlik",        "a-BYET",         "food","intermediate","Обед в 13:00.","Tushlik 13:00 da."),
            ("Ужин",      "Kechki ovqat",   "OO-zhyn",        "food","intermediate","Ужин вкусный.","Kechki ovqat mazali."),
            ("Суп",       "Sho'rva",        "soop",           "food","intermediate","Суп горячий.","Sho'rva issiq."),
            ("Мясо",      "Go'sht",         "MYA-sa",         "food","intermediate","Я люблю мясо.","Men go'sht yaxshi ko'raman."),
            ("Рыба",      "Baliq",          "RY-ba",          "food","intermediate","Рыба полезна.","Baliq foydali."),

            # Ot — ish, ta'lim
            ("Работа",    "Ish",            "ra-BO-ta",       "work","intermediate","Работа трудная.","Ish qiyin."),
            ("Офис",      "Ofis",           "O-fis",          "work","intermediate","Он работает в офисе.","U ofisda ishlaydi."),
            ("Директор",  "Direktor",       "dee-RYEK-tar",   "work","intermediate","Директор на совещании.","Direktor yig'ilishda."),
            ("Коллега",   "Hamkasb",        "kal-LYE-ga",     "work","intermediate","Мой коллега умный.","Hamkasibim aqlli."),
            ("Зарплата",  "Maosh",          "zar-PLA-ta",     "work","intermediate","Зарплата хорошая.","Maosh yaxshi."),
            ("Собрание",  "Yig'ilish",      "sab-RA-niy-ye",  "work","intermediate","Сегодня собрание.","Bugun yig'ilish bor."),
            ("Задание",   "Vazifa",         "za-DA-niy-ye",   "work","intermediate","Задание выполнено.","Vazifa bajarildi."),
            ("Результат", "Natija",         "rye-zool'-TAT",  "work","intermediate","Результат хороший.","Natija yaxshi."),
            ("Университет","Universitet",   "oo-nee-vyer-see-TYET","work","intermediate","Я учусь в университете.","Men universitetda o'qiyman."),
            ("Экзамен",   "Imtihon",        "ek-za-MYEN",     "work","intermediate","Завтра экзамен.","Ertaga imtihon."),

            # Ot — vaqt
            ("Сегодня",   "Bugun",          "see-VOD-nya",    "time","intermediate","Сегодня хорошая погода.","Bugun ob-havo yaxshi."),
            ("Завтра",    "Ertaga",         "ZAV-tra",        "time","intermediate","Завтра выходной.","Ertaga dam olish kuni."),
            ("Вчера",     "Kecha",          "fche-RA",        "time","intermediate","Вчера был дождь.","Kecha yomg'ir yog'di."),
            ("Сейчас",    "Hozir",          "see-CHAS",       "time","intermediate","Я занят сейчас.","Men hozir bandman."),
            ("Скоро",     "Tez orada",      "SKO-ra",         "time","intermediate","Он скоро придёт.","U tez orada keladi."),
            ("Всегда",    "Doimo",          "fsyeg-DA",       "time","intermediate","Я всегда рано встаю.","Men doimo erta turaman."),
            ("Никогда",   "Hech qachon",    "nee-kag-DA",     "time","intermediate","Я никогда не опаздываю.","Men hech qachon kechikmayman."),
            ("Иногда",    "Ba'zan",         "ee-nag-DA",      "time","intermediate","Иногда я смотрю кино.","Ba'zan kino ko'raman."),
            ("Утро",      "Ertalab",        "OOT-ra",         "time","intermediate","Доброе утро!","Xayrli ertalab!"),
            ("Вечер",     "Kechqurun",      "VYE-chyer",      "time","intermediate","Добрый вечер!","Xayrli kechqurun!"),
            ("Ночь",      "Tun",            "noch'",          "time","intermediate","Спокойной ночи!","Xayrli tun!"),
            ("Неделя",    "Hafta",          "nee-DYE-lya",    "time","intermediate","На этой неделе.","Bu hafta."),
            ("Месяц",     "Oy",             "MYE-syats",      "time","intermediate","В этом месяце.","Bu oyda."),
            ("Год",       "Yil",            "got",            "time","intermediate","В этом году.","Bu yil."),

            # Ot — his-tuyg'ular, aloqa
            ("Радость",   "Xursandlik",     "RA-dast'",       "emotions","intermediate","Какая радость!","Qanday xursandlik!"),
            ("Грусть",    "Qayg'u",         "groos't'",       "emotions","intermediate","В его глазах грусть.","Uning ko'zlarida qayg'u bor."),
            ("Страх",     "Qo'rquv",        "strakh",         "emotions","intermediate","Не бойся, страха нет.","Qo'rqma, xavf yo'q."),
            ("Надежда",   "Umid",           "na-DYEZH-da",    "emotions","intermediate","Надежда есть всегда.","Umid doimo bor."),
            ("Удача",     "Omad",           "oo-DA-cha",      "emotions","intermediate","Желаю удачи!","Omad tilayman!"),
            ("Успех",     "Muvaffaqiyat",   "oos-PYEKH",      "emotions","intermediate","Желаю успеха!","Muvaffaqiyat tilayman!"),
            ("Проблема",  "Muammo",         "prab-LYE-ma",    "emotions","intermediate","Нет проблем.","Muammo yo'q."),
            ("Извинение", "Kechirim",       "eez-vee-NYE-niy-ye","emotions","intermediate","Примите мои извинения.","Uzrni qabul qiling."),
            ("Привычка",  "Odat",           "pree-VYCH-ka",   "emotions","intermediate","Хорошая привычка.","Yaxshi odat."),
            ("Мечта",     "Orzu",           "myech-TA",       "emotions","intermediate","Моя мечта — путешествовать.","Mening orzum — sayohat qilish."),

            # Ot — tabiat
            ("Погода",    "Ob-havo",        "pa-GO-da",       "nature","intermediate","Погода хорошая сегодня.","Bugun ob-havo yaxshi."),
            ("Солнце",    "Quyosh",         "SON-tse",        "nature","intermediate","Солнце светит ярко.","Quyosh yorqin nurlanadi."),
            ("Дождь",     "Yomg'ir",        "dozh'd'",        "nature","intermediate","Идёт дождь.","Yomg'ir yog'yapton."),
            ("Снег",      "Qor",            "snyeg",          "nature","intermediate","Снег белый и чистый.","Qor oq va toza."),
            ("Ветер",     "Shamol",         "VYE-tyer",       "nature","intermediate","Сильный ветер.","Kuchli shamol."),
            ("Лес",       "O'rmon",         "lyes",           "nature","intermediate","Мы гуляем в лесу.","Biz o'rmonda sayr qilamiz."),
            ("Река",      "Daryo",          "rye-KA",         "nature","intermediate","Река широкая.","Daryo keng."),
            ("Море",      "Dengiz",         "MO-rye",         "nature","intermediate","Мы едем на море.","Biz dengizga boramiz."),
            ("Горы",      "Tog'lar",        "GO-ry",          "nature","intermediate","Горы красивые.","Tog'lar chiroyli."),
            ("Цветок",    "Gul",            "tsve-TOK",       "nature","intermediate","Этот цветок красивый.","Bu gul chiroyli."),
        ]
        for w in words:
            self.conn.execute("""INSERT OR IGNORE INTO words
                (russian,uzbek,pronunciation,category,level,example_ru,example_uz)
                VALUES(?,?,?,?,?,?,?)""", w)
        self.conn.commit()

    def _insert_introduction_words(self):
        """O'zini tanishtirish uchun 50 ta so'z"""
        words = [
            # ── Asosiy tanishish iboralari ──────────────────────────────────
            ("Меня зовут",   "Mening ismim",       "MYE-nya ZO-voot",    "introduction","beginner",
             "Меня зовут Алишер.",                 "Mening ismim Alisher."),
            ("Как вас зовут?","Sizning ismingiz?",  "kak vas ZO-voot",    "introduction","beginner",
             "Как вас зовут? — Меня зовут Анна.",  "Ismingiz nima? — Mening ismim Anna."),
            ("Приятно познакомиться","Tanishganimdan xursandman","pree-YAT-na paz-na-KO-mee-tsya","introduction","beginner",
             "Очень приятно познакомиться!",        "Tanishganimdan juda xursandman!"),
            ("Рад(а) познакомиться","Tanishgandan xursand","rat paz-na-KO-mee-tsya","introduction","beginner",
             "Рад познакомиться с вами.",           "Siz bilan tanishganimdan xursandman."),
            ("Откуда вы?",   "Qayerdansiz?",       "at-KOO-da vy",       "introduction","beginner",
             "Откуда вы? — Я из Узбекистана.",     "Qayerdansiz? — Men O'zbekistondan."),
            ("Я из ...",     "Men ... dan",        "ya eez",             "introduction","beginner",
             "Я из Ташкента.",                     "Men Toshkentdan."),
            ("Где вы живёте?","Qayerda yashaysiz?","gdye vy zhee-VYO-tye","introduction","beginner",
             "Где вы живёте? — В Ташкенте.",       "Qayerda yashaysiz? — Toshkentda."),
            ("Я живу в ...", "Men ... da yashayman","ya zhee-VOO v",     "introduction","beginner",
             "Я живу в Самарканде.",               "Men Samarqandda yashayman."),
            ("Сколько вам лет?","Yoshingiz necha?","SKOL'-ka vam lyet",  "introduction","beginner",
             "Сколько вам лет? — Мне 25 лет.",     "Yoshingiz necha? — Menga 25 yosh."),
            ("Мне ... лет",  "Menga ... yosh",     "mnye ... lyet",      "introduction","beginner",
             "Мне двадцать два года.",             "Menga yigirma ikki yosh."),
            # ── Kasb va ta'lim ──────────────────────────────────────────────
            ("Кем вы работаете?","Qayerda ishlaysiz?","kyem vy ra-BO-ta-ye-tye","introduction","beginner",
             "Кем вы работаете? — Я учитель.",     "Nima ishlaysiz? — Men o'qituvchiman."),
            ("Я работаю ...", "Men ... da ishlayman","ya ra-BO-ta-yu",   "introduction","beginner",
             "Я работаю в школе.",                 "Men maktabda ishlayman."),
            ("Я студент",    "Men talabaman",       "ya stoo-DYENT",      "introduction","beginner",
             "Я студент университета.",            "Men universitet talabasi."),
            ("Я учусь в ...", "Men ... da o'qiyman","ya oo-CHOOS' v",    "introduction","beginner",
             "Я учусь в университете.",            "Men universitetda o'qiyman."),
            ("Я учитель",    "Men o'qituvchiman",   "ya oo-CHEE-tyel'",   "introduction","beginner",
             "Я учитель русского языка.",          "Men rus tili o'qituvchisiman."),
            ("Я врач",       "Men shifokorman",     "ya vrach",           "introduction","beginner",
             "Я работаю врачом.",                  "Men shifokor bo'lib ishlayman."),
            ("Я инженер",    "Men muhandisман",     "ya een-zhe-NYER",    "introduction","beginner",
             "Я инженер-программист.",             "Men dasturchi muhandisман."),
            ("Профессия",    "Kasb",               "pra-FYE-see-ya",     "introduction","beginner",
             "Какая у вас профессия?",             "Sizning kasbingiz nima?"),
            ("Специальность","Mutaxassislik",      "spye-tsee-AL'-nast'","introduction","intermediate",
             "Моя специальность — экономика.",    "Mening mutaxassisligim — iqtisodiyot."),
            ("Образование",  "Ta'lim/ma'lumot",   "ab-ra-za-VA-niy-ye", "introduction","intermediate",
             "У меня высшее образование.",        "Menda oliy ma'lumot bor."),
            # ── Oilaviy holat ───────────────────────────────────────────────
            ("Женат / Замужем","Uylanganman/Turmushga chiqqanman","zhe-NAT / ZA-moo-zhem","introduction","intermediate",
             "Я женат. — Я замужем.",             "Uylanganman. — Turmushga chiqqanman."),
            ("Холост / Не замужем","Uylanganum yo'q","KHO-last / nye ZA-moo-zhem","introduction","intermediate",
             "Я ещё холост.",                     "Men hali uylanganum yo'q."),
            ("У меня есть дети","Mening bolalarim bor","oo mye-NYA yest' DYE-tee","introduction","intermediate",
             "У меня есть сын и дочь.",           "Menda o'g'il va qiz bor."),
            ("Сын",          "O'g'il",             "syn",                "introduction","beginner",
             "Мой сын учится в школе.",           "Mening o'g'lim maktabda o'qiydi."),
            ("Дочь",         "Qiz (farzand)",      "doch'",              "introduction","beginner",
             "Моей дочери пять лет.",             "Qizimga besh yosh."),
            # ── Til bilish ──────────────────────────────────────────────────
            ("Вы говорите по-русски?","Rus tilida gapirасизми?","vy ga-va-REE-tye pa-ROOS-kee","introduction","beginner",
             "Вы говорите по-русски?",            "Rus tilida gapirасизми?"),
            ("Я говорю по-русски немного","Rus tilida ozgina gapiraman","ya ga-va-RYOO pa-ROOS-kee nee-MNO-ga","introduction","beginner",
             "Я говорю по-русски немного.",       "Men rus tilida ozgina gapiraman."),
            ("Я учу русский язык","Men rus tilini o'rganаман","ya oo-CHOO ROOS-keey ya-ZYK","introduction","beginner",
             "Я учу русский язык уже год.",       "Men rus tilini bir yildan beri o'rganаман."),
            ("Я не понимаю","Men tushunmаман",    "ya nye pa-nee-MA-yu","introduction","beginner",
             "Извините, я не понимаю.",           "Kechirasiz, men tushunmаман."),
            ("Повторите, пожалуйста","Iltimos, takrorlang","paf-ta-REE-tye pa-ZHA-lus-ta","introduction","beginner",
             "Повторите, пожалуйста, медленнее.", "Iltimos, sekinroq takrorlang."),
            # ── Qiziqishlar ─────────────────────────────────────────────────
            ("Хобби",        "Sevimli mashg'ulot",  "KHO-bee",            "introduction","intermediate",
             "Какое у вас хобби?",                "Sizning xobbingiz nima?"),
            ("Мне нравится","Menga yoqadi",        "mnye NRA-vee-tsya",  "introduction","beginner",
             "Мне нравится читать книги.",        "Menga kitob o'qish yoqadi."),
            ("Я люблю",      "Men ... ni yaxshi ko'raman","ya lyoob-LYOO","introduction","beginner",
             "Я люблю слушать музыку.",           "Men musiqa tinglashni yaxshi ko'raman."),
            ("Я занимаюсь спортом","Men sport bilan shug'ullanaman","ya za-nee-MA-yoos' SPOR-tam","introduction","intermediate",
             "Я занимаюсь футболом.",             "Men futbol bilan shug'ullanaman."),
            ("Свободное время","Bo'sh vaqt",       "svа-BOD-na-ye VRE-mya","introduction","intermediate",
             "В свободное время я читаю.",        "Bo'sh vaqtimda kitob o'qiyman."),
            # ── Tashqi ko'rinish va xarakter ───────────────────────────────
            ("Высокий / Низкий","Baland/past bo'yli","vy-SO-keey / NEES-keey","introduction","intermediate",
             "Он высокий и стройный.",            "U baland bo'yli va kelishgan."),
            ("Волосы",       "Soch",               "VO-la-sy",           "introduction","beginner",
             "У меня тёмные волосы.",             "Mening sochlam qora."),
            ("Глаза",        "Ko'zlar",            "gla-ZA",             "introduction","beginner",
             "У неё синие глаза.",                "Uning ko'zlari ko'k."),
            ("Характер",     "Xarakter",           "kha-RAK-tyer",       "introduction","intermediate",
             "У него хороший характер.",          "Uning xarakteri yaxshi."),
            ("Добрый",       "Mehribon",           "DOB-riy",            "introduction","beginner",
             "Она очень добрая.",                 "U juda mehribon."),
            # ── Foydali ibotalar ────────────────────────────────────────────
            ("Разрешите представиться","Tanishamiz, ruxsat eting","raz-rye-SHEE-tye pred-STA-vee-tsya","introduction","intermediate",
             "Разрешите представиться — меня зовут Камол.", "Tanishamiz — mening ismim Kamol."),
            ("Давайте познакомимся","Keling, tanishamiz","da-VAY-tye paz-na-KO-meem-sya","introduction","intermediate",
             "Давайте познакомимся!",             "Keling, tanishamiz!"),
            ("Очень рад(а) вас видеть","Sizni ko'rganimdan xursandman","O-chen' rat vas VEE-dyet'","introduction","intermediate",
             "Очень рад вас снова видеть!",       "Sizni qayta ko'rganimdan xursandman!"),
            ("До свидания",  "Xayr (rasmiy)",      "da svee-DA-nee-ya",  "introduction","beginner",
             "До свидания, до встречи!",          "Xayr, ko'rishguncha!"),
            ("До встречи",   "Ko'rishguncha",      "da VSTRE-chee",      "introduction","beginner",
             "До встречи завтра!",                "Ertaga ko'rishguncha!"),
            ("Пока",         "Xayr (norasmiy)",    "pa-KA",              "introduction","beginner",
             "Пока, увидимся!",                   "Xayr, ko'rishamiz!"),
            ("Как дела?",    "Qanday ishlar?",     "kak dee-LA",         "introduction","beginner",
             "Привет! Как дела? — Всё хорошо.",  "Salom! Qanday ishlar? — Hammasi yaxshi."),
            ("Всё хорошо",   "Hammasi yaxshi",     "fsyo kha-ra-SHO",    "introduction","beginner",
             "У меня всё хорошо, спасибо!",      "Menda hammasi yaxshi, rahmat!"),
            ("Неплохо",      "Yomon emas",         "nye-PLO-kha",        "introduction","beginner",
             "Как дела? — Неплохо, спасибо.",     "Qanday ishlar? — Yomon emas, rahmat."),
            ("Нормально",    "Normal/Oddiy",       "nar-MAL'-na",        "introduction","beginner",
             "Как ты? — Нормально.",              "Qandaysan? — Normal."),
            ("Возраст",      "Yosh (ot)",          "VOZ-rast",           "introduction","intermediate",
             "Какой у вас возраст?",              "Yoshingiz necha?"),
            ("Имя",          "Ism",                "EE-mya",             "introduction","beginner",
             "Как ваше имя?",                     "Ismingiz nima?"),
            ("Фамилия",      "Familiya",           "fa-MEE-lee-ya",      "introduction","beginner",
             "Как ваша фамилия?",                 "Familiyangiz nima?"),
        ]
        for w in words:
            self.conn.execute("""INSERT OR IGNORE INTO words
                (russian,uzbek,pronunciation,category,level,example_ru,example_uz)
                VALUES(?,?,?,?,?,?,?)""", w)
        self.conn.commit()

    def _insert_navigation_words(self):
        """Yo'l va joylarga oid 53 ta grammatik so'z"""
        words = [
            # ── Yo'l so'rash ──────────────────────────────────────────────
            ("Где находится ...?", "... qayerda joylashgan?",     "gdye na-KHO-dee-tsya",  "navigation","beginner",
             "Где находится вокзал?",                             "Vokzal qayerda joylashgan?"),
            ("Как пройти до ...?","... ga qanday borish mumkin?", "kak pray-TEE da",        "navigation","beginner",
             "Как пройти до метро?",                              "Metroga qanday borish mumkin?"),
            ("Как доехать до ...?","... ga qanday etib borish?",  "kak da-YEH-khat' da",   "navigation","beginner",
             "Как доехать до аэропорта?",                         "Aeroportga qanday etib borish?"),
            ("Скажите, пожалуйста","Iltimos, ayting",             "ska-ZHEE-tye pa-ZHA-lus-ta","navigation","beginner",
             "Скажите, пожалуйста, где аптека?",                  "Iltimos, dorixona qayerda?"),
            ("Я заблудился",     "Men adashib qoldim",            "ya za-bloo-DEE-lsya",    "navigation","beginner",
             "Помогите, я заблудился!",                           "Yordam bering, adashib qoldim!"),
            ("Покажите на карте","Xaritada ko'rsating",           "pa-ka-ZHEE-tye na KAR-tye","navigation","intermediate",
             "Покажите на карте, где мы находимся.",              "Xaritada qaerda ekanligimizni ko'rsating."),

            # ── Yo'nalish so'zlari ───────────────────────────────────────
            ("Прямо",            "To'g'ri",                       "PRYA-ma",                "navigation","beginner",
             "Идите прямо двести метров.",                        "To'g'ri ikki yuz metr yuring."),
            ("Налево",           "Chapga",                        "na-LYE-va",              "navigation","beginner",
             "Поверните налево у светофора.",                     "Svetofor oldida chapga buriling."),
            ("Направо",          "O'ngga",                        "na-PRA-va",              "navigation","beginner",
             "Поверните направо.",                                "O'ngga buriling."),
            ("Назад",            "Orqaga",                        "na-ZAT",                 "navigation","beginner",
             "Вернитесь назад.",                                  "Orqaga qayting."),
            ("Вперёд",           "Oldinga",                       "fpye-RYOT",              "navigation","beginner",
             "Идите вперёд.",                                     "Oldinga yuring."),
            ("Рядом",            "Yaqinda / yonida",              "RYA-dam",                "navigation","beginner",
             "Банк рядом с почтой.",                              "Bank pochta yonida."),
            ("Напротив",         "Qarshisida",                    "na-PRO-teev",            "navigation","beginner",
             "Аптека напротив школы.",                            "Dorixona maktab qarshisida."),
            ("Рядом с",          "... yonida",                    "RYA-dam s",              "navigation","beginner",
             "Кафе рядом с банком.",                              "Kafe bank yonida."),
            ("Между",            "Orasida",                       "MYEZH-doo",              "navigation","beginner",
             "Парк между банком и почтой.",                       "Park bank va pochta orasida."),
            ("За углом",         "Burchak ortida",                "za oog-LOM",             "navigation","intermediate",
             "Магазин за углом.",                                 "Do'kon burchak ortida."),
            ("На перекрёстке",   "Chorrahada",                    "na pye-rye-KRYOS-tkye",  "navigation","intermediate",
             "Поверните на перекрёстке.",                         "Chorrahada buriling."),
            ("До светофора",     "Svetoforgacha",                 "da svye-ta-FO-ra",       "navigation","intermediate",
             "Идите прямо до светофора.",                         "Svetoforgacha to'g'ri boring."),

            # ── Transport turlari ─────────────────────────────────────────
            ("Метро",            "Metro",                         "myet-RO",                "navigation","beginner",
             "Где ближайшее метро?",                              "Eng yaqin metro qayerda?"),
            ("Автобус",          "Avtobus",                       "af-TO-boos",             "navigation","beginner",
             "Какой автобус едет в центр?",                       "Markazga qaysi avtobus boradi?"),
            ("Маршрутка",        "Marshrutka",                    "mar-SHROOT-ka",          "navigation","beginner",
             "Маршрутка № 15 идёт до вокзала.",                  "15-marshrutka vokzalgacha boradi."),
            ("Такси",            "Taksi",                         "tak-SEE",                "navigation","beginner",
             "Вызовите такси, пожалуйста.",                       "Iltimos, taksi chaqiring."),
            ("Троллейбус",       "Trolleybus",                    "tral-LYEY-boos",         "navigation","beginner",
             "Троллейбус останавливается здесь.",                 "Trolleybus shu yerda to'xtaydi."),
            ("Трамвай",          "Tramvay",                       "tram-VAY",               "navigation","beginner",
             "Трамвай идёт до центра.",                           "Tramvay markazgacha boradi."),
            ("Пешком",           "Yayov",                         "pyesh-KOM",              "navigation","beginner",
             "Отсюда пешком пять минут.",                         "Bu yerdan yayov besh daqiqa."),

            # ── Joy nomlari ───────────────────────────────────────────────
            ("Остановка",        "Bekat",                         "as-ta-NOF-ka",           "navigation","beginner",
             "Следующая остановка — рынок.",                      "Keyingi bekat — bozor."),
            ("Вокзал",           "Vokzal",                        "vak-ZAL",                "navigation","beginner",
             "До вокзала далеко?",                                "Vokzalgacha uzoqmi?"),
            ("Аэропорт",         "Aeroport",                      "a-e-ra-PORT",            "navigation","beginner",
             "Аэропорт далеко от центра.",                        "Aeroport markazdan uzoq."),
            ("Центр города",     "Shahar markazi",                "TSENTR GO-ra-da",        "navigation","beginner",
             "Как доехать до центра?",                            "Markazga qanday borish mumkin?"),
            ("Площадь",          "Maydon",                        "PLO-shchad'",            "navigation","beginner",
             "Встретимся на площади.",                            "Maydonida uchrashamiz."),
            ("Парк",             "Park",                          "park",                   "navigation","beginner",
             "Парк рядом с домом.",                               "Park uy yonida."),
            ("Банк",             "Bank",                          "bank",                   "navigation","beginner",
             "Банк работает с 9 до 18.",                          "Bank 9 dan 18 gacha ishlaydi."),
            ("Почта",            "Pochta",                        "POCH-ta",                "navigation","beginner",
             "Почта закрыта.",                                    "Pochta yopiq."),
            ("Полиция",          "Politsiya",                     "pa-LEE-tsee-ya",         "navigation","beginner",
             "Где полиция?",                                      "Politsiya qayerda?"),
            ("Посольство",       "Elchixona",                     "pa-SOL'-stva",           "navigation","intermediate",
             "Посольство Узбекистана здесь.",                     "O'zbekiston elchixonasi shu yerda."),

            # ── Masofa va vaqt ────────────────────────────────────────────
            ("Далеко",           "Uzoq",                          "da-lye-KO",              "navigation","beginner",
             "Это далеко отсюда?",                                "Bu yerdan uzoqmi?"),
            ("Близко",           "Yaqin",                         "BLEES-ka",               "navigation","beginner",
             "Вокзал близко.",                                    "Vokzal yaqin."),
            ("Отсюда",           "Bu yerdan",                     "at-SYOO-da",             "navigation","beginner",
             "Отсюда двести метров.",                             "Bu yerdan ikki yuz metr."),
            ("Минут пешком",     "Daqiqa yayov",                  "mee-NOOT pyesh-KOM",     "navigation","beginner",
             "Пять минут пешком.",                                "Besh daqiqa yayov."),
            ("На машине",        "Mashinada",                     "na ma-SHEE-nye",         "navigation","beginner",
             "На машине десять минут.",                           "Mashinada o'n daqiqa."),
            ("Первый поворот",   "Birinchi burilish",             "PYER-viy pa-va-ROT",     "navigation","intermediate",
             "Первый поворот направо.",                           "Birinchi burilishda o'ngga."),
            ("Второй поворот",   "Ikkinchi burilish",             "fta-ROY pa-va-ROT",      "navigation","intermediate",
             "На втором повороте налево.",                        "Ikkinchi burilishda chapga."),

            # ── Buyurtma va so'rash ───────────────────────────────────────
            ("Отвезите меня в ...","Meni ... ga olib boring",     "at-vye-ZEE-tye mye-NYA", "navigation","beginner",
             "Отвезите меня в аэропорт.",                        "Meni aeroportga olib boring."),
            ("Остановите здесь",  "Shu yerda to'xtang",          "as-ta-na-VEE-tye zdyes'", "navigation","beginner",
             "Остановите здесь, пожалуйста.",                    "Iltimos, shu yerda to'xtang."),
            ("Сколько стоит?",    "Qancha turadi?",               "SKOL'-ka STO-eet",        "navigation","beginner",
             "Сколько стоит до центра?",                         "Markazgacha qancha turadi?"),
            ("Есть ли ...?",      "... bormi?",                   "yest' lee",               "navigation","beginner",
             "Есть ли здесь банкомат?",                          "Bu yerda bankomat bormi?"),
            ("Мне нужно в ...",   "Menga ... ga borish kerak",    "mnye NOOZH-na v",         "navigation","beginner",
             "Мне нужно в больницу.",                            "Menga kasalxonaga borish kerak."),
            ("Я еду до ...",      "Men ... gacha ketaman",        "ya YEH-doo da",           "navigation","beginner",
             "Я еду до конечной остановки.",                     "Men oxirgi bekatgacha ketaman."),
            ("Это правильный автобус?","Bu to'g'ri avtobus?",     "ETA PRA-veel'-ny af-TO-boos","navigation","intermediate",
             "Это правильный автобус до вокзала?",               "Bu vokzalga to'g'ri avtobus?"),
            ("Пересадка",        "Ko'chma (transfer)",            "pye-rye-SAD-ka",          "navigation","intermediate",
             "Здесь нужна пересадка?",                           "Bu yerda ko'chish kerakmi?"),
            ("Выход",            "Chiqish",                       "VY-khat",                 "navigation","beginner",
             "Где выход?",                                        "Chiqish qayerda?"),
            ("Вход",             "Kirish",                        "fkhot",                   "navigation","beginner",
             "Вход свободный.",                                   "Kirish bepul."),
            ("Маршрут",          "Marshrut",                      "mar-SHOOT",               "navigation","intermediate",
             "Какой маршрут лучше?",                             "Qaysi marshrut yaxshiroq?"),
            ("Пробка",           "Tiqilinch",                     "PROB-ka",                 "navigation","intermediate",
             "На дороге пробка.",                                 "Yo'lda tiqilinch bor."),
            ("Объезд",           "Aylanma yo'l",                  "ab-YEZD",                 "navigation","intermediate",
             "Здесь объезд.",                                     "Bu yerda aylanma yo'l bor."),
        ]
        for w in words:
            self.conn.execute("""INSERT OR IGNORE INTO words
                (russian,uzbek,pronunciation,category,level,example_ru,example_uz)
                VALUES(?,?,?,?,?,?,?)""", w)
        self.conn.commit()

    def _insert_navigation_grammar(self):
        """Yo'l va yo'nalish grammatika qoidalari"""
        rules = [
            ("Yo'l so'rash: Где? Куда? Как?", "beginner", "navigation",
             "Yo'l va joy uchun 3 ta asosiy savol:\n\n"
             "1. ГДЕ? — Qayerda? (joy)\n"
             "   Где вокзал? — Vokzal qayerda?\n"
             "   Где ближайшее метро? — Eng yaqin metro qayerda?\n\n"
             "2. КУДА? — Qayerga? (yo'nalish)\n"
             "   Куда едет этот автобус? — Bu avtobus qayerga boradi?\n"
             "   Куда мне идти? — Qayerga borish kerak?\n\n"
             "3. КАК ПРОЙТИ / КАК ДОЕХАТЬ? — Qanday borish mumkin?\n"
             "   Как пройти до парка? (yayov)\n"
             "   Как доехать до аэропорта? (transport)\n\n"
             "FOYDALI: СКАЖИТЕ, ПОЖАЛУЙСТА — iltimos ayting\n"
             "(har doim shunday boshlang — odob belgisi!)",
             json.dumps([
                 {"ru": "Где находится вокзал? — Vokzal qayerda?",            "uz": "ГДЕ = qayerda (joy)"},
                 {"ru": "Куда идёт этот автобус? — Bu avtobus qayerga?",       "uz": "КУДА = qayerga (yo'nalish)"},
                 {"ru": "Как пройти до метро? — Metroga qanday borish?",       "uz": "КАК ПРОЙТИ = qanday yayov borish"},
                 {"ru": "Как доехать до центра? — Markazga transport bilan?",  "uz": "КАК ДОЕХАТЬ = qanday transport bilan borish"},
                 {"ru": "Скажите, пожалуйста, где банк?",                      "uz": "Iltimos, bank qayerda?"},
             ]),
             json.dumps([
                 {"q": "Joy so'rashda qaysi savol ishlatiladi?",
                  "a": "Где?", "type":"choice",
                  "options": ["Где?", "Куда?", "Откуда?", "Когда?"]},
                 {"q": "Yayov borish uchun qaysi ibora?",
                  "a": "Как пройти?", "type":"choice",
                  "options": ["Как доехать?", "Как пройти?", "Куда идти?", "Где идти?"]},
                 {"q": "Transport bilan borish uchun qaysi ibora?",
                  "a": "Как доехать?", "type":"choice",
                  "options": ["Как пройти?", "Как доехать?", "Где ехать?", "Куда ехать?"]},
                 {"q": "Murojaat boshlash uchun eng odobli ibora?",
                  "a": "Скажите, пожалуйста", "type":"choice",
                  "options": ["Эй!", "Скажите, пожалуйста", "Ты знаешь?", "Стой!"]},
             ])
            ),
            ("Yo'nalish berish: прямо, налево, направо", "beginner", "navigation",
             "Yo'nalish ko'rsatish so'zlari:\n\n"
             "ИДИТЕ — boring (yayov)\n"
             "ЕЗЖАЙТЕ — boring (transport)\n\n"
             "  ПРЯМО        — to'g'ri\n"
             "  НАЛЕВО       — chapga\n"
             "  НАПРАВО      — o'ngga\n"
             "  НАЗАД        — orqaga\n\n"
             "BURCHAK VA MASOFA:\n"
             "  До светофора прямо — svetoforgacha to'g'ri\n"
             "  На первом повороте налево — birinchi burilishda chapga\n"
             "  Рядом с банком — bank yonida\n"
             "  Напротив школы — maktab qarshisida\n"
             "  За углом — burchak ortida\n\n"
             "MASOFA:\n"
             "  Пять минут пешком — besh daqiqa yayov\n"
             "  На машине десять минут — mashinada o'n daqiqa\n"
             "  Это близко / далеко — bu yaqin / uzoq",
             json.dumps([
                 {"ru": "Идите прямо, потом направо.",          "uz": "To'g'ri boring, keyin o'ngga."},
                 {"ru": "На первом повороте налево.",            "uz": "Birinchi burilishda chapga."},
                 {"ru": "Банк напротив почты.",                  "uz": "Bank pochta qarshisida."},
                 {"ru": "Пять минут пешком отсюда.",            "uz": "Bu yerdan besh daqiqa yayov."},
                 {"ru": "Это рядом, не далеко.",                 "uz": "Bu yaqinda, uzoq emas."},
             ]),
             json.dumps([
                 {"q": "'O'ngga' ruscha qanday?",
                  "a": "направо", "type":"choice",
                  "options": ["налево", "назад", "направо", "прямо"]},
                 {"q": "'Chapga' ruscha qanday?",
                  "a": "налево", "type":"choice",
                  "options": ["направо", "прямо", "налево", "рядом"]},
                 {"q": "'Bank yonida' ruscha qanday?",
                  "a": "рядом с банком", "type":"choice",
                  "options": ["напротив банка", "рядом с банком", "за банком", "между банков"]},
                 {"q": "'Besh daqiqa yayov' ruscha?",
                  "a": "пять минут пешком", "type":"choice",
                  "options": ["пять минут на машине", "пять минут пешком", "пять пешком минут", "минут пять идти"]},
                 {"q": "'Svetoforgacha to'g'ri boring' ruscha?",
                  "a": "Идите прямо до светофора", "type":"choice",
                  "options": ["Идите налево до светофора", "Едьте прямо до светофора",
                              "Идите прямо до светофора", "Прямо идите светофор"]},
             ])
            ),
        ]
        for r in rules:
            self.conn.execute("""INSERT OR IGNORE INTO grammar_rules
                (title,level,category,content,examples_json,exercises_json)
                VALUES(?,?,?,?,?,?)""", r)
        self.conn.commit()

    def _insert_time_words(self):
        w = [
            ("Секунда","Soniya","sye-KOON-da","time_ext","beginner","Одна секунда.","Bir soniya."),
            ("Минута","Daqiqa","mee-NOO-ta","time_ext","beginner","Пять минут.","Besh daqiqa."),
            ("Час","Soat","chas","time_ext","beginner","Один час.","Bir soat."),
            ("День","Kun","dyen'","time_ext","beginner","Каждый день.","Har kuni."),
            ("Неделя","Hafta","nye-DYE-lya","time_ext","beginner","Эта неделя.","Bu hafta."),
            ("Месяц","Oy","MYE-syats","time_ext","beginner","Этот месяц.","Bu oy."),
            ("Год","Yil","got","time_ext","beginner","Этот год.","Bu yil."),
            ("Утро","Ertalab","OOT-ra","time_ext","beginner","Доброе утро.","Xayrli ertalab."),
            ("Вечер","Kechqurun","VYE-chyer","time_ext","beginner","Добрый вечер.","Xayrli kech."),
            ("Ночь","Tun","noch'","time_ext","beginner","Спокойной ночи.","Xayrli tun."),
            ("Понедельник","Dushanba","pa-nye-DYEL'-neek","time_ext","beginner","В понедельник.","Dushanbada."),
            ("Вторник","Seshanba","FTOR-neek","time_ext","beginner","Во вторник.","Seshanbada."),
            ("Среда","Chorshanba","srye-DA","time_ext","beginner","В среду.","Chorshanbada."),
            ("Четверг","Payshanba","chyet-VYERK","time_ext","beginner","В четверг.","Payshanbada."),
            ("Пятница","Juma","PYAT-nee-tsa","time_ext","beginner","В пятницу.","Jumada."),
            ("Суббота","Shanba","soob-BO-ta","time_ext","beginner","В субботу.","Shanbada."),
            ("Воскресенье","Yakshanba","vas-krye-SYEN'-ye","time_ext","beginner","В воскресенье.","Yakshanbada."),
            ("Январь","Yanvar","yan-VAR'","time_ext","beginner","В январе холодно.","Yanvarda sovuq."),
            ("Февраль","Fevral","fyev-RAL'","time_ext","beginner","Февраль — короткий месяц.","Fevral — qisqa oy."),
            ("Март","Mart","mart","time_ext","beginner","В марте весна.","Martda bahor."),
            ("Апрель","Aprel","ap-RYEL'","time_ext","beginner","В апреле тепло.","Aprelda iliq."),
            ("Май","May","may","time_ext","beginner","В мае цветут цветы.","Mayda gullar ochiladi."),
            ("Июнь","Iyun","ee-YOON'","time_ext","beginner","В июне жарко.","Iyunda issiq."),
            ("Июль","Iyul","ee-YOOL'","time_ext","beginner","Июль — самый жаркий.","Iyul — eng issiq oy."),
            ("Август","Avgust","AV-goost","time_ext","beginner","В августе каникулы.","Avgustda ta'til."),
            ("Сентябрь","Sentabr","syen-TYABR'","time_ext","beginner","Сентябрь — осень.","Sentabr — kuz."),
            ("Октябрь","Oktabr","ak-TYABR'","time_ext","beginner","В октябре листья падают.","Oktabrda barglar to'kiladi."),
            ("Ноябрь","Noyabr","na-YABR'","time_ext","beginner","В ноябре дождь.","Noyabrda yomg'ir."),
            ("Декабрь","Dekabr","dye-KABR'","time_ext","beginner","В декабре снег.","Dekabrda qor."),
            ("Сейчас","Hozir","sye-CHAS","time_ext","beginner","Сейчас 3 часа.","Hozir soat 3."),
            ("Потом","Keyin","pa-TOM","time_ext","beginner","Потом поговорим.","Keyin gaplashamiz."),
            ("Через","...dan keyin","CHE-ryes","time_ext","intermediate","Через час приду.","Bir soatdan keyin kelaman."),
            ("Раньше","Avval/ilgari","RAN'-she","time_ext","intermediate","Раньше я жил здесь.","Avval bu yerda yashar edim."),
            ("Позже","Keyinroq","POZ-zhe","time_ext","intermediate","Позже поговорим.","Keyinroq gaplashamiz."),
            ("Давно","Qadim/ancha vaqt oldin","dav-NO","time_ext","intermediate","Это было давно.","Bu qadimda bo'lgan."),
            ("Недавно","Yaqinda/endigina","nye-DAV-na","time_ext","intermediate","Недавно приехал.","Yaqinda keldi."),
            ("Всегда","Doimo","fsyeg-DA","time_ext","beginner","Я всегда прихожу вовремя.","Men doimo o'z vaqtida kelaman."),
            ("Никогда","Hech qachon","nee-kag-DA","time_ext","beginner","Я никогда не опаздываю.","Men hech qachon kechikmayman."),
            ("Иногда","Ba'zan","ee-nag-DA","time_ext","beginner","Иногда я читаю.","Ba'zan kitob o'qiyman."),
            ("Часто","Ko'p/tez-tez","CHAS-ta","time_ext","beginner","Я часто хожу туда.","Men u yerga tez-tez boraman."),
            ("Редко","Kamdan-kam","RYET-ka","time_ext","intermediate","Он редко звонит.","U kamdan-kam qo'ng'iroq qiladi."),
        ]
        for row in w:
            self.conn.execute("INSERT OR IGNORE INTO words (russian,uzbek,pronunciation,category,level,example_ru,example_uz) VALUES(?,?,?,?,?,?,?)", row)
        self.conn.commit()

    def _insert_places_words(self):
        w = [
            ("Школа","Maktab","SHKO-la","places","beginner","Я иду в школу.","Men maktabga boraman."),
            ("Университет","Universitet","oo-nee-vyer-see-TYET","places","beginner","Я учусь в университете.","Men universitetda o'qiyman."),
            ("Библиотека","Kutubxona","beeb-lee-a-TYE-ka","places","beginner","В библиотеке тихо.","Kutubxonada jim."),
            ("Больница","Kasalxona","bal'-NEE-tsa","places","beginner","Он в больнице.","U kasalxonada."),
            ("Аптека","Dorixona","ap-TYE-ka","places","beginner","Аптека рядом.","Dorixona yaqin."),
            ("Кафе","Kafe","ka-FYE","places","beginner","Встретимся в кафе.","Kafeda uchrashamiz."),
            ("Кино","Kino","kee-NO","places","beginner","Идём в кино?","Kinoga boramizmi?"),
            ("Театр","Teatr","tye-ATR","places","beginner","Мы идём в театр.","Biz teatrga boramiz."),
            ("Музей","Muzey","moo-ZYEY","places","beginner","В музее интересно.","Muzeyda qiziq."),
            ("Стадион","Stadion","sta-dee-ON","places","beginner","На стадионе матч.","Stadionda match."),
            ("Бассейн","Suzish havzasi","ba-SYEN'","places","beginner","Я плаваю в бассейне.","Men havzada suzaman."),
            ("Офис","Ofis","O-fis","places","beginner","Я работаю в офисе.","Men ofisda ishlayman."),
            ("Завод","Zavod","za-VOT","places","intermediate","Папа работает на заводе.","Dadam zavodda ishlaydi."),
            ("Фабрика","Fabrika","FAB-ree-ka","places","intermediate","Фабрика далеко.","Fabrika uzoqda."),
            ("Церковь","Cherkov","TSYER-kaf'","places","intermediate","Церковь старая.","Cherkov qadimiy."),
            ("Мечеть","Masjid","mye-CHYET'","places","beginner","Мечеть красивая.","Masjid chiroyli."),
            ("Кладбище","Qabriston","KLAD-bee-shche","places","intermediate","Кладбище рядом.","Qabriston yaqin."),
            ("Тюрьма","Qamoqxona","TYOOR'-ma","places","intermediate","Тюрьма строгая.","Qamoqxona qattiq."),
            ("Гараж","Garaj","ga-RAZH","places","beginner","Машина в гараже.","Mashina garajda."),
            ("Склад","Ombor","sklad","places","intermediate","На складе товары.","Omborda tovarlar bor."),
            ("Пляж","Plyaj","plyazh","places","beginner","Пляж красивый.","Plyaj chiroyli."),
            ("Деревня","Qishloq","dye-RYEV-nya","places","beginner","Я из деревни.","Men qishloqdan."),
            ("Поле","Dala","PO-lye","places","beginner","Поле зелёное.","Dala yashil."),
            ("Ферма","Ferma","FYER-ma","places","beginner","На ферме коровы.","Fermada sigirlar bor."),
            ("Кухня","Oshxona/Kuhnya","KOOKH-nya","places","beginner","Мама на кухне.","Onam oshxonada."),
            ("Ванная","Hammom","VAN-na-ya","places","beginner","Ванная свободна.","Hammom bo'sh."),
            ("Спальня","Yotoqxona","SPAL'-nya","places","beginner","Спальня большая.","Yotoqxona katta."),
            ("Гостиная","Mehmonxona (xona)","gas-TEE-na-ya","places","beginner","Мы в гостиной.","Biz mehmonxonadadamiz."),
            ("Подвал","Yerto'la","pad-VAL","places","intermediate","Подвал тёмный.","Yerto'la qorong'u."),
            ("Чердак","Chordoq","chyer-DAK","places","intermediate","На чердаке пыль.","Chordoqda chang bor."),
        ]
        for row in w:
            self.conn.execute("INSERT OR IGNORE INTO words (russian,uzbek,pronunciation,category,level,example_ru,example_uz) VALUES(?,?,?,?,?,?,?)", row)
        self.conn.commit()

    def _insert_math_words(self):
        w = [
            ("Плюс","Qo'shish/plyus","plyoos","math","beginner","Два плюс два.","Ikki plyus ikki."),
            ("Минус","Ayirish/minus","MEE-noos","math","beginner","Пять минус три.","Besh minus uch."),
            ("Умножить","Ko'paytirish","oom-NO-zheet'","math","beginner","Три умножить на два.","Uchni ikkiga ko'paytirish."),
            ("Разделить","Bo'lish","raz-dye-LEET'","math","beginner","Десять разделить на два.","O'nni ikkiga bo'lish."),
            ("Равно","Teng","rav-NO","math","beginner","Два плюс два равно четыре.","Ikki plyus ikki teng to'rt."),
            ("Число","Son","CHEES-la","math","beginner","Назовите число.","Son ayting."),
            ("Цифра","Raqam (belgi)","TSEEF-ra","math","beginner","Цифра семь.","Yetti raqami."),
            ("Сумма","Yig'indi","SOOM-ma","math","intermediate","Сумма равна десяти.","Yig'indi o'nga teng."),
            ("Разность","Ayirma","RAZ-nast'","math","intermediate","Разность равна трём.","Ayirma uchga teng."),
            ("Произведение","Ko'paytma","pra-eez-vye-DYE-nee-ye","math","intermediate","Произведение равно шести.","Ko'paytma oltiga teng."),
            ("Частное","Bo'linma","CHAST-na-ye","math","intermediate","Частное равно пяти.","Bo'linma beshga teng."),
            ("Процент","Foiz","pra-TSENT","math","beginner","Пятьдесят процентов.","Ellik foiz."),
            ("Дробь","Kasr","drob'","math","intermediate","Простая дробь.","Oddiy kasr."),
            ("Квадрат","Kvadrat","kvad-RAT","math","intermediate","Квадрат числа.","Sonning kvadrati."),
            ("Корень","Ildiz","KO-ryen'","math","intermediate","Квадратный корень.","Kvadrat ildiz."),
            ("Угол","Burchak","OO-gal","math","intermediate","Прямой угол.","To'g'ri burchak."),
            ("Треугольник","Uchburchak","trye-oo-GOL'-neek","math","intermediate","Равносторонний треугольник.","Teng tomonli uchburchak."),
            ("Квадрат (фигура)","Kvadrat (shakl)","kvad-RAT","math","intermediate","Квадрат имеет четыре стороны.","Kvadratning to'rt tomoni bor."),
            ("Круг","Doira","krook","math","intermediate","Начертите круг.","Doira chizing."),
            ("Прямоугольник","To'rtburchak","prya-ma-oo-GOL'-neek","math","intermediate","Прямоугольник.","To'g'ri to'rtburchak."),
            ("Длина","Uzunlik","dlee-NA","math","intermediate","Длина три метра.","Uzunligi uch metr."),
            ("Ширина","Kenglik","shee-ree-NA","math","intermediate","Ширина два метра.","Kengligi ikki metr."),
            ("Высота","Balandlik","vy-sa-TA","math","intermediate","Высота пять метров.","Balandligi besh metr."),
            ("Задача","Masala","za-DA-cha","math","beginner","Решите задачу.","Masalani yeching."),
            ("Пример","Misol","pree-MYER","math","beginner","Решите пример.","Misolni yeching."),
            ("Ответ","Javob","at-VYET","math","beginner","Правильный ответ.","To'g'ri javob."),
            ("Больше","Katta (ko'proq)","BOL'-she","math","beginner","Пять больше трёх.","Besh uchdan katta."),
            ("Меньше","Kichik (kamroq)","MYEN'-she","math","beginner","Два меньше пяти.","Ikki beshdan kichik."),
            ("Чётный","Juft","CHYOT-ny","math","intermediate","Чётное число.","Juft son."),
            ("Нечётный","Toq","nye-CHYOT-ny","math","intermediate","Нечётное число.","Toq son."),
            ("Отрицательный","Manfiy","at-ree-TSA-tyel'-ny","math","advanced","Отрицательное число.","Manfiy son."),
            ("Положительный","Musbat","pa-la-ZHEE-tyel'-ny","math","advanced","Положительное число.","Musbat son."),
            ("Бесконечность","Cheksizlik","byes-ka-NYECH-nast'","math","advanced","Бесконечность.","Cheksizlik."),
        ]
        for row in w:
            self.conn.execute("INSERT OR IGNORE INTO words (russian,uzbek,pronunciation,category,level,example_ru,example_uz) VALUES(?,?,?,?,?,?,?)", row)
        self.conn.commit()

    def _insert_family_words(self):
        w = [
            ("Семья","Oila","syem'-YA","family_ext","beginner","Моя семья большая.","Mening oilam katta."),
            ("Родители","Ota-ona","ra-DEE-tye-lee","family_ext","beginner","Мои родители дома.","Mening ota-onam uyda."),
            ("Отец","Ota","a-TYETS","family_ext","beginner","Мой отец врач.","Mening otam shifokor."),
            ("Мать","Ona","mat'","family_ext","beginner","Моя мать учитель.","Mening onam o'qituvchi."),
            ("Сын","O'g'il","syn","family_ext","beginner","У меня два сына.","Menda ikki o'g'il bor."),
            ("Дочь","Qiz (farzand)","doch'","family_ext","beginner","Моя дочь умная.","Mening qizim aqlli."),
            ("Брат","Aka/uka","brat","family_ext","beginner","Мой брат студент.","Mening ukam talaba."),
            ("Сестра","Opa/singil","syes-TRA","family_ext","beginner","Сестра красивая.","Singil chiroyli."),
            ("Дедушка","Bobo","DYED-oosh-ka","family_ext","beginner","Дедушка мудрый.","Bobo dono."),
            ("Бабушка","Buvi","BA-boosh-ka","family_ext","beginner","Бабушка добрая.","Buvi mehribon."),
            ("Внук","Nevara (o'g'il)","vnook","family_ext","beginner","Внук играет.","Nevara o'ynaydi."),
            ("Внучка","Nevara (qiz)","VNOO-chka","family_ext","beginner","Внучка учится.","Nevara o'qiydi."),
            ("Дядя","Amaki/tog'a","DYA-dya","family_ext","beginner","Дядя добрый.","Amaki yaxshi."),
            ("Тётя","Xola/amma","TYO-tya","family_ext","beginner","Тётя приехала.","Xola keldi."),
            ("Племянник","Jiyani (o'g'il)","plyem-YAN-neek","family_ext","intermediate","Племянник школьник.","Jiyanim o'quvchi."),
            ("Племянница","Jiyani (qiz)","plyem-YAN-nee-tsa","family_ext","intermediate","Племянница умная.","Jiyanim aqlli."),
            ("Двоюродный брат","Amakivachcha","dva-YOO-rad-ny brat","family_ext","intermediate","Двоюродный брат далеко.","Amakivachcha uzoqda."),
            ("Муж","Er","moozh","family_ext","beginner","Мой муж добрый.","Erim yaxshi."),
            ("Жена","Xotin","zhye-NA","family_ext","beginner","Его жена красивая.","Uning xotini chiroyli."),
            ("Тесть","Qaynota","tyest'","family_ext","intermediate","Тесть строгий.","Qaynota qattiq."),
            ("Тёща","Qaynonа","TYOSH-cha","family_ext","intermediate","Тёща добрая.","Qaynona mehribon."),
            ("Свёкор","Qaynotа (erning otasi)","SVYO-kar","family_ext","intermediate","Свёкор работает.","Qaynota ishlaydi."),
            ("Свекровь","Qaynona (erning onasi)","svyek-ROF'","family_ext","intermediate","Свекровь мудрая.","Qaynona dono."),
            ("Зять","Kuyov","zyat'","family_ext","intermediate","Зять приехал.","Kuyov keldi."),
            ("Невестка","Kelin","nye-VYES-tka","family_ext","intermediate","Невестка красивая.","Kelin chiroyli."),
            ("Близнецы","Egizaklar","bleez-nyet-SY","family_ext","intermediate","У них близнецы.","Ularda egizaklar bor."),
            ("Ребёнок","Bola","rye-BYO-nak","family_ext","beginner","Маленький ребёнок.","Kichik bola."),
            ("Младенец","Go'dak","mla-DYE-nyets","family_ext","beginner","Младенец спит.","Go'dak uxlaydi."),
            ("Старший","Katta (tomonida)","STAR-shiy","family_ext","beginner","Старший брат.","Katta aka."),
            ("Младший","Kichik (tomonida)","MLAT-shiy","family_ext","beginner","Младший брат.","Kichik uka."),
        ]
        for row in w:
            self.conn.execute("INSERT OR IGNORE INTO words (russian,uzbek,pronunciation,category,level,example_ru,example_uz) VALUES(?,?,?,?,?,?,?)", row)
        self.conn.commit()

    def _insert_clothing_words(self):
        w = [
            ("Одежда","Kiyim","a-DYEZh-da","clothing","beginner","Новая одежда.","Yangi kiyim."),
            ("Рубашка","Ko'ylak (erkak)","roo-BASH-ka","clothing","beginner","Белая рубашка.","Oq ko'ylak."),
            ("Платье","Ko'ylak (ayol)","PLA-tye","clothing","beginner","Красивое платье.","Chiroyli ko'ylak."),
            ("Брюки","Shim","BRYOO-kee","clothing","beginner","Чёрные брюки.","Qora shim."),
            ("Джинсы","Jinsi shim","DZHEEN-sy","clothing","beginner","Синие джинсы.","Ko'k jinsi."),
            ("Юбка","Yubka","YOOP-ka","clothing","beginner","Короткая юбка.","Qisqa yubka."),
            ("Пиджак","Kostyum (jacket)","peed-ZHAK","clothing","beginner","Синий пиджак.","Ko'k kostyum."),
            ("Куртка","Kurtka","KOORT-ka","clothing","beginner","Тёплая куртка.","Iliq kurtka."),
            ("Пальто","Palto","pal'-TO","clothing","beginner","Зимнее пальто.","Qishki palto."),
            ("Шуба","Mo'ynali palto","SHOO-ba","clothing","intermediate","Дорогая шуба.","Qimmat mo'ynali palto."),
            ("Свитер","Sviter","SVEE-tyer","clothing","beginner","Тёплый свитер.","Iliq sviter."),
            ("Майка","Futbolka/mayka","MAY-ka","clothing","beginner","Белая майка.","Oq mayka."),
            ("Носки","Paypoq","NOS-kee","clothing","beginner","Чистые носки.","Toza paypoq."),
            ("Нижнее бельё","Ichki kiyim","NEEZH-nye-ye byel'-YO","clothing","intermediate","Купить бельё.","Ichki kiyim sotib olish."),
            ("Ботинки","Botinka","ba-TEEN-kee","clothing","beginner","Кожаные ботинки.","Charm botinka."),
            ("Туфли","Tufliya","TOOF-lee","clothing","beginner","Красивые туфли.","Chiroyli tufliya."),
            ("Кроссовки","Krossovka","kras-SOF-kee","clothing","beginner","Спортивные кроссовки.","Sport krossovkasi."),
            ("Тапочки","Shippak","TA-pach-kee","clothing","beginner","Домашние тапочки.","Uy shippagi."),
            ("Шапка","Qalpoq/do'ppi","SHAP-ka","clothing","beginner","Тёплая шапка.","Iliq qalpoq."),
            ("Шарф","Sharf","sharf","clothing","beginner","Длинный шарф.","Uzun sharf."),
            ("Перчатки","Qo'lqop","pyer-CHAT-kee","clothing","beginner","Кожаные перчатки.","Charm qo'lqop."),
            ("Галстук","Galstuk","GAL-stook","clothing","beginner","Красный галстук.","Qizil galstuk."),
            ("Ремень","Kamar","rye-MYEN'","clothing","beginner","Кожаный ремень.","Charm kamar."),
            ("Сумка","Sumka","SOOM-ka","clothing","beginner","Большая сумка.","Katta sumka."),
            ("Рюкзак","Ryukzak","ryook-ZAK","clothing","beginner","Школьный рюкзак.","Maktab ryukzaki."),
            ("Очки","Ko'zoynak","ach-KEE","clothing","beginner","Солнечные очки.","Quyosh ko'zoynagi."),
            ("Украшение","Bezak/taqinchoq","ook-ra-SHYE-nee-ye","clothing","intermediate","Красивое украшение.","Chiroyli bezak."),
            ("Кольцо","Uzuk","kal'-TSO","clothing","beginner","Золотое кольцо.","Oltin uzuk."),
            ("Серьги","Sirg'a","SYER'-gee","clothing","beginner","Красивые серьги.","Chiroyli sirg'a."),
            ("Размер","O'lcham","raz-MYER","clothing","beginner","Какой размер?","Qanday o'lcham?"),
        ]
        for row in w:
            self.conn.execute("INSERT OR IGNORE INTO words (russian,uzbek,pronunciation,category,level,example_ru,example_uz) VALUES(?,?,?,?,?,?,?)", row)
        self.conn.commit()

    def _insert_animals_words(self):
        w = [
            ("Собака","It","sa-BA-ka","animals","beginner","Собака лает.","It huradi."),
            ("Кошка","Mushuk","KOSH-ka","animals","beginner","Кошка мяукает.","Mushuk miyovlaydi."),
            ("Корова","Sigir","ka-RO-va","animals","beginner","Корова даёт молоко.","Sigir sut beradi."),
            ("Лошадь","Ot","LO-shad'","animals","beginner","Лошадь быстрая.","Ot tez."),
            ("Овца","Qo'y","af-TSA","animals","beginner","Белая овца.","Oq qo'y."),
            ("Козёл / Коза","Echki","ka-ZYO-la / ka-ZA","animals","beginner","Коза на горе.","Echki tog'da."),
            ("Курица","Tovuq","KOO-ree-tsa","animals","beginner","Курица несёт яйца.","Tovuq tuxum qo'yadi."),
            ("Утка","O'rdak","OOT-ka","animals","beginner","Утка плавает.","O'rdak suzadi."),
            ("Свинья","Cho'chqa","sveen'-YA","animals","beginner","Розовая свинья.","Pushti cho'chqa."),
            ("Верблюд","Tuya","vyer-BLYOOT","animals","beginner","Верблюд в пустыне.","Tuya cho'lda."),
            ("Лев","Sher","lyef","animals","beginner","Лев — царь зверей.","Sher hayvonlar shohi."),
            ("Тигр","Yo'lbars","teegr","animals","beginner","Тигр прыгает.","Yo'lbars sakradi."),
            ("Медведь","Ayiq","myed-VYED'","animals","beginner","Медведь большой.","Ayiq katta."),
            ("Волк","Bo'ri","volk","animals","beginner","Серый волк.","Kulrang bo'ri."),
            ("Лиса","Tulki","lee-SA","animals","beginner","Хитрая лиса.","Ayyor tulki."),
            ("Заяц","Quyon","ZA-yats","animals","beginner","Белый заяц.","Oq quyon."),
            ("Слон","Fil","slon","animals","beginner","Слон большой.","Fil katta."),
            ("Жираф","Jirafa","zhee-RAF","animals","beginner","Жираф высокий.","Jirafa baland bo'yli."),
            ("Обезьяна","Maymun","a-byes'-YA-na","animals","beginner","Обезьяна умная.","Maymun aqlli."),
            ("Крокодил","Timsoh","kra-ka-DEEL","animals","beginner","Крокодил опасный.","Timsoh xavfli."),
            ("Змея","Ilon","zmye-YA","animals","beginner","Ядовитая змея.","Zaharli ilon."),
            ("Птица","Qush","PTEE-tsa","animals","beginner","Птица летит.","Qush uchadi."),
            ("Орёл","Burgut","a-RYOL","animals","beginner","Орёл летит высоко.","Burgut baland uchadi."),
            ("Рыба","Baliq","RY-ba","animals","beginner","Рыба в реке.","Baliq daryoda."),
            ("Бабочка","Kapalak","BA-bach-ka","animals","beginner","Красивая бабочка.","Chiroyli kapalak."),
            ("Пчела","Asalari","pchye-LA","animals","beginner","Пчела жалит.","Asalari chaqadi."),
            ("Муравей","Chumoli","moo-ra-VYEY","animals","beginner","Трудолюбивый муравей.","Mehnatkash chumoli."),
            ("Черепаха","Toshbaqa","chye-rye-PA-kha","animals","beginner","Медленная черепаха.","Sekin toshbaqa."),
            ("Попугай","To'ti qush","pa-poo-GAY","animals","beginner","Попугай говорит.","To'ti qush gapiradi."),
            ("Хомяк","Hamster","kha-MYAK","animals","beginner","Маленький хомяк.","Kichik hamster."),
        ]
        for row in w:
            self.conn.execute("INSERT OR IGNORE INTO words (russian,uzbek,pronunciation,category,level,example_ru,example_uz) VALUES(?,?,?,?,?,?,?)", row)
        self.conn.commit()

    def _insert_transport_words(self):
        w = [
            ("Машина","Mashina","ma-SHEE-na","transport","beginner","Моя машина красная.","Mening mashinam qizil."),
            ("Велосипед","Velosiped","vye-la-see-PYET","transport","beginner","Я езжу на велосипеде.","Men velosipedda yuraman."),
            ("Мотоцикл","Mototsikl","ma-ta-TSYEKL","transport","beginner","Быстрый мотоцикл.","Tez mototsikl."),
            ("Автобус","Avtobus","af-TO-boos","transport","beginner","Автобус опоздал.","Avtobus kechikdi."),
            ("Троллейбус","Trolleybus","tral-LYEY-boos","transport","beginner","Троллейбус тихий.","Trolleybus jim."),
            ("Трамвай","Tramvay","tram-VAY","transport","beginner","Трамвай идёт.","Tramvay ketyapti."),
            ("Метро","Metro","myet-RO","transport","beginner","Метро быстрое.","Metro tez."),
            ("Поезд","Poyezd","PO-yezd","transport","beginner","Поезд отходит.","Poyezd ketmoqda."),
            ("Самолёт","Samolyot","sa-ma-LYOT","transport","beginner","Самолёт летит.","Samolyot uchmoqda."),
            ("Вертолёт","Vertolyot","vyer-ta-LYOT","transport","intermediate","Вертолёт над городом.","Vertolyot shahar ustida."),
            ("Корабль","Kema","ka-RABL'","transport","beginner","Корабль в море.","Kema dengizda."),
            ("Лодка","Qayiq","LOT-ka","transport","beginner","Маленькая лодка.","Kichik qayiq."),
            ("Такси","Taksi","tak-SEE","transport","beginner","Вызвать такси.","Taksi chaqirish."),
            ("Грузовик","Yuk mashinasi","groo-za-VEEK","transport","intermediate","Большой грузовик.","Katta yuk mashinasi."),
            ("Скорая помощь","Tez yordam","SKO-ra-ya PO-mash'","transport","beginner","Скорая помощь едет.","Tez yordam kelyapti."),
            ("Пожарная машина","O't o'chirish mashinasi","pa-ZHAR-na-ya","transport","beginner","Пожарная машина.","O't o'chirish mashinasi."),
            ("Водитель","Haydovchi","va-DEE-tyel'","transport","beginner","Хороший водитель.","Yaxshi haydovchi."),
            ("Пассажир","Yo'lovchi","pa-sa-ZHEER","transport","beginner","Пассажиры в автобусе.","Yo'lovchilar avtobusda."),
            ("Билет","Chipta","bee-LYET","transport","beginner","Купить билет.","Chipta sotib olish."),
            ("Остановка","Bekat","as-ta-NOF-ka","transport","beginner","Следующая остановка.","Keyingi bekat."),
            ("Расписание","Jadval","ras-pee-SA-nee-ye","transport","intermediate","Расписание поездов.","Poyezdlar jadvali."),
            ("Платформа","Platforma","plat-FOR-ma","transport","beginner","На платформе люди.","Platformada odamlar."),
            ("Перрон","Peron","pye-RON","transport","intermediate","Поезд на перроне.","Poyezd peronda."),
            ("Шоссе","Avtomobil yo'li","shas-SE","transport","intermediate","Широкое шоссе.","Keng avtomobil yo'li."),
            ("Перекрёсток","Chorraxa","pye-rye-KRYOS-tak","transport","intermediate","На перекрёстке.","Chorrahada."),
            ("Светофор","Svetofor","svye-ta-FOR","transport","beginner","Красный светофор.","Qizil svetofor."),
            ("Парковка","Parking","par-KOF-ka","transport","beginner","Бесплатная парковка.","Bepul parking."),
            ("Бензин","Benzin","byen-ZEEN","transport","beginner","Заправить бензин.","Benzin quyish."),
            ("Заправка","Benzin quyish joyi","za-PRAF-ka","transport","intermediate","Заправка рядом.","Benzin stantsiyasi yaqin."),
            ("Водительские права","Haydovchilik guvohnomasi","va-DEE-tyel'-skee-ye pra-VA","transport","intermediate","Права дома.","Guvohnoma uyda."),
        ]
        for row in w:
            self.conn.execute("INSERT OR IGNORE INTO words (russian,uzbek,pronunciation,category,level,example_ru,example_uz) VALUES(?,?,?,?,?,?,?)", row)
        self.conn.commit()

    def _insert_body_words(self):
        w = [
            ("Голова","Bosh","ga-la-VA","body","beginner","Болит голова.","Bosh og'riydi."),
            ("Волосы","Soch","VO-la-sy","body","beginner","Тёмные волосы.","Qora soch."),
            ("Лицо","Yuz","lee-TSO","body","beginner","Красивое лицо.","Chiroyli yuz."),
            ("Глаз","Ko'z","glas","body","beginner","Синие глаза.","Ko'k ko'zlar."),
            ("Нос","Burun","nos","body","beginner","Длинный нос.","Uzun burun."),
            ("Рот","Og'iz","rot","body","beginner","Открой рот.","Og'zingni och."),
            ("Зуб","Tish","zoop","body","beginner","Болит зуб.","Tish og'riydi."),
            ("Язык","Til (organ)","ya-ZYK","body","beginner","Высуни язык.","Tilingni ko'rsat."),
            ("Ухо","Quloq","OO-kha","body","beginner","Болит ухо.","Quloq og'riydi."),
            ("Шея","Bo'yin","shye-YA","body","beginner","Длинная шея.","Uzun bo'yin."),
            ("Плечо","Yelka","plye-CHO","body","beginner","Широкие плечи.","Keng yelkalar."),
            ("Рука","Qo'l","roo-KA","body","beginner","Правая рука.","O'ng qo'l."),
            ("Палец","Barmoq","PA-lyets","body","beginner","Десять пальцев.","O'n barmoq."),
            ("Ноготь","Tirnoq","NO-gat'","body","beginner","Длинные ногти.","Uzun tirnoqlar."),
            ("Грудь","Ko'krak","groot'","body","beginner","Грудь болит.","Ko'krak og'riydi."),
            ("Живот","Qorin","zhee-VOT","body","beginner","Болит живот.","Qorin og'riydi."),
            ("Спина","Orqa","spee-NA","body","beginner","Болит спина.","Orqa og'riydi."),
            ("Нога","Oyoq","na-GA","body","beginner","Правая нога.","O'ng oyoq."),
            ("Колено","Tizza","ka-LYE-na","body","beginner","Болит колено.","Tizza og'riydi."),
            ("Стопа","Tovon","sta-PA","body","beginner","Болит стопа.","Tovon og'riydi."),
            ("Сердце","Yurak","SYERTS-ye","body","beginner","Быстрое сердце.","Yurak tez uryapti."),
            ("Лёгкие","O'pka","LYOKH-kee-ye","body","intermediate","Здоровые лёгкие.","Sog'lom o'pka."),
            ("Печень","Jigar","PYE-chyen'","body","intermediate","Болит печень.","Jigar og'riydi."),
            ("Желудок","Me'da","zhye-LOO-dak","body","intermediate","Болит желудок.","Me'da og'riydi."),
            ("Кровь","Qon","krof'","body","intermediate","Группа крови.","Qon guruhi."),
            ("Кость","Suyak","kost'","body","intermediate","Сломана кость.","Suyak singan."),
            ("Мышца","Mushak","MYSH-tsa","body","intermediate","Сильные мышцы.","Kuchli mushaklar."),
            ("Кожа","Teri","KO-zha","body","beginner","Нежная кожа.","Nozik teri."),
            ("Ноготь","Tirnoq","NO-gat'","body","beginner","Стричь ногти.","Tirnoq kesish."),
            ("Мозг","Miya","mozg","body","intermediate","Работа мозга.","Miyaning ishi."),
        ]
        for row in w:
            self.conn.execute("INSERT OR IGNORE INTO words (russian,uzbek,pronunciation,category,level,example_ru,example_uz) VALUES(?,?,?,?,?,?,?)", row)
        self.conn.commit()

    def _insert_school_words(self):
        w = [
            ("Урок","Dars","oo-ROK","school","beginner","Урок начался.","Dars boshlandi."),
            ("Учебник","Darslik","oo-CHYEB-neek","school","beginner","Открой учебник.","Darslikni och."),
            ("Тетрадь","Daftar","tyet-RAD'","school","beginner","Новая тетрадь.","Yangi daftar."),
            ("Ручка","Ruchka","ROOCH-ka","school","beginner","Синяя ручка.","Ko'k ruchka."),
            ("Карандаш","Qalam","ka-ran-DASH","school","beginner","Острый карандаш.","O'tkir qalam."),
            ("Линейка","Chizg'ich","lee-NYEY-ka","school","beginner","Деревянная линейка.","Yog'och chizg'ich."),
            ("Ластик","O'chirg'ich","LAS-teek","school","beginner","Резиновый ластик.","Rezina o'chirg'ich."),
            ("Доска","Taxtа","das-KA","school","beginner","Пишите на доске.","Taxtada yozing."),
            ("Мел","Bo'r","myel","school","beginner","Белый мел.","Oq bo'r."),
            ("Парта","Parta","PAR-ta","school","beginner","Сиди за партой.","Partada o'tir."),
            ("Класс","Sinf/xona","klas","school","beginner","Наш класс.","Bizning sinfimiz."),
            ("Учитель","O'qituvchi","oo-CHEE-tyel'","school","beginner","Добрый учитель.","Yaxshi o'qituvchi."),
            ("Ученик","O'quvchi (o'g'il)","oo-chye-NEEK","school","beginner","Хороший ученик.","Yaxshi o'quvchi."),
            ("Ученица","O'quvchi (qiz)","oo-chye-NEE-tsa","school","beginner","Умная ученица.","Aqlli o'quvchi."),
            ("Директор","Direktor","dee-RYEK-tar","school","beginner","Директор школы.","Maktab direktori."),
            ("Домашнее задание","Uy vazifa","da-MASH-nye-ye za-DA-nee-ye","school","beginner","Сделай домашнее задание.","Uy vazifasini qil."),
            ("Контрольная","Nazorat ishi","kan-TROL'-na-ya","school","beginner","Завтра контрольная.","Ertaga nazorat ishi."),
            ("Оценка","Baho","a-TSYEN-ka","school","beginner","Хорошая оценка.","Yaxshi baho."),
            ("Пятёрка","Besh (baho)","pya-TYO-rka","school","beginner","Получил пятёрку.","Besh oldi."),
            ("Двойка","Ikki (baho)","DVOY-ka","school","beginner","Получил двойку.","Ikki oldi."),
            ("Каникулы","Ta'til","ka-NEE-koo-ly","school","beginner","Летние каникулы.","Yozgi ta'til."),
            ("Расписание","Dars jadvali","ras-pee-SA-nee-ye","school","beginner","Расписание уроков.","Dars jadvali."),
            ("Перемена","Tanaffus","pye-rye-MYE-na","school","beginner","Во время перемены.","Tanaffus vaqtida."),
            ("Столовая","Oshxona (maktab)","sta-LO-va-ya","school","beginner","В столовой вкусно.","Oshxonada mazali."),
            ("Библиотека","Kutubxona","beeb-lee-a-TYE-ka","school","beginner","В библиотеке тихо.","Kutubxonada jim."),
            ("Спортзал","Sport zal","SPORT-zal","school","beginner","Урок в спортзале.","Dars sport zalida."),
            ("Математика","Matematika","ma-tye-MA-tee-ka","school","beginner","Урок математики.","Matematika darsi."),
            ("Русский язык","Rus tili","ROOS-keey ya-ZYK","school","beginner","Урок русского языка.","Rus tili darsi."),
            ("История","Tarix","ees-TO-ree-ya","school","beginner","Урок истории.","Tarix darsi."),
            ("Физика","Fizika","FEE-zee-ka","school","intermediate","Трудная физика.","Qiyin fizika."),
        ]
        for row in w:
            self.conn.execute("INSERT OR IGNORE INTO words (russian,uzbek,pronunciation,category,level,example_ru,example_uz) VALUES(?,?,?,?,?,?,?)", row)
        self.conn.commit()

    def _insert_weather_words(self):
        w = [
            ("Погода","Ob-havo","pa-GO-da","weather","beginner","Хорошая погода.","Yaxshi ob-havo."),
            ("Температура","Harorat","teem-pye-ra-TOO-ra","weather","beginner","Температура 30 градусов.","Harorat 30 daraja."),
            ("Градус","Daraja","GRA-doos","weather","beginner","Минус 5 градусов.","Minus 5 daraja."),
            ("Солнце","Quyosh","SON-tse","weather","beginner","Светит солнце.","Quyosh charaqlab turibdi."),
            ("Облако","Bulut","OB-la-ka","weather","beginner","Белые облака.","Oq bulutlar."),
            ("Дождь","Yomg'ir","dozh'd'","weather","beginner","Идёт дождь.","Yomg'ir yog'moqda."),
            ("Снег","Qor","snyeg","weather","beginner","Падает снег.","Qor yog'moqda."),
            ("Ветер","Shamol","VYE-tyer","weather","beginner","Сильный ветер.","Kuchli shamol."),
            ("Гроза","Momaqaldiroq","gra-ZA","weather","intermediate","Страшная гроза.","Qo'rqinchli momaqaldiroq."),
            ("Молния","Chaqmoq","MOL-nee-ya","weather","intermediate","Сверкнула молния.","Chaqmoq chaqdi."),
            ("Туман","Tuman","too-MAN","weather","intermediate","Густой туман.","Qalin tuman."),
            ("Мороз","Ayoz","ma-ROS","weather","intermediate","Сильный мороз.","Kuchli ayoz."),
            ("Жара","Issiqlik","zhа-RA","weather","beginner","Летняя жара.","Yozgi issiq."),
            ("Холод","Sovuq","KHO-lat","weather","beginner","Сильный холод.","Kuchli sovuq."),
            ("Весна","Bahor","vyes-NA","weather","beginner","Пришла весна.","Bahor keldi."),
            ("Лето","Yoz","LYE-ta","weather","beginner","Жаркое лето.","Issiq yoz."),
            ("Осень","Kuz","O-syen'","weather","beginner","Красивая осень.","Chiroyli kuz."),
            ("Зима","Qish","zee-MA","weather","beginner","Холодная зима.","Sovuq qish."),
            ("Радуга","Kamalak","RA-doo-ga","weather","beginner","Красивая радуга.","Chiroyli kamalak."),
            ("Лёд","Muz","lyot","weather","beginner","Скользкий лёд.","Sirpanchiq muz."),
            ("Наводнение","Toshqin","na-vad-NYE-nee-ye","weather","advanced","Сильное наводнение.","Kuchli toshqin."),
            ("Засуха","Qurg'oqchilik","ZA-soo-kha","weather","advanced","Долгая засуха.","Uzoq qurg'oqchilik."),
            ("Прогноз погоды","Ob-havo bashorati","prag-NOS pa-GO-dy","weather","intermediate","Прогноз погоды хороший.","Ob-havo bashorati yaxshi."),
            ("Влажность","Namlik","VLAZH-nast'","weather","advanced","Высокая влажность.","Yuqori namlik."),
            ("Давление","Bosim","dav-LYE-nee-ye","weather","advanced","Низкое давление.","Past bosim."),
            ("Ясно","Ochiq (havo)","YAS-na","weather","beginner","Сегодня ясно.","Bugun havo ochiq."),
            ("Пасмурно","Bulutli","PAS-moor-na","weather","intermediate","Пасмурная погода.","Bulutli havo."),
            ("Ураган","To'fon","oo-ra-GAN","weather","intermediate","Сильный ураган.","Kuchli to'fon."),
            ("Иней","Qirov","EE-nyey","weather","intermediate","Утренний иней.","Ertalabki qirov."),
            ("Гололёд","Muzqaymoq yo'l","ga-la-LYOT","weather","intermediate","Гололёд на дороге.","Yo'lda muzqaymoq."),
        ]
        for row in w:
            self.conn.execute("INSERT OR IGNORE INTO words (russian,uzbek,pronunciation,category,level,example_ru,example_uz) VALUES(?,?,?,?,?,?,?)", row)
        self.conn.commit()

    def _insert_house_words(self):
        w = [
            ("Дом","Uy","dom","house","beginner","Большой дом.","Katta uy."),
            ("Квартира","Kvartira","kvar-TEE-ra","house","beginner","Наша квартира.","Bizning kvartira."),
            ("Комната","Xona","KOM-na-ta","house","beginner","Большая комната.","Katta xona."),
            ("Кухня","Oshxona","KOOKH-nya","house","beginner","Мама на кухне.","Onam oshxonada."),
            ("Спальня","Yotoqxona","SPAL'-nya","house","beginner","Тихая спальня.","Jim yotoqxona."),
            ("Гостиная","Mehmonxona","gas-TEE-na-ya","house","beginner","Сидим в гостиной.","Mehmonxonada o'tiramiz."),
            ("Ванная","Hammom","VAN-na-ya","house","beginner","Ванная свободна.","Hammom bo'sh."),
            ("Туалет","Hojatxona","too-a-LYET","house","beginner","Где туалет?","Hojatxona qayerda?"),
            ("Балкон","Balkon","bal-KON","house","beginner","Выйди на балкон.","Balkonga chiq."),
            ("Окно","Deraza","ak-NO","house","beginner","Открой окно.","Derazani och."),
            ("Дверь","Eshik","dvyer'","house","beginner","Закрой дверь.","Eshikni yop."),
            ("Потолок","Shift","pa-ta-LOK","house","beginner","Белый потолок.","Oq shift."),
            ("Пол","Pol","pol","house","beginner","Чистый пол.","Toza pol."),
            ("Стена","Devor","stye-NA","house","beginner","Белые стены.","Oq devorlar."),
            ("Стол","Stol","stol","house","beginner","Накрой стол.","Stolni to'shla."),
            ("Стул","Stul","stool","house","beginner","Сядь на стул.","Stulga o'tir."),
            ("Диван","Divan","dee-VAN","house","beginner","Мягкий диван.","Yumshoq divan."),
            ("Кровать","Karavot","kra-VAT'","house","beginner","Убери кровать.","Karavotni yig'."),
            ("Шкаф","Shkaf","shkaf","house","beginner","Одежда в шкафу.","Kiyimlar shkafda."),
            ("Холодильник","Muzlatgich","kha-la-DEEL'-neek","house","beginner","Еда в холодильнике.","Ovqat muzlatgichda."),
            ("Плита","Pech (gaz)","plee-TA","house","beginner","Готовить на плите.","Pechda pishirish."),
            ("Микроволновка","Mikroto'lqinli pech","meek-ra-val-NOF-ka","house","intermediate","Разогрей в микроволновке.","Mikroto'lqinda isit."),
            ("Телевизор","Televizor","tye-lye-VEE-zar","house","beginner","Смотрю телевизор.","Televizor ko'raman."),
            ("Лампа","Chiroq/lampa","LAM-pa","house","beginner","Включи лампу.","Lampani yoq."),
            ("Зеркало","Ko'zgu","ZYER-ka-la","house","beginner","Смотрюсь в зеркало.","Ko'zguga qaraman."),
            ("Полка","Tokcha","POL-ka","house","beginner","Книги на полке.","Kitoblar tokchada."),
            ("Ковёр","Gilam","ka-VYOR","house","beginner","Мягкий ковёр.","Yumshoq gilam."),
            ("Занавеска","Parda","za-na-VYES-ka","house","beginner","Закрой занавески.","Pardani yop."),
            ("Подушка","Yostiq","pa-DOOSH-ka","house","beginner","Мягкая подушка.","Yumshoq yostiq."),
            ("Одеяло","Ko'rpa","a-dye-YA-la","house","beginner","Тёплое одеяло.","Iliq ko'rpa."),
        ]
        for row in w:
            self.conn.execute("INSERT OR IGNORE INTO words (russian,uzbek,pronunciation,category,level,example_ru,example_uz) VALUES(?,?,?,?,?,?,?)", row)
        self.conn.commit()

    def _insert_sport_words(self):
        w = [
            ("Спорт","Sport","sport","sport","beginner","Спорт полезен.","Sport foydali."),
            ("Футбол","Futbol","foot-BOL","sport","beginner","Играть в футбол.","Futbol o'ynash."),
            ("Баскетбол","Basketbol","bas-kyet-BOL","sport","beginner","Матч по баскетболу.","Basketbol matchi."),
            ("Волейбол","Voleybol","va-lyey-BOL","sport","beginner","Играем в волейбол.","Voleybol o'ynamiz."),
            ("Теннис","Tennis","TYE-nees","sport","beginner","Играть в теннис.","Tennis o'ynash."),
            ("Плавание","Suzish","PLA-va-nee-ye","sport","beginner","Плавание полезно.","Suzish foydali."),
            ("Бег","Yugurish","byek","sport","beginner","Утренний бег.","Ertalabki yugurish."),
            ("Ходьба","Yurish","khad'-BA","sport","beginner","Ходьба полезна.","Yurish foydali."),
            ("Прыжки","Sakrash","PRYZh-kee","sport","beginner","Прыжки в высоту.","Balandlikka sakrash."),
            ("Гимнастика","Gimnastika","geem-NAS-tee-ka","sport","beginner","Утренняя гимнастика.","Ertalabki gimnastika."),
            ("Бокс","Boks","boks","sport","beginner","Заниматься боксом.","Boks bilan shug'ullanish."),
            ("Борьба","Kurash","bar'-BA","sport","beginner","Национальная борьба.","Milliy kurash."),
            ("Шахматы","Shaxmat","SHAKH-ma-ty","sport","beginner","Играть в шахматы.","Shaxmat o'ynash."),
            ("Велоспорт","Velosport","vye-la-SPORT","sport","intermediate","Велоспорт популярен.","Velosport mashhur."),
            ("Каратэ","Karate","ka-ra-TE","sport","beginner","Урок каратэ.","Karate darsi."),
            ("Тренировка","Mashq/trenirovka","trye-nee-ROF-ka","sport","beginner","Ежедневная тренировка.","Har kunlik mashq."),
            ("Стадион","Stadion","sta-dee-ON","sport","beginner","На стадионе матч.","Stadionda match."),
            ("Команда","Jamoa","ka-MAN-da","sport","beginner","Наша команда.","Bizning jamoamiz."),
            ("Игрок","O'yinchi","eeg-ROK","sport","beginner","Лучший игрок.","Eng yaxshi o'yinchi."),
            ("Тренер","Murabbiy","TRE-nyer","sport","beginner","Строгий тренер.","Qattiq murabbiy."),
            ("Победа","G'alaba","pa-BYE-da","sport","beginner","Победа близко.","G'alaba yaqin."),
            ("Поражение","Mag'lubiyat","pa-ra-ZHE-nee-ye","sport","intermediate","Горькое поражение.","Achchiq mag'lubiyat."),
            ("Чемпион","Chempion","chyem-pee-ON","sport","beginner","Новый чемпион.","Yangi chempion."),
            ("Рекорд","Rekord","rye-KORD","sport","beginner","Побить рекорд.","Rekord urish."),
            ("Мяч","To'p","myach","sport","beginner","Пнуть мяч.","To'pni tepish."),
            ("Гол","Gol","gol","sport","beginner","Забить гол.","Gol urish."),
            ("Счёт","Hisob","schyot","sport","beginner","Счёт 2:1.","Hisob 2:1."),
            ("Финал","Final","fee-NAL","sport","beginner","В финале.","Finalda."),
            ("Медаль","Medal","mye-DAL'","sport","beginner","Золотая медаль.","Oltin medal."),
            ("Болельщик","Fanat/tarafdor","ba-LYEL'-shcheek","sport","intermediate","Верный болельщик.","Sodiq tarafdor."),
        ]
        for row in w:
            self.conn.execute("INSERT OR IGNORE INTO words (russian,uzbek,pronunciation,category,level,example_ru,example_uz) VALUES(?,?,?,?,?,?,?)", row)
        self.conn.commit()

    def _insert_introduction_grammar(self):
        """O'zini tanishtirish grammatika qoidalari"""
        rules = [
            ("Tanishish: Меня зовут — Ismni aytish", "beginner", "introduction",
             "O'zini tanishtirish uchun eng muhim 3 ta qurilma:\n\n"
             "1. МЕНЯ ЗОВУТ ... — Mening ismim ...\n"
             "   Меня зовут Алишер. — Mening ismim Alisher.\n"
             "   Меня зовут Малика. — Mening ismim Malika.\n\n"
             "2. КАК ВАС ЗОВУТ? — Sizning ismingiz nima?\n"
             "   (norasmiy: КАК ТЕБЯ ЗОВУТ? — Sening ism nima?)\n\n"
             "3. ПРИЯТНО ПОЗНАКОМИТЬСЯ — Tanishganimdan xursandman\n"
             "   (qisqa: ОЧЕНЬ ПРИЯТНО — Juda xursandman)\n\n"
             "NAMUNA DIALOG:\n"
             "  — Здравствуйте! Меня зовут Камол. А вас?\n"
             "  — Очень приятно! Меня зовут Анна.",
             json.dumps([
                 {"ru": "Меня зовут Алишер. — Mening ismim Alisher.", "uz": "Меня зовут = mening ismim"},
                 {"ru": "Как вас зовут? — Как тебя зовут?", "uz": "вас (rasmiy) / тебя (norasmiy)"},
                 {"ru": "Очень приятно познакомиться!", "uz": "Juda xursandman tanishganimdan!"},
                 {"ru": "Давайте познакомимся! — Keling, tanishamiz!", "uz": "Давайте = keling (taklif)"},
             ]),
             json.dumps([
                 {"q": "'Mening ismim Kamol' ruscha qanday?", "a": "Меня зовут Камол", "type": "choice",
                  "options": ["Я есть Камол", "Меня зовут Камол", "Мне зовут Камол", "Я Камол зовут"]},
                 {"q": "Rasmiy tanishishda qaysi so'z ishlatiladi?", "a": "Как вас зовут?", "type": "choice",
                  "options": ["Как тебя зовут?", "Как вас зовут?", "Кто ты?", "Как ты?"]},
                 {"q": "'Tanishganimdan xursandman' ruscha?", "a": "Приятно познакомиться", "type": "choice",
                  "options": ["Приятно познакомиться", "До свидания", "Как дела?", "Пожалуйста"]},
             ])
            ),
            ("Tanishish: Qayerdan va qancha yoshda", "beginner", "introduction",
             "O'zini to'liq tanishtirish uchun muhim savollar:\n\n"
             "YOSH:\n"
             "  Сколько вам лет? — Yoshingiz necha?\n"
             "  Мне 20 лет.      — Menga 20 yosh.\n"
             "  Мне 21 год.      — Menga 21 yosh.\n"
             "  ⚠ Qoida: 1 → лет emas ГОД, 2-4 → ГОДА, 5+ → ЛЕТ\n\n"
             "QAYERDAN:\n"
             "  Откуда вы? — Qayerdansiz?\n"
             "  Я из Узбекистана. — Men O'zbekistondan.\n"
             "  Я из Ташкента.    — Men Toshkentdan.\n\n"
             "QAYERDA YASHASH:\n"
             "  Где вы живёте? — Qayerda yashaysiz?\n"
             "  Я живу в Ташкенте. — Men Toshkentda yashayman.\n"
             "  Я живу в Узбекистане. — Men O'zbekistonda yashayman.",
             json.dumps([
                 {"ru": "Мне 25 лет. — Menga 25 yosh.", "uz": "5+ yoshda: ЛЕТ"},
                 {"ru": "Мне 21 год. — Menga 21 yosh.", "uz": "1 da: ГОД"},
                 {"ru": "Я из Самарканда. — Men Samarqanddan.", "uz": "ИЗ + shahar nomi"},
                 {"ru": "Я живу в Бухаре. — Men Buxoroda yashayman.", "uz": "В + O'rin-payt kelshigi"},
             ]),
             json.dumps([
                 {"q": "'Menga 5 yosh' ruscha qanday?", "a": "Мне пять лет", "type": "choice",
                  "options": ["Мне пять год", "Мне пять года", "Мне пять лет", "Я пять лет"]},
                 {"q": "'Men Toshkentdan' qanday?", "a": "Я из Ташкента", "type": "choice",
                  "options": ["Я в Ташкенте", "Я из Ташкента", "Я Ташкент", "Я от Ташкента"]},
                 {"q": "'Qayerda yashaysiz?' ruscha?", "a": "Где вы живёте?", "type": "choice",
                  "options": ["Откуда вы?", "Где вы живёте?", "Кто вы?", "Что вы делаете?"]},
                 {"q": "'Men Samarqandda yashayman' ruscha?", "a": "Я живу в Самарканде", "type": "choice",
                  "options": ["Я живу Самарканд", "Я из Самарканда", "Я живу в Самарканде", "Я есть Самарканд"]},
             ])
            ),
            ("Tanishish: To'liq o'z-o'zini taqdim etish", "intermediate", "introduction",
             "To'liq tanishish dialogi — barcha qismlarni birlashtirish:\n\n"
             "NAMUNA MONOLOG:\n"
             "  Здравствуйте! Разрешите представиться.\n"
             "  Меня зовут Алишер Каримов.\n"
             "  Мне двадцать три года.\n"
             "  Я из Узбекистана, живу в Ташкенте.\n"
             "  Я студент, учусь в университете.\n"
             "  Моя специальность — информационные технологии.\n"
             "  Я учу русский язык уже шесть месяцев.\n"
             "  Мне нравится читать книги и слушать музыку.\n"
             "  Приятно познакомиться!\n\n"
             "FOYDALI IBORALAR:\n"
             "  Разрешите представиться — Ruxsat eting, tanishamiz\n"
             "  Я хочу рассказать о себе — O'zim haqimda gapirmoqchiman\n"
             "  Если не секрет... — Agar sir bo'lmasa...",
             json.dumps([
                 {"ru": "Разрешите представиться. Меня зовут ...", "uz": "Rasmiy taqdim etish boshlang'ichi"},
                 {"ru": "Мне нравится читать. — Menga o'qish yoqadi.", "uz": "МНЕ НРАВИТСЯ + infinitiv"},
                 {"ru": "Я занимаюсь спортом. — Men sport bilan shug'ullanaman.", "uz": "заниматься + tvsdk"},
                 {"ru": "В свободное время я... — Bo'sh vaqtimda men...", "uz": "Qiziqishlarni aytish"},
             ]),
             json.dumps([
                 {"q": "Rasmiy taqdim etish so'zi?", "a": "Разрешите представиться", "type": "choice",
                  "options": ["Привет!", "Разрешите представиться", "Пока!", "Как дела?"]},
                 {"q": "'Menga kitob o'qish yoqadi' ruscha?", "a": "Мне нравится читать книги", "type": "choice",
                  "options": ["Я люблю читает книги", "Мне нравится читать книги", "Мне нравится читаю", "Я хочу книги"]},
                 {"q": "'Men 23 yoshdaman' ruscha?", "a": "Мне двадцать три года", "type": "choice",
                  "options": ["Я двадцать три год", "Мне двадцать три года", "Мне двадцать три лет", "Я имею 23"]},
             ])
            ),
        ]
        for r in rules:
            self.conn.execute("""INSERT OR IGNORE INTO grammar_rules
                (title,level,category,content,examples_json,exercises_json)
                VALUES(?,?,?,?,?,?)""", r)
        self.conn.commit()

    def _insert_numbers_words(self):
        """Raqamlar: 1-20, o'nliklar, yuzliklar, mingliklar"""
        nums = [
            # 1-10
            ("Один","Bir","a-DEEN","numbers","beginner","Один плюс один = два.","Bir + bir = ikki."),
            ("Два","Ikki","dva","numbers","beginner","Два яблока.","Ikki olma."),
            ("Три","Uch","tree","numbers","beginner","Три кошки.","Uch mushuk."),
            ("Четыре","To'rt","chye-TYE-rye","numbers","beginner","Четыре урока.","To'rt dars."),
            ("Пять","Besh","pyat'","numbers","beginner","Пять минут.","Besh daqiqa."),
            ("Шесть","Olti","shest'","numbers","beginner","Шесть часов.","Olti soat."),
            ("Семь","Yetti","syem'","numbers","beginner","Семь дней.","Yetti kun."),
            ("Восемь","Sakkiz","VO-syem'","numbers","beginner","Восемь букв.","Sakkiz harf."),
            ("Девять","To'qqiz","DYE-vyat'","numbers","beginner","Девять месяцев.","To'qqiz oy."),
            ("Десять","O'n","DYE-syat'","numbers","beginner","Десять рублей.","O'n so'm."),
            # 11-20
            ("Одиннадцать","O'n bir","a-DEEN-nat-tsat'","numbers","beginner","Ему одиннадцать лет.","Unga o'n bir yosh."),
            ("Двенадцать","O'n ikki","dvye-NAT-tsat'","numbers","beginner","Двенадцать месяцев в году.","Yilda o'n ikki oy."),
            ("Тринадцать","O'n uch","tree-NAT-tsat'","numbers","beginner","Тринадцатый этаж.","O'n uchinchi qavat."),
            ("Четырнадцать","O'n to'rt","chye-TYR-nat-tsat'","numbers","beginner","Четырнадцать дней.","O'n to'rt kun."),
            ("Пятнадцать","O'n besh","pyat-NAT-tsat'","numbers","beginner","Пятнадцать минут.","O'n besh daqiqa."),
            ("Шестнадцать","O'n olti","shes-NAT-tsat'","numbers","beginner","Шестнадцать лет.","O'n olti yosh."),
            ("Семнадцать","O'n yetti","syem-NAT-tsat'","numbers","beginner","Семнадцать студентов.","O'n yetti talaba."),
            ("Восемнадцать","O'n sakkiz","va-syem-NAT-tsat'","numbers","beginner","Восемнадцать часов.","O'n sakkiz soat."),
            ("Девятнадцать","O'n to'qqiz","dye-vyat-NAT-tsat'","numbers","beginner","Девятнадцатый век.","O'n to'qqizinchi asr."),
            ("Двадцать","Yigirma","DVAT-tsat'","numbers","beginner","Двадцать рублей.","Yigirma so'm."),
            # O'nliklar
            ("Тридцать","O'ttiz","TREE-tsat'","numbers","intermediate","Тридцать дней.","O'ttiz kun."),
            ("Сорок","Qirq","SO-rak","numbers","intermediate","Сорок минут.","Qirq daqiqa."),
            ("Пятьдесят","Ellik","pyat'-dye-SYAT","numbers","intermediate","Пятьдесят процентов.","Ellik foiz."),
            ("Шестьдесят","Oltmish","shest'-dye-SYAT","numbers","intermediate","Шестьдесят секунд.","Oltmish soniya."),
            ("Семьдесят","Yetmish","SYEM'-dye-syat","numbers","intermediate","Семьдесят лет.","Yetmish yosh."),
            ("Восемьдесят","Sakson","VO-syem'-dye-syat","numbers","intermediate","Восемьдесят килограммов.","Sakson kilogramm."),
            ("Девяносто","To'qson","dye-vya-NOS-ta","numbers","intermediate","Девяносто дней.","To'qson kun."),
            ("Сто","Yuz","sto","numbers","intermediate","Сто рублей.","Yuz so'm."),
            # Yuzliklar
            ("Двести","Ikki yuz","DVYE-styi","numbers","intermediate","Двести грамм.","Ikki yuz gramm."),
            ("Триста","Uch yuz","TREE-sta","numbers","intermediate","Триста рублей.","Uch yuz so'm."),
            ("Четыреста","To'rt yuz","chye-TY-ryes-ta","numbers","intermediate","Четыреста метров.","To'rt yuz metr."),
            ("Пятьсот","Besh yuz","pyat'-SOT","numbers","intermediate","Пятьсот граммов.","Besh yuz gramm."),
            ("Шестьсот","Olti yuz","shest'-SOT","numbers","intermediate","Шестьсот рублей.","Olti yuz so'm."),
            ("Семьсот","Yetti yuz","syem'-SOT","numbers","intermediate","Семьсот метров.","Yetti yuz metr."),
            ("Восемьсот","Sakkiz yuz","va-syem'-SOT","numbers","intermediate","Восемьсот лет.","Sakkiz yuz yil."),
            ("Девятьсот","To'qqiz yuz","dye-vyat'-SOT","numbers","intermediate","Девятьсот граммов.","To'qqiz yuz gramm."),
            ("Тысяча","Bir ming","TY-sya-cha","numbers","intermediate","Тысяча рублей.","Bir ming so'm."),
            ("Десять тысяч","O'n ming","DYE-syat' TY-syach","numbers","advanced","Десять тысяч человек.","O'n ming kishi."),
            ("Сто тысяч","Yuz ming","sto TY-syach","numbers","advanced","Сто тысяч рублей.","Yuz ming so'm."),
        ]
        for w in nums:
            self.conn.execute("""INSERT OR IGNORE INTO words
                (russian,uzbek,pronunciation,category,level,example_ru,example_uz)
                VALUES(?,?,?,?,?,?,?)""", w)
        self.conn.commit()

    def _insert_grammar_rules(self):
        rules = [
            # ── 1-BOSQICH: ALIFBO VA FONETIKA ──────────────
            ("1-bosqich: Rus alifbosi (Алфавит)", "beginner", "alphabet",
             "Rus tilida 33 ta harf bor: 10 unli, 21 undosh, 2 belgi (Ъ, Ь).\n\n"
             "UNLILAR: А Э И О У — Я Е Ё Ю — bu ikkinchi qator yumshoq variantlar.\n"
             "UNDOSHLAR: Б В Г Д Ж З К Л М Н П Р С Т Ф Х Ц Ч Ш Щ\n"
             "BELGILAR: Ъ (qattiqlik belgisi) — Ь (yumshoqlik belgisi)\n\n"
             "TALAFFUZ QOIDASI: О harfi urg'usiz bo'g'inda 'А' kabi talaffuz qilinadi!\n"
             "Masalan: молоко = ma-la-KO (faqat oxirgi O urg'uli, qolganlari A kabi)",
             json.dumps([
                 {"ru": "А а — 'a' tovushi (ayna kabi)", "uz": "А — olma kabi"},
                 {"ru": "Б б — 'b' tovushi", "uz": "Б — b harfi"},
                 {"ru": "В в — 'v' tovushi", "uz": "В — v harfi"},
                 {"ru": "Г г — 'g' tovushi", "uz": "Г — g harfi"},
             ]),
             json.dumps([
                 {"q": "Rus alifbosida nechta harf bor?", "a": "33", "type": "number"},
                 {"q": "'А' harfi qanday o'qiladi?", "a": "a", "type": "text"},
             ])
            ),
            # ── 2-BOSQICH: OT TURKUMI ──────────────────────
            ("2-bosqich: Otlar jinsi (Род существительных)", "beginner", "nouns",
             "Rus tilida otlarning 3 ta jinsi bor:\n\n"
             "ERKAK JINS (мужской род) — undosh, -й yoki -ь bilan tugaydi:\n"
             "  стол (stol), журнал (jurnal), словарь (lug'at)\n\n"
             "AYOL JINS (женский род) — -а yoki -я bilan tugaydi:\n"
             "  книга (kitob), семья (oila), тетрадь (daftar — istisno!)\n\n"
             "O'RTA JINS (средний род) — -о yoki -е bilan tugaydi:\n"
             "  окно (deraza), море (dengiz), здание (bino)\n\n"
             "KO'PLIK: +ы/и qo'shimchasi: стол→столы, книга→книги, окно→окна",
             json.dumps([
                 {"ru": "стол — столы (erkak → ko'plik +ы)", "uz": "stol — stollar"},
                 {"ru": "книга — книги (ayol → ko'plik +и)", "uz": "kitob — kitoblar"},
                 {"ru": "окно — окна (o'rta → ko'plik +а)", "uz": "deraza — derazalar"},
                 {"ru": "Это мой стол. — Bu mening stolim. (erkak: мой)", "uz": "erkak jins bilan мой"},
                 {"ru": "Это моя книга. — Bu mening kitobim. (ayol: моя)", "uz": "ayol jins bilan моя"},
             ]),
             json.dumps([
                 {"q": "'Стол' qaysi jinsga mansub?", "a": "erkak jins", "type": "choice",
                  "options": ["erkak jins", "ayol jins", "o'rta jins"]},
                 {"q": "'Книга' so'zining ko'plik shakli?", "a": "книги", "type": "choice",
                  "options": ["книгы", "книги", "книга", "книгей"]},
                 {"q": "'Окно' qaysi jinsga mansub?", "a": "o'rta jins", "type": "choice",
                  "options": ["erkak jins", "ayol jins", "o'rta jins"]},
                 {"q": "Ayol jins otlari qanday qo'shimcha bilan tugaydi?", "a": "-а/-я", "type": "choice",
                  "options": ["-а/-я", "-о/-е", "-й/-ь", "-ый"]},
             ])
            ),
            ("2-bosqich: Jonli va jonsiz otlar (Одушевлённые)", "beginner", "nouns",
             "Rus tilida otlar JONLI va JONSIZ bo'linadi.\n\n"
             "JONLI OTLAR (одушевлённые) — KIM? (КТО?) deb so'raladi:\n"
             "  человек (inson), кошка (mushuk), студент (talaba)\n\n"
             "JONSIZ OTLAR (неодушевлённые) — NIMA? (ЧТО?) deb so'raladi:\n"
             "  стол (stol), книга (kitob), машина (mashina)\n\n"
             "AHAMIYATI: Bu bo'linish kelishiklarni ishlatishga ta'sir qiladi!",
             json.dumps([
                 {"ru": "Кто это? — Это студент. (JONLI)", "uz": "Kim bu? — Bu talaba."},
                 {"ru": "Что это? — Это книга. (JONSIZ)", "uz": "Nima bu? — Bu kitob."},
                 {"ru": "Я вижу кошку. (jonli — тушум kelishigi: кошку)", "uz": "Men mushukni ko'ryapman."},
                 {"ru": "Я вижу стол. (jonsiz — тушум kelishigi: стол)", "uz": "Men stolni ko'ryapman."},
             ]),
             json.dumps([
                 {"q": "'Собака' (it) jonli yoki jonsiz?", "a": "jonli", "type": "choice",
                  "options": ["jonli", "jonsiz"]},
                 {"q": "'Книга' uchun qaysi so'roq ishlatiladi?", "a": "Что?", "type": "choice",
                  "options": ["Кто?", "Что?", "Где?", "Когда?"]},
             ])
            ),
            # ── 3-BOSQICH: OLMOSHLAR ───────────────────────
            # ── 3-BOSQICH: OLMOSHLAR ───────────────────────
            ("3-bosqich: Kishilik olmoshlari (Личные местоимения)", "beginner", "pronouns",
             "Kishilik olmoshlari — gapning asosi:\n\n"
             "  Я — men        МЫ — biz\n"
             "  ТЫ — sen       ВЫ — siz (rasmiy yoki ko'plik)\n"
             "  ОН — u (erkak) ОНИ — ular\n"
             "  ОНА — u (ayol)\n"
             "  ОНО — u (narsalar)\n\n"
             "EGALIK OLMOSHLARI (jinsga qarab o'zgaradi):\n"
             "  erkak jins: МОЙ стол, ТВОЙ дом, НАШ город\n"
             "  ayol jins:  МОЯ книга, ТВОЯ машина, НАША семья\n"
             "  o'rta jins: МОЁ окно, ТВОЁ имя, НАШЕ здание\n"
             "  ko'plik:    МОИ друзья, ТВОИ книги, НАШИ дети",
             json.dumps([
                 {"ru": "Я студент. — Men talabaman.", "uz": "Я = men"},
                 {"ru": "Ты мой друг. — Sen mening do'stimsan.", "uz": "Ты = sen, МОЙ = mening (erkak)"},
                 {"ru": "Она моя сестра. — U mening opam.", "uz": "ОНА = u (ayol), МОЯ = mening (ayol)"},
                 {"ru": "Мы учимся. — Biz o'rganamiz.", "uz": "МЫ = biz"},
                 {"ru": "Наш дом большой. — Bizning uyimiz katta.", "uz": "НАШ = bizning (erkak)"},
             ]),
             json.dumps([
                 {"q": "'Men' olmoshi rus tilida?", "a": "Я", "type": "choice",
                  "options": ["Я", "Ты", "Он", "Мы"]},
                 {"q": "'Mening kitobim' — kitob ayol jins (моя/мой/моё?)", "a": "моя книга", "type": "choice",
                  "options": ["мой книга", "моя книга", "моё книга", "мои книга"]},
                 {"q": "'Ular' olmoshi rus tilida?", "a": "Они", "type": "choice",
                  "options": ["Мы", "Вы", "Они", "Оно"]},
             ])
            ),
            ("3-bosqich: Ko'rsatkich olmoshlari (Указательные)", "beginner", "pronouns",
             "Ko'rsatkich olmoshlari — 'bu' va 'o'sha' ma'nosida:\n\n"
             "BU (yaqin): ЭТОТ (erkak), ЭТА (ayol), ЭТО (o'rta), ЭТИ (ko'plik)\n"
             "O'SHA (uzoq): ТОТ (erkak), ТА (ayol), ТО (o'rta), ТЕ (ko'plik)\n\n"
             "QOIDA: Ko'rsatkich olmoshi ham otning jinsi bilan moslashadi!\n\n"
             "MUHIM: ЧТО ЭТО? — Bu nima? Eng ko'p ishlatiladigan ibora!",
             json.dumps([
                 {"ru": "Этот стол большой. — Bu stol katta. (erkak: этот)", "uz": "ЭТОТ = bu (erkak)"},
                 {"ru": "Эта книга интересная. — Bu kitob qiziq. (ayol: эта)", "uz": "ЭТА = bu (ayol)"},
                 {"ru": "Это окно чистое. — Bu deraza toza. (o'rta: это)", "uz": "ЭТО = bu (o'rta)"},
                 {"ru": "Эти студенты умные. — Bu talabalar aqlli. (ko'plik: эти)", "uz": "ЭТИ = bu (ko'plik)"},
             ]),
             json.dumps([
                 {"q": "'Bu stol' (стол = erkak) qanday?", "a": "этот стол", "type": "choice",
                  "options": ["этот стол", "эта стол", "это стол", "эти стол"]},
                 {"q": "'Bu kitob' (книга = ayol) qanday?", "a": "эта книга", "type": "choice",
                  "options": ["этот книга", "эта книга", "это книга", "эти книга"]},
                 {"q": "Ko'plik uchun ko'rsatkich olmoshi?", "a": "эти", "type": "choice",
                  "options": ["этот", "эта", "это", "эти"]},
             ])
            ),
            ("4-bosqich: Sifatlar (Имя прилагательное)", "beginner", "adjectives",
             "Sifatlar otning JINSI va SONIGA moslashadi. So'roqlari: Какой? Какая? Какое? Какие?\n\n"
             "ERKAK (Какой?): -ый/-ий/-ой\n"
             "  новый дом (yangi uy), синий карандаш (ko'k qalam), большой город (katta shahar)\n\n"
             "AYOL (Какая?): -ая/-яя\n"
             "  новая машина (yangi mashina), синяя ручка (ko'k ruchka)\n\n"
             "O'RTA (Какое?): -ое/-ее\n"
             "  новое здание (yangi bino), синее небо (ko'k osmon)\n\n"
             "KO'PLIK (Какие?): -ые/-ие\n"
             "  новые книги (yangi kitoblar), синие цветы (ko'k gullar)",
             json.dumps([
                 {"ru": "новый стол (erkak) — yangi stol", "uz": "Какой стол? — новый"},
                 {"ru": "новая книга (ayol) — yangi kitob", "uz": "Какая книга? — новая"},
                 {"ru": "новое окно (o'rta) — yangi deraza", "uz": "Какое окно? — новое"},
                 {"ru": "новые дома (ko'plik) — yangi uylar", "uz": "Какие дома? — новые"},
                 {"ru": "красивый город — chiroyli shahar (erkak)", "uz": "красивый = chiroyli (erkak)"},
             ]),
             json.dumps([
                 {"q": "'Chiroyli uy' — стол erkak jins (Какой?)", "a": "красивый дом", "type": "choice",
                  "options": ["красивый дом", "красивая дом", "красивое дом", "красивые дом"]},
                 {"q": "'Синий' sifatining ayol jins shakli?", "a": "синяя", "type": "choice",
                  "options": ["синий", "синяя", "синее", "синие"]},
                 {"q": "'Yangi kitoblar' — ko'plik?", "a": "новые книги", "type": "choice",
                  "options": ["новый книги", "новая книги", "новое книги", "новые книги"]},
             ])
            ),
            # ── 5-BOSQICH: FE'L ───────────────────────────
            ("5-bosqich: Fe'llar — Infinitiv va hozirgi zamon", "beginner", "verbs",
             "Fe'lning boshlang'ich shakli (infinitiv) -ТЬ/-ЧЬ bilan tugaydi.\n"
             "Что делать? — nima qilmoq? | Что сделать? — nima qildi?\n\n"
             "1-TUSLANISH (-ать/-ять/-еть/-ыть):\n"
             "  Я читаЮ     — Men o'qiyapman\n"
             "  Ты читаЕШЬ  — Sen o'qiyapsan\n"
             "  Он читаЕТ   — U o'qiyapti\n"
             "  Мы читаЕМ   — Biz o'qiyapmiz\n"
             "  Вы читаЕТЕ  — Siz o'qiyapsiz\n"
             "  Они читаЮТ  — Ular o'qiyapti\n\n"
             "2-TUSLANISH (-ить/-еть ba'zilari):\n"
             "  Я говорЮ    — Men gapiryapman\n"
             "  Ты говорИШЬ — Sen gapiryapsan\n"
             "  Он говорИТ  — U gapiryapti\n"
             "  Мы говорИМ  — Biz gapiryapmiz\n"
             "  Вы говорИТЕ — Siz gapiryapsiz\n"
             "  Они говорЯТ — Ular gapiryapti",
             json.dumps([
                 {"ru": "Я читаю книгу. — Men kitob o'qiyapman.", "uz": "читать = o'qimoq (1-tuslanish)"},
                 {"ru": "Ты говоришь по-русски? — Sen rus tilida gapirasan?", "uz": "говорить = gapirmoq (2-tuslanish)"},
                 {"ru": "Он работает каждый день. — U har kuni ishlaydi.", "uz": "работать = ishlamoq (1-tuslanish)"},
                 {"ru": "Мы учимся в университете. — Biz universitetda o'qiymiz.", "uz": "учиться = o'qimoq (qaytim)"},
             ]),
             json.dumps([
                 {"q": "'Читать' fe'lining 'Я' shakli?", "a": "читаю", "type": "choice",
                  "options": ["читаю", "читаешь", "читает", "читают"]},
                 {"q": "'Говорить' fe'lining 'Они' shakli?", "a": "говорят", "type": "choice",
                  "options": ["говорят", "говорят", "говорите", "говорим"]},
                 {"q": "'Работать' fe'lining 'Мы' shakli?", "a": "работаем", "type": "choice",
                  "options": ["работаю", "работаешь", "работаем", "работают"]},
                 {"q": "Infinitiv qanday qo'shimcha bilan tugaydi?", "a": "-ть", "type": "choice",
                  "options": ["-ть", "-ет", "-ит", "-ют"]},
             ])
            ),
            ("5-bosqich: O'tgan va kelasi zamon", "intermediate", "verbs",
             "O'TGAN ZAMON: fe'l asosiga -Л (erkak), -ЛА (ayol), -ЛО (o'rta), -ЛИ (ko'plik) qo'shiladi.\n\n"
             "  работать → работал (u ishladi — erkak)\n"
             "             работала (u ishladi — ayol)\n"
             "             работали (ular ishlashdi)\n\n"
             "KELASI ZAMON: БУДУ + infinitiv (noaniq) yoki tuslanadi (aniq):\n"
             "  Я буду читать — Men o'qiyman (noaniq)\n"
             "  Я прочитаю   — Men o'qib tugatayman (aniq)\n\n"
             "BUYRUQ MAYL (Императив):\n"
             "  Читай! — O'qi! (sen uchun)\n"
             "  Читайте! — O'qing! (siz uchun / rasmiy)",
             json.dumps([
                 {"ru": "Вчера я читал книгу. — Kecha men kitob o'qidim. (erkak)", "uz": "читал = erkak o'tgan zamon"},
                 {"ru": "Мама работала дома. — Onam uyda ishladi. (ayol)", "uz": "работала = ayol o'tgan zamon"},
                 {"ru": "Завтра я буду учиться. — Ertaga men o'rganaman.", "uz": "буду учиться = kelasi zamon"},
                 {"ru": "Читай каждый день! — Har kuni o'qi!", "uz": "Читай = buyruq (sen)"},
             ]),
             json.dumps([
                 {"q": "'Она работала' — qaysi zamon?", "a": "o'tgan zamon", "type": "choice",
                  "options": ["hozirgi zamon", "o'tgan zamon", "kelasi zamon"]},
                 {"q": "'Ishladi (ayol)' ruscha qanday?", "a": "работала", "type": "choice",
                  "options": ["работал", "работала", "работало", "работали"]},
                 {"q": "Kelasi zamon noaniq: 'Men o'rganaman'?", "a": "Я буду учиться", "type": "choice",
                  "options": ["Я учусь", "Я буду учиться", "Я учился", "Я учите"]},
             ])
            ),
            # ── 6-BOSQICH: KELSHIKLAR ──────────────────────
            ("6-bosqich: Bosh kelshik — Именительный падеж", "beginner", "cases",
             "Rus tilida 6 ta kelshik (падеж) bor. Boshlovchi uchun 3 tasi eng muhim.\n\n"
             "1. BOSH KELSHIK (Именительный падеж) — Kim? Nima? (Кто? Что?)\n"
             "   Bu gapning EGASI uchun ishlatiladi. So'z o'zgarmaydi.\n\n"
             "   Это стол. — Bu stol.\n"
             "   Иван студент. — Ivan talaba.\n"
             "   Книга интересная. — Kitob qiziq.\n\n"
             "QOIDA: Gapda ega (kim yoki nima qilayapti) — doim Bosh kelshikda!",
             json.dumps([
                 {"ru": "Кто это? — Это студент. (KIM = Bosh kelshik)", "uz": "Студент = ega, o'zgarmaydi"},
                 {"ru": "Что это? — Это книга. (NIMA = Bosh kelshik)", "uz": "Книга = ega, o'zgarmaydi"},
                 {"ru": "Иван читает. — Ivan o'qiyapti. (Ivan = ega)", "uz": "Иван = bosh kelshik"},
                 {"ru": "Собака бежит. — It yuguradi.", "uz": "Собака = ega, bosh kelshik"},
             ]),
             json.dumps([
                 {"q": "'Bu talaba' deyilganda qaysi kelshik ishlatiladi?", "a": "Bosh kelshik", "type": "choice",
                  "options": ["Bosh kelshik", "Tushum kelshigi", "O'rin-payt kelshigi"]},
                 {"q": "Gapning EGASI qaysi kelshikda bo'ladi?", "a": "Именительный (Bosh)", "type": "choice",
                  "options": ["Именительный (Bosh)", "Винительный (Tushum)", "Предложный (O'rin-payt)"]},
             ])
            ),
            ("6-bosqich: O'rin-payt kelshigi — Предложный падеж", "beginner", "cases",
             "O'RIN-PAYT KELSHIGI (Предложный падеж) — Qayerda? (Где?)\n\n"
             "Doim В (ichida) yoki НА (ustida/da) predloglari bilan ishlatiladi.\n\n"
             "QOIDA — qo'shimchalar:\n"
             "  Erkak va o'rta: -Е qo'shiladi: стол → на столЕ, окно → на окнЕ\n"
             "  Ayol: -А/-Я o'rniga -Е: книга → в книгЕ, семья → в семьЕ\n\n"
             "В — yopiq joy (ichida): в школе, в городе, в доме\n"
             "НА — ochiq joy yoki sirt: на столе, на работе, на улице",
             json.dumps([
                 {"ru": "Я живу в Ташкенте. — Men Toshkentda yashayman.", "uz": "в + Ташкент → Ташкенте"},
                 {"ru": "Книга лежит на столе. — Kitob stolda yotibdi.", "uz": "на + стол → столе"},
                 {"ru": "Мы учимся в школе. — Biz maktabda o'qiymiz.", "uz": "в + школа → школе"},
                 {"ru": "Он работает на заводе. — U zavodda ishlaydi.", "uz": "на + завод → заводе"},
                 {"ru": "Дети играют на улице. — Bolalar ko'chada o'ynayapti.", "uz": "на + улица → улице"},
             ]),
             json.dumps([
                 {"q": "'Maktabda' (в + школа) — O'rin-payt kelshigi?", "a": "в школе", "type": "choice",
                  "options": ["в школа", "в школе", "на школа", "в школу"]},
                 {"q": "'Stolda' (на + стол)?", "a": "на столе", "type": "choice",
                  "options": ["на стол", "на столе", "в столе", "на столу"]},
                 {"q": "Qaysi predlog YOPIQ joy uchun ishlatiladi?", "a": "В", "type": "choice",
                  "options": ["В", "НА", "ИЗ", "ДО"]},
             ])
            ),
            ("6-bosqich: Tushum kelshigi — Винительный падеж", "intermediate", "cases",
             "TUSHUM KELSHIGI (Винительный падеж) — Nimani? Kimni? (Что? Кого?)\n"
             "To'g'ridan-to'g'ri ob'ekt uchun ishlatiladi.\n\n"
             "JONSIZ OTLAR (Что? — Nimani?):\n"
             "  Erkak: o'zgarmaydi — вижу стол (stolni ko'ryapman)\n"
             "  Ayol: -а/-я → -у/-ю — вижу книгу (kitobni), вижу семью\n"
             "  O'rta: o'zgarmaydi — вижу окно\n\n"
             "JONLI OTLAR (Кого? — Kimni?):\n"
             "  Erkak: -а/-я qo'shiladi — вижу студента, вижу друга\n\n"
             "YO'NALISH (Куда? — Qayerga?) — В/НА + Tushum kelshigi:\n"
             "  Я иду в школу. — Men maktabga borayapman. (школа→школу)",
             json.dumps([
                 {"ru": "Я читаю книгу. — Men kitob o'qiyapman. (книга→книгу)", "uz": "книгу = tushum kelshigi"},
                 {"ru": "Я вижу студента. — Men talabani ko'ryapman. (jonli)", "uz": "студента = jonli tushum"},
                 {"ru": "Я иду в школу. — Men maktabga borayapman.", "uz": "школу = yo'nalish тушум"},
                 {"ru": "Он любит маму. — U onasini sevadi. (мама→маму)", "uz": "маму = тушум"},
             ]),
             json.dumps([
                 {"q": "'Kitobni o'qiyman' — книга (ayol) tushum kelshigi?", "a": "читаю книгу", "type": "choice",
                  "options": ["читаю книга", "читаю книгу", "читаю книге", "читаю книги"]},
                 {"q": "'Maktabga boraman' — yo'nalish tushum kelshigi?", "a": "иду в школу", "type": "choice",
                  "options": ["иду в школа", "иду в школе", "иду в школу", "иду в школой"]},
                 {"q": "Tushum kelshigi — qaysi so'roqqa javob beradi?", "a": "Что? / Кого?", "type": "choice",
                  "options": ["Кто? / Что?", "Что? / Кого?", "Где?", "Когда?"]},
             ])
            ),
        ]
        for r in rules:
            self.conn.execute("""INSERT OR IGNORE INTO grammar_rules
                (title,level,category,content,examples_json,exercises_json)
                VALUES(?,?,?,?,?,?)""", r)
        self.conn.commit()

    # ── Helpers ────────────────────────────────────
    def _row(self, sql, p=()):
        with self._lock:
            r = self.conn.execute(sql, p).fetchone()
            return dict(r) if r else None

    def _rows(self, sql, p=()):
        with self._lock:
            return [dict(r) for r in self.conn.execute(sql, p).fetchall()]

    def _exec(self, sql, p=()):
        with self._lock:
            self.conn.execute(sql, p)
            self.conn.commit()

    def _ins(self, sql, p=()):
        with self._lock:
            c = self.conn.execute(sql, p)
            self.conn.commit()
            return c.lastrowid

    # ── Settings ───────────────────────────────────
    def get_setting(self, key, default=""):
        r = self._row("SELECT value FROM settings WHERE key=?", (key,))
        return r["value"] if r else default

    def set_setting(self, key, value):
        with self._lock:
            self.conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)))
            self.conn.commit()

    def get_all_settings(self):
        return {r["key"]: r["value"] for r in self._rows("SELECT key,value FROM settings")}

    # ── Profile ────────────────────────────────────
    def get_profile(self):
        return self._row("SELECT * FROM profile WHERE id=1")

    def update_profile(self, **kw):
        allowed = {"name", "level", "total_xp", "streak_days", "last_study_date"}
        sets = {k: v for k, v in kw.items() if k in allowed}
        if not sets: return
        sql = "UPDATE profile SET " + ",".join(f"{k}=?" for k in sets) + " WHERE id=1"
        self._exec(sql, list(sets.values()))

    def add_xp(self, amount):
        self._exec("UPDATE profile SET total_xp=total_xp+? WHERE id=1", (amount,))
        today = datetime.now().strftime("%Y-%m-%d")
        p = self.get_profile()
        if p and p["last_study_date"] != today:
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            streak = p["streak_days"] + 1 if p["last_study_date"] == yesterday else 1
            self.update_profile(streak_days=streak, last_study_date=today)
        return self.get_profile()

    # ── Words ──────────────────────────────────────
    def get_words(self, level=None, category=None, limit=50, offset=0, due_only=False):
        q = "SELECT * FROM words WHERE 1=1"
        p = []
        if level:    q += " AND level=?"; p.append(level)
        if category: q += " AND category=?"; p.append(category)
        if due_only:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            q += " AND next_review<=?"; p.append(now)
        q += " ORDER BY next_review LIMIT ? OFFSET ?"
        p += [limit, offset]
        return self._rows(q, p)

    def get_word_count(self, level=None):
        if level:
            return self._row("SELECT COUNT(*) as c FROM words WHERE level=?", (level,))["c"]
        return self._row("SELECT COUNT(*) as c FROM words")["c"]

    def update_word_review(self, word_id, correct: bool):
        """SM-2 algoritm (intervalli takrorlash)"""
        w = self._row("SELECT * FROM words WHERE id=?", (word_id,))
        if not w: return
        ef = w["ease_factor"]
        interval = w["interval_days"]
        if correct:
            q = 4  # "yaxshi"
            interval = max(1, round(interval * ef))
            ef = max(1.3, ef + 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
            next_rev = (datetime.now() + timedelta(days=interval)).strftime("%Y-%m-%d %H:%M:%S")
            self._exec("""UPDATE words SET times_seen=times_seen+1,
                times_correct=times_correct+1,
                ease_factor=?, interval_days=?, next_review=? WHERE id=?""",
                (ef, interval, next_rev, word_id))
        else:
            next_rev = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._exec("""UPDATE words SET times_seen=times_seen+1,
                times_wrong=times_wrong+1, interval_days=1, next_review=? WHERE id=?""",
                (next_rev, word_id))

    def update_word(self, word_id, **kw):
        allowed = {"russian", "uzbek", "pronunciation", "example_ru", "example_uz",
                   "category", "level"}
        sets = {k: v for k, v in kw.items() if k in allowed}
        if not sets: return
        sets["edited_by_user"] = 1
        sql = "UPDATE words SET " + ",".join(f"{k}=?" for k in sets) + " WHERE id=?"
        self._exec(sql, list(sets.values()) + [word_id])

    def add_word(self, russian, uzbek, pronunciation="", category="general",
                 level="beginner", example_ru="", example_uz=""):
        return self._ins("""INSERT INTO words
            (russian,uzbek,pronunciation,category,level,example_ru,example_uz)
            VALUES(?,?,?,?,?,?,?)""",
            (russian, uzbek, pronunciation, category, level, example_ru, example_uz))

    def search_words(self, query):
        q = f"%{query}%"
        return self._rows("""SELECT * FROM words WHERE
            russian LIKE ? OR uzbek LIKE ? OR pronunciation LIKE ?
            LIMIT 30""", (q, q, q))

    # ── Grammar ────────────────────────────────────
    def get_grammar_rules(self, level=None):
        if level:
            return self._rows("SELECT * FROM grammar_rules WHERE level=? ORDER BY id", (level,))
        return self._rows("SELECT * FROM grammar_rules ORDER BY level, id")

    def get_grammar_rule(self, rid):
        return self._row("SELECT * FROM grammar_rules WHERE id=?", (rid,))

    def update_grammar_rule(self, rid, **kw):
        allowed = {"title", "content", "examples_json", "exercises_json"}
        sets = {k: v for k, v in kw.items() if k in allowed}
        if not sets: return
        sql = "UPDATE grammar_rules SET " + ",".join(f"{k}=?" for k in sets) + " WHERE id=?"
        self._exec(sql, list(sets.values()) + [rid])

    # ── Schedule ───────────────────────────────────
    def get_schedule(self, days_ahead=14):
        from_dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        to_dt = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d %H:%M:%S")
        return self._rows("""SELECT * FROM schedule WHERE scheduled_at BETWEEN ? AND ?
            ORDER BY scheduled_at""", (from_dt, to_dt))

    def get_all_schedule(self):
        return self._rows("SELECT * FROM schedule ORDER BY scheduled_at DESC LIMIT 100")

    def add_lesson(self, title, scheduled_at, duration_min=30,
                   lesson_type="vocabulary", description=""):
        return self._ins("""INSERT INTO schedule
            (title,scheduled_at,duration_min,lesson_type,description)
            VALUES(?,?,?,?,?)""",
            (title, scheduled_at, duration_min, lesson_type, description))

    def update_lesson_status(self, lesson_id, status, score=0):
        if status == "completed":
            self._exec("""UPDATE schedule SET status=?, completed_at=datetime('now'),
                score=? WHERE id=?""", (status, score, lesson_id))
        elif status == "started":
            self._exec("""UPDATE schedule SET status=?, started_at=datetime('now')
                WHERE id=?""", (status, lesson_id))
        else:
            self._exec("UPDATE schedule SET status=? WHERE id=?", (status, lesson_id))

    def get_missed_lessons(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return self._rows("""SELECT * FROM schedule WHERE status='pending'
            AND scheduled_at < ? ORDER BY scheduled_at DESC""", (now,))

    def delete_lesson(self, lid):
        self._exec("DELETE FROM schedule WHERE id=?", (lid,))

    # ── History ────────────────────────────────────
    def add_history(self, lesson_type, duration_sec, score, xp_earned, details=None):
        self._ins("""INSERT INTO study_history
            (lesson_type,duration_sec,score,xp_earned,details_json)
            VALUES(?,?,?,?,?)""",
            (lesson_type, duration_sec, score, xp_earned,
             json.dumps(details or {})))
        self.add_xp(xp_earned)

    def get_history(self, limit=30):
        return self._rows("""SELECT * FROM study_history
            ORDER BY studied_at DESC LIMIT ?""", (limit,))

    def get_stats(self):
        today = datetime.now().strftime("%Y-%m-%d")
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        return {
            "total_words": self._row("SELECT COUNT(*) as c FROM words")["c"],
            "learned_words": self._row(
                "SELECT COUNT(*) as c FROM words WHERE times_correct>0")["c"],
            "due_reviews": self._row(
                f"SELECT COUNT(*) as c FROM words WHERE next_review<=datetime('now')")["c"],
            "total_sessions": self._row("SELECT COUNT(*) as c FROM study_history")["c"],
            "today_min": (self._row(
                "SELECT COALESCE(SUM(duration_sec)/60,0) as v FROM study_history WHERE studied_at>=?",
                (today + " 00:00:00",)) or {}).get("v", 0),
            "week_xp": (self._row(
                "SELECT COALESCE(SUM(xp_earned),0) as v FROM study_history WHERE studied_at>=?",
                (week_ago,)) or {}).get("v", 0),
            "grammar_rules": self._row("SELECT COUNT(*) as c FROM grammar_rules")["c"],
            "missed_lessons": len(self.get_missed_lessons()),
        }

    # ── Game Scores ────────────────────────────────
    def add_game_score(self, game_type, score, max_score, time_sec):
        self._ins("""INSERT INTO game_scores(game_type,score,max_score,time_sec)
            VALUES(?,?,?,?)""", (game_type, score, max_score, time_sec))

    def get_leaderboard(self, game_type=None, limit=10):
        if game_type:
            return self._rows("""SELECT * FROM game_scores WHERE game_type=?
                ORDER BY score DESC LIMIT ?""", (game_type, limit))
        return self._rows("SELECT * FROM game_scores ORDER BY score DESC LIMIT ?", (limit,))

    # ── Chat ───────────────────────────────────────
    def save_chat(self, role, content, correction=""):
        self._ins("INSERT INTO chat_history(role,content,correction) VALUES(?,?,?)",
                  (role, content, correction))

    def get_chat_history(self, limit=50):
        return self._rows("""SELECT * FROM chat_history
            ORDER BY created_at DESC LIMIT ?""", (limit,))

    def clear_chat(self):
        self._exec("DELETE FROM chat_history")

    # ── Downloads ──────────────────────────────────
    def mark_downloaded(self, content_type, content_id):
        self._ins("""INSERT OR IGNORE INTO downloads(content_type,content_id)
            VALUES(?,?)""", (content_type, content_id))
        if content_type == "word":
            self._exec("UPDATE words SET is_downloaded=1 WHERE id=?", (content_id,))
        elif content_type == "grammar":
            self._exec("UPDATE grammar_rules SET is_downloaded=1 WHERE id=?", (content_id,))

    def get_download_stats(self):
        dw = self._row("SELECT COUNT(*) as c FROM words WHERE is_downloaded=1")["c"]
        dg = self._row("SELECT COUNT(*) as c FROM grammar_rules WHERE is_downloaded=1")["c"]
        tw = self._row("SELECT COUNT(*) as c FROM words")["c"]
        tg = self._row("SELECT COUNT(*) as c FROM grammar_rules")["c"]
        return {"words_dl": dw, "grammar_dl": dg, "total_words": tw, "total_grammar": tg}

    # ── Foydalanuvchi xotirasi ─────────────────────
db = Database()


# ── Auth ──────────────────────────────────────────
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        pwd = db.get_setting("app_password")
        if pwd and not session.get("auth"):
            if request.is_json:
                return jsonify({"error": "Avtorizatsiya talab etiladi", "auth_required": True}), 401
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated


# ── SCHEDULE CHECKER THREAD ───────────────────────
def _schedule_checker():
    """Har minutda darslarni tekshirish va xabarnoma yuborish"""
    while True:
        time.sleep(60)
        try:
            notify_min = int(db.get_setting("notification_before_min", "30"))
            now = datetime.now()
            target_dt = now + timedelta(minutes=notify_min)
            lessons = db.get_schedule(days_ahead=1)
            for lesson in lessons:
                if lesson["status"] not in ("pending", "started"): continue
                if lesson["notified"]: continue
                scheduled = datetime.strptime(lesson["scheduled_at"], "%Y-%m-%d %H:%M:%S")
                diff_min = (scheduled - now).total_seconds() / 60
                if 0 <= diff_min <= notify_min:
                    send_windows_notif(
                        "📚 RusLearn — Dars eslatmasi",
                        f"{diff_min:.0f} daqiqadan keyin: {lesson['title']}"
                    )
                    db._exec("UPDATE schedule SET notified=1 WHERE id=?", (lesson["id"],))
        except Exception:
            pass

threading.Thread(target=_schedule_checker, daemon=True).start()


# ── ROUTES ────────────────────────────────────────

@app.route("/")
@require_auth
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET"])
def login_page():
    if not db.get_setting("app_password") or session.get("auth"):
        return redirect("/")
    return render_template("login.html")

@app.route("/api/auth/login", methods=["POST"])
def api_login():
    pwd = (request.get_json().get("password") or "").strip()
    stored = db.get_setting("app_password")
    if not stored or hashlib.sha256(pwd.encode()).hexdigest() == stored:
        session["auth"] = True
        session.permanent = True
        return jsonify({"ok": True})
    return jsonify({"error": "Noto'g'ri parol"}), 401

@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/api/auth/set-password", methods=["POST"])
@require_auth
def api_set_password():
    pwd = (request.get_json().get("password") or "").strip()
    if pwd:
        db.set_setting("app_password", hashlib.sha256(pwd.encode()).hexdigest())
    else:
        db.set_setting("app_password", "")
    return jsonify({"ok": True})

# ── Settings & Internet ───────────────────────────
@app.route("/api/settings", methods=["GET"])
@require_auth
def api_get_settings():
    return jsonify(db.get_all_settings())

@app.route("/api/settings", methods=["POST"])
@require_auth
def api_save_settings():
    for k, v in request.get_json().items():
        db.set_setting(k, v)
    return jsonify({"ok": True})

@app.route("/api/internet/toggle", methods=["POST"])
@require_auth
def api_internet_toggle():
    d = request.get_json()
    state = "on" if d.get("allowed") else "off"
    db.set_setting("internet_allowed", state)
    return jsonify({"ok": True, "allowed": state == "on"})

@app.route("/api/internet/status")
@require_auth
def api_internet_status():
    return jsonify({"allowed": db.get_setting("internet_allowed", "on") == "on"})

# ── Profile ────────────────────────────────────────
@app.route("/api/profile")
@require_auth
def api_profile():
    p = db.get_profile()
    s = db.get_stats()
    return jsonify({**p, **s})

@app.route("/api/profile", methods=["POST"])
@require_auth
def api_update_profile():
    d = request.get_json()
    db.update_profile(**{k: d[k] for k in ("name", "level") if k in d})
    return jsonify({"ok": True})

# ── Words ──────────────────────────────────────────
@app.route("/api/words")
@require_auth
def api_words():
    return jsonify(db.get_words(
        level=request.args.get("level"),
        category=request.args.get("category"),
        limit=request.args.get("limit", 50, type=int),
        offset=request.args.get("offset", 0, type=int),
        due_only=request.args.get("due_only") == "true"
    ))

@app.route("/api/words/search")
@require_auth
def api_words_search():
    return jsonify(db.search_words(request.args.get("q", "")))

@app.route("/api/words/<int:wid>", methods=["GET"])
@require_auth
def api_word_get(wid):
    w = db._row("SELECT * FROM words WHERE id=?", (wid,))
    return jsonify(w) if w else (jsonify({"error": "Topilmadi"}), 404)

@app.route("/api/words/<int:wid>", methods=["PUT"])
@require_auth
def api_word_update(wid):
    db.update_word(wid, **request.get_json())
    return jsonify({"ok": True})

@app.route("/api/words", methods=["POST"])
@require_auth
def api_add_word():
    d = request.get_json()
    wid = db.add_word(d["russian"], d["uzbek"],
                      d.get("pronunciation", ""), d.get("category", "general"),
                      d.get("level", "beginner"), d.get("example_ru", ""),
                      d.get("example_uz", ""))
    return jsonify({"ok": True, "id": wid})

@app.route("/api/words/<int:wid>/review", methods=["POST"])
@require_auth
def api_word_review(wid):
    correct = request.get_json().get("correct", False)
    db.update_word_review(wid, correct)
    xp = 10 if correct else 2
    db.add_xp(xp)
    db.streak_today(xp=xp, words=1 if correct else 0)
    return jsonify({"ok": True, "xp": xp})

@app.route("/api/words/categories")
@require_auth
def api_word_categories():
    cats = db._rows("SELECT DISTINCT category FROM words ORDER BY category")
    return jsonify([c["category"] for c in cats])

# ── Grammar ────────────────────────────────────────
@app.route("/api/grammar")
@require_auth
def api_grammar():
    return jsonify(db.get_grammar_rules(request.args.get("level")))

@app.route("/api/grammar/<int:rid>")
@require_auth
def api_grammar_get(rid):
    r = db.get_grammar_rule(rid)
    return jsonify(r) if r else (jsonify({"error": "Topilmadi"}), 404)

@app.route("/api/grammar/<int:rid>", methods=["PUT"])
@require_auth
def api_grammar_update(rid):
    db.update_grammar_rule(rid, **request.get_json())
    return jsonify({"ok": True})

@app.route("/api/grammar", methods=["POST"])
@require_auth
def api_grammar_add():
    d = request.get_json()
    rid = db._ins("""INSERT INTO grammar_rules(title,content,level,category,examples_json,exercises_json)
        VALUES(?,?,?,?,?,?)""",
        (d["title"], d["content"], d.get("level","beginner"), d.get("category","general"),
         json.dumps(d.get("examples", [])), json.dumps(d.get("exercises", []))))
    return jsonify({"ok": True, "id": rid})

# ── Schedule ───────────────────────────────────────
@app.route("/api/schedule")
@require_auth
def api_schedule():
    days = request.args.get("days", 14, type=int)
    return jsonify(db.get_schedule(days))

@app.route("/api/schedule/all")
@require_auth
def api_schedule_all():
    return jsonify(db.get_all_schedule())

@app.route("/api/schedule/missed")
@require_auth
def api_missed():
    return jsonify(db.get_missed_lessons())

@app.route("/api/schedule", methods=["POST"])
@require_auth
def api_add_lesson():
    d = request.get_json()
    lid = db.add_lesson(
        title=d["title"],
        scheduled_at=d["scheduled_at"],
        duration_min=d.get("duration_min", 30),
        lesson_type=d.get("lesson_type", "vocabulary"),
        description=d.get("description", ""),
    )
    return jsonify({"ok": True, "id": lid})

@app.route("/api/schedule/<int:lid>", methods=["PUT"])
@require_auth
def api_lesson_update(lid):
    d = request.get_json()
    db.update_lesson_status(lid, d.get("status"), d.get("score", 0))
    return jsonify({"ok": True})

@app.route("/api/schedule/<int:lid>", methods=["DELETE"])
@require_auth
def api_lesson_delete(lid):
    db.delete_lesson(lid)
    return jsonify({"ok": True})

# ── History & Stats ────────────────────────────────
@app.route("/api/history")
@require_auth
def api_history():
    return jsonify(db.get_history(request.args.get("limit", 30, type=int)))

@app.route("/api/history", methods=["POST"])
@require_auth
def api_add_history():
    d = request.get_json()
    db.add_history(d["lesson_type"], d.get("duration_sec", 0),
                   d.get("score", 0), d.get("xp_earned", 0), d.get("details"))
    # streak yangilash
    minutes = round(d.get("duration_sec", 0) / 60)
    db.streak_today(xp=d.get("xp_earned", 0), minutes=minutes)
    return jsonify({"ok": True, "profile": db.get_profile()})

@app.route("/api/stats")
@require_auth
def api_stats():
    return jsonify({**db.get_stats(), **db.get_profile()})

# ── Games ──────────────────────────────────────────
@app.route("/api/games/score", methods=["POST"])
@require_auth
def api_game_score():
    d = request.get_json()
    db.add_game_score(d["game_type"], d["score"], d.get("max_score", 0), d.get("time_sec", 0))
    xp = min(50, d["score"] // 2)
    db.add_xp(xp)
    db.streak_today(xp=xp, minutes=round(d.get("time_sec", 0) / 60))
    return jsonify({"ok": True, "xp": xp})
# AI CHAT v4 — SMART, IKKI TIL, AI O'QITISH
# ══════════════════════════════════════════════════

# ── AI Xotira ─────────────────────────────────────

@require_auth
def api_chat():
    internet     = db.get_setting("internet_allowed", "on") == "on"
    d            = request.get_json()
    user_msg     = d.get("message", "").strip()
    mode         = d.get("mode", "text")
    topic        = d.get("topic", "free")
    custom_topic = d.get("custom_topic", "").strip()
    action       = d.get("action", "")
    teach_q      = d.get("teach_question", "").strip()
    teach_a      = d.get("teach_answer", "").strip()
    lang_ui      = d.get("ui_lang", "auto")
    level        = db.get_setting("ai_conversation_level", "beginner")

    if action == "confirm_teach" and teach_q and teach_a:
        ai_knowledge_add(teach_q, teach_a)
        resp = f"✅ O'rgandim! '{teach_q}' => '{teach_a}' xotiramga saqlandi. Rahmat! 🧠"
        db.save_chat("assistant", resp)
        return jsonify({"response": resp, "actions": [], "ok": True})

    if action == "skip":
        resp = "Xop, davom etamiz! 😊"
        return jsonify({"response": resp, "actions": [], "ok": True})

    if not user_msg:
        return jsonify({"error": "Xabar bo'sh"}), 400

    detected_lang = _detect_lang(user_msg) if lang_ui == "auto" else lang_ui

    # ── AI PANEL ENGINE: eng birinchi tekshiriladi ──
    panel_result = _panel_engine(user_msg)
    if panel_result:
        resp = panel_result["answer"]
        db.save_chat("user", user_msg)
        db.save_chat("assistant", resp)
        db.add_xp(3)
        return jsonify({
            "response": resp,
            "choices": [],
            "actions": [],
            "ok": True,
            "source": panel_result.get("source", "panel"),
        })

    if not internet or not GEMINI_API_KEY:
        known = ai_knowledge_search(user_msg)
        if known:
            resp = f"✅ {known}"
            db.save_chat("user", user_msg); db.save_chat("assistant", resp)
            return jsonify({"response": resp, "actions": [], "ok": True, "offline": True})
        resp    = offline_ai_response(user_msg, level)
        choices = _offline_choices(topic, level) if mode == "choice" else []
        db.save_chat("user", user_msg); db.save_chat("assistant", resp)
        db.add_xp(3)
        return jsonify({"response": resp, "choices": choices, "actions": [], "ok": True, "offline": True})

    known = ai_knowledge_search(user_msg)
    extra = f"\n[Xotiramdan: {known}]" if known else ""
    history  = db.get_chat_history(12)
    messages = _build_messages(history, user_msg + extra)
    system   = _chat_system(level, mode, topic, custom_topic, detected_lang)
    response = call_ai(messages, system_prompt=system, max_tokens=700)

    if not response:
        resp    = offline_ai_response(user_msg, level)
        choices = _offline_choices(topic, level) if mode == "choice" else []
        db.save_chat("user", user_msg); db.save_chat("assistant", resp)
        return jsonify({"response": resp, "choices": choices, "actions": [], "ok": True, "offline": True})

    db.save_chat("user", user_msg); db.save_chat("assistant", response)
    db.add_xp(5)

    choices = []
    if mode == "choice":
        import re as _re
        m = _re.search(r'CHOICES:\s*(.*?)(?:\n|$)', response)
        if m:
            raw     = m.group(1)
            choices = [c.strip().strip("[]") for c in raw.split("|") if c.strip()]
            response = response[:m.start()].strip()
        if not choices:
            choices = _offline_choices(topic, level)

    response, actions = _parse_actions(response)

    not_know = ["ma'lumotim yo'q","bilmayman","не знаю","не имею информации","нет данных","не могу ответить"]
    if not actions and any(s in response.lower() for s in not_know):
        actions = [
            {"label":"✅ Ha, o'rgataman","action":"teach","question":user_msg,"hint":"Javobni yozing..."},
            {"label":"➡️ Yo'q, davom eting","action":"skip"},
        ]

    return jsonify({"response": response, "choices": choices, "actions": actions, "ok": True})


@require_auth
def api_chat_choices():
    internet     = db.get_setting("internet_allowed", "on") == "on"
    d            = request.get_json()
    topic        = d.get("topic", "greet")
    custom_topic = d.get("custom_topic", "").strip()
    user_msg     = d.get("message", "").strip()
    level        = db.get_setting("ai_conversation_level", "beginner")

    starters = {
        "free":    f"Davayim '{custom_topic}' haqida gaplashamiz!" if custom_topic else "Bugun qanday mavzuda gapiramiz?",
        "greet":   "Привет! Давай познакомимся. Как тебя зовут?",
        "travel":  "Любишь путешествовать? Расскажи!",
        "food":    "Какая твоя любимая еда?",
        "family":  "Расскажи о своей семье.",
        "weather": "Какая сегодня погода у вас?",
        "numbers": "Давай потренируем числа! Сколько тебе лет?",
        "hobbies": "Чем любишь заниматься в свободное время?",
        "school":  "Расскажи об учёбе. Какой предмет любишь?",
        "work":    "Где работаешь? Какая у тебя профессия?",
        "health":  "Как твоё здоровье? Занимаешься спортом?",
        "sport":   "Какой спорт любишь?",
        "city":    "Расскажи о своём городе.",
        "shopping":"Любишь шопинг?",
        "cinema":  "Какие фильмы любишь?",
        "tech":    "Интересуешься технологиями?",
    }
    if not user_msg:
        user_msg = starters.get(topic, starters["greet"])

    if not internet or not GEMINI_API_KEY:
        choices = _offline_choices(topic, level)
        db.save_chat("assistant", user_msg)
        return jsonify({"response": user_msg, "choices": choices, "actions": [], "ok": True, "offline": True})

    history  = db.get_chat_history(8)
    messages = _build_messages(history, user_msg)
    system   = _chat_system(level, "choice", topic, custom_topic)
    response = call_ai(messages, system_prompt=system, max_tokens=500)

    if not response:
        return jsonify({"response": user_msg, "choices": _offline_choices(topic, level), "actions": [], "ok": True, "offline": True})

    choices = []
    import re as _re
    m = _re.search(r'CHOICES:\s*(.*?)(?:\n|$)', response)
    if m:
        raw     = m.group(1)
        choices = [c.strip().strip("[]") for c in raw.split("|") if c.strip()]
        response = response[:m.start()].strip()
    if not choices:
        choices = _offline_choices(topic, level)

    response, actions = _parse_actions(response)
    db.save_chat("assistant", response)
    db.add_xp(3)
    return jsonify({"response": response, "choices": choices, "actions": actions, "ok": True})


@require_auth
def api_chat_teach():
    d        = request.get_json()
    question = d.get("question", "").strip()
    answer   = d.get("answer", "").strip()
    lang     = d.get("lang", "ru")
    category = d.get("category", "general")
    if not question or not answer:
        return jsonify({"error": "Savol va javob to'ldirilishi shart"}), 400
    kid  = ai_knowledge_add(question, answer, lang, category)
    resp = f"✅ O'rgandim! '{question}' => '{answer}'. Endi javob bera olaman! 🧠"
    db.save_chat("assistant", resp)
    return jsonify({"ok": True, "id": kid, "message": resp})


@require_auth
def api_chat_knowledge():
    return jsonify(ai_knowledge_list())


@require_auth
def api_chat_knowledge_delete(kid):
    db._exec("DELETE FROM ai_knowledge WHERE id=?", (kid,))
    return jsonify({"ok": True})


@require_auth
def api_chat_settings():
    allowed = {"ai_conversation_level","ai_chat_mode","ai_topic","ai_personality",
               "ai_custom_topic","ai_tts_enabled","ai_tts_speed","ai_ui_lang"}
    if request.method == "GET":
        return jsonify({k: db.get_setting(k, "") for k in allowed})
    for k, v in request.get_json().items():
        if k in allowed:
            db.set_setting(k, str(v))
    return jsonify({"ok": True})

@require_auth
def api_ai_translate():
    if db.get_setting("internet_allowed", "on") != "on":
        return jsonify({"error": "Internet yo'q"}), 403
    if not GEMINI_API_KEY:
        return jsonify({"error": "API kalit yo'q"}), 400
    word = request.get_json().get("word", "").strip()
    if not word: return jsonify({"error": "So'z kiritilmagan"}), 400
    resp = call_ai([{"role": "user", "content": f"Translate this Russian word to Uzbek and give pronunciation and 2 example sentences: '{word}'. Return ONLY JSON: {{\"uzbek\": \"\", \"pronunciation\": \"\", \"example_ru\": \"\", \"example_uz\": \"\"}}"}])
    if not resp: return jsonify({"error": "AI xatosi"}), 500
    try:
        import re
        m = re.search(r'\{.*\}', resp, re.DOTALL)
        data = json.loads(m.group()) if m else {}
        return jsonify({"ok": True, **data})
    except Exception:
        return jsonify({"ok": True, "raw": resp})

# ── AI — Grammatika tushuntirish ──────────────────
@require_auth
def api_ai_grammar():
    if db.get_setting("internet_allowed", "on") != "on":
        return jsonify({"error": "Internet yo'q"}), 403
    if not GEMINI_API_KEY:
        return jsonify({"error": "API kalit yo'q"}), 400
    topic = request.get_json().get("topic", "").strip()
    resp = call_ai([{"role": "user", "content": f"Rus tili grammatikasini o'zbek tilida tushuntir: '{topic}'. Misollar bilan."}],
                   max_tokens=600)
    return jsonify({"ok": True, "explanation": resp}) if resp else jsonify({"error": "AI xatosi"}), 500

# ── AI — Lug'at yuklash (online) ──────────────────
@require_auth
def api_ai_fetch_words():
    if db.get_setting("internet_allowed", "on") != "on":
        return jsonify({"error": "Internet ruxsat etilmagan"}), 403
    if not GEMINI_API_KEY:
        return jsonify({"error": "API kalit yo'q"}), 400
    d = request.get_json()
    category = d.get("category", "general")
    level = d.get("level", "beginner")
    count = min(20, d.get("count", 10))
    resp = call_ai([{"role": "user", "content":
        f"Generate {count} Russian words for category '{category}', level '{level}'. "
        f"Return ONLY a JSON array: [{{\"russian\": \"\", \"uzbek\": \"\", "
        f"\"pronunciation\": \"\", \"example_ru\": \"\", \"example_uz\": \"\"}}]"}],
        max_tokens=2000)
    if not resp: return jsonify({"error": "AI xatosi"}), 500
    try:
        import re
        m = re.search(r'\[.*\]', resp, re.DOTALL)
        words = json.loads(m.group()) if m else []
        added = 0
        for w in words:
            if w.get("russian") and w.get("uzbek"):
                wid = db.add_word(w["russian"], w["uzbek"],
                                  w.get("pronunciation", ""), category, level,
                                  w.get("example_ru", ""), w.get("example_uz", ""))
                db.mark_downloaded("word", wid)
                added += 1
        return jsonify({"ok": True, "added": added})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Downloads ──────────────────────────────────────
@app.route("/api/downloads/stats")
@require_auth
def api_dl_stats():
    return jsonify(db.get_download_stats())

@app.route("/api/downloads/all-words", methods=["POST"])
@require_auth
def api_dl_all_words():
    """Barcha so'zlarni offline uchun belgilash"""
    words = db._rows("SELECT id FROM words")
    for w in words:
        db.mark_downloaded("word", w["id"])
    grammar = db._rows("SELECT id FROM grammar_rules")
    for g in grammar:
        db.mark_downloaded("grammar", g["id"])
    return jsonify({"ok": True, "count": len(words) + len(grammar)})

# ══════════════════════════════════════════════════
# XOTIRA VA SHAXSIYLASHTIRISH
# ══════════════════════════════════════════════════

@require_auth
def api_memory_get():
    return jsonify(db.memory_all())

@require_auth
def api_memory_set():
    for k, v in request.get_json().items():
        db.memory_set(k, v)
    return jsonify({"ok": True})

@require_auth
def api_memory_delete(key):
    db._exec("DELETE FROM user_memory WHERE key=?", (key,))
    return jsonify({"ok": True})


# ══════════════════════════════════════════════════
# STREAK VA HAFTALIK HISOBOT
# ══════════════════════════════════════════════════

@require_auth
def api_streak():
    today_row = db._row(
        "SELECT * FROM streak_log WHERE date=date('now','localtime')")
    return jsonify({
        "current":     db.streak_current(),
        "today":       today_row or {"xp_earned":0,"minutes":0,"words_learned":0},
        "last_30":     db.streak_last_days(30),
    })

@require_auth
def api_streak_log():
    d = request.get_json()
    db.streak_today(
        xp      = d.get("xp", 0),
        minutes = d.get("minutes", 0),
        words   = d.get("words", 0),
    )
    return jsonify({"ok": True, "streak": db.streak_current()})

@require_auth
def api_weekly_report():
    report = db.weekly_report()
    report["profile"] = db.get_profile()
    report["memory"]  = db.memory_all()

    # ── Streak xabarnomasi ──────────────────────
    streak = report.get("streak", 0)
    notif  = None
    if streak == 1:
        notif = {"type": "info",    "msg": f"🎉 Yangi streak boshlandi! Ertaga ham davom eting!"}
    elif streak == 3:
        notif = {"type": "success", "msg": f"🔥 3 kun ketma-ket! Zo'r natija!"}
    elif streak == 7:
        notif = {"type": "gold",    "msg": f"🏆 1 hafta uzluksiz! Siz ajoyibsiz!"}
    elif streak == 14:
        notif = {"type": "gold",    "msg": f"🌟 2 hafta streak! Ustoz yo'lida!"}
    elif streak == 30:
        notif = {"type": "gold",    "msg": f"👑 30 kun streak! Haqiqiy chempion!"}
    elif streak > 0 and streak % 5 == 0:
        notif = {"type": "success", "msg": f"🔥 {streak} kun uzluksiz o'qidingiz!"}
    elif report.get("active_days",0) == 0:
        notif = {"type": "warn",    "msg": "⏰ Bu hafta hali o'qimadingiz. Bugun boshlang!"}

    report["streak_notif"] = notif
    return jsonify(report)


# ══════════════════════════════════════════════════
# ADAPTIV TEST VA STATISTIKA
# ══════════════════════════════════════════════════

@require_auth
def api_adaptive_stats():
    return jsonify({
        "all":     db.adaptive_stats_all(),
        "weakest": db.adaptive_weakest(5),
    })

@require_auth
def api_adaptive_update():
    d = request.get_json()
    cat     = d.get("category", "general")
    correct = d.get("correct", False)
    db.adaptive_update(cat, correct)
    xp = 5 if correct else 1
    db.add_xp(xp)
    db.streak_today(xp=xp, words=1 if correct else 0)
    return jsonify({"ok": True, "xp": xp})

@require_auth
def api_adaptive_words():
    """Eng kuchsiz kategoriyalardan so'z qaytaradi"""
    weakest = db.adaptive_weakest(3)
    if not weakest:
        # Hali sinalmagan — umumiy so'zlar
        return jsonify(db.get_words(limit=20))
    words = []
    for cat_row in weakest:
        cat = cat_row["category"]
        cat_words = db.get_words(category=cat, limit=10)
        words.extend(cat_words)
    import random
    random.shuffle(words)
    return jsonify(words[:20])


# ══════════════════════════════════════════════════
# CLOZE TEST (Bo'shliq to'ldirish)
# ══════════════════════════════════════════════════

@require_auth
def api_cloze_list():
    level    = request.args.get("level", "")
    category = request.args.get("category", "")
    limit    = request.args.get("limit", 10, type=int)
    return jsonify(db.get_cloze_tests(
        level    = level or None,
        category = category or None,
        limit    = limit,
    ))

@require_auth
def api_cloze_result(cid):
    d       = request.get_json()
    correct = d.get("correct", False)
    db.cloze_result(cid, correct)
    db.adaptive_update(d.get("category","general"), correct)
    xp = 8 if correct else 2
    db.add_xp(xp)
    db.streak_today(xp=xp, words=1 if correct else 0)
    return jsonify({"ok": True, "xp": xp})

@require_auth
def api_cloze_add():
    d = request.get_json()
    cid = db._ins(
        "INSERT INTO cloze_tests"
        "(sentence_ru,sentence_uz,answer,options_json,category,level) VALUES(?,?,?,?,?,?)",
        (d["sentence_ru"], d["sentence_uz"], d["answer"],
         json.dumps(d.get("options",[])),
         d.get("category","general"), d.get("level","beginner")))
    return jsonify({"ok": True, "id": cid})


# ══════════════════════════════════════════════════
# ROLEPLAY SESSIYA
# ══════════════════════════════════════════════════

@require_auth
def api_roleplay_scenarios():
    return jsonify([
        {"id": k, **{kk: vv for kk, vv in v.items() if kk != "starter"}}
        for k, v in ROLEPLAY_SCENARIOS.items()
    ])

@require_auth
def api_roleplay_start():
    d        = request.get_json()
    role_key = d.get("scenario", "shop")
    level    = db.get_setting("ai_conversation_level", "beginner")
    sc       = ROLEPLAY_SCENARIOS.get(role_key, ROLEPLAY_SCENARIOS["shop"])

    internet = db.get_setting("internet_allowed", "on") == "on"
    if not internet or not GEMINI_API_KEY:
        sid = db.roleplay_start(role_key, sc["user_role"], sc["ai_role"])
        return jsonify({
            "ok": True, "session_id": sid,
            "response":   sc["starter"],
            "user_role":  sc["user_role"],
            "ai_role":    sc["ai_role"],
            "title":      sc["title"],
            "icon":       sc["icon"],
            "offline":    True,
        })

    system = (
        f"Sen RusLearn Pro ilovasida ROLEPLAY o'yini o'ynayapsan.\n"
        f"Sening roling: {sc['ai_role']}\n"
        f"Foydalanuvchi roli: {sc['user_role']}\n"
        f"Daraja: {level}\n"
        f"Sahna: {sc['title']}\n\n"
        "QOIDALAR:\n"
        "1. O'z rolingda qol — haqiqiy suhbat olib bor.\n"
        "2. Rus tilida gapir + qavsda o'zbekcha tarjima qo'sh.\n"
        "3. Foydalanuvchi xato qilsa, aylantirmasdan o'sha sahnada davom et "
        "   va xatoning to'g'risini keyingi xabar oxirida [ ] ichida ko'rsat.\n"
        "4. Sahnani realistik va qiziqarli olib bor.\n"
        "5. Har javob 2-4 gap bo'lsin.\n"
        f"6. Suhbatni boshlash uchun: \"{sc['starter']}\""
    )
    resp = call_ai(
        [{"role": "user", "content": "Начнём!"}],
        system_prompt=system, max_tokens=300,
    )
    starter = resp or sc["starter"]
    sid = db.roleplay_start(role_key, sc["user_role"], sc["ai_role"])
    return jsonify({
        "ok": True, "session_id": sid,
        "response":  starter,
        "user_role": sc["user_role"],
        "ai_role":   sc["ai_role"],
        "title":     sc["title"],
        "icon":      sc["icon"],
    })

@require_auth
def api_roleplay_chat():
    d        = request.get_json()
    sid      = d.get("session_id")
    user_msg = d.get("message", "").strip()
    level    = db.get_setting("ai_conversation_level", "beginner")

    if not sid or not user_msg:
        return jsonify({"error": "session_id va message kerak"}), 400

    session_data = db.roleplay_get(sid)
    if not session_data:
        return jsonify({"error": "Sessiya topilmadi"}), 404

    role_key = session_data["role_type"]
    sc       = ROLEPLAY_SCENARIOS.get(role_key, ROLEPLAY_SCENARIOS["shop"])

    internet = db.get_setting("internet_allowed", "on") == "on"
    if not internet or not GEMINI_API_KEY:
        db.add_xp(3)
        return jsonify({"response": "Хорошо! Продолжайте. (Yaxshi! Davom eting.)", "ok": True, "offline": True})

    # Oldingi xabarlar
    try:
        prev_msgs = json.loads(session_data["messages_json"] or "[]")
    except Exception:
        prev_msgs = []

    system = (
        f"Sen RusLearn roleplay o'yinida {sc['ai_role']} rolini o'ynayapsan.\n"
        f"Sahna: {sc['title']} | Daraja: {level}\n"
        "Har javob 2-4 gap. Sahnadan chiqma. Xato = [ To'g'risi: ... ] format."
    )
    messages = prev_msgs + [{"role": "user", "content": user_msg}]
    resp = call_ai(messages, system_prompt=system, max_tokens=300)
    if not resp:
        return jsonify({"response": sc["starter"], "ok": True, "offline": True})

    prev_msgs.append({"role": "user",      "content": user_msg})
    prev_msgs.append({"role": "assistant", "content": resp})
    db.roleplay_update(sid, prev_msgs[-20:])   # oxirgi 20 ta xabar
    db.add_xp(5)
    db.streak_today(xp=5, minutes=1)
    return jsonify({"response": resp, "ok": True})

@require_auth
def api_roleplay_end():
    d   = request.get_json()
    sid = d.get("session_id")
    if not sid:
        return jsonify({"error": "session_id kerak"}), 400

    session_data = db.roleplay_get(sid)
    if not session_data:
        return jsonify({"error": "Topilmadi"}), 404

    try:
        msgs = json.loads(session_data["messages_json"] or "[]")
    except Exception:
        msgs = []

    user_turns = sum(1 for m in msgs if m.get("role") == "user")
    score = min(100, user_turns * 10)
    db.roleplay_end(sid, score)
    db.add_xp(score // 2)
    db.streak_today(xp=score//2, minutes=user_turns * 2)
    return jsonify({"ok": True, "score": score, "turns": user_turns})


# ══════════════════════════════════════════════════
# MAQSAD KUZATUV VA HISOBOT
# ══════════════════════════════════════════════════

@require_auth
def api_goals_get():
    goal_words   = int(db.memory_get("daily_goal_words",  "10"))
    goal_minutes = int(db.get_setting("daily_goal_min",   "30"))
    today        = db._row(
        "SELECT * FROM streak_log WHERE date=date('now','localtime')")
    stats = db.get_stats()
    return jsonify({
        "goals": {
            "words":   goal_words,
            "minutes": goal_minutes,
            "xp":      int(db.memory_get("daily_goal_xp", "50")),
        },
        "today": {
            "words":   today["words_learned"] if today else 0,
            "minutes": today["minutes"]        if today else int(stats.get("today_min",0)),
            "xp":      today["xp_earned"]      if today else 0,
        },
        "streak": db.streak_current(),
    })

@require_auth
def api_goals_set():
    d = request.get_json()
    if "words"   in d: db.memory_set("daily_goal_words", d["words"])
    if "xp"      in d: db.memory_set("daily_goal_xp",    d["xp"])
    if "minutes" in d: db.set_setting("daily_goal_min",  str(d["minutes"]))
    return jsonify({"ok": True})

@require_auth
def api_goals_report():
    """Bugungi maqsad bajarilish foizi + motivatsion xabar"""
    r    = api_goals_get().get_json()
    g    = r["goals"]
    t    = r["today"]
    pcts = {
        "words":   min(100, round(t["words"]   / max(g["words"],1)   * 100)),
        "minutes": min(100, round(t["minutes"] / max(g["minutes"],1) * 100)),
        "xp":      min(100, round(t["xp"]      / max(g["xp"],1)      * 100)),
    }
    avg = round(sum(pcts.values()) / 3)
    if avg >= 100:
        msg = "🏆 Barcha maqsadlar bajarildi! Ajoyib ish!"
    elif avg >= 70:
        msg = f"🔥 Yaxshi bormoqda! {100-avg}% qoldi."
    elif avg >= 40:
        msg = f"💪 Davom eting! Hali {g['words']-t['words']} so'z va {g['minutes']-t['minutes']} daqiqa qoldi."
    else:
        msg = "⏰ Bugun hali ko'p ish bor! Boshlang!"
    return jsonify({**r, "pcts": pcts, "avg_pct": avg, "message": msg})


# ══════════════════════════════════════════════════
# AI PANEL — BOSHQARUV API (15 route)
# ══════════════════════════════════════════════════

# ── 1. Savol so'zlar ───────────────────────────────
@require_auth
def panel_qwords_list():
    return jsonify(db._rows("SELECT * FROM ai_question_words ORDER BY word"))

@require_auth
def panel_qwords_add():
    d    = request.get_json()
    word = d.get("word", "").strip().lower()
    if not word:
        return jsonify({"error": "So'z kiritilmagan"}), 400
    ex = db._row("SELECT id FROM ai_question_words WHERE word=?", (word,))
    if ex:
        return jsonify({"error": "Bu so'z allaqachon mavjud", "id": ex["id"]}), 409
    wid = db._ins(
        "INSERT INTO ai_question_words(word,lang) VALUES(?,?)",
        (word, d.get("lang", "uz")))
    return jsonify({"ok": True, "id": wid})

@require_auth
def panel_qwords_delete(wid):
    db._exec("DELETE FROM ai_question_words WHERE id=?", (wid,))
    return jsonify({"ok": True})

@require_auth
def panel_qwords_toggle(wid):
    row = db._row("SELECT enabled FROM ai_question_words WHERE id=?", (wid,))
    if not row:
        return jsonify({"error": "Topilmadi"}), 404
    new = 0 if row["enabled"] else 1
    db._exec("UPDATE ai_question_words SET enabled=? WHERE id=?", (new, wid))
    return jsonify({"ok": True, "enabled": bool(new)})


# ── 2. Nomlar ──────────────────────────────────────
@require_auth
def panel_names_list():
    return jsonify(db._rows("SELECT * FROM ai_names ORDER BY name"))

@require_auth
def panel_names_add():
    d    = request.get_json()
    name = d.get("name", "").strip().lower()
    if not name:
        return jsonify({"error": "Nom kiritilmagan"}), 400
    ex = db._row("SELECT id FROM ai_names WHERE name=?", (name,))
    if ex:
        return jsonify({"error": "Bu nom allaqachon mavjud", "id": ex["id"]}), 409
    qws = d.get("q_words", "")
    nid = db._ins(
        "INSERT INTO ai_names(name, q_words) VALUES(?,?)", (name, qws))
    return jsonify({"ok": True, "id": nid})

@require_auth
def panel_names_delete(nid):
    nm = db._row("SELECT name FROM ai_names WHERE id=?", (nid,))
    if nm:
        db._exec("DELETE FROM ai_qa_pairs WHERE name=?", (nm["name"],))
    db._exec("DELETE FROM ai_names WHERE id=?", (nid,))
    return jsonify({"ok": True})


# ── 3. Savol+Nom juftliklari (Ma'lumot) ────────────
@require_auth
def panel_qa_list():
    q_word = request.args.get("q_word", "")
    name   = request.args.get("name",   "")
    q = "SELECT * FROM ai_qa_pairs WHERE 1=1"
    p = []
    if q_word: q += " AND q_word=?"; p.append(q_word)
    if name:   q += " AND name=?";   p.append(name)
    q += " ORDER BY updated_at DESC"
    return jsonify(db._rows(q, p))

@require_auth
def panel_qa_save():
    d      = request.get_json()
    q_word = d.get("q_word", "").strip().lower()
    name   = d.get("name",   "").strip().lower()
    answer = d.get("answer", "").strip()
    if not q_word or not name or not answer:
        return jsonify({"error": "q_word, name, answer majburiy"}), 400
    # Nom mavjud bo'lmasa yaratish
    db.conn.execute(
        "INSERT OR IGNORE INTO ai_names(name, q_words) VALUES(?,?)", (name, q_word))
    # Savol so'z mavjud bo'lmasa yaratish
    db.conn.execute(
        "INSERT OR IGNORE INTO ai_question_words(word) VALUES(?)", (q_word,))
    # Juftlik: mavjud bo'lsa yangilash, yo'q bo'lsa qo'shish
    ex = db._row(
        "SELECT id FROM ai_qa_pairs WHERE q_word=? AND name=?", (q_word, name))
    if ex:
        db._exec(
            "UPDATE ai_qa_pairs SET answer=?, updated_at=datetime('now') WHERE id=?",
            (answer, ex["id"]))
        pid = ex["id"]
    else:
        pid = db._ins(
            "INSERT INTO ai_qa_pairs(q_word,name,answer) VALUES(?,?,?)",
            (q_word, name, answer))
    db.conn.commit()
    return jsonify({"ok": True, "id": pid})

@require_auth
def panel_qa_delete(pid):
    db._exec("DELETE FROM ai_qa_pairs WHERE id=?", (pid,))
    return jsonify({"ok": True})


# ── 4. Sinonimlar guruhlari ────────────────────────
@require_auth
def panel_synonyms_list():
    rows = db._rows("SELECT * FROM ai_synonym_groups ORDER BY group_name")
    for r in rows:
        try:    r["synonyms_list"] = json.loads(r["synonyms"])
        except: r["synonyms_list"] = []
    return jsonify(rows)

@require_auth
def panel_synonyms_save():
    d    = request.get_json()
    gid  = d.get("id")
    name = d.get("group_name", "").strip()
    syns = d.get("synonyms", [])    # list
    ans  = d.get("answer", "").strip()
    if not syns or not ans:
        return jsonify({"error": "synonyms va answer majburiy"}), 400
    syns_json = json.dumps([s.strip().lower() for s in syns if s.strip()],
                           ensure_ascii=False)
    if gid:
        db._exec(
            "UPDATE ai_synonym_groups SET group_name=?,synonyms=?,answer=? WHERE id=?",
            (name, syns_json, ans, gid))
        return jsonify({"ok": True, "id": gid})
    new_id = db._ins(
        "INSERT INTO ai_synonym_groups(group_name,synonyms,answer) VALUES(?,?,?)",
        (name, syns_json, ans))
    return jsonify({"ok": True, "id": new_id})

@require_auth
def panel_synonyms_delete(sid):
    db._exec("DELETE FROM ai_synonym_groups WHERE id=?", (sid,))
    return jsonify({"ok": True})


# ── 5. Taqiqlangan so'zlar ─────────────────────────
@require_auth
def panel_banned_list():
    return jsonify(db._rows(
        "SELECT * FROM ai_banned_words ORDER BY word"))

@require_auth
def panel_banned_save():
    d    = request.get_json()
    bid  = d.get("id")
    word = d.get("word", "").strip().lower()
    ans  = d.get("answer", "").strip()
    if not word or not ans:
        return jsonify({"error": "word va answer majburiy"}), 400
    if bid:
        db._exec(
            "UPDATE ai_banned_words SET word=?,answer=?,enabled=? WHERE id=?",
            (word, ans, int(d.get("enabled", 1)), bid))
        return jsonify({"ok": True, "id": bid})
    ex = db._row("SELECT id FROM ai_banned_words WHERE word=?", (word,))
    if ex:
        db._exec("UPDATE ai_banned_words SET answer=? WHERE id=?", (ans, ex["id"]))
        return jsonify({"ok": True, "id": ex["id"]})
    new_id = db._ins(
        "INSERT INTO ai_banned_words(word,answer) VALUES(?,?)", (word, ans))
    return jsonify({"ok": True, "id": new_id})

@require_auth
def panel_banned_delete(bid):
    db._exec("DELETE FROM ai_banned_words WHERE id=?", (bid,))
    return jsonify({"ok": True})


# ── 6. Standart javob ─────────────────────────────
@require_auth
def panel_default_get():
    row = db._row("SELECT text FROM ai_default_response WHERE id=1")
    return jsonify({"text": row["text"] if row else ""})

@require_auth
def panel_default_set():
    text = request.get_json().get("text", "").strip()
    if not text:
        return jsonify({"error": "text bo'sh bo'lmasin"}), 400
    db._exec(
        "INSERT INTO ai_default_response(id,text) VALUES(1,?) "
        "ON CONFLICT(id) DO UPDATE SET text=excluded.text", (text,))
    return jsonify({"ok": True})


# ── 7. Real-vaqt test ──────────────────────────────
@require_auth
def panel_test():
    """Kiritilgan xabarga panel engine javobini qaytaradi"""
    msg = request.get_json().get("message", "").strip()
    if not msg:
        return jsonify({"error": "Xabar bo'sh"}), 400
    result = _panel_engine(msg)
    if result:
        return jsonify({"ok": True, "found": True,
                        "answer": result["answer"],
                        "source": result.get("source","panel")})
    default = db._row("SELECT text FROM ai_default_response WHERE id=1")
    return jsonify({"ok": True, "found": False,
                    "answer": default["text"] if default else "Javob topilmadi",
                    "source": "default"})


# ── 8. Panel umumiy statistika ────────────────────
@require_auth
def panel_stats():
    return jsonify({
        "q_words":  db._row("SELECT COUNT(*) as c FROM ai_question_words")["c"],
        "names":    db._row("SELECT COUNT(*) as c FROM ai_names")["c"],
        "qa_pairs": db._row("SELECT COUNT(*) as c FROM ai_qa_pairs")["c"],
        "synonyms": db._row("SELECT COUNT(*) as c FROM ai_synonym_groups")["c"],
        "banned":   db._row("SELECT COUNT(*) as c FROM ai_banned_words")["c"],
    })


# ══════════════════════════════════════════════════
# SAMARALI AI v3 — Python backend API
# LocalStorage → SQLite (barcha ma'lumotlar doimiy)
# ══════════════════════════════════════════════════

# ── Yordamchi funksiyalar ─────────────────────────
@require_auth
def sc_triggers_list():
    return jsonify(_sc_rows(
        "SELECT * FROM sc_triggers ORDER BY word"))

@require_auth
def sc_triggers_add():
    d    = request.get_json()
    word = (d.get("word") or "").strip().lower()
    if not word:
        return jsonify({"error": "word kerak"}), 400
    ex = _sc_row("SELECT id FROM sc_triggers WHERE word=?", (word,))
    if ex:
        return jsonify({"error": "Allaqachon bor", "id": ex["id"]}), 409
    wid = _sc_ins(
        "INSERT INTO sc_triggers(word) VALUES(?)", (word,))
    return jsonify({"ok": True, "id": wid})

@require_auth
def sc_triggers_delete(wid):
    _sc_exec("DELETE FROM sc_triggers WHERE id=?", (wid,))
    return jsonify({"ok": True})

@require_auth
def sc_triggers_toggle(wid):
    r = _sc_row("SELECT enabled FROM sc_triggers WHERE id=?", (wid,))
    if not r:
        return jsonify({"error": "topilmadi"}), 404
    new = 0 if r["enabled"] else 1
    _sc_exec("UPDATE sc_triggers SET enabled=? WHERE id=?", (new, wid))
    return jsonify({"ok": True, "enabled": bool(new)})


# ── 2. Entities (Nomlar) ──────────────────────────
@require_auth
def sc_entities_list():
    return jsonify(_sc_rows(
        "SELECT * FROM sc_entities ORDER BY name"))

@require_auth
def sc_entities_add():
    d    = request.get_json()
    name = (d.get("name") or "").strip().lower()
    if not name:
        return jsonify({"error": "name kerak"}), 400
    ex = _sc_row("SELECT id FROM sc_entities WHERE name=?", (name,))
    if ex:
        # Yangilash
        _sc_exec(
            "UPDATE sc_entities SET triggers=?,aliases=? WHERE id=?",
            (d.get("triggers",""), d.get("aliases",""), ex["id"]))
        return jsonify({"ok": True, "id": ex["id"]})
    eid = _sc_ins(
        "INSERT INTO sc_entities(name,triggers,aliases) VALUES(?,?,?)",
        (name, d.get("triggers",""), d.get("aliases","")))
    return jsonify({"ok": True, "id": eid})

@require_auth
def sc_entities_delete(eid):
    row = _sc_row("SELECT name FROM sc_entities WHERE id=?", (eid,))
    if row:
        _sc_exec("DELETE FROM sc_facts WHERE entity=?", (row["name"],))
    _sc_exec("DELETE FROM sc_entities WHERE id=?", (eid,))
    return jsonify({"ok": True})


# ── 3. Facts (Savol+Nom → Javob) ─────────────────
@require_auth
def sc_facts_list():
    rows = _sc_rows("SELECT * FROM sc_facts ORDER BY updated_at DESC")
    for r in rows:
        try:
            r["variants"] = json.loads(r.get("variants_json") or "[]")
        except Exception:
            r["variants"] = []
        try:
            r["sm2"] = json.loads(r.get("sm2_json") or "{}")
        except Exception:
            r["sm2"] = {}
    return jsonify(rows)

@require_auth
def sc_facts_save():
    d       = request.get_json()
    trigger = (d.get("trigger_word") or d.get("trigger") or "").strip().lower()
    entity  = (d.get("entity") or "").strip().lower()
    reply   = (d.get("reply") or "").strip()
    if not trigger or not entity or not reply:
        return jsonify({"error": "trigger_word, entity, reply kerak"}), 400
    variants = json.dumps(d.get("variants") or [], ensure_ascii=False)
    sm2_def  = json.dumps({
        "interval": 1, "ef": 2.5, "reps": 0,
        "nextReviewAt": ""
    })
    # Avtomatik entity qo'shish
    db.conn.execute(
        "INSERT OR IGNORE INTO sc_entities(name,triggers) VALUES(?,?)",
        (entity, trigger))
    # Avtomatik trigger qo'shish
    db.conn.execute(
        "INSERT OR IGNORE INTO sc_triggers(word) VALUES(?)", (trigger,))
    ex = _sc_row(
        "SELECT id FROM sc_facts WHERE trigger_word=? AND entity=?",
        (trigger, entity))
    if ex:
        _sc_exec(
            "UPDATE sc_facts SET reply=?,variants_json=?,updated_at=datetime('now') WHERE id=?",
            (reply, variants, ex["id"]))
        db.conn.commit()
        return jsonify({"ok": True, "id": ex["id"]})
    fid = _sc_ins(
        "INSERT INTO sc_facts(trigger_word,entity,reply,variants_json,sm2_json) VALUES(?,?,?,?,?)",
        (trigger, entity, reply, variants, sm2_def))
    db.conn.commit()
    return jsonify({"ok": True, "id": fid})

@require_auth
def sc_facts_delete(fid):
    _sc_exec("DELETE FROM sc_facts WHERE id=?", (fid,))
    return jsonify({"ok": True})

@require_auth
def sc_facts_sm2(fid):
    d       = request.get_json()
    quality = d.get("quality", 3)
    row     = _sc_row("SELECT * FROM sc_facts WHERE id=?", (fid,))
    if not row:
        return jsonify({"error": "topilmadi"}), 404
    try:
        sm2 = json.loads(row.get("sm2_json") or "{}")
    except Exception:
        sm2 = {}
    interval = sm2.get("interval", 1)
    ef       = sm2.get("ef", 2.5)
    reps     = sm2.get("reps", 0)
    if quality < 3:
        reps = 0; interval = 1
    else:
        if   reps == 0: interval = 1
        elif reps == 1: interval = 3
        else:           interval = round(interval * ef)
        reps += 1
    ef = max(1.3, ef + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    from datetime import datetime, timedelta
    next_review = (datetime.now() + timedelta(days=interval)).strftime("%Y-%m-%d")
    sm2.update({"interval": interval, "ef": round(ef, 2), "reps": reps,
                "nextReviewAt": next_review})
    if quality >= 3:
        _sc_exec("UPDATE sc_facts SET correct_count=correct_count+1,sm2_json=? WHERE id=?",
                 (json.dumps(sm2), fid))
    else:
        _sc_exec("UPDATE sc_facts SET wrong_count=wrong_count+1,sm2_json=? WHERE id=?",
                 (json.dumps(sm2), fid))
    return jsonify({"ok": True, "sm2": sm2})


# ── 4. Aliases (Sinonimlar) ───────────────────────
@require_auth
def sc_aliases_list():
    rows = _sc_rows("SELECT * FROM sc_aliases ORDER BY id")
    for r in rows:
        try:
            r["words"] = json.loads(r.get("words_json") or "[]")
        except Exception:
            r["words"] = []
    return jsonify(rows)

@require_auth
def sc_aliases_save():
    d     = request.get_json()
    words = d.get("words") or []
    reply = (d.get("reply") or "").strip()
    fuzz  = int(d.get("fuzz") or 80)
    bid   = d.get("id")
    if len(words) < 2 or not reply:
        return jsonify({"error": "kamida 2 so'z va reply kerak"}), 400
    wj = json.dumps([w.lower() for w in words], ensure_ascii=False)
    if bid:
        _sc_exec("UPDATE sc_aliases SET words_json=?,reply=?,fuzz=? WHERE id=?",
                 (wj, reply, fuzz, bid))
        return jsonify({"ok": True, "id": bid})
    aid = _sc_ins(
        "INSERT INTO sc_aliases(words_json,reply,fuzz) VALUES(?,?,?)",
        (wj, reply, fuzz))
    return jsonify({"ok": True, "id": aid})

@require_auth
def sc_aliases_delete(aid):
    _sc_exec("DELETE FROM sc_aliases WHERE id=?", (aid,))
    return jsonify({"ok": True})


# ── 5. Blocklist (Taqiqlangan so'zlar) ────────────
@require_auth
def sc_blocklist_list():
    return jsonify(_sc_rows(
        "SELECT * FROM sc_blocklist ORDER BY word"))

@require_auth
def sc_blocklist_save():
    d    = request.get_json()
    word = (d.get("word") or "").strip().lower()
    rep  = (d.get("reply") or "").strip()
    bid  = d.get("id")
    if not word or not rep:
        return jsonify({"error": "word va reply kerak"}), 400
    if bid:
        _sc_exec("UPDATE sc_blocklist SET word=?,reply=? WHERE id=?",
                 (word, rep, bid))
        return jsonify({"ok": True, "id": bid})
    ex = _sc_row("SELECT id FROM sc_blocklist WHERE word=?", (word,))
    if ex:
        _sc_exec("UPDATE sc_blocklist SET reply=? WHERE id=?", (rep, ex["id"]))
        return jsonify({"ok": True, "id": ex["id"]})
    new_id = _sc_ins(
        "INSERT INTO sc_blocklist(word,reply) VALUES(?,?)", (word, rep))
    return jsonify({"ok": True, "id": new_id})

@require_auth
def sc_blocklist_delete(bid):
    _sc_exec("DELETE FROM sc_blocklist WHERE id=?", (bid,))
    return jsonify({"ok": True})


# ── 6. LTM (Uzoq muddatli xotira) ────────────────
@require_auth
def sc_ltm_list():
    rows = _sc_rows("SELECT * FROM sc_ltm ORDER BY ltm_key, confidence DESC")
    # Guruhlab qaytarish
    result = {}
    for r in rows:
        k = r["ltm_key"]
        if k not in result:
            result[k] = []
        result[k].append(r)
    return jsonify(result)

@require_auth
def sc_ltm_save():
    d   = request.get_json()
    key = (d.get("key") or "").strip()
    val = (d.get("value") or "").strip()
    conf = float(d.get("confidence") or 0.8)
    src  = d.get("source") or "manual"
    if not key or not val:
        return jsonify({"error": "key va value kerak"}), 400
    # Mavjudligini tekshirish
    ex = _sc_row(
        "SELECT id,count FROM sc_ltm WHERE ltm_key=? AND ltm_val=?", (key, val))
    if ex:
        _sc_exec(
            "UPDATE sc_ltm SET confidence=MIN(1.0,confidence+0.05),count=count+1 WHERE id=?",
            (ex["id"],))
        return jsonify({"ok": True, "id": ex["id"]})
    lid = _sc_ins(
        "INSERT INTO sc_ltm(ltm_key,ltm_val,confidence,source) VALUES(?,?,?,?)",
        (key, val, conf, src))
    return jsonify({"ok": True, "id": lid})

@require_auth
def sc_ltm_delete(key):
    _sc_exec("DELETE FROM sc_ltm WHERE ltm_key=?", (key,))
    return jsonify({"ok": True})

@require_auth
def sc_ltm_clear():
    _sc_exec("DELETE FROM sc_ltm")
    return jsonify({"ok": True})


# ── 7. Personality ────────────────────────────────
@require_auth
def sc_personality_get():
    row = _sc_row("SELECT data_json FROM sc_personality WHERE id=1")
    try:
        return jsonify(json.loads(row["data_json"]) if row else {})
    except Exception:
        return jsonify({})

@require_auth
def sc_personality_save():
    d = request.get_json()
    _sc_exec(
        "INSERT INTO sc_personality(id,data_json) VALUES(1,?) "
        "ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json",
        (json.dumps(d, ensure_ascii=False),))
    return jsonify({"ok": True})


# ── 8. Default javob ──────────────────────────────
@require_auth
def sc_default_get():
    row = _sc_row("SELECT text FROM sc_default WHERE id=1")
    return jsonify({"text": row["text"] if row else ""})

@require_auth
def sc_default_save():
    text = (request.get_json().get("text") or "").strip()
    if not text:
        return jsonify({"error": "text kerak"}), 400
    _sc_exec(
        "INSERT INTO sc_default(id,text) VALUES(1,?) "
        "ON CONFLICT(id) DO UPDATE SET text=excluded.data_json",
        (text,))
    _sc_exec(
        "UPDATE sc_default SET text=? WHERE id=1", (text,))
    return jsonify({"ok": True})


# ── 9. Stats ──────────────────────────────────────
@require_auth
def sc_stats_get():
    row = _sc_row("SELECT data_json FROM sc_stats WHERE id=1")
    try:
        return jsonify(json.loads(row["data_json"]) if row else {})
    except Exception:
        return jsonify({})

@require_auth
def sc_stats_save():
    d = request.get_json()
    _sc_exec(
        "INSERT INTO sc_stats(id,data_json) VALUES(1,?) "
        "ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json",
        (json.dumps(d, ensure_ascii=False),))
    return jsonify({"ok": True})

@require_auth
def sc_stats_reset():
    empty = json.dumps({
        "total":0,"learned":0,"correct":0,"wrong":0,
        "topicMap":{},"dayMap":{},"feedPos":0,"feedNeg":0,"rejected":0
    })
    _sc_exec("UPDATE sc_stats SET data_json=? WHERE id=1", (empty,))
    return jsonify({"ok": True})


# ── 10. Learn log ─────────────────────────────────
@require_auth
def sc_log_list():
    return jsonify(_sc_rows(
        "SELECT * FROM sc_learn_log ORDER BY logged_at DESC LIMIT 50"))

@require_auth
def sc_log_add():
    d = request.get_json()
    _sc_ins(
        "INSERT INTO sc_learn_log(q,a,trigger_w,entity,log_type) VALUES(?,?,?,?,?)",
        (d.get("q"), d.get("a"), d.get("trigger"), d.get("entity"), d.get("type")))
    return jsonify({"ok": True})

@require_auth
def sc_log_clear():
    _sc_exec("DELETE FROM sc_learn_log")
    return jsonify({"ok": True})


# ── 11. Bulk ma'lumot yuklanishi ──────────────────
@require_auth
def sc_bulk():
    rows    = request.get_json().get("rows") or []
    added   = 0; updated = 0; errors = 0
    sm2_def = json.dumps({"interval":1,"ef":2.5,"reps":0,"nextReviewAt":""})
    for r in rows:
        trigger = (r.get("trigger") or "").strip().lower()
        entity  = (r.get("entity")  or "").strip().lower()
        reply   = (r.get("reply")   or "").strip()
        if not trigger or not entity or not reply:
            errors += 1; continue
        db.conn.execute(
            "INSERT OR IGNORE INTO sc_entities(name,triggers) VALUES(?,?)",
            (entity, trigger))
        db.conn.execute(
            "INSERT OR IGNORE INTO sc_triggers(word) VALUES(?)", (trigger,))
        ex = _sc_row(
            "SELECT id FROM sc_facts WHERE trigger_word=? AND entity=?",
            (trigger, entity))
        variants = json.dumps(r.get("variants") or [], ensure_ascii=False)
        if ex:
            _sc_exec(
                "UPDATE sc_facts SET reply=?,variants_json=? WHERE id=?",
                (reply, variants, ex["id"]))
            updated += 1
        else:
            _sc_ins(
                "INSERT INTO sc_facts(trigger_word,entity,reply,variants_json,sm2_json) VALUES(?,?,?,?,?)",
                (trigger, entity, reply, variants, sm2_def))
            added += 1
    db.conn.commit()
    return jsonify({"ok": True, "added": added, "updated": updated, "errors": errors})


# ── 12. Export/Import (to'liq DB) ─────────────────
@require_auth
def sc_export():
    data = {
        "version":   "3.0",
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "triggers":  _sc_rows("SELECT * FROM sc_triggers"),
        "entities":  _sc_rows("SELECT * FROM sc_entities"),
        "facts":     _sc_rows("SELECT * FROM sc_facts"),
        "aliases":   _sc_rows("SELECT * FROM sc_aliases"),
        "blocklist": _sc_rows("SELECT * FROM sc_blocklist"),
        "ltm":       _sc_rows("SELECT * FROM sc_ltm"),
        "learn_log": _sc_rows("SELECT * FROM sc_learn_log ORDER BY id DESC LIMIT 200"),
    }
    row_p = _sc_row("SELECT data_json FROM sc_personality WHERE id=1")
    row_d = _sc_row("SELECT text FROM sc_default WHERE id=1")
    row_s = _sc_row("SELECT data_json FROM sc_stats WHERE id=1")
    try:
        data["personality"] = json.loads(row_p["data_json"]) if row_p else {}
    except Exception:
        data["personality"] = {}
    data["default_reply"] = row_d["text"] if row_d else ""
    try:
        data["stats"] = json.loads(row_s["data_json"]) if row_s else {}
    except Exception:
        data["stats"] = {}
    return jsonify(data)

@require_auth
def sc_import():
    d = request.get_json()
    added = 0
    sm2d  = json.dumps({"interval":1,"ef":2.5,"reps":0,"nextReviewAt":""})
    for t in (d.get("triggers") or []):
        db.conn.execute(
            "INSERT OR IGNORE INTO sc_triggers(word,enabled) VALUES(?,?)",
            (t.get("word",""), t.get("enabled",1)))
        added += 1
    for e in (d.get("entities") or []):
        db.conn.execute(
            "INSERT OR REPLACE INTO sc_entities(name,triggers,aliases) VALUES(?,?,?)",
            (e.get("name",""), e.get("triggers",""), e.get("aliases","")))
        added += 1
    for f in (d.get("facts") or []):
        db.conn.execute(
            "INSERT OR REPLACE INTO sc_facts(trigger_word,entity,reply,variants_json,score,sm2_json) VALUES(?,?,?,?,?,?)",
            (f.get("trigger_word",""), f.get("entity",""), f.get("reply",""),
             f.get("variants_json","[]"), f.get("score",5), f.get("sm2_json",sm2d)))
        added += 1
    for a in (d.get("aliases") or []):
        db.conn.execute(
            "INSERT OR IGNORE INTO sc_aliases(words_json,reply,fuzz) VALUES(?,?,?)",
            (a.get("words_json","[]"), a.get("reply",""), a.get("fuzz",80)))
        added += 1
    for b in (d.get("blocklist") or []):
        db.conn.execute(
            "INSERT OR REPLACE INTO sc_blocklist(word,reply) VALUES(?,?)",
            (b.get("word",""), b.get("reply","")))
        added += 1
    if d.get("personality"):
        _sc_exec(
            "UPDATE sc_personality SET data_json=? WHERE id=1",
            (json.dumps(d["personality"], ensure_ascii=False),))
    if d.get("default_reply"):
        _sc_exec("UPDATE sc_default SET text=? WHERE id=1", (d["default_reply"],))
    db.conn.commit()
    return jsonify({"ok": True, "imported": added})


# ── 13. Nuke (hammasini o'chirish) ────────────────
@require_auth
def sc_nuke():
    for tbl in ["sc_triggers","sc_entities","sc_facts","sc_aliases",
                "sc_blocklist","sc_ltm","sc_learn_log"]:
        _sc_exec(f"DELETE FROM {tbl}")
    _sc_exec("UPDATE sc_stats SET data_json=? WHERE id=1",
             ('{"total":0,"learned":0,"correct":0,"wrong":0,"topicMap":{},"dayMap":{},"feedPos":0,"feedNeg":0,"rejected":0}',))
    return jsonify({"ok": True})


# ── Notify test ────────────────────────────────────
@app.route("/api/notify/test", methods=["POST"])
@require_auth
def api_notify_test():
    send_windows_notif("📚 RusLearn — Test", "Xabarnoma tizimi ishlayapti! ✅")
    return jsonify({"ok": True})

# ── Entry Point ────────────────────────────────────
def open_browser():
    time.sleep(1.2)
    webbrowser.open("http://localhost:5800")

if __name__ == "__main__":
    print("=" * 60)
    print("  🇷🇺  RusLearn Pro v1.0  —  Rus tilini o'rganish")
    print("=" * 60)
    print(f"  🌐  URL     : http://localhost:5800")
    print(f"  📂  Papka  : {BASE_DIR}")
    ai_ok = "✅ tayyor (Gemini)" if GEMINI_API_KEY else "❌ GEMINI_API_KEY o'rnatilmagan"
    print(f"  🤖  AI     : {ai_ok}")
    notif_ok = "✅" if NOTIF_AVAILABLE else "⚠ win10toast o'rnatilmagan (pip install win10toast)"
    print(f"  🔔  Notif  : {notif_ok}")
    print("=" * 60)
    if not GEMINI_API_KEY:
        print("\n  ⚠️  AI funksiyalari uchun bepul kalit oling:")
        print("  https://aistudio.google.com/app/apikey")
        print("  set GEMINI_API_KEY=AIza... (Windows)")
        print("  yoki: export GEMINI_API_KEY=AIza... (Linux/Mac)\n")
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host="0.0.0.0", port=5800, debug=False, threaded=True)
