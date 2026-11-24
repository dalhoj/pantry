import os, sqlite3, uuid
from datetime import date, datetime
import requests
from flask import Flask, redirect, render_template, request, url_for
DATA=os.getenv('PANTRY_DATA_DIR','/data'); DB=os.path.join(DATA,'pantry.db'); os.makedirs(DATA,exist_ok=True)
app=Flask(__name__); app.secret_key=os.getenv('SECRET_KEY','change-me'); OFF='https://world.openfoodfacts.org/api/v2/product/{}'
def db(): c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def now(): return datetime.now().isoformat(timespec='seconds')
def kind(n,c=''):
 s=(n+' '+c).lower(); rules=[('Mayonnaise',['mayo']),('Mælk',['mælk','milk']),('Ost',['ost','cheese']),('Smør',['smør','butter']),('Æg',['æg','egg']),('Pasta',['pasta']),('Ris',['ris','rice']),('Brød',['brød','bread']),('Drikkevarer',['juice','cola','sodavand','vand']),('Rengøring',['opvask','sæbe','soap']),('Kød',['kød','meat']),('Fisk',['fisk','fish']),('Frugt',['frugt','fruit']),('Grøntsager',['kartoff','grønt','vegetable'])]
 for k,ws in rules:
  if any(w in s for w in ws): return k
 return (c.split(',')[0].strip() if c else 'Andet') or 'Andet'
def init():
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,barcode TEXT UNIQUE,name TEXT NOT NULL,brand TEXT,type TEXT NOT NULL,variant TEXT,category TEXT,default_location TEXT,created_at TEXT NOT NULL)')
  c.execute('CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY,product_id INTEGER NOT NULL,quantity INTEGER NOT NULL DEFAULT 1,expiry DATE,location TEXT NOT NULL,created_at TEXT NOT NULL)')
  pc={x[1] for x in c.execute('PRAGMA table_info(products)')}
  if 'no_expiry_default' not in pc:c.execute('ALTER TABLE products ADD COLUMN no_expiry_default INTEGER NOT NULL DEFAULT 0')
  if 'minimum_stock' not in pc:c.execute('ALTER TABLE products ADD COLUMN minimum_stock INTEGER')
  c.execute('CREATE TABLE IF NOT EXISTS shopping(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,type TEXT,product_id INTEGER,quantity INTEGER NOT NULL DEFAULT 1,checked INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL)')
  c.execute('CREATE TABLE IF NOT EXISTS locations(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,sort_order INTEGER NOT NULL DEFAULT 0)')
  c.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
  c.execute('CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT,action TEXT NOT NULL,product_id INTEGER,inventory_id INTEGER,name TEXT NOT NULL,quantity_change INTEGER NOT NULL DEFAULT 0,details TEXT,created_at TEXT NOT NULL)')
  for n,o in [('Køleskab',10),('Fryser',20),('Skab',30),('Viktualierum',40),('Andet',50)]:c.execute('INSERT OR IGNORE INTO locations(name,sort_order) VALUES(?,?)',(n,o))
  c.execute("INSERT OR IGNORE INTO settings VALUES('expiry_warning_days','7')")
def log(c,a,pid,iid,n,q=0,d=''):c.execute('INSERT INTO history(action,product_id,inventory_id,name,quantity_change,details,created_at) VALUES(?,?,?,?,?,?,?)',(a,pid,iid,n,q,d,now()))
def locs():
 with db() as c:return c.execute('SELECT * FROM locations ORDER BY sort_order,name').fetchall()
def dleft(x):
 if not x:return None
 try:return (datetime.strptime(x,'%Y-%m-%d').date()-date.today()).days
 except:return None
def setting(k,d=''):
 with db() as c:r=c.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone();return r['value'] if r else d
def shopcount():
 with db() as c:return c.execute('SELECT COALESCE(SUM(quantity),0)n FROM shopping WHERE checked=0').fetchone()['n']
def lookup(b):
 try:
  j=requests.get(OFF.format(b),params={'fields':'product_name,product_name_da,brands,categories'},headers={'User-Agent':'Pantry/0.6.2'},timeout=8).json();p=j.get('product',{});n=p.get('product_name_da') or p.get('product_name') or '';cat=(p.get('categories') or '').split(',')[0].strip();return {'name':n,'brand':p.get('brands') or '','type':kind(n,cat),'category':cat,'variant':''} if j.get('status')==1 else {}
 except:return {}
init()
@app.context_processor
def ctx():return {'dleft':dleft,'shopcount':shopcount()}
def rows(loc=''):
 q="SELECT p.*,i.id iid,i.quantity,i.expiry,i.location FROM products p JOIN inventory i ON p.id=i.product_id WHERE i.quantity>0 AND p.barcode!='__migration_v03__'";a=[]
 if loc:q+=' AND i.location=?';a=[loc]
 with db() as c:return c.execute(q,a).fetchall()
def sortrows(r,s):
 if s=='expiry':return sorted(r,key=lambda x:(x['expiry'] is None,x['expiry'] or '9999'))
 if s=='qty_asc':return sorted(r,key=lambda x:x['quantity'])
 if s=='qty_desc':return sorted(r,key=lambda x:-x['quantity'])
 return sorted(r,key=lambda x:x['name'].lower())
@app.get('/')
def home():
 q=request.args.get('q','').lower();s=request.args.get('sort','name');r=rows();r=[x for x in r if not q or q in ' '.join(str(x[k] or '') for k in ['name','brand','type','variant','location']).lower()];r=sortrows(r,s);g={}
 for x in r:g.setdefault(x['type'],[]).append(x)
 w=int(setting('expiry_warning_days','7'));soon=sorted([x for x in r if x['expiry'] and dleft(x['expiry'])<=w],key=lambda x:x['expiry'])[:5]
 return render_template('index.html',active='home',groups=g,q=request.args.get('q',''),sort=s,total=sum(x['quantity'] for x in r),soon=soon,warning=w)
@app.get('/locations')
def locations():
 st=[];w=int(setting('expiry_warning_days','7'))
 for l in locs():
  r=rows(l['name']);st.append({'name':l['name'],'products':len(r),'units':sum(x['quantity'] for x in r),'soon':sum(1 for x in r if x['expiry'] and dleft(x['expiry'])<=w)})
 return render_template('locations.html',active='locations',stats=st)
@app.get('/locations/<path:name>')
def location(name):return render_template('location.html',active='locations',name=name,rows=sortrows(rows(name),request.args.get('sort','name')),sort=request.args.get('sort','name'))
@app.get('/scan')
def scan():return render_template('scan.html',active='scan')
@app.get('/scan/in')
def scanin():
 b=request.args.get('barcode','');p=None
 if b:
  with db() as c:p=c.execute('SELECT * FROM products WHERE barcode=?',(b,)).fetchone()
  p=dict(p) if p else lookup(b)
 return render_template('scan_in.html',active='scan',barcode=b,product=p,locations=locs())
@app.get('/scan/out')
def scanout():
 b=request.args.get('barcode','');r=[]
 if b:
  with db() as c:r=c.execute('SELECT p.name,p.brand,p.type,p.id product_id,i.* FROM products p JOIN inventory i ON p.id=i.product_id WHERE p.barcode=? AND i.quantity>0 ORDER BY CASE WHEN i.expiry IS NULL THEN 1 ELSE 0 END,i.expiry',(b,)).fetchall()
 return render_template('scan_out.html',active='scan',barcode=b,rows=r)
@app.route('/inventory/manual',methods=['GET','POST'])
def manual():
 if request.method=='POST':
  f=request.form;b='manual-'+uuid.uuid4().hex;n=f['name'].strip();t=f['type'].strip() or kind(n);no=f.get('no_expiry')=='1';exp=None if no else f.get('expiry') or None;q=max(1,int(f.get('quantity',1)))
  with db() as c:c.execute('INSERT INTO products(barcode,name,brand,type,variant,category,default_location,no_expiry_default,minimum_stock,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(b,n,f.get('brand',''),t,f.get('variant',''),'manual',f['location'],int(no),int(f['minimum_stock']) if f.get('minimum_stock') else None,now()));pid=c.execute('SELECT last_insert_rowid() id').fetchone()['id'];c.execute('INSERT INTO inventory(product_id,quantity,expiry,location,created_at) VALUES(?,?,?,?,?)',(pid,q,exp,f['location'],now()));iid=c.execute('SELECT last_insert_rowid() id').fetchone()['id'];log(c,'MANUAL_ADD',pid,iid,n,q,'Manuel oprettelse')
  return redirect('/')
 return render_template('manual.html',active='scan',locations=locs())
@app.post('/inventory/add')
def add():
 f=request.form;b=f['barcode'];n=f['name'];t=f['type'] or kind(n);no=f.get('no_expiry')=='1';exp=None if no else f.get('expiry') or None;q=max(1,int(f.get('quantity',1)))
 with db() as c:c.execute('INSERT OR IGNORE INTO products(barcode,name,brand,type,variant,category,default_location,no_expiry_default,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(b,n,f.get('brand',''),t,f.get('variant',''),f.get('category',''),f['location'],int(no),now()));c.execute('UPDATE products SET name=?,brand=?,type=?,variant=?,default_location=?,no_expiry_default=? WHERE barcode=?',(n,f.get('brand',''),t,f.get('variant',''),f['location'],int(no),b));pid=c.execute('SELECT id FROM products WHERE barcode=?',(b,)).fetchone()['id'];batch=c.execute('SELECT id FROM inventory WHERE product_id=? AND expiry IS ? AND location=?',(pid,exp,f['location'])).fetchone()
 if batch:
  with db() as c:c.execute('UPDATE inventory SET quantity=quantity+? WHERE id=?',(q,batch['id']));log(c,'SCAN_IN',pid,batch['id'],n,q,'Scan ind')
 else:
  with db() as c:c.execute('INSERT INTO inventory(product_id,quantity,expiry,location,created_at) VALUES(?,?,?,?,?)',(pid,q,exp,f['location'],now()));iid=c.execute('SELECT last_insert_rowid()id').fetchone()['id'];log(c,'SCAN_IN',pid,iid,n,q,'Scan ind')
 return redirect('/')
@app.route('/inventory/<int:i>/edit',methods=['GET','POST'])
def edit(i):
 with db() as c:r=c.execute('SELECT p.*,i.id iid,i.quantity,i.expiry,i.location FROM inventory i JOIN products p ON p.id=i.product_id WHERE i.id=?',(i,)).fetchone()
 if request.method=='POST' and r:
  f=request.form;no=f.get('no_expiry')=='1';exp=None if no else f.get('expiry') or None;q=max(0,int(f.get('quantity',0)));ret=f.get('return_to') or '/'
  with db() as c:c.execute('UPDATE products SET name=?,brand=?,type=?,variant=?,default_location=?,no_expiry_default=?,minimum_stock=? WHERE id=?',(f['name'],f.get('brand',''),f['type'],f.get('variant',''),f['location'],int(no),int(f['minimum_stock']) if f.get('minimum_stock') else None,r['id']));c.execute('UPDATE inventory SET quantity=?,expiry=?,location=? WHERE id=?',(q,exp,f['location'],i));log(c,'MANUAL_EDIT',r['id'],i,f['name'],q-r['quantity'],'Redigeret')
  return redirect(ret)
 return render_template('edit.html',active='home',item=r,locations=locs(),return_to=request.args.get('return_to','/'))
@app.post('/inventory/<int:i>/change')
def change(i):
 d=int(request.form['delta']);ret=request.form.get('return_to','/')
 with db() as c:r=c.execute('SELECT i.quantity,p.id pid,p.name FROM inventory i JOIN products p ON p.id=i.product_id WHERE i.id=?',(i,)).fetchone();c.execute('UPDATE inventory SET quantity=MAX(0,quantity+?) WHERE id=?',(d,i));log(c,'MANUAL_EDIT',r['pid'],i,r['name'],d,'Hurtig justering')
 return redirect(ret)
@app.post('/inventory/<int:i>/delete')
def delete(i):
 ret=request.form.get('return_to','/')
 with db() as c:r=c.execute('SELECT p.id pid,p.name FROM inventory i JOIN products p ON p.id=i.product_id WHERE i.id=?',(i,)).fetchone();log(c,'DELETE',r['pid'],i,r['name'],0,'Lagerpost slettet');c.execute('DELETE FROM inventory WHERE id=?',(i,))
 return redirect(ret)
@app.post('/inventory/use/<int:i>/<action>')
def use(i,action):
 with db() as c:r=c.execute('SELECT i.quantity,p.id pid,p.name,p.type FROM inventory i JOIN products p ON p.id=i.product_id WHERE i.id=?',(i,)).fetchone();c.execute('UPDATE inventory SET quantity=MAX(0,quantity-1) WHERE id=?',(i,));log(c,'DISCARD' if action=='discard' else 'SCAN_OUT',r['pid'],i,r['name'],-1,'Kasseret' if action=='discard' else 'Taget i brug')
 return redirect('/')
@app.get('/shopping')
def shopping():
 with db() as c:r=c.execute('SELECT * FROM shopping ORDER BY checked,created_at DESC').fetchall()
 return render_template('shopping.html',active='shopping',rows=r)
@app.post('/shopping/add')
def shopadd():
 n=request.form['name'].strip()
 with db() as c:c.execute('INSERT INTO shopping(name,type,quantity,created_at) VALUES(?,?,1,?)',(n,kind(n),now()))
 return redirect('/shopping')
@app.post('/shopping/<int:i>/<op>')
def shopop(i,op):
 with db() as c:
  if op=='toggle':c.execute('UPDATE shopping SET checked=1-checked WHERE id=?',(i,))
  elif op=='delete':c.execute('DELETE FROM shopping WHERE id=?',(i,))
  else:c.execute('UPDATE shopping SET quantity=MAX(1,quantity+?) WHERE id=?',(1 if op=='plus' else -1,i))
 return redirect('/shopping')
@app.get('/more')
def more():return render_template('more.html',active='more',warning=setting('expiry_warning_days','7'))
@app.route('/manage/locations',methods=['GET','POST'])
def manage():
 if request.method=='POST':
  with db() as c:c.execute('INSERT OR IGNORE INTO locations(name,sort_order) VALUES(?,100)',(request.form['name'],))
  return redirect('/manage/locations')
 return render_template('manage.html',active='more',locations=locs())
@app.post('/settings/warning')
def warning():
 with db() as c:c.execute("INSERT INTO settings VALUES('expiry_warning_days',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(request.form['days'],))
 return redirect('/more')
@app.get('/health')
def health():return {'status':'ok','version':'0.6.2'}
