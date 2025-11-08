from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
import sqlite3
import json
import requests
from datetime import datetime, timedelta
from utils import generate_decoys, generate_decoy_message, send_email
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DATABASE = 'database.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        if not username or not email or not password:
            flash("All fields are required!")
            return redirect(url_for('register'))

        with get_db() as conn:
            cursor = conn.cursor()
            existing_user = cursor.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if existing_user:
            flash("Email is already registered!")
            return redirect(url_for('register'))

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (username, email, password_hash, failed_attempts, last_failed_attempt) 
                VALUES (?, ?, ?, 0, NULL)
            """, (username, email, hashed_password))
            conn.commit()
        
        with get_db() as conn:
            cursor = conn.cursor()
            decoys = generate_decoys(password)
            cursor.execute("SELECT id FROM users WHERE email = ?",(email,))
            user_id = cursor.fetchone()['id']
            cursor.execute("INSERT INTO decoy_passwords (user_id, real_password, decoy_passwords) VALUES (?, ?, ?)", (user_id, password, json.dumps(decoys)))
            conn.commit()
        flash("Registration successful!")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        with get_db() as conn:
            cursor = conn.cursor()
            user = cursor.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if user:
             with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT decoy_passwords FROM decoy_passwords WHERE user_id = ?",(user['id'],))
                decoy_passwords = cursor.fetchone()
                if decoy_passwords:
                    decoys = json.loads(decoy_passwords['decoy_passwords'])
                else:
                    decoys = []
             if password in decoys:
                flash("Login Successful!")
                reset_token = generate_password_hash(email + str(datetime.utcnow()), method='pbkdf2:sha256')
                reset_url = url_for('reset_password', token=reset_token, _external=True)
                send_email("Account Under Attack", email, f"Your account has been accessed using a decoy password. Change your password immediately using this link: {reset_url}")
                
                expiration_time = datetime.now() + timedelta(hours=1)
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE users SET reset_token = ?, reset_token_expiration = ? WHERE email = ?", 
                               (reset_token, expiration_time, email))
                    conn.commit()
                
                session['decoy_username'] = user['username']
                session['decoy_email'] = user['email']
                return redirect(url_for('decoy_dashboard'))

             if user['failed_attempts'] >= 3:
                flash("Account locked due to multiple failed login attempts. Check your email.")
                reset_token = generate_password_hash(email + str(datetime.utcnow()), method='pbkdf2:sha256')
                reset_url = url_for('reset_password', token=reset_token, _external=True)
                send_email("Account Under Attack", email, f"Your account has been locked. Change your password immediately using this link: {reset_url}")

                expiration_time = datetime.now() + timedelta(hours=1)
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE users SET reset_token = ?, reset_token_expiration = ? WHERE email = ?", 
                               (reset_token, expiration_time, email))
                    conn.commit()
                return redirect(url_for('forgot_password'))

             if check_password_hash(user['password_hash'], password):
                session['user_id'] = user['id']
                session['email'] = user['email']
                session['username'] = user['username']
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE users SET failed_attempts = 0 WHERE email = ?", (email,))
                    conn.commit()
                return redirect(url_for('dashboard'))
             else:
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE users SET failed_attempts = failed_attempts + 1 WHERE email = ?", (email,))
                    conn.commit()
                flash("Invalid credentials!")
        else:
            flash("No account found with this email.")
    return render_template('login.html')


@app.route('/subscribe', methods=['POST'])
def subscribe():
    if request.method == 'POST':
        email = request.form['email']
        
        if not email:
             flash("All fields are required!")
             return redirect(url_for('login'))
             
        with get_db() as conn:
            cursor = conn.cursor()
            existing_subscriber = cursor.execute("SELECT * FROM subscribers WHERE email = ?", (email,)).fetchone()

        if existing_subscriber:
            flash("You are already subscribed.")
        else:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO subscribers (email) VALUES (?)", (email,))
                conn.commit()
            
                send_email("Subscription Confirmation", email, "Thank you for subscribing to our newsletter! You'll now receive updates and news from us.")
            
                flash("Subscription successful! Check your email for confirmation.")
    return redirect(url_for('login'))


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']

        with get_db() as conn:
            cursor = conn.cursor()
            user = cursor.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if user:
            reset_token = generate_password_hash(email + str(datetime.utcnow()), method='pbkdf2:sha256')
            reset_url = url_for('reset_password', token=reset_token, _external=True)
            send_email("Password Recovery", email, f"Click the link to reset your password: {reset_url}")

            expiration_time = datetime.now() + timedelta(hours=1)
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET reset_token = ?, reset_token_expiration = ? WHERE email = ?", 
                               (reset_token, expiration_time, email))
                conn.commit()

            flash("Password recovery instructions have been sent to your email.")
        else:
            flash("No account found with that email address.")

        return redirect(url_for('login'))
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash("Passwords do not match!")
            return redirect(request.url)

        with get_db() as conn:
            cursor = conn.cursor()
            user = cursor.execute("SELECT * FROM users WHERE reset_token = ? AND reset_token_expiration > ?", 
                                  (token, datetime.now())).fetchone()

        if user:
            hashed_password = generate_password_hash(password)
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_expiration = NULL WHERE id = ?", 
                               (hashed_password, user['id']))
                conn.commit()

                cursor.execute("UPDATE decoy_passwords SET real_password = ? WHERE user_id = ?", (password,user['id']))
                conn.commit()
            flash("Password reset successful!")
            return redirect(url_for('login'))
        else:
            flash("Invalid or expired token.")
            return redirect(url_for('forgot_password'))

    return render_template('reset_password.html', token=token)


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')


@app.route('/send-message', methods=['GET', 'POST'])
def send_message():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        recipient_email = request.form['recipient_email']
        message = request.form['message']
        
        file = request.files['file']

        with get_db() as conn:
            cursor = conn.cursor()
            recipient = cursor.execute("SELECT * FROM users WHERE email = ?", (recipient_email,)).fetchone()

        if not recipient:
            flash("Recipient email not found!")
            return redirect(url_for('send_message'))

        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
        else:
            filename = None

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO messages (sender_id, receiver_id, message, file_name) VALUES (?, ?, ?, ?)", 
                           (session['user_id'], recipient['id'], message, filename))
            conn.commit()
        flash("Message sent successfully!")
        return redirect(url_for('dashboard'))
    return render_template('send_message.html')


@app.route('/inbox')
def inbox():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    with get_db() as conn:
        cursor = conn.cursor()
        messages = cursor.execute("""
            SELECT m.id, u.email AS sender, m.message, m.file_name
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.receiver_id = ?""", (session['user_id'],)).fetchall()
    return render_template('inbox.html', messages=messages)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/decoy_dashboard')
def decoy_dashboard():
    username = session.get('decoy_username')
    email = session.get('decoy_email')
    return render_template('decoy_dashboard.html', username=username, email=email)

@app.route('/decoy_page')
def decoy_page():
    email = session.get('decoy_email')
    if not email:
        flash("No email found in session. Cannot generate decoy messages.")
        return redirect(url_for('decoy_dashboard'))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.id, u.email AS sender, m.message, m.file_name
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            JOIN users receiver ON m.receiver_id = receiver.id
            WHERE receiver.email = ?
            ORDER BY m.id DESC
            LIMIT 3
        """, (email,))
        messages = cursor.fetchall()

    decoy_messages = []
    for message in messages:
        decoy_message_text = generate_decoy_message(message['message'])
        decoy_messages.append({
            'sender': message['sender'],
            'message': decoy_message_text
        })

    return render_template('decoy_page.html', decoy_messages=decoy_messages)

@app.route('/decoy_send_message')
def decoy_send_message():
    return render_template('decoy_send_message.html')

def setup_database():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                failed_attempts INTEGER DEFAULT 0,
                last_failed_attempt TEXT,
                reset_token TEXT,
                reset_token_expiration TEXT,
                encrypted_data TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                receiver_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                file_name TEXT,
                FOREIGN KEY (sender_id) REFERENCES users (id),
                FOREIGN KEY (receiver_id) REFERENCES users (id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decoy_passwords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                real_password TEXT NOT NULL,
                decoy_passwords TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL
            )
        """)
        conn.commit()


if __name__ == '__main__':
    setup_database()
    app.run(debug=True)