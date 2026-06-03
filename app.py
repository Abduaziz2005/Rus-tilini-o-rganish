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

# ── GOOGLE GEMINI API (bepul: 1500 so'rov/kun) ───
# Kalit olish: https://aistudio.google.com/app/apikey
# Kalit saqlash: app.py yonida .env fayl yarating:
#   GEMINI_API_KEY=sizning_kalitingiz_shu_yerga
GEMINI_MODEL = "gemini-1.5-flash"

def _load_env_key():
    """app.py yonidagi .env fayldan GEMINI_API_KEY ni o'qiydi"""
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or _load_env_key()

def call_ai(messages, system_prompt="", max_tokens=1000):
    """Google Gemini API chaqiruvi (bepul, tashqi kutubxonasiz)"""
    import urllib.request
    if not GEMINI_API_KEY:
        return None

    # Gemini format: system + messages → contents
    contents = []
    if system_prompt:
        contents.append({
            "role": "user",
            "parts": [{"text": f"[Tizim ko'rsatmasi]: {system_prompt}"}]
        })
        contents.append({
            "role": "model",
            "parts": [{"text": "Tushundim, shu ko'rsatmalarga amal qilaman."}]
        })

    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    payload = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.7,
        }
    }
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    data = json.dumps(payload).encode("utf-8")
    # AQ. prefiksi → x-goog-api-key header orqali yuboriladi
    if GEMINI_API_KEY.startswith("AQ."):
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            data=data,
            headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
            method="POST"
        )
    else:
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"[Gemini HTTP {e.code}]: {body[:300]}")
        return None
    except Exception as e:
        print(f"[Gemini xato]: {e}")
        return None

# ── DATABASE ──────────────────────────────────────
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

        -- Lug'at so'zlari
        CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            russian TEXT NOT NULL,
            uzbek TEXT NOT NULL,
            pronunciation TEXT DEFAULT '',
            category TEXT DEFAULT 'general',
            level TEXT DEFAULT 'beginner',
            example_ru TEXT DEFAULT '',
            example_uz TEXT DEFAULT '',
            audio_file TEXT DEFAULT '',
            image_url TEXT DEFAULT '',
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

        -- AI suhbat tarixi
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            is_corrected INTEGER DEFAULT 0,
            correction TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
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

        -- Foydalanuvchi lug'ati (o'zi qo'shgan)
        CREATE TABLE IF NOT EXISTS user_words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            russian TEXT NOT NULL,
            uzbek TEXT NOT NULL,
            notes TEXT DEFAULT '',
            added_at TEXT DEFAULT (datetime('now'))
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
        num_cnt = self.conn.execute(
            "SELECT COUNT(*) as c FROM words WHERE category='numbers'").fetchone()["c"]
        if num_cnt < 30:
            self._insert_numbers_words()
        # Tanishish so'zlari (agar yo'q bo'lsa)
        intro_cnt = self.conn.execute(
            "SELECT COUNT(*) as c FROM words WHERE category='introduction'").fetchone()["c"]
        if intro_cnt < 20:
            self._insert_introduction_words()
        # Tanishish grammatikasi (agar yo'q bo'lsa)
        intro_gr = self.conn.execute(
            "SELECT COUNT(*) as c FROM grammar_rules WHERE category='introduction'").fetchone()["c"]
        if intro_gr < 3:
            self._insert_introduction_grammar()

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


# ── Global DB ─────────────────────────────────────
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
    return jsonify({"ok": True, "xp": xp})

@app.route("/api/games/leaderboard")
@require_auth
def api_leaderboard():
    return jsonify(db.get_leaderboard(request.args.get("game_type")))

# ── AI Chat ────────────────────────────────────────
@app.route("/api/chat", methods=["POST"])
@require_auth
def api_chat():
    if db.get_setting("internet_allowed", "on") != "on":
        return jsonify({"error": "Internet ruxsat etilmagan"}), 403
    if not GEMINI_API_KEY:
        return jsonify({"error": "AI API kalit topilmadi. aistudio.google.com dan bepul kalit oling."}), 400

    d = request.get_json()
    user_msg = d.get("message", "").strip()
    level = db.get_setting("ai_conversation_level", "beginner")

    # So'nggi 10 ta xabarni olib suhbat tarixi
    history = db.get_chat_history(10)
    messages = []
    for h in reversed(history):
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_msg})

    if level == 'beginner':
        lang_hint = "Oddiy so'zlar va gaplardan foydalanin"
    else:
        lang_hint = "Normal rus tilida gaplashing"
    system = (
        "Sen rus tili o'qituvchisi va suhbat sherigi bo'lib ishlayapsan.\n"
        f"Foydalanuvchi daraja: {level}.\n"
        "Qoidalar:\n"
        "- Foydalanuvchining rus tilidagi xatolarini tuzat (qisqacha)\n"
        f"- {lang_hint}\n"
        "- Har javobda o'zbekcha tarjima qo'shing\n"
        "- Agar xato qilsa, xatoni ko'rsat va to'g'risini yoz\n"
        "- Qiziqarli savollar ber, suhbatni davom ettir\n"
        "- Qisqa va aniq javob ber"
    )

    response = call_ai(messages, system_prompt=system, max_tokens=500)
    if not response:
        return jsonify({"error": "AI bilan bog'lanib bo'lmadi"}), 500

    db.save_chat("user", user_msg)
    db.save_chat("assistant", response)
    db.add_xp(5)
    return jsonify({"response": response, "ok": True})

@app.route("/api/chat/correct", methods=["POST"])
@require_auth
def api_chat_correct():
    """Foydalanuvchi AI javobini tahrirlash"""
    d = request.get_json()
    chat_id = d.get("id")
    correction = d.get("correction", "").strip()
    if chat_id:
        db._exec("UPDATE chat_history SET is_corrected=1, correction=? WHERE id=?",
                 (correction, chat_id))
    return jsonify({"ok": True})

@app.route("/api/chat/history")
@require_auth
def api_chat_history():
    return jsonify(db.get_chat_history(50))

@app.route("/api/chat/clear", methods=["POST"])
@require_auth
def api_chat_clear():
    db.clear_chat()
    return jsonify({"ok": True})

# ── AI — So'z tarjima va misol ────────────────────
@app.route("/api/ai/translate", methods=["POST"])
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
@app.route("/api/ai/explain-grammar", methods=["POST"])
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
@app.route("/api/ai/fetch-words", methods=["POST"])
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
