import os
import re
import sqlite3
from datetime import date

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from jinja2 import DictLoader, ChoiceLoader

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
DB = os.path.join(os.path.dirname(__file__), "bookings.db")
ADMIN_KEY = os.environ.get("ADMIN_KEY", "change-admin-key")

# ---------- Контент (меняйте здесь) ----------
BRAND = "Igal's Wave"
EMAIL = "hello@igalswave.com"
PHONE = "+972 00 000 0000"
SERVICES = ["Запись в студии", "Живое выступление", "Сведение и мастеринг", "Уроки / консультация"]
TRACKS = [  # положите mp3 в static/audio/ и укажите имя файла в "file"
    {"title": "Low Tide", "genre": "Ambient / Electronic", "year": 2025, "file": "low-tide.mp3"},
    {"title": "Salt Air", "genre": "Indie Pop", "year": 2025, "file": "salt-air.mp3"},
    {"title": "Night Swim", "genre": "Downtempo", "year": 2024, "file": "night-swim.mp3"},
]

# ---------- База данных ----------
def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created TEXT DEFAULT CURRENT_TIMESTAMP,
            name TEXT, email TEXT, phone TEXT,
            service TEXT, event_date TEXT, message TEXT)"""
        )


# ---------- Шаблоны ----------
BASE = """<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block title %}{{ brand }}{% endblock %}</title>
<meta name="description" content="Igal's Wave — музыка, запись, живые выступления.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#0F2236;--surface:#16304B;--text:#EDF3F7;--muted:#9FB3C4;--accent:#7EE0C9;--amber:#F4B860;--line:#2A4763}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);font:400 1.05rem/1.65 "DM Sans",system-ui,sans-serif}
h1,h2,h3{font-family:Syne,"DM Sans",sans-serif;line-height:1.1;margin:0 0 .5em}
h1{font-size:clamp(2.6rem,8vw,5.5rem);letter-spacing:-.02em}
h2{font-size:clamp(1.8rem,4vw,2.6rem)}
p{max-width:62ch;color:var(--muted)}
a{color:var(--accent)}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid var(--amber);outline-offset:2px}
.wrap{width:min(1100px,100% - 2.5rem);margin-inline:auto}
header.site{border-bottom:1px solid var(--line)}
header.site .wrap{display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1rem 0;flex-wrap:wrap}
.logo{font:800 1.4rem Syne,sans-serif;color:var(--text);text-decoration:none}
.logo span{color:var(--accent)}
nav{display:flex;gap:1.4rem;flex-wrap:wrap}
nav a{color:var(--muted);text-decoration:none;padding:.3rem 0;border-bottom:2px solid transparent}
nav a:hover,nav a[aria-current=page]{color:var(--text);border-color:var(--accent)}
section{padding:clamp(3rem,8vw,6rem) 0}
.btn{display:inline-block;background:var(--accent);color:#06222A;font-weight:700;border:0;border-radius:999px;padding:.85rem 1.8rem;text-decoration:none;cursor:pointer;font-size:1rem;transition:transform .15s}
.btn:hover{transform:translateY(-2px)}
.btn.ghost{background:transparent;color:var(--text);border:1px solid var(--line)}
.hero p{font-size:1.2rem;margin-bottom:1.8rem}
.actions{display:flex;gap:.8rem;flex-wrap:wrap}
.wave{display:block;width:100%;height:120px;margin-top:3rem}
.wave rect{fill:var(--accent);transform-box:fill-box;transform-origin:center;animation:pulse 2.4s ease-in-out infinite}
@keyframes pulse{0%,100%{transform:scaleY(.25)}50%{transform:scaleY(1)}}
.grid{display:grid;gap:1.2rem;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.card{background:var(--surface);border-radius:14px;padding:1.5rem}
.card h3{font-size:1.25rem}
.card p{margin:0}
.track{display:grid;gap:.6rem;background:var(--surface);border-radius:14px;padding:1.2rem 1.5rem;margin-bottom:1rem}
.track b{font:700 1.2rem Syne,sans-serif}
.track small{color:var(--muted)}
audio{width:100%}
form{display:grid;gap:1rem;max-width:620px}
label{display:grid;gap:.35rem;font-weight:500}
input,select,textarea{font:inherit;background:var(--surface);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:.75rem .9rem;width:100%}
textarea{min-height:130px;resize:vertical}
.row{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
.hp{position:absolute;left:-9999px}
.flash{padding:.9rem 1.2rem;border-radius:10px;margin-bottom:1.5rem;background:var(--surface);border-left:4px solid var(--accent)}
.flash.error{border-color:#FF8A80}
footer{border-top:1px solid var(--line);padding:2rem 0;color:var(--muted);font-size:.95rem}
@media (prefers-reduced-motion:reduce){.wave rect{animation:none}.btn{transition:none}html{scroll-behavior:auto}}
</style></head>
<body>
<header class="site"><div class="wrap">
  <a class="logo" href="{{ url_for('home') }}">Igal's <span>Wave</span></a>
  <nav aria-label="Основное меню">
    {% for ep, label in [('home','Главная'),('about','О нас'),('music','Музыка'),('contact','Контакты')] %}
    <a href="{{ url_for(ep) }}" {% if request.endpoint == ep %}aria-current="page"{% endif %}>{{ label }}</a>
    {% endfor %}
  </nav>
</div></header>
<main class="wrap">
  {% with msgs = get_flashed_messages(with_categories=true) %}
    {% for cat, m in msgs %}<div class="flash {{ cat }}" role="status">{{ m }}</div>{% endfor %}
  {% endwith %}
  {% block content %}{% endblock %}
</main>
<footer><div class="wrap">© {{ year }} {{ brand }} · <a href="mailto:{{ email }}">{{ email }}</a></div></footer>
</body></html>"""

HOME = """{% extends 'base.html' %}
{% block content %}
<section class="hero">
  <h1>Музыка, которая приходит волной.</h1>
  <p>Igal's Wave — студийная запись, живые выступления и продакшн для артистов и событий.</p>
  <div class="actions">
    <a class="btn" href="{{ url_for('contact') }}#booking">Забронировать</a>
    <a class="btn ghost" href="{{ url_for('music') }}">Слушать</a>
  </div>
  <svg class="wave" viewBox="0 0 600 120" preserveAspectRatio="none" aria-hidden="true">
    {% for i in range(40) %}
    <rect x="{{ i*15 }}" y="10" width="7" height="100" rx="3.5" style="animation-delay:-{{ (i*0.13)|round(2) }}s"/>
    {% endfor %}
  </svg>
</section>
<section>
  <h2>Чем мы занимаемся</h2>
  <div class="grid">
    {% for s in services %}<div class="card"><h3>{{ s }}</h3><p>Подробности и цена — по запросу в форме бронирования.</p></div>{% endfor %}
  </div>
</section>
{% endblock %}"""

ABOUT = """{% extends 'base.html' %}
{% block title %}О нас — {{ brand }}{% endblock %}
{% block content %}
<section>
  <h1>О нас</h1>
  <p>Igal's Wave — музыкальный проект и студия. Мы работаем с исполнителями, группами и организаторами событий: от первой демо-записи до готового релиза и выступления на сцене.</p>
  <p>Замените этот текст историей бренда: кто вы, какой у вас опыт и чем ваш звук отличается от других.</p>
</section>
<section>
  <div class="grid">
    <div class="card"><h3>Звук</h3><p>Живые инструменты и электроника в одном миксе.</p></div>
    <div class="card"><h3>Подход</h3><p>Работаем с вашей идеей, а не вместо неё.</p></div>
    <div class="card"><h3>Результат</h3><p>Готовые файлы для стриминга, видео и сцены.</p></div>
  </div>
</section>
{% endblock %}"""

MUSIC = """{% extends 'base.html' %}
{% block title %}Музыка — {{ brand }}{% endblock %}
{% block content %}
<section>
  <h1>Музыка</h1>
  <p>Последние работы. Нажмите на плеер, чтобы послушать.</p>
  {% for t in tracks %}
  <div class="track">
    <div><b>{{ t.title }}</b><br><small>{{ t.genre }} · {{ t.year }}</small></div>
    {% if t.available %}<audio controls preload="none" src="{{ url_for('static', filename='audio/' + t.file) }}"></audio>
    {% else %}<small>Аудио скоро появится.</small>{% endif %}
  </div>
  {% endfor %}
</section>
{% endblock %}"""

CONTACT = """{% extends 'base.html' %}
{% block title %}Контакты и бронирование — {{ brand }}{% endblock %}
{% block content %}
<section id="booking">
  <h1>Бронирование</h1>
  <p>Расскажите, что нужно, — ответим на почту в течение рабочего дня.</p>
  <form method="post" action="{{ url_for('book') }}">
    <div class="row">
      <label>Имя <input name="name" required maxlength="80" autocomplete="name" value="{{ f.name }}"></label>
      <label>Email <input type="email" name="email" required maxlength="120" autocomplete="email" value="{{ f.email }}"></label>
    </div>
    <div class="row">
      <label>Телефон (по желанию) <input type="tel" name="phone" maxlength="30" autocomplete="tel" value="{{ f.phone }}"></label>
      <label>Желаемая дата <input type="date" name="event_date" min="{{ today }}" required value="{{ f.event_date }}"></label>
    </div>
    <label>Услуга
      <select name="service" required>
        {% for s in services %}<option {% if f.service == s %}selected{% endif %}>{{ s }}</option>{% endfor %}
      </select>
    </label>
    <label>Сообщение <textarea name="message" maxlength="1500">{{ f.message }}</textarea></label>
    <input class="hp" name="website" tabindex="-1" autocomplete="off" aria-hidden="true">
    <button class="btn" type="submit">Отправить заявку</button>
  </form>
</section>
<section>
  <h2>Связаться напрямую</h2>
  <p>Email: <a href="mailto:{{ email }}">{{ email }}</a><br>Телефон: {{ phone }}</p>
</section>
{% endblock %}"""

ADMIN = """{% extends 'base.html' %}
{% block content %}<section><h1>Заявки</h1>
{% for b in rows %}<div class="track"><b>{{ b.name }} — {{ b.service }}</b>
<small>{{ b.created }} · {{ b.event_date }} · {{ b.email }} · {{ b.phone }}</small><span>{{ b.message }}</span></div>
{% else %}<p>Заявок пока нет.</p>{% endfor %}</section>{% endblock %}"""

app.jinja_loader = ChoiceLoader([DictLoader({
    "base.html": BASE, "home.html": HOME, "about.html": ABOUT,
    "music.html": MUSIC, "contact.html": CONTACT, "admin.html": ADMIN,
})])


@app.context_processor
def inject_globals():
    return dict(brand=BRAND, email=EMAIL, phone=PHONE, year=date.today().year, services=SERVICES)


# ---------- Маршруты ----------
@app.route("/")
def home():
    return render_template("home.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/music")
def music():
    base = os.path.join(app.static_folder, "audio")
    tracks = [dict(t, available=os.path.exists(os.path.join(base, t["file"]))) for t in TRACKS]
    return render_template("music.html", tracks=tracks)


@app.route("/contact")
def contact():
    empty = dict(name="", email="", phone="", event_date="", service="", message="")
    return render_template("contact.html", f=empty, today=date.today().isoformat())


@app.post("/book")
def book():
    f = {k: request.form.get(k, "").strip() for k in
         ("name", "email", "phone", "event_date", "service", "message", "website")}
    if f["website"]:  # honeypot: бот заполнил скрытое поле
        return redirect(url_for("contact"))
    errors = []
    if not f["name"]:
        errors.append("Укажите имя.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", f["email"]):
        errors.append("Проверьте адрес email.")
    if f["service"] not in SERVICES:
        errors.append("Выберите услугу из списка.")
    try:
        if date.fromisoformat(f["event_date"]) < date.today():
            errors.append("Дата должна быть сегодня или позже.")
    except ValueError:
        errors.append("Укажите дату.")
    if errors:
        for e in errors:
            flash(e, "error")
        return render_template("contact.html", f=f, today=date.today().isoformat()), 400
    with db() as con:
        con.execute(
            "INSERT INTO bookings (name,email,phone,service,event_date,message) VALUES (?,?,?,?,?,?)",
            (f["name"], f["email"], f["phone"], f["service"], f["event_date"], f["message"]),
        )
    flash("Заявка отправлена. Мы ответим на ваш email.", "ok")
    return redirect(url_for("contact"))


@app.route("/admin")
def admin():
    if request.args.get("key") != ADMIN_KEY:
        abort(404)
    with db() as con:
        rows = con.execute("SELECT * FROM bookings ORDER BY id DESC").fetchall()
    return render_template("admin.html", rows=rows)


init_db()

if __name__ == "__main__":
    app.run(debug=True)