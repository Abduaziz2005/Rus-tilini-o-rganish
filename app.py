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
# API kalit olish: https://aistudio.google.com/app/apikey (bepul, Google akkaunt kifoya)
GEMINI_API_KEY = os.environ.get(
    "GEMINI_API_KEY",
    "AIzaSyD-9tSrke72I3lGdwjgKMoLKyHH9VwBMh0"   # ← demo kalit (cheklangan)
)
GEMINI_MODEL = "gemini-1.5-flash"   # eng tez va bepul model

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
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result["candidates"][0]["content"]["parts"][0]["text"]
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
        ]
        for w in words:
            self.conn.execute("""INSERT OR IGNORE INTO words
                (russian,uzbek,pronunciation,category,level,example_ru,example_uz)
                VALUES(?,?,?,?,?,?,?)""", w)
        self.conn.commit()

    def _insert_grammar_rules(self):
        rules = [
            ("Rus alifbosi (Кириллица)", "beginner", "alphabet",
             "Rus tilida 33 ta harf bor. Ularning 10 tasi unli, 21 tasi undosh, 2 tasi belgi harflar.",
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
            ("Ismlar — Nominativ kelishigi", "beginner", "nouns",
             "Rus tilida otlarning 3 ta jins (rod) bor: erkak (мужской), ayol (женский), o'rta (средний). "
             "Erkak jins: -й, -ь yoki undosh bilan tugaydi. Ayol jins: -а, -я bilan tugaydi. "
             "O'rta jins: -о, -е bilan tugaydi.",
             json.dumps([
                 {"ru": "стол (erkak) — stol", "uz": "undosh bilan tugaydi → erkak jins"},
                 {"ru": "книга (ayol) — kitob", "uz": "-а bilan tugaydi → ayol jins"},
                 {"ru": "окно (o'rta) — deraza", "uz": "-о bilan tugaydi → o'rta jins"},
             ]),
             json.dumps([
                 {"q": "'Книга' qaysi jinsga mansub?", "a": "ayol jins", "type": "choice",
                  "options": ["erkak jins", "ayol jins", "o'rta jins"]},
             ])
            ),
            ("Fe'llar — Hozirgi zamon", "beginner", "verbs",
             "Rus tilida fe'llar ikkita spryajeniyaga (tuslanish) bo'linadi. "
             "1-spryajeniye: -ю/-у, -ешь/-ёшь, -ет/-ёт, -ем/-ём, -ете/-ёте, -ют/-ут. "
             "2-spryajeniye: -ю/-у, -ишь, -ит, -им, -ите, -ят/-ат.",
             json.dumps([
                 {"ru": "Я читаю — Men o'qiyapman", "uz": "читать → 1-spryajeniye"},
                 {"ru": "Ты читаешь — Sen o'qiyapsan", "uz": "-ешь qo'shimchasi"},
                 {"ru": "Он/она читает — U o'qiyapti", "uz": "-ет qo'shimchasi"},
                 {"ru": "Я говорю — Men gapiryapman", "uz": "говорить → 2-spryajeniye"},
                 {"ru": "Ты говоришь — Sen gapiryapsan", "uz": "-ишь qo'shimchasi"},
             ]),
             json.dumps([
                 {"q": "'Читать' fe'lining 'Я' shakli qanday?", "a": "читаю",
                  "type": "choice", "options": ["читаю", "читаешь", "читает"]},
             ])
            ),
            ("Sifatlar — Kelishish (Согласование)", "intermediate", "adjectives",
             "Rus tilida sifatlar ot bilan jins, son va kelishik bo'yicha moslashadi. "
             "Erkak: -ый/-ий/-ой. Ayol: -ая/-яя. O'rta: -ое/-ее. Ko'plik: -ые/-ие.",
             json.dumps([
                 {"ru": "красный стол (erkak)", "uz": "qizil stol"},
                 {"ru": "красная книга (ayol)", "uz": "qizil kitob"},
                 {"ru": "красное яблоко (o'rta)", "uz": "qizil olma"},
                 {"ru": "красные цветы (ko'plik)", "uz": "qizil gullar"},
             ]),
             json.dumps([
                 {"q": "'Синий' sifatining ayol jins shakli?", "a": "синяя",
                  "type": "choice", "options": ["синий", "синяя", "синее", "синие"]},
             ])
            ),
            ("Olmoshlar (Местоимения)", "beginner", "pronouns",
             "Shaxs olmoshlari: Я (men), Ты (sen), Он (u — erkak), Она (u — ayol), "
             "Оно (u — narsalar), Мы (biz), Вы (siz/sizlar), Они (ular).",
             json.dumps([
                 {"ru": "Я студент. — Men talabaman.", "uz": "Я — men"},
                 {"ru": "Ты говоришь по-русски. — Sen rus tilida gapirasan.", "uz": "Ты — sen"},
                 {"ru": "Мы учимся вместе. — Biz birga o'rganamiz.", "uz": "Мы — biz"},
             ]),
             json.dumps([
                 {"q": "'Biz' olmoshi rus tilida?", "a": "Мы",
                  "type": "choice", "options": ["Я", "Ты", "Мы", "Вы"]},
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
