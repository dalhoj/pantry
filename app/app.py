import os
import re
import sqlite3
import uuid
from datetime import date, datetime
from urllib.parse import urlparse

import requests
import pytesseract
from flask import Flask, flash, redirect, render_template, request, send_from_directory, url_for
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pyzbar.pyzbar import decode as decode_barcode
from werkzeug.utils import secure_filename

DATA_DIR = os.getenv("PANTRY_DATA_DIR", "/data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "pantry.db")
OFF_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}

os.makedirs(UPLOAD_DIR, exist_ok=True)
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me")
app.config["MAX_CONTENT_LENGTH"] = 24 * 1024 * 1024


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with db() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT,
                location TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity >= 0),
                expiry DATE,
                image TEXT,
                created_at TEXT NOT NULL
            )
        """)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(items)")}
        for name, definition in {
            "barcode": "TEXT",
            "brand": "TEXT",
            "scan_confidence": "INTEGER DEFAULT 0"
        }.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE items ADD COLUMN {name} {definition}")


init_db()


def days_left(expiry):
    if not expiry:
        return None
    try:
        return (datetime.strptime(expiry, "%Y-%m-%d").date() - date.today()).days
    except ValueError:
        return None


def save_upload(file_storage, prefix="item"):
    if not file_storage or not file_storage.filename:
        return None, None
    extension = os.path.splitext(secure_filename(file_storage.filename))[1].lower() or ".jpg"
    if extension not in ALLOWED_EXTENSIONS:
        extension = ".jpg"
    filename = f"{prefix}-{uuid.uuid4().hex}{extension}"
    output_path = os.path.join(UPLOAD_DIR, filename)
    file_storage.save(output_path)
    try:
        with Image.open(output_path) as image:
            image.thumbnail((1800, 1800))
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
                filename = f"{prefix}-{uuid.uuid4().hex}.jpg"
                output_path = os.path.join(UPLOAD_DIR, filename)
                image.save(output_path, "JPEG", quality=90)
            else:
                image.save(output_path)
    except Exception:
        pass
    return filename, output_path


def scan_barcode(image_paths):
    for image_path in image_paths:
        if not image_path:
            continue
        try:
            with Image.open(image_path) as image:
                variants = [image.convert("RGB"), ImageOps.grayscale(image)]
                for variant in variants:
                    codes = decode_barcode(variant)
                    if codes:
                        value = codes[0].data.decode("utf-8", errors="ignore").strip()
                        if value:
                            return value
        except Exception:
            continue
    return ""


def lookup_product(barcode):
    if not barcode:
        return {}
    try:
        response = requests.get(
            OFF_URL.format(barcode=barcode),
            params={"fields": "product_name,product_name_da,brands,categories,categories_tags,image_front_url"},
            headers={"User-Agent": "Pantry/0.2 (github.com/dalhoj/pantry)"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != 1:
            return {}
        product = payload.get("product", {})
        categories = product.get("categories", "")
        category = categories.split(",")[0].strip() if categories else ""
        return {
            "name": product.get("product_name_da") or product.get("product_name") or "",
            "brand": product.get("brands") or "",
            "category": category,
            "remote_image": product.get("image_front_url") or "",
        }
    except (requests.RequestException, ValueError):
        return {}


def normalize_year(year):
    year = int(year)
    if year < 100:
        return 2000 + year if year <= 79 else 1900 + year
    return year


def valid_future_date(day, month, year):
    try:
        candidate = date(normalize_year(year), int(month), int(day))
    except ValueError:
        return None
    delta = (candidate - date.today()).days
    if -365 <= delta <= 3650:
        return candidate.isoformat()
    return None


def parse_dates(text):
    candidates = []
    patterns = [
        r"(?<!\d)(\d{1,2})[.\-/ ](\d{1,2})[.\-/ ](\d{2,4})(?!\d)",
        r"(?<!\d)(\d{2})(\d{2})(\d{2,4})(?!\d)",
    ]
    for pattern in patterns:
        for day, month, year in re.findall(pattern, text):
            parsed = valid_future_date(day, month, year)
            if parsed and parsed not in candidates:
                candidates.append(parsed)
    return sorted(candidates, key=lambda value: abs((datetime.strptime(value, "%Y-%m-%d").date() - date.today()).days))


def ocr_expiry(image_path):
    if not image_path:
        return "", "", 0
    texts = []
    try:
        with Image.open(image_path) as source:
            source = ImageOps.exif_transpose(source).convert("L")
            source.thumbnail((2200, 2200))
            variants = [
                source,
                ImageEnhance.Contrast(source).enhance(2.2),
                ImageOps.autocontrast(source).filter(ImageFilter.SHARPEN),
                ImageOps.autocontrast(source).point(lambda pixel: 255 if pixel > 145 else 0),
            ]
            for variant in variants:
                for psm in (6, 11, 7):
                    text = pytesseract.image_to_string(variant, config=f"--oem 1 --psm {psm}")
                    if text.strip():
                        texts.append(text.strip())
    except Exception:
        return "", "", 0
    combined = "\n".join(texts)
    dates = parse_dates(combined)
    if not dates:
        return "", combined[:1000], 0
    confidence = 90 if sum(value in combined for value in ["BEDST", "BEST", "ANVEND", "EXP"]) else 72
    return dates[0], combined[:1000], confidence


@app.context_processor
def helpers():
    return {"days_left": days_left}


@app.get("/")
def index():
    with db() as connection:
        items = connection.execute("""
            SELECT * FROM items WHERE quantity > 0
            ORDER BY CASE WHEN expiry IS NULL OR expiry = '' THEN 1 ELSE 0 END, expiry, name
        """).fetchall()
    stats = {
        "total": sum(item["quantity"] for item in items),
        "soon": sum(item["quantity"] for item in items if days_left(item["expiry"]) is not None and 0 <= days_left(item["expiry"]) <= 3),
        "expired": sum(item["quantity"] for item in items if days_left(item["expiry"]) is not None and days_left(item["expiry"]) < 0),
    }
    return render_template("index.html", items=items, stats=stats)


@app.route("/scan", methods=["GET", "POST"])
def scan():
    if request.method == "GET":
        return render_template("scan.html", result=None)
    product_name, product_path = save_upload(request.files.get("product_image"), "product")
    date_name, date_path = save_upload(request.files.get("date_image"), "date")
    if not product_path and not date_path:
        flash("Tag mindst ét billede.")
        return redirect(url_for("scan"))
    barcode = scan_barcode([product_path, date_path])
    product = lookup_product(barcode)
    expiry, raw_ocr, date_confidence = ocr_expiry(date_path or product_path)
    confidence = 0
    if barcode:
        confidence += 35
    if product.get("name"):
        confidence += 35
    if expiry:
        confidence += 30
    result = {
        "name": product.get("name", ""),
        "brand": product.get("brand", ""),
        "category": product.get("category", ""),
        "barcode": barcode,
        "expiry": expiry,
        "image": product_name or date_name,
        "date_confidence": date_confidence,
        "confidence": confidence,
        "raw_ocr": raw_ocr,
    }
    return render_template("scan.html", result=result)


@app.post("/add")
def add():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Navn er obligatorisk.")
        return redirect(request.referrer or url_for("index"))
    location = request.form.get("location", "Skab").strip()
    category = request.form.get("category", "").strip()
    brand = request.form.get("brand", "").strip()
    barcode = request.form.get("barcode", "").strip()
    expiry = request.form.get("expiry") or None
    existing_image = request.form.get("existing_image", "").strip()
    try:
        quantity = max(1, int(request.form.get("quantity", "1")))
        confidence = max(0, min(100, int(request.form.get("scan_confidence", "0"))))
    except ValueError:
        quantity, confidence = 1, 0
    image = existing_image or None
    new_image, _ = save_upload(request.files.get("image"), "item")
    if new_image:
        image = new_image
    with db() as connection:
        connection.execute("""
            INSERT INTO items(name, category, location, quantity, expiry, image, created_at, barcode, brand, scan_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, category, location, quantity, expiry, image, datetime.now().isoformat(), barcode, brand, confidence))
    return redirect(url_for("index"))


@app.post("/item/<int:item_id>/change")
def change(item_id):
    try:
        delta = int(request.form.get("delta", "0"))
    except ValueError:
        delta = 0
    with db() as connection:
        connection.execute("UPDATE items SET quantity = MAX(0, quantity + ?) WHERE id = ?", (delta, item_id))
    return redirect(url_for("index"))


@app.post("/item/<int:item_id>/delete")
def delete(item_id):
    with db() as connection:
        row = connection.execute("SELECT image FROM items WHERE id = ?", (item_id,)).fetchone()
        connection.execute("DELETE FROM items WHERE id = ?", (item_id,))
    if row and row["image"]:
        try:
            os.remove(os.path.join(UPLOAD_DIR, row["image"]))
        except OSError:
            pass
    return redirect(url_for("index"))


@app.get("/uploads/<path:name>")
def uploads(name):
    return send_from_directory(UPLOAD_DIR, name)


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.2"}
