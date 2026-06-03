# 🇷🇺 RusLearn Pro — Rus tilini o'rganish platformasi

Murakkab, ko'p funksiyali rus tili o'rganish veb-saytı.

## 🚀 Ishga tushirish

```bash
pip install -r requirements.txt
python app.py
```

Brauzer avtomatik ochiladi: **http://localhost:5800**

## 🤖 AI (ixtiyoriy)

```bash
# Windows
set ANTHROPIC_API_KEY=sk-ant-...

# Linux/Mac
export ANTHROPIC_API_KEY=sk-ant-...
```

## ✨ Funksiyalar

| Modul | Tavsif |
|-------|--------|
| 📖 **Lug'at** | 30+ boshlang'ich so'z, AI orqali yangi so'zlar yuklash, qidirish, tahrirlash |
| 🃏 **Kartochkalar** | SM-2 Spaced Repetition algoritmi — yadni mustahkamlash |
| 📝 **Grammatika** | 5+ qoida, misollar, mashqlar, AI tushuntirish |
| 🎮 **O'yinlar** | So'z moslashtirish, harflarni joylashtirish, yozuv poygasi, bo'sh joy to'ldirish |
| ❓ **Viktorina** | Daraja va savol soni tanlov, batafsil natija |
| 🤖 **AI Suhbat** | Claude AI bilan rus tilida muloqot, xatolarni tuzatish |
| 📅 **Jadval** | Dars rejalashtirish, o'tkazilgan darslar, Windows xabarnoma |
| 📊 **Yutuqlar** | XP tizimi, streak, darajalar, haftalik grafik, o'qish tarixi |
| 🌐 **Internet/Offline** | Internet ON/OFF tugmasi, yuklab olish imkoni |
| 🔔 **Xabarnoma** | Darsdan 30 daqiqa oldin Windows xabarnomasi |

## 📁 Loyiha tuzilmasi

```
RusLearn/
├── app.py              # Flask backend (1100+ qator)
├── templates/
│   ├── index.html      # Asosiy sahifa (740 qator)
│   └── login.html      # Kirish sahifasi
├── static/
│   ├── css/style.css   # Dark theme CSS (1000+ qator)
│   └── js/app.js       # JavaScript logikasi (1370+ qator)
├── data/
│   └── ruslearn.db     # SQLite database (avtomatik yaratiladi)
└── requirements.txt
```

## ⌨️ Klaviatura yorliqlari

- `Space` — Kartochkani aylashtirish
- `←` — Noto'g'ri deb belgilash
- `→` — To'g'ri deb belgilash
