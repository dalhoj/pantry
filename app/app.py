import os, sqlite3
from datetime import datetime
import requests
from flask import Flask, redirect, render_template, request, url_for
DATA=os.getenv('PANTRY_DATA_DIR','/data'); DB=os.path.join(DATA,'pantry.db'); os.makedirs(DATA,exist_ok=True)
app=Flask(__name__); app.secret_key=os.getenv('SECRET_KEY','change-me'); OFF='https://world.openfoodfacts.org/api/v2/product/{}'
def db(): c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def kind(name,cat=''):
 s=(name+' '+cat).lower(); rules=[('Mayonnaise',['mayonnaise','mayo']),('Mælk',['mælk','milk']),('Ost',['ost','cheese']),('Smør',['smør','butter']),('Æg',['æg','egg']),('Pasta',['pasta','spaghetti','penne']),('Ris',['ris','rice']),('Ketchup',['ketchup']),('Sennep',['sennep','mustard']),('Brød',['brød','bread']),('Drikkevarer',['juice','cola','sodavand','vand','water'])]
 for k,ws in rules:
  if any(w in s for w in ws): return k
 return (cat.split(',')[0].strip() if cat else 'Andet') or 'Andet'
def init():
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,barcode TEXT UNIQUE,name TEXT NOT NULL,brand TEXT,type TEXT NOT NULL,variant TEXT,category TEXT,default_location TEXT,created_at TEXT NOT NULL)')
  c.execute('CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY,product_id INTEGER NOT NULL,quantity INTEGER NOT NULL DEFAULT 1,expiry DATE,location TEXT NOT NULL,created_at TEXT NOT NULL)')
  tables={x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  if 'items' in tables and not c.execute("SELECT 1 FROM products WHERE barcode='__migration_v03__'").fetchone():
   cols={x[1] for x in c.execute('PRAGMA table_info(items)')}
   for r in c.execute('SELECT * FROM items WHERE quantity>0').fetchall():
    bc=(r['barcode'] if 'barcode' in cols else '') or f"legacy-{r['id']}"; brand=(r['brand'] if 'brand' in cols else '') or ''; typ=kind(r['name'],r['category'] or '')
    c.execute('INSERT OR IGNORE INTO products(barcode,name,brand,type,variant,category,default_location,created_at) VALUES(?,?,?,?,?,?,?,?)',(bc,r['name'],brand,typ,'',r['category'] or '',r['location'],datetime.now().isoformat())); p=c.execute('SELECT id FROM products WHERE barcode=?',(bc,)).fetchone(); c.execute('INSERT INTO inventory(product_id,quantity,expiry,location,created_at) VALUES(?,?,?,?,?)',(p['id'],r['quantity'],r['expiry'],r['location'],datetime.now().isoformat()))
   c.execute("INSERT INTO products(barcode,name,brand,type,variant,category,created_at) VALUES('__migration_v03__','migration','','System','','',?)",(datetime.now().isoformat(),))
def lookup(bc):
 try:
  j=requests.get(OFF.format(bc),params={'fields':'product_name,product_name_da,brands,categories'},headers={'User-Agent':'Pantry/0.3.1 dalhoj'},timeout=8).json(); p=j.get('product',{}); n=p.get('product_name_da') or p.get('product_name') or ''; cat=(p.get('categories') or '').split(',')[0].strip(); return {'name':n,'brand':p.get('brands') or '','category':cat,'type':kind(n,cat),'variant':''} if j.get('status')==1 else {}
 except: return {}
init()
@app.get('/')
def index():
 q=request.args.get('q','').strip(); like=f'%{q}%'; args=[]; sql="SELECT p.*,i.id iid,i.quantity,i.expiry,i.location FROM products p JOIN inventory i ON p.id=i.product_id WHERE i.quantity>0 AND p.barcode!='__migration_v03__' "
 if q: sql+='AND (p.type LIKE ? OR p.name LIKE ? OR p.brand LIKE ? OR p.variant LIKE ? OR p.category LIKE ? OR p.barcode LIKE ? OR i.location LIKE ?) '; args=[like]*7
 sql+='ORDER BY p.type,i.expiry,p.name'
 with db() as c: rows=c.execute(sql,args).fetchall()
 groups={}
 for r in rows: groups.setdefault(r['type'],[]).append(r)
 return render_template('index.html',groups=groups,q=q,total=sum(r['quantity'] for r in rows))
@app.get('/scan/in')
def scan_in():
 bc=request.args.get('barcode','').strip(); p=None
 if bc:
  with db() as c:p=c.execute('SELECT * FROM products WHERE barcode=?',(bc,)).fetchone()
  p=dict(p) if p else lookup(bc)
 return render_template('scan_in.html',barcode=bc,product=p)
@app.post('/inventory/add')
def add():
 f=request.form; bc=f['barcode']; name=f['name'].strip(); typ=f.get('type','').strip() or kind(name); loc=f['location']; expiry=f.get('expiry') or None; qty=max(1,int(f.get('quantity',1)))
 with db() as c:
  c.execute('INSERT OR IGNORE INTO products(barcode,name,brand,type,variant,category,default_location,created_at) VALUES(?,?,?,?,?,?,?,?)',(bc,name,f.get('brand',''),typ,f.get('variant',''),f.get('category',''),loc,datetime.now().isoformat())); c.execute('UPDATE products SET name=?,brand=?,type=?,variant=?,category=?,default_location=? WHERE barcode=?',(name,f.get('brand',''),typ,f.get('variant',''),f.get('category',''),loc,bc)); pid=c.execute('SELECT id FROM products WHERE barcode=?',(bc,)).fetchone()['id']; b=c.execute('SELECT id FROM inventory WHERE product_id=? AND expiry IS ? AND location=?',(pid,expiry,loc)).fetchone()
  if b:c.execute('UPDATE inventory SET quantity=quantity+? WHERE id=?',(qty,b['id']))
  else:c.execute('INSERT INTO inventory(product_id,quantity,expiry,location,created_at) VALUES(?,?,?,?,?)',(pid,qty,expiry,loc,datetime.now().isoformat()))
 return redirect(url_for('index'))
@app.get('/scan/out')
def scan_out():
 bc=request.args.get('barcode','').strip(); rows=[]
 if bc:
  with db() as c:rows=c.execute('SELECT p.name,p.brand,p.type,i.* FROM products p JOIN inventory i ON p.id=i.product_id WHERE p.barcode=? AND i.quantity>0 ORDER BY CASE WHEN i.expiry IS NULL THEN 1 ELSE 0 END,i.expiry',(bc,)).fetchall()
 return render_template('scan_out.html',barcode=bc,rows=rows)
@app.post('/inventory/use/<int:iid>')
def use(iid):
 with db() as c:c.execute('UPDATE inventory SET quantity=MAX(0,quantity-1) WHERE id=?',(iid,))
 return redirect(url_for('index'))
@app.get('/health')
def health():return {'status':'ok','version':'0.3.1'}
