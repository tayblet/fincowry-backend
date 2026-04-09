# ================================================================
# FinCowry Trades — Flask Backend v4
# Fixes: email sending, forgot password, persistent login
# ================================================================

from flask import Flask, request, jsonify, session, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import bcrypt
import os
import smtplib
import secrets
import string
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import timedelta, datetime

app = Flask(__name__)

app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

app.config.update(
    SESSION_COOKIE_HTTPONLY   = True,
    SESSION_COOKIE_SECURE     = True,
    SESSION_COOKIE_SAMESITE   = 'None',
    SESSION_COOKIE_NAME       = 'fincowry_session',
    PERMANENT_SESSION_LIFETIME = timedelta(days=30),
    SESSION_REFRESH_EACH_REQUEST = True,
)

database_url = os.environ.get('DATABASE_URL', 'sqlite:///fincowry.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI']        = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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

db = SQLAlchemy(app)

# ── Your Netlify URL (used in email links) ─────────────────────
SITE_URL = os.environ.get('SITE_URL', 'https://famous-pony-57cf10.netlify.app')


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
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self):
        return {
            'id':       self.id,
            'fullname': self.fullname,
            'email':    self.email,
            'phone':    self.phone or '',
            'country':  self.country or '',
            'balance':  self.balance or 0.0,
            'joined':   self.created_at.strftime('%B %Y') if self.created_at else ''
        }


class PasswordReset(db.Model):
    __tablename__ = 'password_resets'
    id         = db.Column(db.Integer, primary_key=True)
    email      = db.Column(db.String(150), nullable=False)
    token      = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used       = db.Column(db.Boolean, default=False)


with app.app_context():
    db.create_all()


# ── Email Helper ───────────────────────────────────────────────
def send_email(to_email, subject, html_body):
    """Send email via SMTP. Uses env vars set in Render."""
    smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_USER', '')
    smtp_pass = os.environ.get('SMTP_PASS', '')

    if not smtp_user or not smtp_pass:
        print("SMTP not configured — skipping email")
        return False

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        # Send FROM your real Gmail, but display FinCowry name
        msg['From']    = f'FinCowry Trades <{smtp_user}>'
        msg['To']      = to_email
        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())
        print(f"Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


def email_html_wrapper(title, content):
    """Shared email template wrapper."""
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"/></head>
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
      <a href="mailto:support@fincowry.com" style="color:#00d4aa;">support@fincowry.com</a> |
      <a href="{SITE_URL}" style="color:#00d4aa;">{SITE_URL}</a>
    </p>
  </div>
</div>
</body></html>"""


def send_welcome_email(to_email, fullname):
    content = f"""
    <h2 style="color:#f1f5f9;font-size:1.4rem;margin:0 0 16px;">Hello {fullname} 👋</h2>
    <p style="color:#94a3b8;line-height:1.7;margin:0 0 16px;">
      Welcome to <strong style="color:#00d4aa;">FinCowry Trades</strong>!
      Your account has been created successfully.
    </p>
    <div style="background:#0a0e1a;border:1px solid #1e293b;border-radius:10px;padding:20px;margin:20px 0;">
      <p style="color:#f1f5f9;font-weight:700;margin:0 0 12px;">Before you start:</p>
      <p style="color:#94a3b8;line-height:1.7;margin:0 0 10px;">
        1. Log in using the email and password you registered with.
      </p>
      <p style="color:#94a3b8;line-height:1.7;margin:0 0 10px;">
        2. Explore our <strong style="color:#00d4aa;">Plans</strong> page to choose the right trading tier.
      </p>
      <p style="color:#94a3b8;line-height:1.7;margin:0;">
        3. Our support team is available <strong style="color:#00d4aa;">24/7</strong> via WhatsApp:
        <strong style="color:#00d4aa;">+1 272 360 9064</strong>
      </p>
    </div>
    <div style="text-align:center;margin:28px 0;">
      <a href="{SITE_URL}/login.html"
         style="display:inline-block;background:#00d4aa;color:#0a0e1a;font-weight:700;
                font-size:1rem;padding:14px 36px;border-radius:8px;text-decoration:none;">
        Log In to Your Account →
      </a>
    </div>
    <p style="color:#94a3b8;margin:0;">
      We wish you profitable trading!<br/>
      <strong style="color:#00d4aa;">The FinCowry Trades Team</strong>
    </p>"""
    send_email(to_email, 'Welcome to FinCowry Trades — Your Account is Ready!',
               email_html_wrapper('Welcome', content))


def send_reset_email(to_email, fullname, token):
    reset_url = f"{SITE_URL}/reset-password.html?token={token}"
    content = f"""
    <h2 style="color:#f1f5f9;font-size:1.3rem;margin:0 0 16px;">Password Reset Request</h2>
    <p style="color:#94a3b8;line-height:1.7;margin:0 0 16px;">
      Hello {fullname}, we received a request to reset your FinCowry Trades password.
      Click the button below to set a new password. This link expires in <strong style="color:#f59e0b;">1 hour</strong>.
    </p>
    <div style="text-align:center;margin:28px 0;">
      <a href="{reset_url}"
         style="display:inline-block;background:#00d4aa;color:#0a0e1a;font-weight:700;
                font-size:1rem;padding:14px 36px;border-radius:8px;text-decoration:none;">
        Reset My Password →
      </a>
    </div>
    <p style="color:#94a3b8;font-size:.85rem;margin:16px 0 0;">
      If you did not request this, please ignore this email. Your password will not change.<br/><br/>
      Or copy this link: <a href="{reset_url}" style="color:#00d4aa;word-break:break-all;">{reset_url}</a>
    </p>"""
    send_email(to_email, 'FinCowry Trades — Reset Your Password',
               email_html_wrapper('Password Reset', content))


# ── Routes ─────────────────────────────────────────────────────

@app.route('/')
def home():
    return jsonify({'status': 'FinCowry API is running ✅'})


@app.route('/api/signup', methods=['POST'])
def signup():
    data     = request.get_json()
    fullname = data.get('fullname', '').strip()
    email    = data.get('email', '').strip().lower()
    phone    = data.get('phone', '').strip()
    country  = data.get('country', '').strip()
    password = data.get('password', '')

    if not fullname or not email or not password:
        return jsonify({'error': 'Full name, email and password are required.'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters.'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'An account with this email already exists.'}), 409

    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    user   = User(fullname=fullname, email=email, phone=phone,
                  country=country, password=hashed.decode('utf-8'))
    db.session.add(user)
    db.session.commit()

    session.permanent = True
    session['user_id'] = user.id

    # Send welcome email in background (don't crash if it fails)
    try:
        send_welcome_email(email, fullname)
    except Exception as e:
        print(f"Welcome email failed: {e}")

    return make_response(jsonify({
        'message': 'Account created successfully!',
        'user': user.to_dict()
    }), 201)


@app.route('/api/login', methods=['POST'])
def login():
    data     = request.get_json()
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password are required.'}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'error': 'Invalid email or password.'}), 401
    if not bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
        return jsonify({'error': 'Invalid email or password.'}), 401

    session.permanent = True
    session['user_id'] = user.id

    return make_response(jsonify({
        'message': 'Logged in successfully!',
        'user': user.to_dict()
    }))


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out.'})


@app.route('/api/me', methods=['GET'])
def me():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not logged in.'}), 401
    user = db.session.get(User, user_id)
    if not user:
        session.clear()
        return jsonify({'error': 'User not found.'}), 404
    return jsonify({'user': user.to_dict()})


@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    data  = request.get_json()
    email = data.get('email', '').strip().lower()

    if not email:
        return jsonify({'error': 'Email is required.'}), 400

    user = User.query.filter_by(email=email).first()

    # Always return success — never reveal if email exists (security)
    if user:
        # Delete any existing tokens for this email
        PasswordReset.query.filter_by(email=email).delete()
        db.session.commit()

        token      = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(hours=1)
        reset      = PasswordReset(email=email, token=token, expires_at=expires_at)
        db.session.add(reset)
        db.session.commit()

        try:
            send_reset_email(email, user.fullname, token)
        except Exception as e:
            print(f"Reset email failed: {e}")

    return jsonify({'message': 'If an account exists for this email, a reset link has been sent.'})


@app.route('/api/reset-password', methods=['POST'])
def reset_password():
    data     = request.get_json()
    token    = data.get('token', '').strip()
    password = data.get('password', '')

    if not token or not password:
        return jsonify({'error': 'Token and new password are required.'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters.'}), 400

    reset = PasswordReset.query.filter_by(token=token, used=False).first()

    if not reset:
        return jsonify({'error': 'Invalid or expired reset link.'}), 400
    if reset.expires_at < datetime.utcnow():
        return jsonify({'error': 'This reset link has expired. Please request a new one.'}), 400

    user = User.query.filter_by(email=reset.email).first()
    if not user:
        return jsonify({'error': 'Account not found.'}), 404

    hashed       = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    user.password = hashed.decode('utf-8')
    reset.used    = True
    db.session.commit()

    return jsonify({'message': 'Password reset successfully! You can now log in.'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
