from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
import sqlite3
import json
import random
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from utils import honey_decrypt,honey_encrypt,send_email

app = Flask(__name__)
app.secret_key = 'secure_key'
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DATABASE = 'database.db'
app.jinja_env.globals.update(honey_decrypt=honey_decrypt)
app.jinja_env.filters['honey_decrypt'] = honey_decrypt



#database connection
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


#routes
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        with get_db() as conn:
            cursor = conn.cursor()
            existing_user = cursor.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if existing_user:
            flash("Email is already registered!")
            return redirect(url_for('register'))

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (email, password_hash, failed_attempts, last_failed_attempt) VALUES (?, ?, 0, NULL)", 
                           (email, password))
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
            if user['failed_attempts'] >= 3:
                flash("Account locked due to multiple failed login attempts. Check your email.")
                send_email("Account Under Attack", email, "Your account has been locked. Change your password immediately.")
                return redirect(url_for('forgot_password'))

            if check_password_hash(user['password_hash'], password):
                session['user_id'] = user['id']
                session['email'] = user['email']
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE users SET failed_attempts = 0 WHERE email = ?", (email,))
                return redirect(url_for('dashboard'))
            else:
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE users SET failed_attempts = failed_attempts + 1 WHERE email = ?", (email,))
                flash("Invalid credentials!")
        else:
            flash("No account found with this email.")
    return render_template('login.html')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']

        with get_db() as conn:
            cursor = conn.cursor()
            user = cursor.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if user:
            reset_token = generate_password_hash(email + str(datetime.utcnow()), method='sha256')
            reset_url = url_for('reset_password', token=reset_token, _external=True)
            send_email("Password Recovery", email, f"Click the link to reset your password: {reset_url}")

            expiration_time = datetime.utcnow() + timedelta(hours=1)
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
                                  (token, datetime.utcnow())).fetchone()

        if user:
            hashed_password = generate_password_hash(password)
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_expiration = NULL WHERE id = ?", 
                               (hashed_password, user['id']))
                conn.commit()
            flash("Password reset successful!")
            return redirect(url_for('login'))
        else:
            flash("Invalid or expired token.")
            return redirect(url_for('forgot_password'))
    return render_template('reset_password.html')


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

        encrypted_message = honey_encrypt(message, "correct_key")

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO messages (sender_id, receiver_id, encrypted_data, file_name) VALUES (?, ?, ?, ?)", 
                           (session['user_id'], recipient['id'], encrypted_message, filename))
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
            SELECT m.id, u.email AS sender, m.encrypted_data, m.file_name
            FROM messages m
            JOIN users u ON m.sender_id = u.id
            WHERE m.receiver_id = ?""", (session['user_id'],)).fetchall()
    return render_template('inbox.html', messages=messages)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


def setup_database():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                failed_attempts INTEGER DEFAULT 0,
                last_failed_attempt TEXT,
                reset_token TEXT,
                reset_token_expiration TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                receiver_id INTEGER NOT NULL,
                encrypted_data TEXT NOT NULL,
                file_name TEXT,
                FOREIGN KEY (sender_id) REFERENCES users (id),
                FOREIGN KEY (receiver_id) REFERENCES users (id)
            )
        """)
        conn.commit()


if __name__ == '__main__':
    setup_database()
    app.run(debug=True)
