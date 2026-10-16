from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from flask import Flask, flash, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "flagman.db"
app = Flask(__name__)
app.secret_key = "change-this-key-before-deployment"
app.jinja_env.globals["dish_image"] = lambda name: DISH_IMAGES.get(name, "https://images.unsplash.com/photo-1473093295043-cdd812d0e601?auto=format&fit=crop&w=900&q=85")


DISH_IMAGES = {
    "Паста с курицей": "https://images.unsplash.com/photo-1473093295043-cdd812d0e601?auto=format&fit=crop&w=900&q=85",
    "Томатная паста": "https://images.unsplash.com/photo-1551183053-bf91a1d81141?auto=format&fit=crop&w=900&q=85",
    "Салат с курицей": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?auto=format&fit=crop&w=900&q=85",
    "Грибной тост": "https://images.unsplash.com/photo-1525351484163-7529414344d8?auto=format&fit=crop&w=900&q=85",
    "Ризотто с грибами": "https://images.unsplash.com/photo-1476124369491-e7addf5db371?auto=format&fit=crop&w=900&q=85",
    "Крем-суп из грибов": "https://images.unsplash.com/photo-1547592180-85f173990554?auto=format&fit=crop&w=900&q=85",
    "Брускетта с томатами": "https://images.unsplash.com/photo-1572695157366-5e585ab2b69f?auto=format&fit=crop&w=900&q=85",
    "Салат с томатами и сыром": "https://images.unsplash.com/photo-1540420773420-3366772f4999?auto=format&fit=crop&w=900&q=85",
    "Паста в сливочном соусе": "https://images.unsplash.com/photo-1555949258-eb67b1ef0ec7?auto=format&fit=crop&w=900&q=85",
    "Куриное филе с грибами": "https://images.unsplash.com/photo-1532550907401-a500c9a57435?auto=format&fit=crop&w=900&q=85",
    "Тёплый салат с курицей": "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?auto=format&fit=crop&w=900&q=85",
    "Запечённая паста с сыром": "https://images.unsplash.com/photo-1576402187878-974f70c890e6?auto=format&fit=crop&w=900&q=85",
}


def connect_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db() -> None:
    with connect_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            unit TEXT NOT NULL DEFAULT 'г',
            low_stock REAL NOT NULL DEFAULT 500 CHECK(low_stock >= 0)
        );
        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_no TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_id INTEGER NOT NULL REFERENCES deliveries(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity REAL NOT NULL CHECK(quantity > 0),
            remaining REAL NOT NULL CHECK(remaining >= 0),
            received_on TEXT NOT NULL,
            expires_on TEXT NOT NULL,
            unit_cost REAL NOT NULL DEFAULT 0 CHECK(unit_cost >= 0),
            CHECK(expires_on >= received_on)
        );
        CREATE TABLE IF NOT EXISTS dishes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            price REAL NOT NULL DEFAULT 0 CHECK(price >= 0),
            cost REAL NOT NULL DEFAULT 0 CHECK(cost >= 0)
        );
        CREATE TABLE IF NOT EXISTS recipe_items (
            dish_id INTEGER NOT NULL REFERENCES dishes(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL REFERENCES products(id),
            quantity REAL NOT NULL CHECK(quantity > 0),
            PRIMARY KEY(dish_id, product_id)
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id),
            dish_id INTEGER NOT NULL REFERENCES dishes(id),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            unit_price REAL,
            unit_cost REAL
        );
        CREATE TABLE IF NOT EXISTS dish_price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dish_id INTEGER NOT NULL REFERENCES dishes(id),
            price REAL NOT NULL CHECK(price >= 0),
            cost REAL NOT NULL CHECK(cost >= 0),
            changed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS writeoffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id),
            batch_id INTEGER REFERENCES batches(id),
            quantity REAL NOT NULL CHECK(quantity > 0),
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS hot_offers_manual (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dish_id INTEGER NOT NULL REFERENCES dishes(id),
            mode TEXT NOT NULL CHECK(mode IN ('hide','pin')),
            note TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(dish_id, mode)
        );
        """)
        # Safe migrations for existing databases; preserve all current records.
        dish_cols = {r["name"] for r in db.execute("PRAGMA table_info(dishes)")}
        if "cost" not in dish_cols:
            db.execute("ALTER TABLE dishes ADD COLUMN cost REAL NOT NULL DEFAULT 0")
        order_item_cols = {r["name"] for r in db.execute("PRAGMA table_info(order_items)")}
        if "unit_price" not in order_item_cols:
            db.execute("ALTER TABLE order_items ADD COLUMN unit_price REAL")
        if "unit_cost" not in order_item_cols:
            db.execute("ALTER TABLE order_items ADD COLUMN unit_cost REAL")
        batch_cols = {r["name"] for r in db.execute("PRAGMA table_info(batches)")}
        if "unit_cost" not in batch_cols:
            db.execute("ALTER TABLE batches ADD COLUMN unit_cost REAL NOT NULL DEFAULT 0")
        # Legacy orders had no snapshots. Leave them NULL rather than invent history.


def seed_demo_data() -> None:
    """Create sample data only on a brand-new database, for a quick demo."""
    with connect_db() as db:
        if db.execute("SELECT COUNT(*) FROM products").fetchone()[0]:
            return
        products = [
            ("Куриное филе", "г", 800), ("Сливки", "мл", 500),
            ("Паста", "г", 1000), ("Томаты", "г", 600),
            ("Сыр", "г", 400), ("Листья салата", "г", 200),
            ("Хлеб", "г", 300), ("Грибы", "г", 300),
        ]
        db.executemany("INSERT INTO products(name, unit, low_stock) VALUES(?,?,?)", products)
        dishes = [("Паста с курицей", 590), ("Томатная паста", 420), ("Салат с курицей", 490), ("Грибной тост", 350)]
        db.executemany("INSERT INTO dishes(name, price) VALUES(?,?)", dishes)
        product_ids = {r["name"]: r["id"] for r in db.execute("SELECT id,name FROM products")}
        dish_ids = {r["name"]: r["id"] for r in db.execute("SELECT id,name FROM dishes")}
        recipes = {
            "Паста с курицей": [("Куриное филе", 180), ("Сливки", 80), ("Паста", 120), ("Сыр", 20)],
            "Томатная паста": [("Паста", 120), ("Томаты", 150), ("Сыр", 20)],
            "Салат с курицей": [("Куриное филе", 120), ("Листья салата", 80), ("Томаты", 100)],
            "Грибной тост": [("Грибы", 100), ("Хлеб", 70), ("Сыр", 25)],
        }
        for dish, items in recipes.items():
            db.executemany("INSERT INTO recipe_items(dish_id,product_id,quantity) VALUES(?,?,?)",
                           [(dish_ids[dish], product_ids[p], q) for p, q in items])


def ensure_extended_demo_menu() -> None:
    """Add a varied demo menu and any ingredients needed by its recipes.

    New ingredient records start with no stock: they become orderable only after
    a real delivery is received, so the demo menu never invents inventory.
    """
    with connect_db() as db:
        extra_products = [
            ("Лосось", "г", 800), ("Креветки", "г", 500), ("Говядина", "г", 800),
            ("Свинина", "г", 800), ("Картофель", "г", 1500), ("Рис", "г", 1000),
            ("Авокадо", "г", 400), ("Огурцы", "г", 500), ("Болгарский перец", "г", 500),
            ("Лимон", "г", 300), ("Чеснок", "г", 200), ("Фасоль", "г", 500),
            ("Яйца", "шт", 20), ("Мука", "г", 1000), ("Сахар", "г", 500),
            ("Ягоды", "г", 500), ("Тунец", "г", 500), ("Тортилья", "шт", 10),
            ("Молоко", "мл", 1000),
            ("Морковь", "г", 500), ("Лук", "г", 500), ("Кокосовое молоко", "мл", 500),
        ]
        db.executemany("INSERT OR IGNORE INTO products(name,unit,low_stock) VALUES(?,?,?)", extra_products)
        products = {r["name"]: r["id"] for r in db.execute("SELECT id,name FROM products")}
        extra = {
            "Ризотто с грибами": (640, [("Грибы", 120), ("Сыр", 35), ("Сливки", 40), ("Рис", 100)]),
            "Крем-суп из грибов": (390, [("Грибы", 150), ("Сливки", 80), ("Лук", 20)]),
            "Брускетта с томатами": (320, [("Хлеб", 90), ("Томаты", 100)]),
            "Салат с томатами и сыром": (430, [("Томаты", 140), ("Сыр", 50), ("Листья салата", 50)]),
            "Паста в сливочном соусе": (560, [("Паста", 130), ("Сливки", 90), ("Сыр", 15)]),
            "Куриное филе с грибами": (720, [("Куриное филе", 200), ("Грибы", 60), ("Сливки", 30)]),
            "Тёплый салат с курицей": (520, [("Куриное филе", 120), ("Листья салата", 70), ("Томаты", 80)]),
            "Запечённая паста с сыром": (590, [("Паста", 140), ("Сыр", 40), ("Томаты", 80)]),
            "Салат «Свежий сад»": (410, [("Листья салата", 90), ("Томаты", 120), ("Огурцы", 80)]),
            "Паста с грибами": (570, [("Паста", 130), ("Грибы", 100), ("Сливки", 40)]),
            "Тёплая паста с томатами": (510, [("Паста", 130), ("Томаты", 140), ("Чеснок", 5)]),
            "Лосось с лимоном и рисом": (890, [("Лосось", 180), ("Лимон", 15), ("Рис", 100)]),
            "Креветки с чесноком": (760, [("Креветки", 160), ("Чеснок", 8), ("Лимон", 10)]),
            "Боул с лососем и авокадо": (820, [("Лосось", 120), ("Авокадо", 70), ("Рис", 100), ("Огурцы", 50)]),
            "Говядина с картофелем": (790, [("Говядина", 180), ("Картофель", 200), ("Лук", 30)]),
            "Свинина с овощами": (720, [("Свинина", 170), ("Болгарский перец", 80), ("Морковь", 60), ("Лук", 25)]),
            "Картофель по-деревенски": (290, [("Картофель", 220), ("Чеснок", 5)]),
            "Рис с овощами": (350, [("Рис", 120), ("Морковь", 40), ("Болгарский перец", 50), ("Лук", 20)]),
            "Тако с говядиной": (640, [("Говядина", 120), ("Тортилья", 1), ("Томаты", 40), ("Листья салата", 20)]),
            "Тортилья с фасолью и овощами": (430, [("Тортилья", 1), ("Фасоль", 90), ("Болгарский перец", 50), ("Томаты", 40)]),
            "Салат с тунцом и огурцом": (550, [("Тунец", 120), ("Огурцы", 80), ("Листья салата", 50), ("Лимон", 8)]),
            "Креветки в кокосовом соусе": (790, [("Креветки", 150), ("Кокосовое молоко", 80), ("Рис", 80)]),
            "Омлет с томатами": (320, [("Яйца", 2), ("Томаты", 80)]),
            "Блинчики с ягодами": (360, [("Яйца", 1), ("Мука", 60), ("Молоко", 100), ("Ягоды", 60), ("Сахар", 10)]),
            "Ягодный десерт": (310, [("Ягоды", 120), ("Сахар", 10), ("Сливки", 30)]),
        }
        for name, (price, recipe) in extra.items():
            if any(product not in products for product, _ in recipe):
                continue
            row = db.execute("SELECT id FROM dishes WHERE name=?", (name,)).fetchone()
            if row:
                continue
            dish_id = db.execute("INSERT INTO dishes(name,price) VALUES(?,?)", (name, price)).lastrowid
            db.executemany("INSERT INTO recipe_items(dish_id,product_id,quantity) VALUES(?,?,?)",
                           [(dish_id, products[product], quantity) for product, quantity in recipe])
        product_ids = {r["name"]: r["id"] for r in db.execute("SELECT id,name FROM products")}
        existing_delivery = db.execute(
            "SELECT id FROM deliveries WHERE delivery_no=?", ("DEMO-001",)
        ).fetchone()
        if existing_delivery is None:
            delivery_id = db.execute("INSERT INTO deliveries(delivery_no,created_at) VALUES(?,?)",
                                     ("DEMO-001", datetime.now().isoformat(timespec="seconds"))).lastrowid
            initial = [("Куриное филе", 800, 2), ("Сливки", 500, 3), ("Паста", 1000, 5),
                       ("Томаты", 600, 4), ("Сыр", 400, 3), ("Листья салата", 200, 2),
                       ("Хлеб", 300, 2), ("Грибы", 300, 3)]
            for name, quantity, days in initial:
                if name not in product_ids:
                    continue
                db.execute("INSERT INTO batches(delivery_id,product_id,quantity,remaining,received_on,expires_on,unit_cost) VALUES(?,?,?,?,?,?,?)",
                           (delivery_id, product_ids[name], quantity, quantity, date.today().isoformat(),
                            (date.today() + timedelta(days=days)).isoformat(), 0))


def stock_by_product(db: sqlite3.Connection, as_of: date | None = None) -> dict[int, float]:
    as_of = as_of or date.today()
    rows = db.execute("SELECT product_id, SUM(remaining) AS total FROM batches WHERE expires_on >= ? GROUP BY product_id", (as_of.isoformat(),)).fetchall()
    return {r["product_id"]: float(r["total"] or 0) for r in rows}


def recipe_availability(db: sqlite3.Connection, dish_id: int, stock: dict[int, float] | None = None) -> dict[str, Any]:
    stock = stock if stock is not None else stock_by_product(db)
    ingredients = db.execute("""SELECT p.id, p.name, p.unit, ri.quantity
        FROM recipe_items ri JOIN products p ON p.id=ri.product_id WHERE ri.dish_id=? ORDER BY p.name""", (dish_id,)).fetchall()
    missing = []
    portions = None
    for item in ingredients:
        have = stock.get(item["id"], 0.0)
        needed = float(item["quantity"])
        possible = int(have // needed)
        portions = possible if portions is None else min(portions, possible)
        if have + 1e-9 < needed:
            missing.append({"name": item["name"], "need": needed, "have": have, "unit": item["unit"]})
    return {"available": bool(ingredients) and not missing, "ingredients": ingredients, "missing": missing,
            "portions": portions or 0, "has_recipe": bool(ingredients)}


def get_dashboard_data(db: sqlite3.Connection) -> dict[str, Any]:
    today = date.today()
    stock = stock_by_product(db, today)
    products = db.execute("SELECT * FROM products ORDER BY name").fetchall()
    stock_rows = []
    for product in products:
        total = stock.get(product["id"], 0.0)
        stock_rows.append({**dict(product), "stock": total, "low": total < product["low_stock"]})
    batches = db.execute("""SELECT b.*, p.name AS product_name, p.unit, d.delivery_no
        FROM batches b JOIN products p ON p.id=b.product_id JOIN deliveries d ON d.id=b.delivery_id
        WHERE b.remaining > 0 ORDER BY b.expires_on, p.name""").fetchall()
    batch_rows = []
    for batch in batches:
        days_left = (date.fromisoformat(batch["expires_on"]) - today).days
        batch_rows.append({**dict(batch), "days_left": days_left,
                           "state": "Просрочен" if days_left < 0 else "Скоро истекает" if days_left <= 3 else "В норме"})

    # --- Подробный список: что именно протухает и что уже просрочено ---
    expiring_soon: dict[tuple[str, str], dict[str, Any]] = {}
    expired_list: list[dict[str, Any]] = []
    for b in batch_rows:
        if b["days_left"] < 0:
            expired_list.append(b)
        elif b["days_left"] <= 3:
            key = (b["product_name"], b["unit"])
            agg = expiring_soon.setdefault(key, {
                "product": b["product_name"],
                "unit": b["unit"],
                "remaining": 0.0,
                "earliest": b["expires_on"],
                "days_left": b["days_left"],
                "batches": 0,
            })
            agg["remaining"] += float(b["remaining"])
            agg["batches"] += 1
            if b["expires_on"] < agg["earliest"]:
                agg["earliest"] = b["expires_on"]
                agg["days_left"] = b["days_left"]

    expiring_list = sorted(expiring_soon.values(), key=lambda x: (x["days_left"], x["product"]))
    expired_list.sort(key=lambda x: (x["days_left"], x["product_name"]))

    dishes = db.execute("SELECT * FROM dishes ORDER BY name").fetchall()
    dish_rows = []
    for dish in dishes:
        availability = recipe_availability(db, dish["id"], stock)
        dish_rows.append({**dict(dish), **availability})
    usage_rows = db.execute("""
        SELECT ri.product_id, SUM(oi.quantity * ri.quantity) AS used
        FROM orders o
        JOIN order_items oi ON oi.order_id=o.id
        JOIN recipe_items ri ON ri.dish_id=oi.dish_id
        WHERE o.status='Оформлен' AND datetime(o.created_at) >= datetime('now','-7 days')
        GROUP BY ri.product_id
    """).fetchall()
    usage_7d = {r['product_id']: float(r['used'] or 0) for r in usage_rows}
    has_usage_history = db.execute("SELECT COUNT(*) FROM orders WHERE status='Оформлен' AND datetime(created_at) >= datetime('now','-7 days')").fetchone()[0] > 0
    daily_usage = {pid: used / 7.0 for pid, used in usage_7d.items()}

    forecast = []
    for dish in dishes:
        availability = recipe_availability(db, dish['id'], stock)
        if not availability['has_recipe'] or not availability['available']:
            continue
        risks = []
        projected_missing = []
        for item in availability['ingredients']:
            product_id = item['id']
            have = stock.get(product_id, 0.0)
            per_day = daily_usage.get(product_id, 0.0)
            projected = max(0.0, have - per_day * 3)
            portions_now = int(have // float(item['quantity']))
            portions_3d = int(projected // float(item['quantity']))
            earliest = db.execute("SELECT MIN(expires_on) FROM batches WHERE product_id=? AND remaining>0 AND expires_on>=?", (product_id, today.isoformat())).fetchone()[0]
            days_to_expiry = (date.fromisoformat(earliest) - today).days if earliest else None
            if portions_3d < 1 or (days_to_expiry is not None and days_to_expiry <= 3 and have <= float(item['quantity']) * 2):
                risks.append(item['name'])
            if portions_3d < 1:
                projected_missing.append(item['name'])
        if risks:
            if has_usage_history:
                reason = 'Риск дефицита в ближайшие 3 дня: ' + ', '.join(risks)
                confidence = 'По расходу за 7 дней и срокам годности'
            else:
                reason = 'Низкий запас или близкий срок годности: ' + ', '.join(risks)
                confidence = 'Предварительный сигнал: ещё нет истории заказов'
            forecast.append({**dict(dish), 'reason': reason, 'confidence': confidence,
                             'portions_now': availability['portions'],
                             'projected_missing': projected_missing,
                             'risk_level': 'Высокий' if projected_missing else 'Средний'})
    forecast.sort(key=lambda item: (0 if item['risk_level']=='Высокий' else 1, item['portions_now'], item['name']))

    expiring_by_product = {}
    expiring_rows = db.execute("""
        SELECT product_id, SUM(remaining) AS qty, MIN(expires_on) AS first_expiry
        FROM batches WHERE remaining>0 AND expires_on>=? AND expires_on<=?
        GROUP BY product_id
    """, (today.isoformat(), (today + timedelta(days=7)).isoformat())).fetchall()
    for row in expiring_rows:
        expiring_by_product[row['product_id']] = {
            'quantity': float(row['qty'] or 0),
            'days': (date.fromisoformat(row['first_expiry']) - today).days
        }
    hot = []
    for dish in dishes:
        availability = recipe_availability(db, dish['id'], stock)
        if not availability['has_recipe'] or not availability['available']:
            continue
        candidates = []
        for item in availability['ingredients']:
            exp = expiring_by_product.get(item['id'])
            if not exp or exp['quantity'] <= 0:
                continue
            per_portion = float(item['quantity'])
            portions_using_expiring = int(exp['quantity'] // per_portion)
            portions_using_expiring = min(portions_using_expiring, availability['portions'])
            if portions_using_expiring <= 0:
                continue
            urgency = max(0.12, (8 - exp['days']) / 8)
            use_share = min(1.0, (portions_using_expiring * per_portion) / max(stock.get(item['id'], 0.0), 1.0))
            popularity = min(1.0, daily_usage.get(item['id'], 0.0) / max(per_portion, 1.0))
            score = urgency * 0.55 + use_share * 0.30 + popularity * 0.15
            candidates.append({'product': item['name'], 'days': exp['days'],
                               'portions': portions_using_expiring, 'score': score})
        if candidates:
            best = max(candidates, key=lambda x: x['score'])
            hot.append({**dict(dish), 'score': round(best['score'], 3),
                        'reason': f"{best['product']} — срок через {best['days']} дн.; можно использовать примерно в {best['portions']} порц.",
                        'portions': availability['portions'],
                        'use_expiring_portions': best['portions'],
                        'offer_product': best['product'],
                        'days_left': best['days'],
                        'confidence': 'Рецептура, доступный остаток и срок партии'})
    hot.sort(key=lambda item: (-item['score'], item['days_left'], item['name']))

    # --- Ручное управление горячими предложениями ---
    manual_rows = db.execute("""
        SELECT m.mode, m.note, d.id, d.name, d.price, d.cost
        FROM hot_offers_manual m
        JOIN dishes d ON d.id = m.dish_id
    """).fetchall()
    hide_ids = {r["id"] for r in manual_rows if r["mode"] == "hide"}
    pin_rows = [r for r in manual_rows if r["mode"] == "pin"]

    hot = [h for h in hot if h["id"] not in hide_ids]

    existing_hot_ids = {h["id"] for h in hot}
    for r in pin_rows:
        if r["id"] in existing_hot_ids:
            for h in hot:
                if h["id"] == r["id"]:
                    h["manual"] = True
                    h["reason"] = r["note"] or h.get("reason") or "Ручное предложение"
                    h["confidence"] = "Указано вручную"
            continue
        availability = recipe_availability(db, r["id"], stock)
        hot.append({
            **dict(r),
            "score": 1.0,
            "reason": r["note"] or "Ручное предложение",
            "portions": availability["portions"],
            "use_expiring_portions": availability["portions"],
            "offer_product": None,
            "days_left": 0,
            "confidence": "Указано вручную",
            "manual": True,
        })

    hot.sort(key=lambda item: (0 if item.get("manual") else 1, -item.get("score", 0), item["name"]))

    metrics = {
        "products": len(products), "low_stock": sum(1 for p in stock_rows if p["low"]),
        "expiring": sum(1 for b in batch_rows if 0 <= b["days_left"] <= 3),
        "expired": sum(1 for b in batch_rows if b["days_left"] < 0),
        "stop_list": sum(1 for d in dish_rows if not d["available"]),
        "orders_today": db.execute("SELECT COUNT(*) FROM orders WHERE date(created_at)=date('now','localtime') AND status='Оформлен'").fetchone()[0],
    }
    return {
        "metrics": metrics,
        "stock_rows": stock_rows,
        "batch_rows": batch_rows,
        "dishes": dish_rows,
        "hot": hot,
        "forecast": forecast,
        "has_usage_history": has_usage_history,
        "expiring_list": expiring_list,
        "expired_list": expired_list,
    }


def auto_write_off_expired() -> int:
    """Atomically write off remaining stock in batches past their expiry date.

    Expiry date is inclusive: a batch is expired from the day after expires_on.
    Remaining quantity is zeroed in the same transaction as the write-off record,
    so repeated requests cannot create duplicate write-offs for the same batch.
    """
    today = date.today().isoformat()
    count = 0
    with connect_db() as db:
        db.execute("BEGIN IMMEDIATE")
        expired = db.execute(
            "SELECT id,product_id,remaining FROM batches WHERE remaining>0 AND expires_on<? ORDER BY expires_on,id",
            (today,),
        ).fetchall()
        now = datetime.now().isoformat(timespec="seconds")
        for batch in expired:
            changed = db.execute("UPDATE batches SET remaining=0 WHERE id=? AND remaining>0", (batch["id"],)).rowcount
            if changed:
                db.execute(
                    "INSERT INTO writeoffs(product_id,batch_id,quantity,reason,created_at) VALUES(?,?,?,?,?)",
                    (batch["product_id"], batch["id"], batch["remaining"], "Автоматическое списание: истек срок годности", now),
                )
                count += 1
        db.commit()
    return count


@app.before_request
def run_expiry_automation():
    auto_write_off_expired()


@app.get("/")
def dashboard():
    with connect_db() as db:
        data = get_dashboard_data(db)
    return render_template("index.html", **data, today=date.today().isoformat())


@app.post("/deliveries")
def create_delivery():
    """Register a delivery; new product names are created on demand."""
    delivery_no = request.form.get("delivery_no", "").strip()
    names = request.form.getlist("product_name[]")
    units = request.form.getlist("unit[]")
    quantities = request.form.getlist("quantity[]")
    unit_costs = request.form.getlist("unit_cost[]")
    received_dates = request.form.getlist("received_on[]") or request.form.getlist("received_on")
    expiry_dates = request.form.getlist("expires_on[]") or request.form.getlist("expires_on")
    legacy_ids = request.form.getlist("product_id[]") or request.form.getlist("product_id")
    row_count = max(len(names), len(legacy_ids), len(quantities), len(expiry_dates), len(received_dates), 0)
    errors, items = [], []
    default_received_on = request.form.get("received_on", "").strip() or date.today().isoformat()
    allowed_units = {"г", "кг", "мл", "л", "шт", "упак."}
    if not delivery_no: errors.append("Укажи номер поставки.")
    if row_count == 0: errors.append("Добавь хотя бы один продукт в поставку.")
    for i in range(row_count):
        try:
            name = names[i].strip() if i < len(names) else ""
            legacy_id = legacy_ids[i].strip() if i < len(legacy_ids) else ""
            unit = units[i].strip() if i < len(units) else "г"
            quantity = float(quantities[i])
            unit_cost = float(unit_costs[i] or 0) if i < len(unit_costs) else 0.0
            if unit_cost < 0: raise ValueError("себестоимость закупки не может быть отрицательной")
            received_on = (received_dates[i].strip() if i < len(received_dates) else "") or default_received_on
            expires_on = expiry_dates[i].strip()
            received_date, expiry_date = date.fromisoformat(received_on), date.fromisoformat(expires_on)
            if not name and legacy_id:
                with connect_db() as lookup_db:
                    found = lookup_db.execute("SELECT name,unit FROM products WHERE id=?", (int(legacy_id),)).fetchone()
                if found: name, unit = found["name"], found["unit"]
            if not name: raise ValueError("введи название продукта")
            if unit not in allowed_units: raise ValueError("выбери единицу измерения из списка")
            if quantity <= 0: raise ValueError("количество должно быть больше нуля")
            if expiry_date < received_date: raise ValueError("срок годности не может быть раньше даты поступления")
            items.append((name, unit, quantity, received_on, expires_on, unit_cost))
        except (ValueError, IndexError, TypeError) as exc:
            errors.append(f"Строка {i + 1}: проверь название, количество, единицу измерения и даты. {exc}")
    if errors:
        flash(" ".join(errors), "error")
        return redirect(url_for("deliveries_page"))
    try:
        with connect_db() as db:
            db.execute("BEGIN IMMEDIATE")
            cur = db.execute("INSERT INTO deliveries(delivery_no,created_at) VALUES(?,?)",
                             (delivery_no, datetime.now().isoformat(timespec="seconds")))
            delivery_id = cur.lastrowid
            for name, unit, quantity, received_on, expires_on, unit_cost in items:
                product = db.execute("SELECT id,unit FROM products WHERE name=? COLLATE NOCASE", (name,)).fetchone()
                if product:
                    product_id = product["id"]
                    if product["unit"] != unit:
                        db.execute("UPDATE products SET unit=? WHERE id=?", (unit, product_id))
                else:
                    product_id = db.execute("INSERT INTO products(name,unit,low_stock) VALUES(?,?,?)",
                                            (name, unit, 1 if unit in {"шт", "упак."} else 500)).lastrowid
                db.execute("INSERT INTO batches(delivery_id,product_id,quantity,remaining,received_on,expires_on,unit_cost) VALUES(?,?,?,?,?,?,?)",
                           (delivery_id, product_id, quantity, quantity, received_on, expires_on, unit_cost))
        flash(f"Поставка {delivery_no} принята: добавлено позиций — {len(items)}. Новые названия автоматически добавлены в справочник.", "success")
    except sqlite3.IntegrityError as exc:
        if "delivery_no" in str(exc) or "UNIQUE constraint failed: deliveries.delivery_no" in str(exc):
            flash("Такой номер поставки уже существует. Укажи уникальный номер.", "error")
        else:
            flash("Поставка не сохранена: проверь данные строк. Изменения не применены.", "error")
    except sqlite3.Error:
        flash("Не удалось сохранить поставку. Изменения не применены; проверь журнал приложения.", "error")
    return redirect(url_for("deliveries_page"))


def _place_order(db: sqlite3.Connection, quantities: dict[int, int]) -> tuple[bool, str, int | None]:
    """Оформляет заказ в уже открытой транзакции.

    Возвращает (успех, сообщение, order_id).
    """
    today = date.today()
    stock = stock_by_product(db, today)
    requirements: dict[int, float] = {}
    failures: list[str] = []
    for dish_id, count in quantities.items():
        dish = db.execute("SELECT name FROM dishes WHERE id=?", (dish_id,)).fetchone()
        if not dish:
            failures.append("Обнаружено неизвестное блюдо.")
            continue
        recipe = db.execute("SELECT product_id, quantity FROM recipe_items WHERE dish_id=?", (dish_id,)).fetchall()
        if not recipe:
            failures.append(f"У блюда «{dish['name']}» не задан состав.")
            continue
        for item in recipe:
            requirements[item["product_id"]] = requirements.get(item["product_id"], 0) + float(item["quantity"]) * count
    for product_id, needed in requirements.items():
        product = db.execute("SELECT name, unit FROM products WHERE id=?", (product_id,)).fetchone()
        have = stock.get(product_id, 0.0)
        if have + 1e-9 < needed:
            failures.append(f"{product['name']}: нужно {needed:g} {product['unit']}, доступно {have:g} {product['unit']}.")
    if failures:
        return False, "Заказ не оформлен: " + " ".join(failures), None

    order_id = db.execute("INSERT INTO orders(created_at,status,note) VALUES(?,?,?)",
                          (datetime.now().isoformat(timespec="seconds"), "Оформлен", "")).lastrowid
    for dish_id, count in quantities.items():
        dish_prices = db.execute("SELECT price,cost FROM dishes WHERE id=?", (dish_id,)).fetchone()
        db.execute("INSERT INTO order_items(order_id,dish_id,quantity,unit_price,unit_cost) VALUES(?,?,?,?,?)",
                   (order_id, dish_id, count, float(dish_prices["price"]), float(dish_prices["cost"])))
    for product_id, needed in requirements.items():
        batches = db.execute("SELECT id,remaining FROM batches WHERE product_id=? AND remaining>0 AND expires_on>=? ORDER BY expires_on, received_on, id", (product_id, today.isoformat())).fetchall()
        for batch in batches:
            take = min(float(batch["remaining"]), needed)
            if take > 0:
                db.execute("UPDATE batches SET remaining=remaining-? WHERE id=?", (take, batch["id"]))
                needed -= take
                if needed <= 1e-9:
                    break
    return True, f"Заказ №{order_id} оформлен. Остатки списаны по ближайшему сроку годности.", order_id


@app.post("/orders")
def create_order():
    quantities: dict[int, int] = {}
    for key, value in request.form.items():
        if key.startswith("dish_"):
            try:
                dish_id = int(key.removeprefix("dish_"))
                quantity = int(value or 0)
            except ValueError:
                continue
            if quantity > 0:
                quantities[dish_id] = quantity
    if not quantities:
        flash("Выбери хотя бы одно блюдо и укажи количество.", "error")
        return redirect(url_for("dashboard"))
    db = connect_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        ok, message, _ = _place_order(db, quantities)
        if not ok:
            db.rollback()
            flash(message, "error")
        else:
            db.commit()
            flash(message, "success")
    except sqlite3.Error:
        db.rollback()
        flash("Не удалось оформить заказ из-за ошибки базы данных. Остатки не изменены.", "error")
    finally:
        db.close()
    return redirect(url_for("dashboard"))


# ============ ОФИЦИАНТ ============

@app.route("/waiter", methods=["GET", "POST"])
def waiter_page():
    """Отдельный интерфейс официанта: без сайдбара, крупные кнопки."""
    if request.method == "POST":
        quantities: dict[int, int] = {}
        for key, value in request.form.items():
            if key.startswith("dish_"):
                try:
                    dish_id = int(key.removeprefix("dish_"))
                    quantity = int(value or 0)
                except ValueError:
                    continue
                if quantity > 0:
                    quantities[dish_id] = quantity
        if not quantities:
            flash("Добавь хотя бы одно блюдо в заказ.", "error")
            return redirect(url_for("waiter_page"))
        db = connect_db()
        try:
            db.execute("BEGIN IMMEDIATE")
            ok, message, _ = _place_order(db, quantities)
            if not ok:
                db.rollback()
                flash(message, "error")
            else:
                db.commit()
                flash(message, "success")
        except sqlite3.Error:
            db.rollback()
            flash("Ошибка базы данных. Заказ не оформлен.", "error")
        finally:
            db.close()
        return redirect(url_for("waiter_page"))

    with connect_db() as db:
        data = get_dashboard_data(db)
    hot_names = {h["name"] for h in data["hot"]}
    data["dishes"] = sorted(
        data["dishes"],
        key=lambda d: (d["name"] not in hot_names, d["name"]),
    )
    return render_template(
        "waiter.html",
        **data,
        hot_lookup={h["name"]: h for h in data["hot"]},
        today=date.today().isoformat(),
    )

# ============ РУЧНОЕ УПРАВЛЕНИЕ ГОРЯЧИМИ ПРЕДЛОЖЕНИЯМИ ============

@app.post("/hot-offers/hide")
def hot_offer_hide():
    dish_id = request.form.get("dish_id", type=int)
    note = request.form.get("note", "").strip()
    if not dish_id:
        flash("Не указано блюдо.", "error")
        return redirect(request.referrer or url_for("menu_page"))
    with connect_db() as db:
        db.execute("INSERT OR REPLACE INTO hot_offers_manual(dish_id, mode, note, created_at) VALUES(?, 'hide', ?, ?)",
                   (dish_id, note, datetime.now().isoformat(timespec="seconds")))
    flash("Блюдо скрыто из горячих предложений.", "success")
    return redirect(request.referrer or url_for("menu_page"))


@app.post("/hot-offers/pin")
def hot_offer_pin():
    dish_id = request.form.get("dish_id", type=int)
    note = request.form.get("note", "").strip() or "Ручное предложение"
    if not dish_id:
        flash("Не указано блюдо.", "error")
        return redirect(request.referrer or url_for("menu_page"))
    with connect_db() as db:
        db.execute("INSERT OR REPLACE INTO hot_offers_manual(dish_id, mode, note, created_at) VALUES(?, 'pin', ?, ?)",
                   (dish_id, note, datetime.now().isoformat(timespec="seconds")))
    flash("Блюдо добавлено в горячие предложения вручную.", "success")
    return redirect(request.referrer or url_for("menu_page"))


@app.post("/hot-offers/reset")
def hot_offer_reset():
    dish_id = request.form.get("dish_id", type=int)
    if not dish_id:
        flash("Не указано блюдо.", "error")
        return redirect(request.referrer or url_for("menu_page"))
    with connect_db() as db:
        db.execute("DELETE FROM hot_offers_manual WHERE dish_id=?", (dish_id,))
    flash("Ручное правило снято. Действует автоматический расчёт.", "success")
    return redirect(request.referrer or url_for("menu_page"))


@app.post("/writeoffs/expired")
def write_off_expired():
    count = auto_write_off_expired()
    flash(f"Списано просроченных партий: {count}.", "success")
    return redirect(url_for("dashboard"))


@app.post("/products")
def create_product():
    name = request.form.get("name", "").strip()
    unit = request.form.get("unit", "г").strip() or "г"
    low_stock = request.form.get("low_stock", type=float)
    if not name or low_stock is None or low_stock < 0:
        flash("Укажи название продукта и неотрицательный порог остатка.", "error")
        return redirect(url_for("dashboard"))
    try:
        with connect_db() as db:
            db.execute("INSERT INTO products(name,unit,low_stock) VALUES(?,?,?)", (name, unit, low_stock))
        flash("Продукт добавлен.", "success")
    except sqlite3.IntegrityError:
        flash("Продукт с таким названием уже есть.", "error")
    return redirect(url_for("dashboard"))


@app.get("/analytics")
def analytics():
    period = request.args.get("period", "30")
    if period not in {"7", "30", "90"}: period = "30"
    days = int(period)
    today = date.today()
    start = today - timedelta(days=days - 1)
    start_iso, end_iso = start.isoformat(), today.isoformat()
    with connect_db() as db:
        summary = db.execute("""
          SELECT COUNT(DISTINCT o.id) orders_count, COALESCE(SUM(oi.quantity),0) portions,
                 COALESCE(SUM(oi.quantity*COALESCE(oi.unit_price,d.price)),0) revenue
          FROM orders o LEFT JOIN order_items oi ON oi.order_id=o.id
          LEFT JOIN dishes d ON d.id=oi.dish_id
          WHERE o.status='Оформлен' AND date(o.created_at) BETWEEN ? AND ?
        """,(start_iso,end_iso)).fetchone()
        daily = db.execute("""
          SELECT date(o.created_at) day, COUNT(DISTINCT o.id) orders_count,
                 COALESCE(SUM(oi.quantity),0) portions
          FROM orders o LEFT JOIN order_items oi ON oi.order_id=o.id
          WHERE o.status='Оформлен' AND date(o.created_at) BETWEEN ? AND ?
          GROUP BY date(o.created_at)
        """,(start_iso,end_iso)).fetchall()
        top = db.execute("""
          SELECT d.name, SUM(oi.quantity) portions, SUM(oi.quantity*COALESCE(oi.unit_price,d.price)) revenue
          FROM order_items oi JOIN orders o ON o.id=oi.order_id JOIN dishes d ON d.id=oi.dish_id
          WHERE o.status='Оформлен' AND date(o.created_at) BETWEEN ? AND ?
          GROUP BY d.id ORDER BY portions DESC LIMIT 8
        """,(start_iso,end_iso)).fetchall()
        writeoffs = db.execute("""
          SELECT p.name,p.unit,SUM(w.quantity) quantity,COUNT(w.id) events
          FROM writeoffs w JOIN products p ON p.id=w.product_id
          WHERE date(w.created_at) BETWEEN ? AND ?
          GROUP BY p.id ORDER BY quantity DESC LIMIT 10
        """,(start_iso,end_iso)).fetchall()
        wo_summary = db.execute("SELECT COUNT(*) events,COALESCE(SUM(quantity),0) quantity FROM writeoffs WHERE date(created_at) BETWEEN ? AND ?",(start_iso,end_iso)).fetchone()
        stock = stock_by_product(db,today)
        low = []
        for p in db.execute("SELECT id,name,unit,low_stock FROM products ORDER BY name").fetchall():
            qty = stock.get(p["id"],0.0)
            if qty < float(p["low_stock"]):
                low.append({"name":p["name"],"unit":p["unit"],"stock":qty,"threshold":float(p["low_stock"]),"shortage":float(p["low_stock"])-qty})
        low.sort(key=lambda x:(-x["shortage"],x["name"]))
        expiry = db.execute("""SELECT
          SUM(CASE WHEN expires_on < ? THEN 1 ELSE 0 END) expired,
          SUM(CASE WHEN expires_on >= ? AND expires_on <= ? THEN 1 ELSE 0 END) next3,
          SUM(CASE WHEN expires_on > ? AND expires_on <= ? THEN 1 ELSE 0 END) next7
          FROM batches WHERE remaining>0""",(end_iso,end_iso,(today+timedelta(days=3)).isoformat(),(today+timedelta(days=3)).isoformat(),(today+timedelta(days=7)).isoformat())).fetchone()
    day_map = {r["day"]:dict(r) for r in daily}
    chart = []
    cur = start
    while cur <= today:
        r = day_map.get(cur.isoformat(),{})
        chart.append({"day":cur.strftime("%d.%m"),"orders":int(r.get("orders_count",0) or 0),"portions":int(r.get("portions",0) or 0)})
        cur += timedelta(days=1)
    return render_template("analytics.html", period=period, start_day=start_iso, end_day=end_iso,
        summary=dict(summary), writeoff_summary=dict(wo_summary), daily_chart=chart,
        top_dishes=[dict(r) for r in top], writeoff_rows=[dict(r) for r in writeoffs],
        low_stock_rows=low, expiry_counts=dict(expiry))


@app.get("/deliveries")
def deliveries_page():
    with connect_db() as db:
        data = get_dashboard_data(db)
        rows = [dict(r) for r in db.execute("""SELECT d.id,d.delivery_no,d.created_at,COUNT(b.id) positions,
            COALESCE(SUM(b.quantity),0) total FROM deliveries d LEFT JOIN batches b ON b.delivery_id=d.id
            GROUP BY d.id ORDER BY d.id DESC LIMIT 100""").fetchall()]
    return render_template("section.html", page="deliveries", title="Поставки", subtitle="История поступлений и регистрация новых партий.", today=date.today().isoformat(), deliveries=rows, **data)


@app.get("/orders-page")
def orders_page():
    with connect_db() as db:
        data = get_dashboard_data(db)
        rows = [dict(r) for r in db.execute("""SELECT o.id,o.created_at,o.status,COALESCE(SUM(oi.quantity),0) portions,
            GROUP_CONCAT(d.name, ', ') dishes FROM orders o LEFT JOIN order_items oi ON oi.order_id=o.id
            LEFT JOIN dishes d ON d.id=oi.dish_id GROUP BY o.id ORDER BY o.id DESC LIMIT 100""").fetchall()]
    return render_template("section.html", page="orders", title="Заказы",
                           subtitle="Оформление заказов и история операций.",
                           today=date.today().isoformat(),
                           order_rows=rows,
                           hot_lookup={h["name"]: h for h in data["hot"]},
                           **data)


@app.get("/stock")
def stock_page():
    with connect_db() as db: data = get_dashboard_data(db)
    return render_template("section.html", page="stock", title="Склад", subtitle="Остатки продуктов, партии и сроки годности.", today=date.today().isoformat(), **data)


@app.route("/menu", methods=["GET", "POST"])
def menu_page():
    if request.method == "POST" and request.form.get("action") == "create_dish":
        name = request.form.get("new_dish_name", "").strip()
        try:
            price = float(request.form.get("new_dish_price", ""))
            cost = float(request.form.get("new_dish_cost", ""))
        except (ValueError, TypeError):
            flash("Укажи корректные цену и себестоимость нового блюда.", "error")
            return redirect(url_for("menu_page"))
        product_ids = request.form.getlist("ingredient_product_id[]")
        ingredient_names = request.form.getlist("ingredient_name[]")
        ingredient_units = request.form.getlist("ingredient_unit[]")
        quantities = request.form.getlist("ingredient_quantity[]")
        recipe_specs = []
        try:
            count = max(len(product_ids), len(ingredient_names), len(ingredient_units), len(quantities))
            for i in range(count):
                product_id = product_ids[i].strip() if i < len(product_ids) else ""
                ingredient_name = ingredient_names[i].strip() if i < len(ingredient_names) else ""
                unit = ingredient_units[i].strip() if i < len(ingredient_units) else "г"
                quantity = quantities[i].strip() if i < len(quantities) else ""
                if not product_id and not ingredient_name and not quantity:
                    continue
                qty = float(quantity)
                if qty <= 0 or (not product_id and not ingredient_name):
                    raise ValueError
                if unit not in {"г", "кг", "мл", "л", "шт", "упак."}:
                    unit = "г"
                recipe_specs.append((product_id, ingredient_name, unit, qty))
        except (ValueError, TypeError):
            flash("Для каждого ингредиента укажи продукт (из списка или вручную) и количество больше нуля.", "error")
            return redirect(url_for("menu_page"))
        if not recipe_specs:
            flash("Добавь хотя бы один ингредиент в рецептуру.", "error")
            return redirect(url_for("menu_page"))
        if not name or price < 0 or cost < 0 or not recipe_specs:
            flash("Для нового блюда нужны название, цена, себестоимость и хотя бы один ингредиент с количеством.", "error")
            return redirect(url_for("menu_page"))
        with connect_db() as db:
            try:
                recipe = []
                for product_id, ingredient_name, unit, qty in recipe_specs:
                    if product_id:
                        product = db.execute("SELECT id FROM products WHERE id=?", (int(product_id),)).fetchone()
                        if not product:
                            raise ValueError("unknown product")
                        pid = int(product["id"])
                    else:
                        product = db.execute("SELECT id FROM products WHERE name=? COLLATE NOCASE", (ingredient_name,)).fetchone()
                        if product:
                            pid = int(product["id"])
                        else:
                            pid = db.execute("INSERT INTO products(name,unit,low_stock) VALUES(?,?,?)",
                                             (ingredient_name, unit, 500)).lastrowid
                    if any(existing_pid == pid for existing_pid, _ in recipe):
                        raise ValueError("duplicate ingredient")
                    recipe.append((pid, qty))
                cur = db.execute("INSERT INTO dishes(name,price,cost) VALUES(?,?,?)", (name, price, cost))
                dish_id = cur.lastrowid
                db.executemany("INSERT INTO recipe_items(dish_id,product_id,quantity) VALUES(?,?,?)",
                               [(dish_id, pid, qty) for pid, qty in recipe])
                db.execute("INSERT INTO dish_price_history(dish_id,price,cost,changed_at) VALUES(?,?,?,?)",
                           (dish_id, price, cost, datetime.now().isoformat(timespec="seconds")))
                flash("Блюдо добавлено в меню вместе с рецептурой.", "success")
            except ValueError as exc:
                flash("Проверь рецептуру: продукты должны существовать, а один ингредиент нельзя добавлять дважды.", "error")
                return redirect(url_for("menu_page"))
            except sqlite3.IntegrityError:
                flash("Блюдо с таким названием уже существует или данные рецептуры некорректны.", "error")
                return redirect(url_for("menu_page"))
        return redirect(url_for("menu_page"))
    if request.method == "POST":
        try:
            dish_id = int(request.form.get("dish_id", ""))
            new_price = float(request.form.get("price", ""))
            new_cost = float(request.form.get("cost", ""))
            if new_price < 0 or new_cost < 0:
                raise ValueError
        except (ValueError, TypeError):
            flash("Укажи корректные неотрицательные значения цены и себестоимости.", "error")
            return redirect(url_for("menu_page"))
        with connect_db() as db:
            dish = db.execute("SELECT id,price,cost FROM dishes WHERE id=?", (dish_id,)).fetchone()
            if not dish:
                flash("Блюдо не найдено.", "error")
                return redirect(url_for("menu_page"))
            old_price, old_cost = float(dish["price"]), float(dish["cost"] or 0)
            if old_price != new_price or old_cost != new_cost:
                db.execute("INSERT INTO dish_price_history(dish_id,price,cost,changed_at) VALUES(?,?,?,?)",
                           (dish_id, new_price, new_cost, datetime.now().isoformat(timespec="seconds")))
                db.execute("UPDATE dishes SET price=?,cost=? WHERE id=?", (new_price,new_cost,dish_id))
                flash("Цена и себестоимость обновлены. Новые значения будут сохраняться в следующих заказах.", "success")
            else:
                flash("Изменений нет.", "success")
        return redirect(url_for("menu_page"))
    with connect_db() as db:
        data = get_dashboard_data(db)
        for dish in data["dishes"]:
            current_cost = float(dish.get("cost") or 0)
            if current_cost <= 0:
                recipe_rows = db.execute("""SELECT ri.quantity, p.id product_id,
                    (SELECT b.unit_cost FROM batches b WHERE b.product_id=p.id AND b.unit_cost>0
                     ORDER BY b.received_on DESC,b.id DESC LIMIT 1) unit_cost
                    FROM recipe_items ri JOIN products p ON p.id=ri.product_id WHERE ri.dish_id=?""", (dish["id"],)).fetchall()
                if recipe_rows and all(r["unit_cost"] is not None for r in recipe_rows):
                    estimated_cost = sum(float(r["quantity"]) * float(r["unit_cost"]) for r in recipe_rows)
                    cost_source = "по закупочным ценам ингредиентов"
                else:
                    estimated_cost = round(float(dish["price"]) * 0.30, 2)
                    cost_source = "предварительная оценка 30% цены — уточни по рецептуре"
                db.execute("UPDATE dishes SET cost=? WHERE id=?", (estimated_cost, dish["id"]))
                dish["cost"] = estimated_cost
                dish["cost_source"] = cost_source
            else:
                dish["cost_source"] = "сохранённое значение"
        price_history = [dict(r) for r in db.execute("""SELECT h.changed_at,d.name,h.price,h.cost
            FROM dish_price_history h JOIN dishes d ON d.id=h.dish_id ORDER BY h.id DESC LIMIT 50""").fetchall()]
    return render_template("section.html", page="menu", title="Меню ресторана",
                           subtitle="Управление блюдами, рецептурами, ценами и себестоимостью.",
                           today=date.today().isoformat(),
                           price_history=price_history,
                           hot_lookup={h["name"]: h for h in data["hot"]},
                           **data)


@app.get("/forecasts")
def forecasts_page():
    with connect_db() as db: data = get_dashboard_data(db)
    return render_template("section.html", page="forecasts", title="Прогнозы", subtitle="Риски стоп-листа и блюда для использования продуктов с коротким сроком годности.", today=date.today().isoformat(), **data)


@app.get("/warehouse-dashboard")
def warehouse_dashboard():
    with connect_db() as db:
        data = get_dashboard_data(db)
        total_value = db.execute("SELECT COALESCE(SUM(b.remaining*b.unit_cost),0) FROM batches b WHERE b.expires_on>=?", (date.today().isoformat(),)).fetchone()[0]
        purchased_cost_rows = db.execute("""SELECT p.name,p.unit,COALESCE(SUM(CASE WHEN b.expires_on>=? THEN b.remaining ELSE 0 END),0) stock,
            p.low_stock,COALESCE(MAX(CASE WHEN b.unit_cost>0 THEN b.unit_cost END),0) unit_cost
            FROM products p LEFT JOIN batches b ON b.product_id=p.id GROUP BY p.id ORDER BY stock ASC""", (date.today().isoformat(),)).fetchall()
        stock_chart = [dict(r) for r in purchased_cost_rows[:12]]
        expiry = db.execute("""SELECT SUM(CASE WHEN expires_on<? AND remaining>0 THEN 1 ELSE 0 END) expired,
            SUM(CASE WHEN expires_on>=? AND expires_on<=? AND remaining>0 THEN 1 ELSE 0 END) soon,
            SUM(CASE WHEN expires_on>? AND remaining>0 THEN 1 ELSE 0 END) good
            FROM batches""", (date.today().isoformat(), date.today().isoformat(), (date.today()+timedelta(days=3)).isoformat(), (date.today()+timedelta(days=3)).isoformat())).fetchone()
        recent = [dict(r) for r in db.execute("SELECT created_at,delivery_no FROM deliveries ORDER BY id DESC LIMIT 6").fetchall()]
    total_units = sum(max(0,float(r["stock"])) for r in stock_chart)
    return render_template("warehouse_dashboard.html", page="warehouse_dashboard", title="Дашборд склада", today=date.today().isoformat(),
        metrics=data["metrics"], stock_chart=stock_chart, total_value=float(total_value or 0), expiry=dict(expiry), recent=recent,
        total_units=total_units, expiring_list=data["expiring_list"], expired_list=data["expired_list"],
        subtitle="Состояние запасов, сроки годности и стоимость складских остатков.")


@app.get("/api/status")
def api_status():
    """Small JSON endpoint for integrations and live dashboard refresh."""
    with connect_db() as db:
        data = get_dashboard_data(db)
    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "metrics": data["metrics"],
        "stop_list": [d["name"] for d in data["dishes"] if not d["available"]],
        "hot_offers": [
            {
                "name": d["name"],
                "score": d["score"],
                "reason": d["reason"],
                "portions": d.get("use_expiring_portions", d.get("portions", 0)),
                "manual": bool(d.get("manual")),
            }
            for d in data["hot"]
        ],
        "stop_list_forecast": [
            {"name": d["name"], "risk_level": d["risk_level"], "reason": d["reason"]}
            for d in data["forecast"]
        ],
        "expiring": data["expiring_list"],
        "expired": data["expired_list"],
    }


with app.app_context():
    init_db()
    seed_demo_data()
    ensure_extended_demo_menu()


if __name__ == "__main__":
    app.run(debug=True)