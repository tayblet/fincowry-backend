# ================================================================
# FinCowry Trades — Flask Backend
# Handles: Sign Up, Log In, Log Out, Dashboard
# Database: PostgreSQL (via SQLAlchemy)
# ================================================================

from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import bcrypt
import os
from datetime import timedelta

app = Flask(__name__)

# ── Configuration ─────────────────────────────────────────────
# SECRET_KEY is used to encrypt session cookies.
# On Render, set this as an environment variable (we'll show you how).
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

# DATABASE_URL is provided automatically by Render's PostgreSQL.
# Locally it uses a simple SQLite file (no setup needed).
database_url = os.environ.get('DATABASE_URL', 'sqlite:///fincowry.db')

# Render gives Postgres URLs starting with "postgres://" but
# SQLAlchemy needs "postgresql://" — this line fixes that.
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Sessions last 7 days — users stay logged in
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# ── CORS ──────────────────────────────────────────────────────
# CORS = Cross-Origin Resource Sharing.
# Browsers block requests from one website to another by default.
# This tells Flask to ALLOW requests from your Netlify site.
# Replace the URL below with your actual Netlify URL.
CORS(app, supports_credentials=True, origins=[
    'http://localhost:5500',          # Local development
    'http://127.0.0.1:5500',          # Local development
    'https://heroic-meringue-3fc200.netlify.app',   # ← Replace with YOUR Netlify URL
])

db = SQLAlchemy(app)


# ── Database Model ─────────────────────────────────────────────
# This defines the "users" table in the database.
# Each attribute = one column in the table.
class User(db.Model):
    __tablename__ = 'users'

    id         = db.Column(db.Integer, primary_key=True)
    fullname   = db.Column(db.String(100), nullable=False)
    email      = db.Column(db.String(150), unique=True, nullable=False)
    password   = db.Column(db.String(200), nullable=False)  # stored as bcrypt hash
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def to_dict(self):
        """Return user data safe to send to the browser (no password)."""
        return {
            'id':        self.id,
            'fullname':  self.fullname,
            'email':     self.email,
            'joined':    self.created_at.strftime('%B %Y') if self.created_at else ''
        }


# ── Create tables on first run ─────────────────────────────────
with app.app_context():
    db.create_all()


# ── Routes ─────────────────────────────────────────────────────

@app.route('/')
def home():
    return jsonify({'status': 'FinCowry API is running ✅'})


# ── SIGN UP ───────────────────────────────────────────────────
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json()

    # Validate required fields
    fullname = data.get('fullname', '').strip()
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not fullname or not email or not password:
        return jsonify({'error': 'All fields are required.'}), 400

    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters.'}), 400

    # Check if email is already registered
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'An account with this email already exists.'}), 409

    # Hash the password — NEVER store plain text passwords.
    # bcrypt generates a random "salt" and combines it with the password.
    # Even if two users have the same password, the hashes are different.
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    # Save the new user to the database
    user = User(fullname=fullname, email=email, password=hashed.decode('utf-8'))
    db.session.add(user)
    db.session.commit()

    # Log the user in immediately after signup
    session.permanent = True
    session['user_id'] = user.id

    return jsonify({
        'message': 'Account created successfully!',
        'user': user.to_dict()
    }), 201


# ── LOG IN ────────────────────────────────────────────────────
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()

    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password are required.'}), 400

    # Find the user by email
    user = User.query.filter_by(email=email).first()

    # checkpw compares the plain password against the stored hash.
    # It returns True if they match.
    if not user or not bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
        # Give a vague error — don't reveal whether the email exists
        return jsonify({'error': 'Invalid email or password.'}), 401

    # Store user ID in the session cookie
    session.permanent = True
    session['user_id'] = user.id

    return jsonify({
        'message': 'Logged in successfully!',
        'user': user.to_dict()
    })


# ── LOG OUT ───────────────────────────────────────────────────
@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out.'})


# ── GET CURRENT USER (check if logged in) ────────────────────
@app.route('/api/me', methods=['GET'])
def me():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not logged in.'}), 401

    user = User.query.get(user_id)
    if not user:
        session.clear()
        return jsonify({'error': 'User not found.'}), 404

    return jsonify({'user': user.to_dict()})


# ── Run the app ───────────────────────────────────────────────
if __name__ == '__main__':
    # debug=True shows errors in the browser during development.
    # Render sets PORT automatically; we read it with os.environ.get.
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)

