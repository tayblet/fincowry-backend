# ================================================================
# FinCowry Trades — Flask Backend v5
# Fixes: JWT tokens (no cookie issues), email debugging, forgot pw
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

# ── Database ───────────────────────────────────────────────────
database_url = os.environ.get('DATABASE_URL', 'sqlite:///fincowry.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI']        = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ── CORS ───────────────────────────────────────────────────────
CORS(app,
     supports_credentials=True,
     origins=[
         'http://localhost:5500',
         'http://127.0.0.1:5500',
         'http://localhost:3000',
         'https://heroic-meringue-3fc200.netlify.app',
         'https://fincowry.netlify.app',
         'https://famous-pony-57cf10.netlify.app',
     ],
     allow_headers=['Content-Type', 'Authorization'],
     methods=['GET', 'POST', 'OPTIONS']
)

SITE_URL = os.environ.get('SITE_URL', 'https://famous-pony-57cf10.netlify.app')
db       = SQLAlchemy(app)


# ── Models ─────────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = 'users'
    id         = db.Column(db.Integer, primary_key=True)
    fullname   = db.Column(db.String(100), nullable=False)
    email      = db.Column(db.String(150), unique=True, nullable=False)
    phone      = db.Column(db.String(30))
    country    = db.Column(db.String(80))
    password   = db.Column(db.String(200), nullable=False)
    balance    = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':       self.id,
            'fullname': self.fullname,
            'email':    self.email,
            'phone':    self.phone or '',
            'country':  self.country or '',
            'balance':  float(self.balance or 0),
            'joined':   self.created_at.strftime('%B %Y') if self.created_at else ''
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


# ── JWT helpers ────────────────────────────────────────────────
def make_jwt(user_id):
    """Create a JWT token valid for 30 days."""
    payload = {
        'user_id': user_id,
        'exp':     datetime.now(timezone.utc) + timedelta(days=30),
        'iat':     datetime.now(timezone.utc)
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')


def decode_jwt(token):
    """Decode JWT. Returns user_id or None."""
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload.get('user_id')
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_current_user():
    """Get user from Authorization: Bearer <token> header."""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    token   = auth[7:]
    user_id = decode_jwt(token)
    if not user_id:
        return None
    return db.session.get(User, user_id)


# ── Email ──────────────────────────────────────────────────────
def send_email(to_email, subject, html_body):
    smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_USER', '')
    smtp_pass = os.environ.get('SMTP_PASS', '')

    if not smtp_user or not smtp_pass:
        print("⚠️  SMTP_USER or SMTP_PASS not set in Render env vars — skipping email")
        return False

    try:
        msg            = MIMEMultipart('alternative')
        msg['Subject'] = subject
        # FROM must match your Gmail address exactly
        msg['From']    = f'FinCowry Trades <{smtp_user}>'
        msg['To']      = to_email
        msg.attach(MIMEText(html_body, 'html'))

        print(f"📧 Sending email to {to_email} via {smtp_host}:{smtp_port} from {smtp_user}")

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())

        print(f"✅ Email sent to {to_email}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ Gmail auth failed. Check SMTP_USER/SMTP_PASS in Render. Make sure 2FA is ON and you are using an App Password. Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Email error: {type(e).__name__}: {e}")
        return False


def email_wrap(content):
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
      FinCowry Trades | 100523 US Highway 59, Sallisaw, OK 74955-4132, USA<br/>
      <a href="mailto:support@fincowry.com" style="color:#00d4aa;">support@fincowry.com</a>
    </p>
  </div>
</div></body></html>"""


# ── Routes ─────────────────────────────────────────────────────

@app.route('/')
def home():
    smtp_user = os.environ.get('SMTP_USER', 'NOT SET')
    smtp_pass = '✅ SET' if os.environ.get('SMTP_PASS') else '❌ NOT SET'
    return jsonify({
        'status':    'FinCowry API is running ✅',
        'smtp_user': smtp_user,
        'smtp_pass': smtp_pass,
        'site_url':  SITE_URL
    })


@app.route('/api/signup', methods=['POST'])
def signup():
    data     = request.get_json()
    fullname = data.get('fullname', '').strip()
    email    = data.get('email',    '').strip().lower()
    phone    = data.get('phone',    '').strip()
    country  = data.get('country',  '').strip()
    password = data.get('password', '')

    if not fullname or not email or not password:
        return jsonify({'error': 'Full name, email and password are required.'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters.'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'An account with this email already exists.'}), 409

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user   = User(fullname=fullname, email=email, phone=phone,
                  country=country, password=hashed)
    db.session.add(user)
    db.session.commit()

    token = make_jwt(user.id)

    # Welcome email
    try:
        body = f"""
        <h2 style="color:#f1f5f9;margin:0 0 16px;">Hello {fullname} 👋</h2>
        <p style="color:#94a3b8;line-height:1.7;">Welcome to <strong style="color:#00d4aa;">FinCowry Trades</strong>!
        Your account has been created successfully. Log in using the email and password you just set.</p>
        <div style="text-align:center;margin:28px 0;">
          <a href="{SITE_URL}/login.html" style="display:inline-block;background:#00d4aa;color:#0a0e1a;
             font-weight:700;font-size:1rem;padding:14px 36px;border-radius:8px;text-decoration:none;">
            Log In to Your Account →
          </a>
        </div>
        <p style="color:#94a3b8;margin:0;">
          Support: <a href="https://api.whatsapp.com/send/?phone=12723609064" style="color:#00d4aa;">WhatsApp +1 272 360 9064</a><br/>
          Email: <a href="mailto:support@fincowry.com" style="color:#00d4aa;">support@fincowry.com</a>
        </p>"""
        send_email(email, 'Welcome to FinCowry Trades — Your Account is Ready!', email_wrap(body))
    except Exception as e:
        print(f"Welcome email error: {e}")

    return jsonify({'message': 'Account created!', 'token': token, 'user': user.to_dict()}), 201


@app.route('/api/login', methods=['POST'])
def login():
    data     = request.get_json()
    email    = data.get('email',    '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password are required.'}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not bcrypt.checkpw(password.encode(), user.password.encode()):
        return jsonify({'error': 'Invalid email or password.'}), 401

    token = make_jwt(user.id)
    return jsonify({'message': 'Logged in!', 'token': token, 'user': user.to_dict()})


@app.route('/api/me', methods=['GET'])
def me():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in or token expired.'}), 401
    return jsonify({'user': user.to_dict()})


@app.route('/api/logout', methods=['POST'])
def logout():
    # JWT is stateless — client just deletes the token
    return jsonify({'message': 'Logged out.'})


@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    data  = request.get_json()
    email = data.get('email', '').strip().lower()
    if not email:
        return jsonify({'error': 'Email is required.'}), 400

    user = User.query.filter_by(email=email).first()
    if user:
        PasswordReset.query.filter_by(email=email).delete()
        db.session.commit()

        token      = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=1)
        db.session.add(PasswordReset(email=email, token=token, expires_at=expires_at))
        db.session.commit()

        reset_url = f"{SITE_URL}/reset-password.html?token={token}"
        body = f"""
        <h2 style="color:#f1f5f9;margin:0 0 16px;">Password Reset Request</h2>
        <p style="color:#94a3b8;line-height:1.7;">Hello {user.fullname},<br/><br/>
        We received a request to reset your FinCowry Trades password.
        Click the button below — this link expires in <strong style="color:#f59e0b;">1 hour</strong>.</p>
        <div style="text-align:center;margin:28px 0;">
          <a href="{reset_url}" style="display:inline-block;background:#00d4aa;color:#0a0e1a;
             font-weight:700;font-size:1rem;padding:14px 36px;border-radius:8px;text-decoration:none;">
            Reset My Password →
          </a>
        </div>
        <p style="color:#94a3b8;font-size:.85rem;">
          If you did not request this, ignore this email. Your password will not change.<br/>
          Direct link: <a href="{reset_url}" style="color:#00d4aa;word-break:break-all;">{reset_url}</a>
        </p>"""
        try:
            send_email(email, 'FinCowry Trades — Reset Your Password', email_wrap(body))
        except Exception as e:
            print(f"Reset email error: {e}")

    # Always return success (security: don't reveal if email exists)
    return jsonify({'message': 'If an account exists for this email, a reset link has been sent.'})


@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    data     = request.get_json()
    token    = data.get('token', '').strip()
    password = data.get('password', '')

    if not token or not password:
        return jsonify({'error': 'Token and password are required.'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters.'}), 400

    reset = PasswordReset.query.filter_by(token=token, used=False).first()
    if not reset:
        return jsonify({'error': 'Invalid or already used reset link.'}), 400
    if reset.expires_at < datetime.utcnow():
        return jsonify({'error': 'This link has expired. Please request a new one.'}), 400

    user = User.query.filter_by(email=reset.email).first()
    if not user:
        return jsonify({'error': 'Account not found.'}), 404

    user.password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    reset.used    = True
    db.session.commit()

    return jsonify({'message': 'Password reset successfully! You can now log in.'})


@app.route('/api/test-email', methods=['POST'])
def test_email():
    """Use this to verify your SMTP setup is working."""
    data = request.get_json()
    to   = data.get('email', '')
    if not to:
        return jsonify({'error': 'email required'}), 400

    smtp_user = os.environ.get('SMTP_USER', 'NOT SET')
    smtp_pass = os.environ.get('SMTP_PASS', '')
    smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = os.environ.get('SMTP_PORT', '587')

    result = send_email(
        to,
        'FinCowry Trades — Email Test ✅',
        email_wrap(f"""
        <h2 style="color:#f1f5f9;">Email is working! ✅</h2>
        <p style="color:#94a3b8;">Your SMTP is configured correctly.<br/><br/>
        Sent from: {smtp_user}<br/>
        Host: {smtp_host}:{smtp_port}</p>""")
    )
    return jsonify({
        'sent':          result,
        'smtp_user':     smtp_user,
        'smtp_host':     smtp_host,
        'smtp_port':     smtp_port,
        'smtp_pass_set': bool(smtp_pass)
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
