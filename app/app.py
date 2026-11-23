import os, sqlite3, uuid
from datetime import date, datetime
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
from werkzeug.utils import secure_filename

DATA_DIR=os.getenv('PANTRY_DATA_DIR','/data')
UPLOAD_DIR=os.path.join(DATA_DIR,'uploads')
DB=os.path.join(DATA_DIR,'pantry.db')
os.makedirs(UPLOAD_DIR, exist_ok=True)
app=Flask(__name__)
app.secret_key=os.getenv('SECRET_KEY','change-me-on-truenas')

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def init_db():
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT, location TEXT NOT NULL, quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity>=0), expiry DATE, image TEXT, created_at TEXT NOT NULL)''')
init_db()

def days_left(expiry):
    if not expiry: return None
    try: return (datetime.strptime(expiry,'%Y-%m-%d').date()-date.today()).days
    except ValueError: return None

@app.context_processor
def helpers(): return dict(days_left=days_left)

@app.get('/')
def index():
    with db() as c:
        items=c.execute('SELECT * FROM items WHERE quantity>0 ORDER BY CASE WHEN expiry IS NULL OR expiry="" THEN 1 ELSE 0 END, expiry, name').fetchall()
    stats={'total':sum(i['quantity'] for i in items),'soon':sum(i['quantity'] for i in items if days_left(i['expiry']) is not None and 0 <= days_left(i['expiry']) <= 3),'expired':sum(i['quantity'] for i in items if days_left(i['expiry']) is not None and days_left(i['expiry']) < 0)}
    return render_template('index.html',items=items,stats=stats)

@app.post('/add')
def add():
    name=request.form.get('name','').strip(); location=request.form.get('location','Skab').strip(); category=request.form.get('category','').strip(); expiry=request.form.get('expiry') or None
    try: quantity=max(1,int(request.form.get('quantity','1')))
    except ValueError: quantity=1
    if not name: flash('Navn er obligatorisk.'); return redirect(url_for('index'))
    image=None; f=request.files.get('image')
    if f and f.filename:
        ext=os.path.splitext(secure_filename(f.filename))[1].lower()
        if ext in {'.jpg','.jpeg','.png','.webp','.heic'}:
            image=f'{uuid.uuid4().hex}{ext}'; f.save(os.path.join(UPLOAD_DIR,image))
    with db() as c:
        c.execute('INSERT INTO items(name,category,location,quantity,expiry,image,created_at) VALUES(?,?,?,?,?,?,?)',(name,category,location,quantity,expiry,image,datetime.now().isoformat()))
    return redirect(url_for('index'))

@app.post('/item/<int:item_id>/change')
def change(item_id):
    try: delta=int(request.form.get('delta','0'))
    except ValueError: delta=0
    with db() as c:
        c.execute('UPDATE items SET quantity=MAX(0,quantity+?) WHERE id=?',(delta,item_id))
    return redirect(url_for('index'))

@app.post('/item/<int:item_id>/delete')
def delete(item_id):
    with db() as c:
        row=c.execute('SELECT image FROM items WHERE id=?',(item_id,)).fetchone(); c.execute('DELETE FROM items WHERE id=?',(item_id,))
    if row and row['image']:
        try: os.remove(os.path.join(UPLOAD_DIR,row['image']))
        except OSError: pass
    return redirect(url_for('index'))

@app.get('/uploads/<path:name>')
def uploads(name): return send_from_directory(UPLOAD_DIR,name)
@app.get('/health')
def health(): return {'status':'ok'}
