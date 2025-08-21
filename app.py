import os
import sqlite3
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
import yagmail
from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'Uploads'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key')  # Fallback for local testing
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

DB_FILE = 'orders.db'

# Initialize database and handle schema migrations
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create orders table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            order_number TEXT,
            pickup_time TEXT,
            item_name TEXT,
            full_name TEXT,
            send_time DATETIME,
            status TEXT DEFAULT 'pending',
            job_id TEXT
        )
    ''')
    
    # Check if custom_subject and custom_body columns exist, and add them if not
    cursor.execute("PRAGMA table_info(orders)")
    columns = [info[1] for info in cursor.fetchall()]
    
    if 'custom_subject' not in columns:
        cursor.execute('ALTER TABLE orders ADD COLUMN custom_subject TEXT')
    if 'custom_body' not in columns:
        cursor.execute('ALTER TABLE orders ADD COLUMN custom_body TEXT')
    
    conn.commit()
    conn.close()

init_db()

# Scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Email configuration
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'orderbentolicious@gmail.com')  # Fallback for local testing
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD', 'ttys iklb sbcw zvlt')  # Fallback for local testing

yag = yagmail.SMTP(SENDER_EMAIL, SENDER_PASSWORD)

def send_reminder_email(order_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT email, full_name, pickup_time, item_name, order_number, custom_subject, custom_body FROM orders WHERE id = ?', (order_id,))
    row = cursor.fetchone()
    if row:
        email, full_name, pickup_time, item_name, order_number, custom_subject, custom_body = row
        default_subject = "Reminder: Your Order {order_number} is Ready Soon"
        default_body = "Dear {full_name},\n\nThis is a reminder that your order '{item_name}' is scheduled for pickup at {pickup_time}.\n\nThank you!"
        subject = custom_subject.format(full_name=full_name, order_number=order_number, item_name=item_name, pickup_time=pickup_time) if custom_subject else default_subject.format(order_number=order_number)
        body = custom_body.format(full_name=full_name, order_number=order_number, item_name=item_name, pickup_time=pickup_time) if custom_body else default_body.format(full_name=full_name, item_name=item_name, pickup_time=pickup_time)
        try:
            yag.send(to=email, subject=subject, contents=body)
            cursor.execute('UPDATE orders SET status = "sent" WHERE id = ?', (order_id,))
            conn.commit()
        except Exception as e:
            print(f"Error sending email for order {order_id}: {e}")
            flash(f"Error sending email for order {order_id}: {e}", 'error')
    conn.close()

def parse_date_from_item_name(item_name):
    # Extract date like 8/18 from "8/18 Family Meal"
    match = re.search(r'(\d{1,2}/\d{1,2})', item_name)
    if match:
        month, day = map(int, match.group(1).split('/'))
        year = datetime.now(tz=ZoneInfo('UTC')).year  # Use UTC for consistency
        return datetime(year, month, day).date()
    raise ValueError(f"Could not parse date from item_name: {item_name}")

def parse_pickup_time(pickup_str):
    # Parse "1:11 PM" to datetime.time
    try:
        return datetime.strptime(pickup_str, '%I:%M %p').time()
    except ValueError as e:
        raise ValueError(f"Invalid pickup time format: {pickup_str}") from e

# Custom Jinja2 filter for formatting datetime
def format_datetime(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime('%Y-%m-%d %I:%M %p')

app.jinja_env.filters['format_datetime'] = format_datetime

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    global SENDER_EMAIL, SENDER_PASSWORD, yag
    sender_email = request.form.get('sender_email')
    sender_password = request.form.get('sender_password')
    if sender_email and sender_password:
        SENDER_EMAIL = sender_email
        SENDER_PASSWORD = sender_password
        try:
            yag = yagmail.SMTP(SENDER_EMAIL, SENDER_PASSWORD)
        except Exception as e:
            flash(f"Error setting email credentials: {e}", 'error')
            return redirect(url_for('index'))

    custom_subject = request.form.get('custom_subject', '').strip() or None
    custom_body = request.form.get('custom_body', '').strip() or None

    if 'file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('index'))
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    if file:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        try:
            file.save(filepath)
            df = pd.read_csv(filepath)
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            success_count = 0
            for _, row in df.iterrows():
                try:
                    email = row['Email']
                    order_number = row['Order Number']
                    pickup_time_str = row['Pick Up']
                    item_name = row['Item Name']
                    full_name = row['Full Name']
                    
                    pickup_time = parse_pickup_time(pickup_time_str)
                    date = parse_date_from_item_name(item_name)
                    pickup_datetime = datetime.combine(date, pickup_time).replace(tzinfo=ZoneInfo('UTC'))
                    
                    send_datetime = pickup_datetime - timedelta(hours=2)
                    
                    cursor.execute('''
                        INSERT INTO orders (email, order_number, pickup_time, item_name, full_name, send_time, status, custom_subject, custom_body)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (email, order_number, pickup_time_str, item_name, full_name, send_datetime, 'pending', custom_subject, custom_body))
                    order_id = cursor.lastrowid
                    
                    job_id = None
                    if send_datetime > datetime.now(tz=ZoneInfo('UTC')):
                        trigger = DateTrigger(run_date=send_datetime)
                        job = scheduler.add_job(send_reminder_email, trigger, args=[order_id])
                        job_id = job.id
                    cursor.execute('UPDATE orders SET job_id = ? WHERE id = ?', (job_id, order_id))
                    success_count += 1
                except Exception as e:
                    print(f"Error processing row {row.to_dict()}: {e}")
                    flash(f"Error processing row for {row.get('Email', 'unknown')}: {e}", 'error')
            conn.commit()
            conn.close()
            os.remove(filepath)  # Clean up uploaded file
            flash(f'Successfully processed {success_count} orders', 'success')
        except Exception as e:
            flash(f"Error reading CSV file: {e}", 'error')
            if os.path.exists(filepath):
                os.remove(filepath)
        return redirect(url_for('index'))
    flash('Invalid file', 'error')
    return redirect(url_for('index'))

@app.route('/scheduled')
def scheduled():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, full_name, email, pickup_time, send_time, status 
        FROM orders 
        ORDER BY send_time DESC
    ''')
    rows = cursor.fetchall()
    # Convert send_time strings to datetime objects
    rows = [
        (row[0], row[1], row[2], row[3], datetime.fromisoformat(row[4]) if isinstance(row[4], str) else row[4], row[5])
        for row in rows
    ]
    conn.close()
    return render_template('scheduled.html', rows=rows, now=datetime.now(tz=ZoneInfo('UTC')))

@app.route('/delete/<int:order_id>', methods=['GET'])
def delete_order(order_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT status, job_id FROM orders WHERE id = ?', (order_id,))
    row = cursor.fetchone()
    if row:
        status, job_id = row
        if status == 'pending' and job_id:
            try:
                scheduler.remove_job(job_id)
            except:
                pass
    cursor.execute('DELETE FROM orders WHERE id = ?', (order_id,))
    conn.commit()
    conn.close()
    flash('Order deleted successfully', 'success')
    return redirect(url_for('scheduled'))

@app.route('/send/<int:order_id>', methods=['GET'])
def send_order(order_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT status, job_id FROM orders WHERE id = ?', (order_id,))
    row = cursor.fetchone()
    if row:
        status, job_id = row
        if status == 'pending':
            if job_id:
                try:
                    scheduler.remove_job(job_id)
                except:
                    pass
            send_reminder_email(order_id)
            flash('Email sent successfully', 'success')
    conn.close()
    return redirect(url_for('scheduled'))

@app.route('/delete_bulk', methods=['POST'])
def delete_bulk():
    orders = request.form.getlist('orders[]')
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    for order_id in orders:
        cursor.execute('SELECT status, job_id FROM orders WHERE id = ?', (order_id,))
        row = cursor.fetchone()
        if row:
            status, job_id = row
            if status == 'pending' and job_id:
                try:
                    scheduler.remove_job(job_id)
                except:
                    pass
        cursor.execute('DELETE FROM orders WHERE id = ?', (order_id,))
    conn.commit()
    conn.close()
    flash(f'Deleted {len(orders)} orders successfully', 'success')
    return redirect(url_for('scheduled'))

if __name__ == '__main__':
    app.run(debug=True)