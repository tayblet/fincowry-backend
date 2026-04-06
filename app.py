# ================================================================
# FinCowry Trades — Flask Backend v2
# ================================================================

from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
import bcrypt
import os
from datetime import timedelta

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fincowry-dev-secret-2025')
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True

database_url = os.environ.get('DATABASE_URL', 'sqlite:///fincowry.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

CORS(app, supports_credentials=True, origins=[
    'http://localhost:5500',
    'http://127.0.0.1:5500',
    'http://localhost:3000',
    'https://heroic-meringue-3fc200.netlify.app',
    'https://fincowry.netlify.app',
    'https://famous-pony-57cf10.netlify.app',

])

db = SQLAlchemy(app)


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


with app.app_context():
    db.create_all()


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
    user = User(fullname=fullname, email=email, phone=phone,
                country=country, password=hashed.decode('utf-8'))
    db.session.add(user)
    db.session.commit()

    session.permanent = True
    session['user_id'] = user.id

    return jsonify({'message': 'Account created successfully!', 'user': user.to_dict()}), 201


@app.route('/api/login', methods=['POST'])
def login():
    data     = request.get_json()
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password are required.'}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
        return jsonify({'error': 'Invalid email or password.'}), 401

    session.permanent = True
    session['user_id'] = user.id

    return jsonify({'message': 'Logged in successfully!', 'user': user.to_dict()})


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


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
