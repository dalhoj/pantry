import os,re,sqlite3,uuid
from datetime import date,datetime
import requests,pytesseract
from flask import Flask,flash,redirect,render_template,request,send_from_directory,url_for
from PIL import Image,ImageEnhance,ImageFilter,ImageOps
from pyzbar.pyzbar import decode as decode_barcode
from werkzeug.utils import secure_filename
DATA_DIR=os.getenv('PANTRY_DATA_DIR','/data'); UPLOAD_DIR=os.path.join(DATA_DIR,'uploads'); DB_PATH=os.path.join(DATA_DIR,'pantry.db')
OFF_URL='https://world.openfoodfacts.org/api/v2/product/{barcode}'; ALLOWED={'.jpg','.jpeg','.png','.webp','.heic'}
os.makedirs(UPLOAD_DIR,exist_ok=True); app=Flask(__name__); app.secret_key=os.getenv('SECRET_KEY','change-me'); app.config['MAX_CONTENT_LENGTH']=24*1024*1024
def db():
 c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c
def init_db():
 with db() as c:
  c.execute('CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,category TEXT,location TEXT NOT NULL,quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity>=0),expiry DATE,image TEXT,created_at TEXT NOT NULL)')
  cols={r[1] for r in c.execute('PRAGMA table_info(items)')}
  for n,d in {'barcode':'TEXT','brand':'TEXT','scan_confidence':'INTEGER DEFAULT 0'}.items():
   if n not in cols:c.execute(f'ALTER TABLE items ADD COLUMN {n} {d}')
init_db()
def days_left(expiry):
 if not expiry:return None
 try:return (datetime.strptime(expiry,'%Y-%m-%d').date()-date.today()).days
 except ValueError:return None
def save_upload(f,prefix='item'):
 if not f or not f.filename:return None,None
 ext=os.path.splitext(secure_filename(f.filename))[1].lower() or '.jpg'; ext=ext if ext in ALLOWED else '.jpg'; name=f'{prefix}-{uuid.uuid4().hex}{ext}'; path=os.path.join(UPLOAD_DIR,name); f.save(path)
 try:
  with Image.open(path) as im:
   im=ImageOps.exif_transpose(im); im.thumbnail((2200,2200)); im=im.convert('RGB');
   if ext not in {'.jpg','.jpeg','.png','.webp'}: name=f'{prefix}-{uuid.uuid4().hex}.jpg'; path=os.path.join(UPLOAD_DIR,name)
   im.save(path,quality=92)
 except Exception:pass
 return name,path
def scan_barcode(paths):
 for path in paths:
  if not path:continue
  try:
   with Image.open(path) as im:
    for v in [im.convert('RGB'),ImageOps.grayscale(im)]:
     codes=decode_barcode(v)
     if codes:return codes[0].data.decode('utf-8',errors='ignore').strip()
  except Exception:pass
 return ''
def lookup_product(barcode):
 if not barcode:return {}
 try:
  r=requests.get(OFF_URL.format(barcode=barcode),params={'fields':'product_name,product_name_da,brands,categories'},headers={'User-Agent':'Pantry/0.2.1 (github.com/dalhoj/pantry)'},timeout=8); r.raise_for_status(); p=r.json()
  if p.get('status')!=1:return {}
  x=p.get('product',{}); cats=x.get('categories','')
  return {'name':x.get('product_name_da') or x.get('product_name') or '','brand':x.get('brands') or '','category':cats.split(',')[0].strip() if cats else ''}
 except Exception:return {}
def normalize_year(y):
 y=int(y); return 2000+y if y<80 else (1900+y if y<100 else y)
def valid_date(d,m,y):
 try:v=date(normalize_year(y),int(m),int(d))
 except ValueError:return None
 return v.isoformat() if -365 <= (v-date.today()).days <= 3650 else None
def parse_dates(text):
 out=[]; text=text.upper().replace('Ø','O')
 for pat in [r'(?<!\d)(\d{1,2})[.\-/ ](\d{1,2})[.\-/ ](\d{2,4})(?!\d)',r'(?<!\d)(\d{2})(\d{2})(\d{2,4})(?!\d)']:
  for d,m,y in re.findall(pat,text):
   v=valid_date(d,m,y)
   if v and v not in out:out.append(v)
 return sorted(out,key=lambda v:abs((datetime.strptime(v,'%Y-%m-%d').date()-date.today()).days))
def ocr_expiry(path):
 if not path:return '', '',0
 texts=[]
 try:
  with Image.open(path) as im:
   im=ImageOps.exif_transpose(im).convert('L')
   if max(im.size)<3000:
    scale=min(3.0,3000/max(im.size)); im=im.resize((int(im.width*scale),int(im.height*scale)),Image.Resampling.LANCZOS)
   variants=[im,ImageEnhance.Contrast(im).enhance(2.6),ImageOps.autocontrast(im).filter(ImageFilter.SHARPEN),ImageOps.autocontrast(im).point(lambda p:255 if p>135 else 0),ImageOps.autocontrast(im).point(lambda p:255 if p>165 else 0)]
   configs=['--oem 1 --psm 6','--oem 1 --psm 11','--oem 1 --psm 7','--oem 1 --psm 11 -c tessedit_char_whitelist=0123456789./-:']
   for v in variants:
    for cfg in configs:
     t=pytesseract.image_to_string(v,config=cfg,lang='dan+eng')
     if t.strip():texts.append(t.strip())
 except Exception:return '', '',0
 combined='\n'.join(texts); dates=parse_dates(combined)
 if not dates:return '',combined[:1200],0
 marker=combined.upper().replace('Ø','O'); labels=['BEDST FOR','BEST BEFORE','MINDST HOLDBAR','SIDSTE ANVENDELSE','ANVENDES SENEST','USE BY','EXP','EXPIRY']
 return dates[0],combined[:1200],94 if any(x in marker for x in labels) else 78
@app.context_processor
def helpers():return {'days_left':days_left}
@app.get('/')
def index():
 with db() as c:items=c.execute("SELECT * FROM items WHERE quantity>0 ORDER BY CASE WHEN expiry IS NULL OR expiry='' THEN 1 ELSE 0 END,expiry,name").fetchall()
 stats={'total':sum(x['quantity'] for x in items),'soon':sum(x['quantity'] for x in items if days_left(x['expiry']) is not None and 0<=days_left(x['expiry'])<=3),'expired':sum(x['quantity'] for x in items if days_left(x['expiry']) is not None and days_left(x['expiry'])<0)}; return render_template('index.html',items=items,stats=stats)
@app.route('/scan',methods=['GET','POST'])
def scan():
 if request.method=='GET':return render_template('scan.html',result=None)
 pn,pp=save_upload(request.files.get('product_image'),'product'); dn,dp=save_upload(request.files.get('date_image'),'date')
 if not pp and not dp:flash('Tag mindst ét billede.'); return redirect(url_for('scan'))
 barcode=scan_barcode([pp,dp]); product=lookup_product(barcode); expiry,raw,dc=ocr_expiry(dp or pp); conf=(35 if barcode else 0)+(35 if product.get('name') else 0)+(30 if expiry else 0)
 return render_template('scan.html',result={'name':product.get('name',''),'brand':product.get('brand',''),'category':product.get('category',''),'barcode':barcode,'expiry':expiry,'image':pn or dn,'date_confidence':dc,'confidence':conf,'raw_ocr':raw})
@app.post('/add')
def add():
 name=request.form.get('name','').strip()
 if not name:flash('Navn er obligatorisk.');return redirect(request.referrer or '/')
 try:q=max(1,int(request.form.get('quantity','1'))); conf=max(0,min(100,int(request.form.get('scan_confidence','0'))))
 except ValueError:q,conf=1,0
 img=request.form.get('existing_image','').strip() or None; ni,_=save_upload(request.files.get('image'),'item'); img=ni or img
 with db() as c:c.execute('INSERT INTO items(name,category,location,quantity,expiry,image,created_at,barcode,brand,scan_confidence) VALUES(?,?,?,?,?,?,?,?,?,?)',(name,request.form.get('category','').strip(),request.form.get('location','Skab').strip(),q,request.form.get('expiry') or None,img,datetime.now().isoformat(),request.form.get('barcode','').strip(),request.form.get('brand','').strip(),conf))
 return redirect('/')
@app.post('/item/<int:i>/change')
def change(i):
 try:d=int(request.form.get('delta','0'))
 except:d=0
 with db() as c:c.execute('UPDATE items SET quantity=MAX(0,quantity+?) WHERE id=?',(d,i))
 return redirect('/')
@app.post('/item/<int:i>/delete')
def delete(i):
 with db() as c:r=c.execute('SELECT image FROM items WHERE id=?',(i,)).fetchone();c.execute('DELETE FROM items WHERE id=?',(i,))
 if r and r['image']:
  try:os.remove(os.path.join(UPLOAD_DIR,r['image']))
  except OSError:pass
 return redirect('/')
@app.get('/uploads/<path:name>')
def uploads(name):return send_from_directory(UPLOAD_DIR,name)
@app.get('/health')
def health():return {'status':'ok','version':'0.2.1'}
