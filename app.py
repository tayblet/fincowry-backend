# ================================================================
# FinCowry Trades — Flask Backend v6
# ================================================================

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import bcrypt, os, smtplib, secrets, jwt
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))

database_url = os.environ.get('DATABASE_URL', 'sqlite:///fincowry.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI']        = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

CORS(app, supports_credentials=True, origins=[
    'http://localhost:5500','http://127.0.0.1:5500','http://localhost:3000',
    'https://heroic-meringue-3fc200.netlify.app',
    'https://fincowry.netlify.app',
    'https://famous-pony-57cf10.netlify.app',
    'https://moonlit-jelly-fca06c.netlify.app',
], allow_headers=['Content-Type','Authorization'], methods=['GET','POST','OPTIONS'])

SITE_URL = os.environ.get('SITE_URL', 'https://moonlit-jelly-fca06c.netlify.app')
ADMIN_EMAIL = os.environ.get('SMTP_USER', '')   # messages go to this Gmail
db = SQLAlchemy(app)

# JWT expiry: 7 days (not 30 — more secure, auto-refresh on activity)
JWT_EXPIRY_DAYS = 7

# ── Models ─────────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = 'users'
    id               = db.Column(db.Integer, primary_key=True)
    fullname         = db.Column(db.String(100), nullable=False)
    email            = db.Column(db.String(150), unique=True, nullable=False)
    phone            = db.Column(db.String(30))
    country          = db.Column(db.String(80))
    password         = db.Column(db.String(200), nullable=False)
    balance          = db.Column(db.Float, default=0.0)
    email_verified   = db.Column(db.Boolean, default=False)
    verify_token     = db.Column(db.String(100))
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':             self.id,
            'fullname':       self.fullname,
            'email':          self.email,
            'phone':          self.phone or '',
            'country':        self.country or '',
            'balance':        float(self.balance or 0),
            'email_verified': self.email_verified,
            'joined':         self.created_at.strftime('%B %Y') if self.created_at else ''
        }

class PasswordReset(db.Model):
    __tablename__ = 'password_resets'
    id         = db.Column(db.Integer, primary_key=True)
    email      = db.Column(db.String(150), nullable=False)
    token      = db.Column(db.String(100), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used       = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

# ── JWT ────────────────────────────────────────────────────────
def make_jwt(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
        'iat': datetime.now(timezone.utc)
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

def get_user_from_request():
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    try:
        payload = jwt.decode(auth[7:], app.config['SECRET_KEY'], algorithms=['HS256'])
        return db.session.get(User, payload.get('user_id'))
    except:
        return None

# ── Email ──────────────────────────────────────────────────────
def send_email(to_email, subject, html_body, reply_to=None):
    host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    port = int(os.environ.get('SMTP_PORT', 587))
    user = os.environ.get('SMTP_USER', '')
    pwd  = os.environ.get('SMTP_PASS', '')
    if not user or not pwd:
        print("⚠️ SMTP not configured"); return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f'FinCowry Trades <{user}>'
        msg['To']      = to_email
        if reply_to:
            msg['Reply-To'] = reply_to   # so you can reply directly to the sender
        msg.attach(MIMEText(html_body, 'html'))
        with smtplib.SMTP(host, port) as s:
            s.ehlo(); s.starttls(); s.ehlo()
            s.login(user, pwd)
            s.sendmail(user, to_email, msg.as_string())
        print(f"✅ Email sent to {to_email}"); return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ SMTP Auth error: {e}"); return False
    except Exception as e:
        print(f"❌ Email error: {type(e).__name__}: {e}"); return False

def wrap(content):
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#0a0e1a;font-family:'Segoe UI',Arial,sans-serif;">
<div style="max-width:600px;margin:40px auto;background:#111827;border-radius:16px;overflow:hidden;border:1px solid #1e293b;">
  <div style="background:linear-gradient(135deg,#0d1f3c,#0a1a2e);padding:36px 32px;text-align:center;">
    <h1 style="color:#00d4aa;font-size:1.8rem;margin:0;font-weight:800;">FinCowry Trades</h1>
    <p style="color:#94a3b8;margin:6px 0 0;font-size:.9rem;">Smart Trading for Modern Investors</p>
  </div>
  <div style="padding:36px 32px;">{content}</div>
  <div style="background:#0a0e1a;padding:18px 32px;text-align:center;border-top:1px solid #1e293b;">
    <p style="color:#475569;font-size:.75rem;margin:0;">
      FinCowry Trades | 100523 US Highway 59, Sallisaw OK 74955-4132, USA<br/>
      <a href="mailto:support@fincowry.com" style="color:#00d4aa;">support@fincowry.com</a>
    </p>
  </div>
</div></body></html>"""

# ── Routes ─────────────────────────────────────────────────────
@app.route('/')
def home():
    user = os.environ.get('SMTP_USER','NOT SET')
    pw   = '✅ SET' if os.environ.get('SMTP_PASS') else '❌ NOT SET'
    return jsonify({'status':'FinCowry API ✅','smtp_user':user,'smtp_pass':pw,'site':SITE_URL})

@app.route('/api/signup', methods=['POST'])
def signup():
    d        = request.get_json()
    fullname = d.get('fullname','').strip()
    email    = d.get('email','').strip().lower()
    phone    = d.get('phone','').strip()
    country  = d.get('country','').strip()
    password = d.get('password','')
    if not fullname or not email or not password:
        return jsonify({'error':'Full name, email and password are required.'}), 400
    if len(password) < 6:
        return jsonify({'error':'Password must be at least 6 characters.'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error':'An account with this email already exists.'}), 409

    hashed       = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    verify_token = secrets.token_urlsafe(32)
    user         = User(fullname=fullname, email=email, phone=phone,
                        country=country, password=hashed, verify_token=verify_token)
    db.session.add(user); db.session.commit()
    token = make_jwt(user.id)

    # Send verification + welcome email
    verify_url = f"{SITE_URL}/verify-email.html?token={verify_token}"
    body = f"""
    <h2 style="color:#f1f5f9;margin:0 0 16px;">Hello {fullname} 👋</h2>
    <p style="color:#94a3b8;line-height:1.7;">Welcome to <strong style="color:#00d4aa;">FinCowry Trades</strong>!
    Your account is active. Please verify your email address to unlock all features.</p>
    <div style="background:rgba(0,212,170,.08);border:1px solid rgba(0,212,170,.2);border-radius:10px;padding:20px;margin:20px 0;">
      <p style="color:#f1f5f9;font-weight:700;margin:0 0 10px;">⚠️ Verify your email address</p>
      <p style="color:#94a3b8;margin:0;">Click the button below to confirm your email. This keeps your account secure.</p>
    </div>
    <div style="text-align:center;margin:28px 0;">
      <a href="{verify_url}" style="display:inline-block;background:#00d4aa;color:#0a0e1a;
         font-weight:700;font-size:1rem;padding:14px 36px;border-radius:8px;text-decoration:none;">
        ✅ Verify My Email →
      </a>
    </div>
    <p style="color:#94a3b8;font-size:.85rem;">Or copy: <a href="{verify_url}" style="color:#00d4aa;word-break:break-all;">{verify_url}</a></p>
    <p style="color:#94a3b8;margin-top:20px;">
      WhatsApp support: <a href="https://api.whatsapp.com/send/?phone=12723609064" style="color:#00d4aa;">+1 272 360 9064</a>
    </p>"""
    try: send_email(email, 'FinCowry Trades — Welcome! Please Verify Your Email', wrap(body))
    except Exception as e: print(f"Welcome email error: {e}")

    return jsonify({'message':'Account created!','token':token,'user':user.to_dict()}), 201

@app.route('/api/login', methods=['POST'])
def login():
    d        = request.get_json()
    email    = d.get('email','').strip().lower()
    password = d.get('password','')
    if not email or not password:
        return jsonify({'error':'Email and password are required.'}), 400
    user = User.query.filter_by(email=email).first()
    if not user or not bcrypt.checkpw(password.encode(), user.password.encode()):
        return jsonify({'error':'Invalid email or password.'}), 401
    token = make_jwt(user.id)
    return jsonify({'message':'Logged in!','token':token,'user':user.to_dict()})

@app.route('/api/me', methods=['GET'])
def me():
    user = get_user_from_request()
    if not user: return jsonify({'error':'Not logged in.'}), 401
    # Refresh token (extends session on activity)
    new_token = make_jwt(user.id)
    return jsonify({'user':user.to_dict(),'token':new_token})

@app.route('/api/logout', methods=['POST'])
def logout():
    return jsonify({'message':'Logged out.'})

@app.route('/api/verify-email', methods=['POST'])
def verify_email():
    token = request.get_json().get('token','').strip()
    user  = User.query.filter_by(verify_token=token).first()
    if not user: return jsonify({'error':'Invalid verification link.'}), 400
    user.email_verified = True
    user.verify_token   = None
    db.session.commit()
    return jsonify({'message':'Email verified! Your account is fully activated.'})

@app.route('/api/update-profile', methods=['POST'])
def update_profile():
    user = get_user_from_request()
    if not user: return jsonify({'error':'Not logged in.'}), 401
    d = request.get_json()

    new_email = d.get('email','').strip().lower()
    new_name  = d.get('fullname','').strip()
    new_phone = d.get('phone','').strip()
    new_country = d.get('country','').strip()

    # Email change — requires re-verification
    if new_email and new_email != user.email:
        existing = User.query.filter_by(email=new_email).first()
        if existing: return jsonify({'error':'This email is already in use.'}), 409
        user.email          = new_email
        user.email_verified = False
        user.verify_token   = secrets.token_urlsafe(32)
        verify_url = f"{SITE_URL}/verify-email.html?token={user.verify_token}"
        body = f"""<h2 style="color:#f1f5f9;">Verify your new email</h2>
        <p style="color:#94a3b8;">Your email has been updated. Please verify your new address.</p>
        <div style="text-align:center;margin:24px 0;">
          <a href="{verify_url}" style="background:#00d4aa;color:#0a0e1a;font-weight:700;
             padding:14px 32px;border-radius:8px;text-decoration:none;display:inline-block;">
            Verify New Email →
          </a>
        </div>"""
        try: send_email(new_email, 'FinCowry Trades — Verify Your New Email', wrap(body))
        except: pass

    if new_name:    user.fullname = new_name
    if new_phone:   user.phone    = new_phone
    if new_country: user.country  = new_country
    db.session.commit()

    new_token = make_jwt(user.id)
    return jsonify({'message':'Profile updated!','user':user.to_dict(),'token':new_token})

@app.route('/api/change-password', methods=['POST'])
def change_password():
    user = get_user_from_request()
    if not user: return jsonify({'error':'Not logged in.'}), 401
    d           = request.get_json()
    current_pw  = d.get('current_password','')
    new_pw      = d.get('new_password','')
    if not bcrypt.checkpw(current_pw.encode(), user.password.encode()):
        return jsonify({'error':'Current password is incorrect.'}), 401
    if len(new_pw) < 6:
        return jsonify({'error':'New password must be at least 6 characters.'}), 400
    user.password = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
    db.session.commit()
    return jsonify({'message':'Password changed successfully!'})

@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    email = request.get_json().get('email','').strip().lower()
    if not email: return jsonify({'error':'Email is required.'}), 400
    user = User.query.filter_by(email=email).first()
    if user:
        PasswordReset.query.filter_by(email=email).delete(); db.session.commit()
        token      = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=1)
        db.session.add(PasswordReset(email=email, token=token, expires_at=expires_at))
        db.session.commit()
        reset_url = f"{SITE_URL}/reset-password.html?token={token}"
        body = f"""<h2 style="color:#f1f5f9;margin:0 0 16px;">Password Reset</h2>
        <p style="color:#94a3b8;line-height:1.7;">Hello {user.fullname}, click below to reset your password.
        Link expires in <strong style="color:#f59e0b;">1 hour</strong>.</p>
        <div style="text-align:center;margin:28px 0;">
          <a href="{reset_url}" style="background:#00d4aa;color:#0a0e1a;font-weight:700;
             padding:14px 36px;border-radius:8px;text-decoration:none;display:inline-block;">
            Reset My Password →
          </a>
        </div>
        <p style="color:#94a3b8;font-size:.85rem;">
          Didn't request this? Ignore this email.<br/>
          Link: <a href="{reset_url}" style="color:#00d4aa;word-break:break-all;">{reset_url}</a>
        </p>"""
        try: send_email(email, 'FinCowry Trades — Reset Your Password', wrap(body))
        except Exception as e: print(f"Reset email error: {e}")
    return jsonify({'message':'If an account exists, a reset link has been sent.'})

@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    d        = request.get_json()
    token    = d.get('token','').strip()
    password = d.get('password','')
    if not token or not password: return jsonify({'error':'Token and password required.'}), 400
    if len(password) < 6: return jsonify({'error':'Password must be at least 6 characters.'}), 400
    reset = PasswordReset.query.filter_by(token=token, used=False).first()
    if not reset: return jsonify({'error':'Invalid or already used link.'}), 400
    if reset.expires_at < datetime.utcnow(): return jsonify({'error':'Link expired. Request a new one.'}), 400
    user = User.query.filter_by(email=reset.email).first()
    if not user: return jsonify({'error':'Account not found.'}), 404
    user.password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    reset.used    = True; db.session.commit()
    return jsonify({'message':'Password reset! You can now log in.'})

@app.route('/api/contact', methods=['POST'])
def contact():
    """Receive contact form and email it to admin."""
    d       = request.get_json()
    name    = d.get('name','').strip()
    email   = d.get('email','').strip()
    subject = d.get('subject','General Enquiry')
    message = d.get('message','').strip()
    if not name or not email or not message:
        return jsonify({'error':'Name, email and message are required.'}), 400
    admin = os.environ.get('SMTP_USER','')
    if not admin: return jsonify({'message':'Message received! We will be in touch soon.'})
    body = f"""
    <h2 style="color:#f1f5f9;margin:0 0 16px;">New Contact Form Message</h2>
    <div style="background:#0a0e1a;border:1px solid #1e293b;border-radius:10px;padding:20px;margin-bottom:20px;">
      <p style="color:#94a3b8;margin:0 0 8px;"><strong style="color:#f1f5f9;">From:</strong> {name}</p>
      <p style="color:#94a3b8;margin:0 0 8px;"><strong style="color:#f1f5f9;">Email:</strong>
        <a href="mailto:{email}" style="color:#00d4aa;">{email}</a></p>
      <p style="color:#94a3b8;margin:0 0 8px;"><strong style="color:#f1f5f9;">Subject:</strong> {subject}</p>
      <p style="color:#94a3b8;margin:0;"><strong style="color:#f1f5f9;">Message:</strong><br/>{message}</p>
    </div>
    <p style="color:#94a3b8;font-size:.85rem;">Reply directly to: <a href="mailto:{email}" style="color:#00d4aa;">{email}</a></p>"""
    ok = send_email(admin, f'FinCowry Contact: {subject} — from {name}', wrap(body), reply_to=email)
    # Also send auto-reply to sender
    auto = f"""
    <h2 style="color:#f1f5f9;">Message Received ✅</h2>
    <p style="color:#94a3b8;line-height:1.7;">Hello {name},<br/><br/>
    Thank you for contacting FinCowry Trades. We have received your message and will
    respond within <strong style="color:#00d4aa;">24 hours</strong>.<br/><br/>
    For urgent help, message us on WhatsApp:
    <a href="https://api.whatsapp.com/send/?phone=12723609064" style="color:#00d4aa;">+1 272 360 9064</a>
    </p>"""
    try: send_email(email, 'FinCowry Trades — We received your message', wrap(auto))
    except: pass
    return jsonify({'message':'Message sent! We will reply to your email shortly.' if ok else 'Message received!'})

@app.route('/api/test-email', methods=['POST'])
def test_email():
    to   = request.get_json().get('email','')
    user = os.environ.get('SMTP_USER','NOT SET')
    pw   = bool(os.environ.get('SMTP_PASS'))
    ok   = send_email(to, 'FinCowry — Email Test ✅',
                      wrap(f'<h2 style="color:#f1f5f9;">Email working! ✅</h2><p style="color:#94a3b8;">Sent from: {user}</p>')) if to else False
    return jsonify({'sent':ok,'smtp_user':user,'smtp_pass_set':pw})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
