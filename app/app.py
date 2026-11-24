import os, sqlite3
from datetime import date, datetime
import requests
from flask import Flask, redirect, render_template, request, url_for
DATA=os.getenv('PANTRY_DATA_DIR','/data'); DB=os.path.join(DATA,'pantry.db'); os.makedirs(DATA,exist_ok=True)
app=Flask(__name__); app.secret_key=os.getenv('SECRET_KEY','change-me'); OFF='https://world.openfoodfacts.org/api/v2/product/{}'
def db(): c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def kind(name,cat=''):
 s=(name+' '+cat).lower(); rules=[('Mayonnaise',['mayonnaise','mayo']),('Mælk',['mælk','milk']),('Ost',['ost','cheese']),('Smør',['smør','butter']),('Æg',['æg','egg']),('Pasta',['pasta']),('Ris',['ris','rice']),('Brød',['brød','bread']),('Drikkevarer',['juice','cola','sodavand','vand']),('Opvaskemiddel',['opvaskemiddel']),('Opvaskemaskinesalt',['opvaskemaskinesalt']),('Sæbe',['sæbe']),('Kød',['kød','meat']),('Fisk',['fisk','fish']),('Frugt',['frugt','fruit']),('Grøntsager',['grønt','vegetable'])]
 for k,ws in rules:
  if any(w in s for w in ws): return k
 return (cat.split(',')[0].strip() if cat else 'Andet') or 'Andet'
def icon_key(t): return {'Mayonnaise':'mayo','Mælk':'milk','Ost':'cheese','Smør':'butter','Æg':'eggs','Brød':'bread','Pasta':'pasta','Ris':'rice','Drikkevarer':'drink','Opvaskemiddel':'soap','Opvaskemaskinesalt':'salt','Sæbe':'soap','Kød':'meat','Fisk':'fish','Frugt':'fruit','Grøntsager':'veg'}.get(t,'box')
def init():
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,barcode TEXT UNIQUE,name TEXT NOT NULL,brand TEXT,type TEXT NOT NULL,variant TEXT,category TEXT,default_location TEXT,created_at TEXT NOT NULL)'); c.execute('CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY,product_id INTEGER NOT NULL,quantity INTEGER NOT NULL DEFAULT 1,expiry DATE,location TEXT NOT NULL,created_at TEXT NOT NULL)')
  if 'no_expiry_default' not in {x[1] for x in c.execute('PRAGMA table_info(products)')}: c.execute('ALTER TABLE products ADD COLUMN no_expiry_default INTEGER NOT NULL DEFAULT 0')
  c.execute('CREATE TABLE IF NOT EXISTS shopping(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,type TEXT,product_id INTEGER,quantity INTEGER NOT NULL DEFAULT 1,checked INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL)'); c.execute('CREATE TABLE IF NOT EXISTS locations(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,sort_order INTEGER NOT NULL DEFAULT 0)'); c.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
  for n,o in [('Køleskab',10),('Fryser',20),('Skab',30),('Viktualierum',40),('Andet',50)]: c.execute('INSERT OR IGNORE INTO locations(name,sort_order) VALUES(?,?)',(n,o))
  c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('expiry_warning_days','7')")
def lookup(bc):
 try:
  j=requests.get(OFF.format(bc),params={'fields':'product_name,product_name_da,brands,categories'},headers={'User-Agent':'Pantry/0.6.1 dalhoj'},timeout=8).json();p=j.get('product',{});n=p.get('product_name_da') or p.get('product_name') or '';cat=(p.get('categories') or '').split(',')[0].strip();return {'name':n,'brand':p.get('brands') or '','category':cat,'type':kind(n,cat),'variant':'','default_location':'','no_expiry_default':0} if j.get('status')==1 else {}
 except:return {}
def dleft(x):
 if not x:return None
 try:return (datetime.strptime(x,'%Y-%m-%d').date()-date.today()).days
 except:return None
def setting(k,d=''):
 with db() as c:r=c.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone();return r['value'] if r else d
def locations():
 with db() as c:return c.execute('SELECT * FROM locations ORDER BY sort_order,name').fetchall()
def shopcount():
 with db() as c:return c.execute('SELECT COALESCE(SUM(quantity),0)n FROM shopping WHERE checked=0').fetchone()['n']
init()
@app.context_processor
def ctx():return {'dleft':dleft,'icon_key':icon_key,'shopcount':shopcount()}
def rows(location=''):
 sql="SELECT p.*,i.id iid,i.quantity,i.expiry,i.location FROM products p JOIN inventory i ON p.id=i.product_id WHERE i.quantity>0 AND p.barcode!='__migration_v03__'"; a=[]
 if location:sql+=' AND i.location=?';a=[location]
 with db() as c:return c.execute(sql,a).fetchall()
def order(rs,s):
 if s=='expiry':return sorted(rs,key=lambda r:(r['expiry'] is None,r['expiry'] or '9999'))
 if s=='qty_asc':return sorted(rs,key=lambda r:r['quantity'])
 if s=='qty_desc':return sorted(rs,key=lambda r:-r['quantity'])
 return sorted(rs,key=lambda r:r['name'].lower())
@app.get('/')
def home():
 q=request.args.get('q','').lower();s=request.args.get('sort','name');rs=rows();rs=[r for r in rs if not q or q in ' '.join(str(r[k] or '') for k in ['name','brand','type','variant','location']).lower()];rs=order(rs,s);g={}
 for r in rs:g.setdefault(r['type'],[]).append(r)
 w=int(setting('expiry_warning_days','7'));soon=sorted([r for r in rs if r['expiry'] and dleft(r['expiry'])<=w],key=lambda r:r['expiry'])[:5]
 return render_template('index.html',active='home',groups=g,q=request.args.get('q',''),sort=s,total=sum(r['quantity'] for r in rs),soon=soon,warning=w)
@app.get('/locations')
def locs():
 w=int(setting('expiry_warning_days','7')); st=[]
 for l in locations():
  rr=rows(l['name']);st.append({'name':l['name'],'products':len(rr),'units':sum(x['quantity'] for x in rr),'soon':sum(1 for x in rr if x['expiry'] and dleft(x['expiry'])<=w)})
 return render_template('locations.html',active='locations',stats=st)
@app.get('/locations/<path:name>')
def locdetail(name):return render_template('location_detail.html',active='locations',name=name,rows=order(rows(name),request.args.get('sort','name')),sort=request.args.get('sort','name'))
@app.get('/scan')
def scan():return render_template('scan_menu.html',active='scan')
@app.get('/scan/in')
def scanin():
 bc=request.args.get('barcode','');p=None
 if bc:
  with db() as c:p=c.execute('SELECT * FROM products WHERE barcode=?',(bc,)).fetchone()
  p=dict(p) if p else lookup(bc)
 return render_template('scan_in.html',active='scan',barcode=bc,product=p,locations=locations())
@app.post('/inventory/add')
def add():
 f=request.form;bc=f['barcode'];n=f['name'];t=f['type'] or kind(n);loc=f['location'];no=f.get('no_expiry')=='1';exp=None if no else f.get('expiry') or None;q=max(1,int(f.get('quantity',1)))
 with db() as c:c.execute('INSERT OR IGNORE INTO products(barcode,name,brand,type,variant,category,default_location,no_expiry_default,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(bc,n,f.get('brand',''),t,f.get('variant',''),f.get('category',''),loc,int(no),datetime.now().isoformat()));c.execute('UPDATE products SET name=?,brand=?,type=?,variant=?,default_location=?,no_expiry_default=? WHERE barcode=?',(n,f.get('brand',''),t,f.get('variant',''),loc,int(no),bc));pid=c.execute('SELECT id FROM products WHERE barcode=?',(bc,)).fetchone()['id'];b=c.execute('SELECT id FROM inventory WHERE product_id=? AND expiry IS ? AND location=?',(pid,exp,loc)).fetchone();c.execute('UPDATE inventory SET quantity=quantity+? WHERE id=?',(q,b['id'])) if b else c.execute('INSERT INTO inventory(product_id,quantity,expiry,location,created_at) VALUES(?,?,?,?,?)',(pid,q,exp,loc,datetime.now().isoformat()))
 return redirect('/')
@app.get('/scan/out')
def scanout():
 bc=request.args.get('barcode','');rr=[]
 if bc:
  with db() as c:rr=c.execute('SELECT p.name,p.brand,p.type,i.* FROM products p JOIN inventory i ON p.id=i.product_id WHERE p.barcode=? AND i.quantity>0 ORDER BY CASE WHEN i.expiry IS NULL THEN 1 ELSE 0 END,i.expiry',(bc,)).fetchall()
 return render_template('scan_out.html',active='scan',barcode=bc,rows=rr)
@app.post('/inventory/use/<int:i>')
def use(i):
 with db() as c:c.execute('UPDATE inventory SET quantity=MAX(0,quantity-1) WHERE id=?',(i,))
 return redirect('/')
@app.get('/shopping')
def shopping():
 with db() as c:rr=c.execute('SELECT * FROM shopping ORDER BY checked,created_at DESC').fetchall()
 return render_template('shopping.html',active='shopping',rows=rr)
@app.post('/shopping/add')
def shopadd():
 f=request.form;n=f.get('name','').strip()
 if n:
  with db() as c:c.execute('INSERT INTO shopping(name,type,quantity,created_at) VALUES(?,?,1,?)',(n,kind(n),datetime.now().isoformat()))
 return redirect('/shopping')
@app.post('/shopping/<int:i>/change')
def shopchange(i):
 with db() as c:c.execute('UPDATE shopping SET quantity=MAX(1,quantity+?) WHERE id=?',(int(request.form['delta']),i))
 return redirect('/shopping')
@app.post('/shopping/<int:i>/toggle')
def toggle(i):
 with db() as c:c.execute('UPDATE shopping SET checked=1-checked WHERE id=?',(i,))
 return redirect('/shopping')
@app.post('/shopping/<int:i>/delete')
def shopdelete(i):
 with db() as c:c.execute('DELETE FROM shopping WHERE id=?',(i,))
 return redirect('/shopping')
@app.get('/more')
def more():return render_template('more.html',active='more',warning=setting('expiry_warning_days','7'))
@app.route('/manage/locations',methods=['GET','POST'])
def manage():
 if request.method=='POST':
  with db() as c:c.execute('INSERT OR IGNORE INTO locations(name,sort_order) VALUES(?,100)',(request.form['name'].strip(),))
  return redirect('/manage/locations')
 return render_template('manage_locations.html',active='more',locations=locations())
@app.post('/manage/locations/<int:i>/rename')
def rename(i):
 new=request.form['name'].strip()
 with db() as c:o=c.execute('SELECT name FROM locations WHERE id=?',(i,)).fetchone();c.execute('UPDATE inventory SET location=? WHERE location=?',(new,o['name']));c.execute('UPDATE products SET default_location=? WHERE default_location=?',(new,o['name']));c.execute('UPDATE locations SET name=? WHERE id=?',(new,i))
 return redirect('/manage/locations')
@app.post('/manage/locations/<int:i>/delete')
def delloc(i):
 tar=request.form.get('target','')
 with db() as c:o=c.execute('SELECT name FROM locations WHERE id=?',(i,)).fetchone();n=c.execute('SELECT COUNT(*) n FROM inventory WHERE location=? AND quantity>0',(o['name'],)).fetchone()['n'];
 if not n or tar:
  with db() as c:
   o=c.execute('SELECT name FROM locations WHERE id=?',(i,)).fetchone()
   if tar:c.execute('UPDATE inventory SET location=? WHERE location=?',(tar,o['name']));c.execute('UPDATE products SET default_location=? WHERE default_location=?',(tar,o['name']))
   c.execute('DELETE FROM locations WHERE id=?',(i,))
 return redirect('/manage/locations')
@app.post('/settings/warning')
def warn():
 with db() as c:c.execute("INSERT INTO settings(key,value) VALUES('expiry_warning_days',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(request.form['days'],))
 return redirect('/more')
@app.get('/health')
def health():return {'status':'ok','version':'0.6.1'}
