import os, sqlite3, uuid
from datetime import date, datetime, timedelta
import requests
from flask import Flask, flash, redirect, render_template, request, url_for
DATA=os.getenv('PANTRY_DATA_DIR','/data'); DB=os.path.join(DATA,'pantry.db'); os.makedirs(DATA,exist_ok=True)
app=Flask(__name__); app.secret_key=os.getenv('SECRET_KEY','change-me'); OFF='https://world.openfoodfacts.org/api/v2/product/{}'
def db(): c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def now(): return datetime.now().isoformat(timespec='seconds')
def kind(n,c=''):
 s=(n+' '+c).lower()
 rules=[('Dåsemad',['makrel i tomat','tun i dåse','tuna','canned','konserv','dåse']),('Tørvarer / Kolonial',['mel','flour','sukker','sugar','havregryn','oats','linser','lentil','bagepulver']),('Saucer & dressinger',['mayonnaise','mayo','ketchup','sennep','mustard','dressing']),('Mælk',['mælk','milk']),('Ost',['ost','cheese']),('Smør',['smør','butter']),('Æg',['æg','egg']),('Pasta',['pasta','spaghetti','penne']),('Ris',['ris','rice']),('Brød',['brød','bread']),('Frostvarer',['frost','frozen']),('Drikkevarer',['juice','cola','sodavand','vand','water']),('Rengøring',['rengøring','cleaner']),('Opvask',['opvask','dishwash']),('Kød',['kød','meat','beef','chicken']),('Fisk',['fisk','fish']),('Frugt',['frugt','fruit','apple']),('Grøntsager',['kartoff','grønt','vegetable','carrot'])]
 for k,ws in rules:
  if any(w in s for w in ws):return k
 return 'Andet'

def init():
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,barcode TEXT UNIQUE,name TEXT NOT NULL,brand TEXT,type TEXT NOT NULL,variant TEXT,category TEXT,default_location TEXT,created_at TEXT NOT NULL)')
  c.execute('CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY,product_id INTEGER NOT NULL,quantity INTEGER NOT NULL DEFAULT 1,expiry DATE,location TEXT NOT NULL,created_at TEXT NOT NULL)')
  pc={x[1] for x in c.execute('PRAGMA table_info(products)')}
  if 'no_expiry_default' not in pc:c.execute('ALTER TABLE products ADD COLUMN no_expiry_default INTEGER NOT NULL DEFAULT 0')
  if 'minimum_stock' not in pc:c.execute('ALTER TABLE products ADD COLUMN minimum_stock INTEGER')
  if 'source' not in pc:c.execute("ALTER TABLE products ADD COLUMN source TEXT NOT NULL DEFAULT 'local'")
  c.execute('CREATE TABLE IF NOT EXISTS product_types(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,default_location TEXT,icon_key TEXT,sort_order INTEGER NOT NULL DEFAULT 0)')
  type_init=c.execute("SELECT value FROM settings WHERE key='product_types_initialized'").fetchone()
  if not type_init:
   defaults=[('Mælk','Køleskab','milk',10),('Ost','Køleskab','cheese',20),('Smør','Køleskab','butter',30),('Æg','Køleskab','eggs',40),('Yoghurt / syrnede produkter','Køleskab','milk',50),('Pålæg','Køleskab','meat',60),('Kød','Køleskab','meat',70),('Fisk','Køleskab','fish',80),('Frugt','Skab','fruit',90),('Grøntsager','Skab','veg',100),('Brød','Skab','bread',110),('Dåsemad','Skab','box',120),('Tørvarer / Kolonial','Skab','box',130),('Pasta','Skab','pasta',140),('Ris','Skab','rice',150),('Morgenmad','Skab','box',160),('Krydderier','Skab','box',170),('Saucer & dressinger','Skab','mayo',180),('Snacks','Skab','box',190),('Slik','Skab','box',200),('Drikkevarer','Skab','drink',210),('Frostvarer','Fryser','box',220),('Opvask','Skab','soap',230),('Rengøring','Skab','soap',240),('Vaskemiddel','Skab','soap',250),('Sæbe & personlig pleje','Skab','soap',260),('Papirvarer','Skab','box',270),('Husholdningsartikler','Skab','box',280),('Andet','Andet','box',999)]
   for n,l,i,o in defaults:c.execute('INSERT OR IGNORE INTO product_types(name,default_location,icon_key,sort_order) VALUES(?,?,?,?)',(n,l,i,o))
   c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('product_types_initialized','true')")
  c.execute('CREATE TABLE IF NOT EXISTS shopping(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,type TEXT,product_id INTEGER,quantity INTEGER NOT NULL DEFAULT 1,checked INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL)')
  c.execute('CREATE TABLE IF NOT EXISTS locations(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,sort_order INTEGER NOT NULL DEFAULT 0)')
  c.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
  c.execute('CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY AUTOINCREMENT,action TEXT NOT NULL,product_id INTEGER,inventory_id INTEGER,name TEXT NOT NULL,quantity_change INTEGER NOT NULL DEFAULT 0,details TEXT,created_at TEXT NOT NULL)')
  hc={x[1] for x in c.execute('PRAGMA table_info(history)')}
  if 'product_type' not in hc:c.execute('ALTER TABLE history ADD COLUMN product_type TEXT')
  if 'location' not in hc:c.execute('ALTER TABLE history ADD COLUMN location TEXT')
  initialized=c.execute("SELECT value FROM settings WHERE key='locations_initialized'").fetchone()
  if not initialized:
   existing=c.execute('SELECT COUNT(*) n FROM locations').fetchone()['n']
   if existing==0:
    for n,o in [('Køleskab',10),('Fryser',20),('Skab',30),('Viktualierum',40),('Andet',50)]:c.execute('INSERT OR IGNORE INTO locations(name,sort_order) VALUES(?,?)',(n,o))
   c.execute("INSERT OR REPLACE INTO settings VALUES('locations_initialized','true')")
  c.execute("INSERT OR IGNORE INTO settings VALUES('expiry_warning_days','7')")
def log(c,a,pid,iid,n,q=0,d='',typ='',loc=''):c.execute('INSERT INTO history(action,product_id,inventory_id,name,quantity_change,details,created_at,product_type,location) VALUES(?,?,?,?,?,?,?,?,?)',(a,pid,iid,n,q,d,now(),typ,loc))
def locs():
 with db() as c:return c.execute('SELECT * FROM locations ORDER BY sort_order,name').fetchall()
def product_types():
 with db() as c:return c.execute('SELECT * FROM product_types ORDER BY sort_order,name').fetchall()
def recommended_location(type_name,product=None):
 if product and product.get('default_location') and any(l['name']==product.get('default_location') for l in locs()):return product.get('default_location'),'Husket fra tidligere'
 with db() as c:r=c.execute('SELECT default_location FROM product_types WHERE name=?',(type_name,)).fetchone()
 candidate=r['default_location'] if r else None
 available=[l['name'] for l in locs()]
 if candidate in available:return candidate,'Foreslået ud fra produkttypen'
 # Never recreate locations; use a best existing fallback.
 if available:return available[0],'Foreslået placering'
 return '',''
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
  j=requests.get(OFF.format(b),params={'fields':'product_name,product_name_da,brands,categories'},headers={'User-Agent':'Pantry/0.6.3'},timeout=8).json();p=j.get('product',{});n=p.get('product_name_da') or p.get('product_name') or '';cat=(p.get('categories') or '').split(',')[0].strip();return {'name':n,'brand':p.get('brands') or '','type':kind(n,cat),'category':cat,'variant':'','source':'openfoodfacts'} if j.get('status')==1 else {}
 except:return {}
def total_for_product(c,pid): return c.execute('SELECT COALESCE(SUM(quantity),0)n FROM inventory WHERE product_id=?',(pid,)).fetchone()['n']
def maybe_shop(c,pid,name,typ):
 total=total_for_product(c,pid)
 p=c.execute('SELECT minimum_stock FROM products WHERE id=?',(pid,)).fetchone()
 threshold=p['minimum_stock'] if p and p['minimum_stock'] is not None else 0
 if total<=threshold:
  exists=c.execute('SELECT 1 FROM shopping WHERE checked=0 AND (product_id=? OR lower(name)=lower(?))',(pid,name)).fetchone()
  if not exists:
   c.execute('INSERT INTO shopping(name,type,product_id,quantity,created_at) VALUES(?,?,?,?,?)',(name,typ,pid,1,now()))
   return True
 return False

init()
@app.context_processor
def ctx():return {'dleft':dleft,'shopcount':shopcount()}
def rows(loc=''):
 q="SELECT p.*,i.id iid,i.quantity,i.expiry,i.location FROM products p JOIN inventory i ON p.id=i.product_id WHERE i.quantity>0 AND p.barcode!='__migration_v03__'";a=[]
 if loc:q+=' AND i.location=?';a=[loc]
 with db() as c:return c.execute(q,a).fetchall()
def order(r,s):
 if s=='expiry':return sorted(r,key=lambda x:(x['expiry'] is None,x['expiry'] or '9999'))
 if s=='qty_asc':return sorted(r,key=lambda x:x['quantity'])
 if s=='qty_desc':return sorted(r,key=lambda x:-x['quantity'])
 return sorted(r,key=lambda x:x['name'].lower())
@app.get('/')
def home():
 q=request.args.get('q','').lower();s=request.args.get('sort','name');r=rows();r=[x for x in r if not q or q in ' '.join(str(x[k] or '') for k in ['name','brand','type','variant','location']).lower()];r=order(r,s);g={}
 for x in r:g.setdefault(x['type'],[]).append(x)
 groups=[]
 for typ,it in g.items():
  dates=[x['expiry'] for x in it if x['expiry']];groups.append({'type':typ,'batches':it,'total':sum(x['quantity'] for x in it),'next_expiry':min(dates) if dates else None})
 w=int(setting('expiry_warning_days','7'));soon=sorted([x for x in r if x['expiry'] and dleft(x['expiry'])<=w],key=lambda x:x['expiry'])[:5]
 return render_template('index.html',active='home',groups=groups,q=request.args.get('q',''),sort=s,total=sum(x['quantity'] for x in r),soon=soon,warning=w)
@app.get('/locations')
def locations():
 st=[];w=int(setting('expiry_warning_days','7'))
 for l in locs():
  r=rows(l['name']);st.append({'name':l['name'],'products':len(r),'units':sum(x['quantity'] for x in r),'soon':sum(1 for x in r if x['expiry'] and dleft(x['expiry'])<=w)})
 return render_template('locations.html',active='locations',stats=st)
@app.get('/locations/<path:name>')
def location(name):return render_template('location.html',active='locations',name=name,rows=order(rows(name),request.args.get('sort','name')),sort=request.args.get('sort','name'))
@app.get('/scan')
def scan():return render_template('scan.html',active='scan')
@app.get('/scan/in')
def scanin():
 b=request.args.get('barcode','');p=None
 if b:
  with db() as c:p=c.execute('SELECT * FROM products WHERE barcode=?',(b,)).fetchone()
  p=dict(p) if p else lookup(b)
 pdata=dict(p) if p else {}
 suggested_type=pdata.get('type') or 'Andet'
 rec_loc,rec_reason=recommended_location(suggested_type,pdata)
 return render_template('scan_in.html',active='scan',barcode=b,product=pdata,locations=locs(),product_types=product_types(),recommended_location=rec_loc,recommendation_reason=rec_reason,is_unknown=bool(b and not pdata.get('name')))
@app.get('/scan/out/select')
def scanout_select():
 q=request.args.get('q','').strip().lower();items=rows()
 if q:items=[x for x in items if q in ' '.join(str(x[k] or '') for k in ['name','brand','type','variant','location']).lower()]
 return render_template('scan_out_select.html',active='scan',items=order(items,'expiry'),q=request.args.get('q',''))
@app.get('/scan/out/item/<int:i>')
def scanout_item(i):
 with db() as c:
  chosen=c.execute('SELECT p.id product_id,p.name,p.brand,p.type,p.barcode,i.* FROM inventory i JOIN products p ON p.id=i.product_id WHERE i.id=?',(i,)).fetchone();batches=[]
  if chosen:batches=c.execute('SELECT p.id product_id,p.name,p.brand,p.type,p.barcode,i.* FROM inventory i JOIN products p ON p.id=i.product_id WHERE p.id=? AND i.quantity>0 ORDER BY CASE WHEN i.expiry IS NULL THEN 1 ELSE 0 END,i.expiry',(chosen['product_id'],)).fetchall()
 return render_template('scan_out_item.html',active='scan',item=chosen,rows=batches)
@app.get('/scan/out')
def scanout():
 b=request.args.get('barcode','');r=[]
 if b:
  with db() as c:r=c.execute('SELECT p.name,p.brand,p.type,p.id product_id,i.* FROM products p JOIN inventory i ON p.id=i.product_id WHERE p.barcode=? AND i.quantity>0 ORDER BY CASE WHEN i.expiry IS NULL THEN 1 ELSE 0 END,i.expiry',(b,)).fetchall()
 return render_template('scan_out.html',active='scan',barcode=b,rows=r)
@app.post('/inventory/use/<int:i>/<action>')
def use(i,action):
 with db() as c:
  r=c.execute('SELECT i.quantity,p.id pid,p.name,p.type FROM inventory i JOIN products p ON p.id=i.product_id WHERE i.id=?',(i,)).fetchone();c.execute('UPDATE inventory SET quantity=MAX(0,quantity-1) WHERE id=?',(i,));log(c,'DISCARD' if action=='discard' else 'SCAN_OUT',r['pid'],i,r['name'],-1,'Kasseret' if action=='discard' else 'Taget i brug');added=maybe_shop(c,r['pid'],r['name'],r['type'])
 flash((f"{r['type']} tilføjet til indkøbslisten" if added else f"{r['name']} {'kasseret' if action=='discard' else 'taget i brug'}"),'success')
 return redirect('/')
@app.route('/manage/locations',methods=['GET','POST'])
def manage():
 if request.method=='POST':
  n=request.form.get('name','').strip()
  if n:
   with db() as c:c.execute('INSERT OR IGNORE INTO locations(name,sort_order) VALUES(?,100)',(n,))
  return redirect('/manage/locations')
 stats=[]
 with db() as c:
  for loc in locs():
   r=c.execute('SELECT COUNT(*) products,COALESCE(SUM(quantity),0) units FROM inventory WHERE location=? AND quantity>0',(loc['name'],)).fetchone()
   stats.append({'id':loc['id'],'name':loc['name'],'sort_order':loc['sort_order'],'products':r['products'],'units':r['units']})
 return render_template('manage.html',active='more',locations=stats)
@app.post('/manage/locations/<int:i>/rename')
def rename(i):
 new=request.form.get('name','').strip()
 with db() as c:
  old=c.execute('SELECT name FROM locations WHERE id=?',(i,)).fetchone()
  if old and new:
   c.execute('UPDATE inventory SET location=? WHERE location=?',(new,old['name']));c.execute('UPDATE products SET default_location=? WHERE default_location=?',(new,old['name']));c.execute('UPDATE locations SET name=? WHERE id=?',(new,i));flash(f"Placeringen er omdøbt til {new}",'success')
 return redirect('/manage/locations')
@app.post('/manage/locations/<int:i>/delete')
def delloc(i):
 tar=request.form.get('target','')
 with db() as c:
  old=c.execute('SELECT name FROM locations WHERE id=?',(i,)).fetchone();count=c.execute('SELECT COUNT(*)n FROM inventory WHERE location=? AND quantity>0',(old['name'],)).fetchone()['n'] if old else 0
  if old and count and not tar:flash('Placeringen indeholder varer. Vælg hvor varerne skal flyttes.','error')
  elif old:
   if tar:c.execute('UPDATE inventory SET location=? WHERE location=?',(tar,old['name']));c.execute('UPDATE products SET default_location=? WHERE default_location=?',(tar,old['name']))
   c.execute('DELETE FROM locations WHERE id=?',(i,));flash(f"{old['name']} er slettet",'success')
 return redirect('/manage/locations')
# Preserve manual/edit/shopping from 0.6.2 with concise implementations
@app.route('/inventory/manual',methods=['GET','POST'])
def manual():
 if request.method=='POST':
  f=request.form;b='manual-'+uuid.uuid4().hex;n=f['name'];t=f['type'] or kind(n);no=f.get('no_expiry')=='1';exp=None if no else f.get('expiry') or None
  with db() as c:c.execute('INSERT INTO products(barcode,name,brand,type,variant,category,default_location,no_expiry_default,minimum_stock,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(b,n,f.get('brand',''),t,f.get('variant',''),'manual',f['location'],int(no),int(f['minimum_stock']) if f.get('minimum_stock') else None,now()));pid=c.execute('SELECT last_insert_rowid()id').fetchone()['id'];c.execute('INSERT INTO inventory(product_id,quantity,expiry,location,created_at) VALUES(?,?,?,?,?)',(pid,int(f.get('quantity',1)),exp,f['location'],now()))
  return redirect('/')
 return render_template('manual.html',active='scan',locations=locs(),product_types=product_types())
@app.post('/inventory/add')
def add_scanned():
 f=request.form;b=f['barcode'];n=f['name'].strip();t=f.get('type','').strip() or kind(n);no=f.get('no_expiry')=='1';exp=None if no else (f.get('expiry') or None);q=max(1,int(f.get('quantity',1)));loc=f['location']
 with db() as c:
  c.execute('INSERT OR IGNORE INTO products(barcode,name,brand,type,variant,category,default_location,no_expiry_default,created_at,source) VALUES(?,?,?,?,?,?,?,?,?,?)',(b,n,f.get('brand',''),t,f.get('variant',''),f.get('category',''),loc,int(no),now(),f.get('source','local')))
  c.execute("UPDATE products SET name=?,brand=?,type=?,variant=?,category=?,default_location=?,no_expiry_default=?,source='local' WHERE barcode=?",(n,f.get('brand',''),t,f.get('variant',''),f.get('category',''),loc,int(no),b))
  pid=c.execute('SELECT id FROM products WHERE barcode=?',(b,)).fetchone()['id']
  batch=c.execute('SELECT id FROM inventory WHERE product_id=? AND expiry IS ? AND location=?',(pid,exp,loc)).fetchone()
  if batch:
   iid=batch['id'];c.execute('UPDATE inventory SET quantity=quantity+? WHERE id=?',(q,iid))
  else:
   c.execute('INSERT INTO inventory(product_id,quantity,expiry,location,created_at) VALUES(?,?,?,?,?)',(pid,q,exp,loc,now()));iid=c.execute('SELECT last_insert_rowid()id').fetchone()['id']
  log(c,'SCAN_IN',pid,iid,n,q,'Scan ind')
 flash(f'{n} tilføjet til lageret','success')
 return redirect('/')
@app.route('/inventory/<int:i>/edit',methods=['GET','POST'])
def edit(i):
 with db() as c:r=c.execute('SELECT p.*,i.id iid,i.quantity,i.expiry,i.location FROM inventory i JOIN products p ON p.id=i.product_id WHERE i.id=?',(i,)).fetchone()
 if request.method=='POST':
  f=request.form;no=f.get('no_expiry')=='1';exp=None if no else f.get('expiry') or None
  with db() as c:c.execute('UPDATE products SET name=?,brand=?,type=?,variant=?,default_location=?,no_expiry_default=?,minimum_stock=? WHERE id=?',(f['name'],f.get('brand',''),f['type'],f.get('variant',''),f['location'],int(no),int(f['minimum_stock']) if f.get('minimum_stock') else None,r['id']));c.execute('UPDATE inventory SET quantity=?,expiry=?,location=? WHERE id=?',(int(f['quantity']),exp,f['location'],i))
  flash('Lagerpost gemt','success');return redirect(f.get('return_to','/'))
 suggested_type=kind(r['name'],r['category'] or '')
 return render_template('edit.html',active='home',item=r,locations=locs(),product_types=product_types(),suggested_type=suggested_type,return_to=request.args.get('return_to','/'))
@app.post('/inventory/<int:i>/delete')
def delete(i):
 with db() as c:c.execute('DELETE FROM inventory WHERE id=?',(i,))
 flash('Lagerpost slettet','success');return redirect(request.form.get('return_to','/'))
@app.get('/shopping')
def shopping():
 with db() as c:r=c.execute('SELECT * FROM shopping ORDER BY checked,created_at DESC').fetchall()
 return render_template('shopping.html',active='shopping',rows=r)
@app.post('/shopping/add')
def shopadd():
 n=request.form['name']
 with db() as c:
  if not c.execute('SELECT 1 FROM shopping WHERE checked=0 AND lower(name)=lower(?)',(n,)).fetchone():c.execute('INSERT INTO shopping(name,type,quantity,created_at)VALUES(?,?,1,?)',(n,kind(n),now()))
 return redirect('/shopping')
@app.post('/shopping/<int:i>/<op>')
def shopop(i,op):
 with db() as c:
  if op=='toggle':c.execute('UPDATE shopping SET checked=1-checked WHERE id=?',(i,))
  elif op=='delete':c.execute('DELETE FROM shopping WHERE id=?',(i,))
  else:c.execute('UPDATE shopping SET quantity=MAX(1,quantity+?) WHERE id=?',(1 if op=='plus' else -1,i))
 return redirect('/shopping')
@app.get('/statistics')
def statistics():
 period=request.args.get('period','week')
 days={'week':7,'month':30,'year':365}.get(period,7)
 start=(datetime.now()-timedelta(days=days)).isoformat(timespec='seconds')
 action_filter=request.args.get('action','all')
 with db() as c:
  history=c.execute('SELECT h.*,COALESCE(h.product_type,p.type,\'Andet\') resolved_type FROM history h LEFT JOIN products p ON p.id=h.product_id WHERE h.created_at>=? ORDER BY h.created_at DESC',(start,)).fetchall()
  stock=c.execute('SELECT COALESCE(SUM(quantity),0)n FROM inventory').fetchone()['n']
 sums={'added':0,'used':0,'discarded':0};consumption={};waste={}
 for h in history:
  qty=abs(h['quantity_change']);typ=h['resolved_type'] or 'Andet'
  if h['action'] in ('SCAN_IN','MANUAL_ADD') and h['quantity_change']>0:sums['added']+=h['quantity_change']
  elif h['action']=='SCAN_OUT':sums['used']+=qty;consumption[typ]=consumption.get(typ,0)+qty
  elif h['action']=='DISCARD':sums['discarded']+=qty;waste[typ]=waste.get(typ,0)+qty
 filtered=[h for h in history if action_filter=='all' or h['action']==action_filter]
 return render_template('statistics.html',active='more',period=period,action_filter=action_filter,sums=sums,stock=stock,consumption=sorted(consumption.items(),key=lambda x:-x[1]),waste=sorted(waste.items(),key=lambda x:-x[1]),history=filtered)
@app.route('/manage/product-types',methods=['GET','POST'])
def manage_product_types():
 if request.method=='POST':
  name=request.form.get('name','').strip();default_location=request.form.get('default_location') or None;icon=request.form.get('icon_key','box').strip() or 'box'
  if name:
   with db() as c:c.execute('INSERT OR IGNORE INTO product_types(name,default_location,icon_key,sort_order) VALUES(?,?,?,1000)',(name,default_location,icon))
  return redirect('/manage/product-types')
 stats=[]
 with db() as c:
  for t in product_types():
   count=c.execute('SELECT COUNT(*) n FROM products WHERE type=?',(t['name'],)).fetchone()['n']
   stats.append({'id':t['id'],'name':t['name'],'default_location':t['default_location'],'icon_key':t['icon_key'],'sort_order':t['sort_order'],'products':count})
 return render_template('manage_product_types.html',active='more',types=stats,locations=locs())
@app.post('/manage/product-types/<int:i>/update')
def update_product_type(i):
 new=request.form.get('name','').strip();loc=request.form.get('default_location') or None;icon=request.form.get('icon_key','box').strip() or 'box'
 with db() as c:
  old=c.execute('SELECT name FROM product_types WHERE id=?',(i,)).fetchone()
  if old and new:
   if old['name']!=new:c.execute('UPDATE products SET type=? WHERE type=?',(new,old['name']))
   c.execute('UPDATE product_types SET name=?,default_location=?,icon_key=? WHERE id=?',(new,loc,icon,i))
 return redirect('/manage/product-types')
@app.post('/manage/product-types/<int:i>/delete')
def delete_product_type(i):
 target=request.form.get('target','').strip()
 with db() as c:
  old=c.execute('SELECT name FROM product_types WHERE id=?',(i,)).fetchone()
  count=c.execute('SELECT COUNT(*) n FROM products WHERE type=?',(old['name'],)).fetchone()['n'] if old else 0
  if old and count and target:
   c.execute('UPDATE products SET type=? WHERE type=?',(target,old['name']));c.execute('DELETE FROM product_types WHERE id=?',(i,))
  elif old and count==0:c.execute('DELETE FROM product_types WHERE id=?',(i,))
 return redirect('/manage/product-types')
@app.post('/manage/product-types/reorder')
def reorder_product_types():
 ids=(request.get_json(silent=True) or {}).get('ids',[])
 with db() as c:
  for index,pid in enumerate(ids):c.execute('UPDATE product_types SET sort_order=? WHERE id=?',((index+1)*10,int(pid)))
 return {'status':'ok'}
@app.get('/more')
def more():return render_template('more.html',active='more',warning=setting('expiry_warning_days','7'))
@app.post('/manage/locations/reorder')
def reorder_locations():
 ids=(request.get_json(silent=True) or {}).get('ids',[])
 with db() as c:
  for index,lid in enumerate(ids):c.execute('UPDATE locations SET sort_order=? WHERE id=?',((index+1)*10,int(lid)))
 return {'status':'ok'}
@app.post('/settings/warning')
def warning():
 with db() as c:c.execute("INSERT INTO settings VALUES('expiry_warning_days',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(request.form['days'],))
 return redirect('/more')
@app.get('/health')
def health():return {'status':'ok','version':'0.6.9.1'}
