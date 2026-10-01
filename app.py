import re
import sqlite3
import random
from datetime import datetime
from pathlib import Path

from flask import (Flask, render_template_string, request, session,
                   redirect, url_for, flash, abort, g)

app = Flask(__name__)
app.secret_key = "change-me-in-real-life"  # нужен для работы сессий
DB_PATH = Path(__file__).with_name("orders.db")

# ---------------------------------------------------------------- Данные
PRODUCTS = [
    {"id": 1, "name": "Ржаной на закваске", "cat": "Хлеб", "price": 280, "emoji": "🍞", "desc": "Плотный мякиш, хрустящая корка, тмин."},
    {"id": 2, "name": "Багет", "cat": "Хлеб", "price": 140, "emoji": "🥖", "desc": "Долгая ферментация, воздушный мякиш."},
    {"id": 3, "name": "Цельнозерновой", "cat": "Хлеб", "price": 260, "emoji": "🌾", "desc": "Мука грубого помола, семечки сверху."},
    {"id": 4, "name": "Круассан", "cat": "Выпечка", "price": 170, "emoji": "🥐", "desc": "Слоёный, на сливочном масле."},
    {"id": 5, "name": "Булочка с корицей", "cat": "Выпечка", "price": 150, "emoji": "🌀", "desc": "С корицей и сливочной глазурью."},
    {"id": 6, "name": "Крендель с солью", "cat": "Выпечка", "price": 120, "emoji": "🥨", "desc": "Тёмная корочка и крупная соль."},
    {"id": 7, "name": "Яблочный пирог", "cat": "Сладкое", "price": 320, "emoji": "🥧", "desc": "Яблоки, ваниль, песочное тесто."},
    {"id": 8, "name": "Шоколадный маффин", "cat": "Сладкое", "price": 160, "emoji": "🧁", "desc": "Тёмный шоколад внутри и сверху."},
    {"id": 9, "name": "Овсяное печенье", "cat": "Сладкое", "price": 90, "emoji": "🍪", "desc": "С изюмом, мягкое в центре."},
]
PRODUCTS_BY_ID = {p["id"]: p for p in PRODUCTS}
CATEGORIES = ["Все"] + sorted({p["cat"] for p in PRODUCTS}, key=lambda c: ["Хлеб", "Выпечка", "Сладкое"].index(c))
PICKUP_SLOTS = [f"{m // 60:02d}:{m % 60:02d}" for m in range(7 * 60, 12 * 60, 30)]

# Что печётся в какой час (для живого статуса печи)
OVEN_SCHEDULE = [
    (22, 24, "Хлеб на закваске"),
    (0, 2, "Ржаной и цельнозерновой"),
    (2, 4, "Круассаны"),
    (4, 6, "Багеты"),
    (6, 8, "Булочки с корицей"),
]


def oven_status():
    hour = datetime.now().hour
    for start, end, what in OVEN_SCHEDULE:
        if start <= hour < end:
            return {"active": True, "now": f"Сейчас в печи: {what}",
                    "next": f"Загрузка закончится в {end % 24:02d}:00"}
    return {"active": False, "now": "Печь отдыхает", "next": "Следующая загрузка — в 22:00"}


# ---------------------------------------------------------------- База данных
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                number INTEGER UNIQUE NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                pickup_time TEXT NOT NULL,
                items TEXT NOT NULL,
                total INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )""")


# ---------------------------------------------------------------- Корзина
def get_cart():
    """Корзина в сессии: {'id товара': количество}."""
    return session.setdefault("cart", {})


def cart_lines():
    lines = []
    for pid, qty in get_cart().items():
        product = PRODUCTS_BY_ID.get(int(pid))
        if product:
            lines.append({"product": product, "qty": qty, "sum": product["price"] * qty})
    return lines


def cart_total():
    return sum(line["sum"] for line in cart_lines())


def cart_count():
    return sum(get_cart().values())


@app.context_processor
def inject_globals():
    return {"cart_count": cart_count(), "money": lambda n: f"{n:,}".replace(",", " ") + " ₽"}


# ---------------------------------------------------------------- Страницы
@app.route("/")
def index():
    cat = request.args.get("cat", "Все")
    products = PRODUCTS if cat == "Все" else [p for p in PRODUCTS if p["cat"] == cat]
    return render_template_string(INDEX_TPL, products=products, categories=CATEGORIES,
                                  active_cat=cat, oven=oven_status())


@app.post("/add/<int:pid>")
def add(pid):
    if pid not in PRODUCTS_BY_ID:
        abort(404)
    cart = get_cart()
    cart[str(pid)] = cart.get(str(pid), 0) + 1
    session.modified = True
    flash(f"Добавлено: {PRODUCTS_BY_ID[pid]['name']}")
    return redirect(request.referrer or url_for("index"))


@app.get("/cart")
def cart_page():
    return render_template_string(CART_TPL, lines=cart_lines(), total=cart_total(),
                                  slots=PICKUP_SLOTS, form={}, errors={})


@app.post("/cart/<int:pid>/<action>")
def change_qty(pid, action):
    cart = get_cart()
    key = str(pid)
    if key in cart:
        if action == "inc":
            cart[key] += 1
        elif action == "dec":
            cart[key] -= 1
            if cart[key] <= 0:
                del cart[key]
        session.modified = True
    return redirect(url_for("cart_page"))


@app.post("/order")
def order():
    lines = cart_lines()
    if not lines:
        flash("Корзина пуста. Выберите что-нибудь в меню.")
        return redirect(url_for("index"))

    form = {k: request.form.get(k, "").strip() for k in ("name", "phone", "time")}
    errors = {}
    if len(form["name"]) < 2:
        errors["name"] = "Введите имя, чтобы мы подписали заказ."
    digits = re.sub(r"\D", "", form["phone"])
    if not 10 <= len(digits) <= 12:
        errors["phone"] = "Введите телефон, например +7 900 000-00-00."
    if form["time"] not in PICKUP_SLOTS:
        errors["time"] = "Выберите время из списка."

    if errors:
        return render_template_string(CART_TPL, lines=lines, total=cart_total(),
                                      slots=PICKUP_SLOTS, form=form, errors=errors), 400

    items_text = "; ".join(f"{l['product']['name']} × {l['qty']}" for l in lines)
    total = cart_total()
    db = get_db()
    while True:  # ищем свободный номер заказа
        number = random.randint(1000, 9999)
        if not db.execute("SELECT 1 FROM orders WHERE number = ?", (number,)).fetchone():
            break
    db.execute(
        "INSERT INTO orders (number, name, phone, pickup_time, items, total, created_at) VALUES (?,?,?,?,?,?,?)",
        (number, form["name"], form["phone"], form["time"], items_text, total,
         datetime.now().strftime("%Y-%m-%d %H:%M")))
    db.commit()
    session.pop("cart", None)
    return redirect(url_for("order_done", number=number))


@app.get("/order/<int:number>")
def order_done(number):
    row = get_db().execute("SELECT * FROM orders WHERE number = ?", (number,)).fetchone()
    if row is None:
        abort(404)
    return render_template_string(DONE_TPL, order=row)


@app.get("/admin")
def admin():
    # Внимание: у этой страницы нет пароля. В настоящем проекте её нужно защитить.
    rows = get_db().execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    return render_template_string(ADMIN_TPL, orders=rows)


@app.errorhandler(404)
def not_found(_e):
    return render_template_string(BASE_TPL.replace("{% block content %}{% endblock %}",
        '<section><div class="wrap"><h2>Страница не найдена</h2>'
        '<p class="sub">Проверьте адрес или вернитесь <a href="/">в меню</a>.</p></div></section>')), 404


# ---------------------------------------------------------------- Шаблоны
BASE_TPL = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ночная пекарня — хлеб к утру</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Onest:wght@400;500;700&family=Unbounded:wght@500;800&display=swap" rel="stylesheet">
<style>
  :root { --cobalt:#2340d9; --butter:#ffe27a; --flour:#fffdf7; --crust:#b5542b; --ink:#101a3d; --radius:14px; }
  * { box-sizing:border-box; margin:0; }
  body { font-family:"Onest",system-ui,sans-serif; background:var(--flour); color:var(--ink); line-height:1.55; font-size:17px; }
  h1,h2,h3 { font-family:"Unbounded","Onest",sans-serif; line-height:1.1; }
  button,input,select { font:inherit; color:inherit; }
  button { cursor:pointer; }
  a { color:var(--cobalt); }
  :focus-visible { outline:3px solid var(--butter); outline-offset:3px; }
  .wrap { max-width:1080px; margin:0 auto; padding:0 20px; }
  header.top { background:var(--cobalt); color:var(--flour); position:sticky; top:0; z-index:20; }
  header.top .wrap { display:flex; align-items:center; justify-content:space-between; height:64px; }
  .logo { font-family:"Unbounded",sans-serif; font-weight:800; font-size:18px; text-decoration:none; color:inherit; }
  nav { display:flex; align-items:center; gap:22px; }
  nav a { color:inherit; text-decoration:none; font-weight:500; }
  nav a.cart-btn { background:var(--butter); color:var(--ink); border-radius:999px; padding:9px 18px; font-weight:700; }
  .hero { background:var(--cobalt); color:var(--flour); padding:56px 0 72px; }
  .hero h1 { font-size:clamp(40px,9vw,104px); font-weight:800; letter-spacing:-.03em; max-width:9em; }
  .hero p.lead { max-width:34em; margin-top:22px; font-size:19px; opacity:.92; }
  .oven { margin-top:40px; display:inline-flex; align-items:center; gap:16px; background:var(--butter); color:var(--ink); border-radius:var(--radius); padding:16px 22px; }
  .oven .glow { width:14px; height:14px; border-radius:50%; background:var(--crust); flex:none; animation:pulse 1.8s ease-in-out infinite; }
  .oven.idle .glow { animation:none; background:#8a8f9f; }
  .oven b { display:block; } .oven small { opacity:.75; font-size:14px; }
  @keyframes pulse { 0%,100%{box-shadow:0 0 0 0 rgba(181,84,43,.6)} 50%{box-shadow:0 0 0 10px rgba(181,84,43,0)} }
  section { padding:64px 0; }
  section h2 { font-size:clamp(28px,5vw,44px); letter-spacing:-.02em; }
  .sub { margin-top:10px; max-width:36em; opacity:.8; }
  .chips { display:flex; flex-wrap:wrap; gap:10px; margin:28px 0 32px; }
  .chip { border:2px solid var(--ink); border-radius:999px; padding:7px 18px; font-weight:500; text-decoration:none; color:var(--ink); }
  .chip.on { background:var(--ink); color:var(--flour); }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:22px; }
  .item { border:2px solid var(--ink); border-radius:var(--radius); overflow:hidden; display:flex; flex-direction:column; background:#fff; }
  .item .pic { font-size:64px; text-align:center; padding:26px 0 18px; background:#ffe9b0; }
  .item .body { padding:0 18px 18px; display:flex; flex-direction:column; flex:1; }
  .item h3 { font-size:17px; font-weight:500; margin-top:16px; }
  .item p { font-size:15px; opacity:.75; margin:6px 0 16px; flex:1; }
  .row { display:flex; align-items:center; justify-content:space-between; gap:10px; }
  .price { font-weight:700; font-size:18px; }
  .btn { background:var(--cobalt); color:var(--flour); border:0; border-radius:10px; padding:9px 16px; font-weight:500; text-decoration:none; display:inline-block; }
  .btn:hover { background:var(--ink); }
  .btn.wide { width:100%; margin-top:18px; padding:14px; text-align:center; font-weight:700; border-radius:12px; }
  .flash { position:fixed; left:50%; bottom:24px; transform:translateX(-50%); background:var(--ink); color:var(--flour); padding:10px 20px; border-radius:999px; z-index:50; animation:fade 3s forwards; }
  @keyframes fade { 0%,75%{opacity:1} 100%{opacity:0; visibility:hidden} }
  .line { display:grid; grid-template-columns:1fr auto; gap:4px 16px; padding:14px 0; border-bottom:1px solid #d6d9e6; }
  .qty { display:inline-flex; align-items:center; gap:10px; margin-top:6px; }
  .qty form { display:inline; }
  .qty button { width:32px; height:32px; border-radius:8px; border:2px solid var(--ink); background:#fff; font-weight:700; }
  .total { display:flex; justify-content:space-between; font-weight:700; font-size:22px; margin:20px 0; }
  .cart-layout { display:grid; grid-template-columns:1.2fr 1fr; gap:48px; margin-top:28px; align-items:start; }
  form.order label { display:block; font-weight:500; margin-top:14px; font-size:15px; }
  form.order input, form.order select { width:100%; padding:11px 12px; margin-top:4px; border:2px solid var(--ink); border-radius:10px; background:#fff; }
  form.order .bad { border-color:#c0261d; }
  .err { color:#c0261d; font-size:14px; }
  .done { text-align:center; padding:40px 0; }
  .done .big { font-size:72px; }
  table { width:100%; border-collapse:collapse; margin-top:24px; font-size:15px; }
  th,td { text-align:left; padding:10px 8px; border-bottom:1px solid #d6d9e6; vertical-align:top; }
  footer { background:var(--cobalt); color:var(--flour); padding:32px 0; margin-top:40px; }
  footer .wrap { display:flex; flex-wrap:wrap; gap:12px 40px; justify-content:space-between; }
  @media (max-width:760px) { .cart-layout { grid-template-columns:1fr; gap:24px; } nav a.hide { display:none; } }
  @media (prefers-reduced-motion:reduce) { * { animation:none !important; } .flash { opacity:1; } }
</style>
</head>
<body>
<header class="top">
  <div class="wrap">
    <a class="logo" href="{{ url_for('index') }}">Ночная пекарня</a>
    <nav>
      <a class="hide" href="{{ url_for('index') }}#menu">Меню</a>
      <a class="cart-btn" href="{{ url_for('cart_page') }}">Корзина {{ cart_count }}</a>
    </nav>
  </div>
</header>
{% for msg in get_flashed_messages() %}<div class="flash" role="status">{{ msg }}</div>{% endfor %}
{% block content %}{% endblock %}
<footer>
  <div class="wrap">
    <div><b>Ночная пекарня</b><br>ул. Мельничная, 12</div>
    <div>Выдача заказов: 7:00–12:00<br>Телефон: +7 (900) 000-00-00</div>
  </div>
</footer>
</body>
</html>"""


def page(content):
    """Собирает страницу: подставляет содержимое в базовый шаблон."""
    return BASE_TPL.replace("{% block content %}{% endblock %}", content)


INDEX_TPL = page("""
<div class="hero"><div class="wrap">
  <h1>Хлеб, который пекли, пока вы спали</h1>
  <p class="lead">Печём ночью, отдаём с шести утра. Закажите сегодня, заберите завтра ещё тёплым.</p>
  <div class="oven {{ '' if oven.active else 'idle' }}" role="status">
    <i class="glow"></i><div><b>{{ oven.now }}</b><small>{{ oven.next }}</small></div>
  </div>
</div></div>
<section id="menu"><div class="wrap">
  <h2>Что сегодня пекут</h2>
  <p class="sub">Выберите, что хотите забрать утром. Цены за штуку.</p>
  <div class="chips">
    {% for c in categories %}
      <a class="chip {{ 'on' if c == active_cat }}" href="{{ url_for('index', cat=c) }}#menu">{{ c }}</a>
    {% endfor %}
  </div>
  <div class="grid">
    {% for p in products %}
    <article class="item">
      <div class="pic" aria-hidden="true">{{ p.emoji }}</div>
      <div class="body">
        <h3>{{ p.name }}</h3><p>{{ p.desc }}</p>
        <div class="row">
          <span class="price">{{ money(p.price) }}</span>
          <form method="post" action="{{ url_for('add', pid=p.id) }}"><button class="btn">В корзину</button></form>
        </div>
      </div>
    </article>
    {% endfor %}
  </div>
</div></section>
""")

CART_TPL = page("""
<section><div class="wrap">
  <h2>Ваш заказ</h2>
  {% if not lines %}
    <p class="sub">Корзина пуста. <a href="{{ url_for('index') }}#menu">Выберите что-нибудь в меню</a>.</p>
  {% else %}
  <div class="cart-layout">
    <div>
      {% for l in lines %}
      <div class="line">
        <div>
          <div>{{ l.product.name }}</div>
          <div class="qty">
            <form method="post" action="{{ url_for('change_qty', pid=l.product.id, action='dec') }}"><button aria-label="Убрать одну штуку">−</button></form>
            <span>{{ l.qty }}</span>
            <form method="post" action="{{ url_for('change_qty', pid=l.product.id, action='inc') }}"><button aria-label="Добавить ещё одну">+</button></form>
          </div>
        </div>
        <div class="price">{{ money(l.sum) }}</div>
      </div>
      {% endfor %}
      <div class="total"><span>Итого</span><span>{{ money(total) }}</span></div>
    </div>
    <form class="order" method="post" action="{{ url_for('order') }}" novalidate>
      <h3>Когда заберёте</h3>
      <label for="name">Имя</label>
      <input id="name" name="name" autocomplete="name" value="{{ form.get('name', '') }}" class="{{ 'bad' if errors.name }}">
      {% if errors.name %}<div class="err">{{ errors.name }}</div>{% endif %}
      <label for="phone">Телефон</label>
      <input id="phone" name="phone" type="tel" autocomplete="tel" placeholder="+7 900 000-00-00" value="{{ form.get('phone', '') }}" class="{{ 'bad' if errors.phone }}">
      {% if errors.phone %}<div class="err">{{ errors.phone }}</div>{% endif %}
      <label for="time">Время завтра</label>
      <select id="time" name="time">
        {% for s in slots %}<option value="{{ s }}" {{ 'selected' if form.get('time') == s }}>{{ s }}</option>{% endfor %}
      </select>
      {% if errors.time %}<div class="err">{{ errors.time }}</div>{% endif %}
      <button class="btn wide">Оформить заказ</button>
    </form>
  </div>
  {% endif %}
</div></section>
""")

DONE_TPL = page("""
<section><div class="wrap done">
  <div class="big">🥖</div>
  <h2>Заказ №{{ order.number }} принят</h2>
  <p class="sub" style="margin:12px auto">{{ order.name }}, ждём вас завтра в {{ order.pickup_time }}.<br>
  Сумма к оплате на месте: <b>{{ money(order.total) }}</b>.</p>
  <a class="btn wide" style="max-width:280px" href="{{ url_for('index') }}">Вернуться в меню</a>
</div></section>
""")

ADMIN_TPL = page("""
<section><div class="wrap">
  <h2>Все заказы</h2>
  {% if not orders %}
    <p class="sub">Пока заказов нет.</p>
  {% else %}
  <div style="overflow-x:auto">
  <table>
    <tr><th>№</th><th>Когда создан</th><th>Клиент</th><th>Телефон</th><th>Заберёт в</th><th>Состав</th><th>Сумма</th></tr>
    {% for o in orders %}
    <tr><td>{{ o.number }}</td><td>{{ o.created_at }}</td><td>{{ o.name }}</td><td>{{ o.phone }}</td>
        <td>{{ o.pickup_time }}</td><td>{{ o['items'] }}</td><td>{{ money(o.total) }}</td></tr>
    {% endfor %}
  </table>
  </div>
  {% endif %}
</div></section>
""")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)