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

LOCAL_TZ = ZoneInfo('America/Los_Angeles')

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
            job_id TEXT,
            custom_subject TEXT,
            custom_body TEXT
        )
    ''')
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

def format_pickup_time(pickup_str):
    try:
        # Normalize input like "12:41am" → "12:41 AM" or handle ranges like "4:30pm-7:30pm"
        pickup_str = pickup_str.strip().upper().replace("AM", " AM").replace("PM", " PM")
        pickup_str = pickup_str.replace("  ", " ")
        # Handle range format (e.g., "4:30pm-7:30pm")
        if '-' in pickup_str:
            pickup_str = pickup_str.split('-')[0].strip()  # Take start time
        pickup_dt = datetime.strptime(pickup_str, "%I:%M %p")
        return pickup_dt.strftime("%I:%M %p")
    except Exception:
        return pickup_str  # Fallback if parsing fails
    
def send_reminder_email(order_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT email, full_name, pickup_time, item_name, order_number, custom_subject, custom_body FROM orders WHERE id = ?', (order_id,))
    row = cursor.fetchone()
    if row:
        email, full_name, pickup_time, item_name, order_number, custom_subject, custom_body = row

        # Define default templates based on item_name
        if 'Wonton' in item_name:
            default_subject = "[Bentolicious] Wonton Order Reminder (Order #{order_number})"
            default_body = """Hi {full_name},

This is a reminder for your wonton order '{item_name}' scheduled for pickup around {pickup_time}.

Thank you,
Bentolicious Team

Pick up Location: Bentolicious (4833 Hopyard Road, E#3 Pleasanton)
The store is located at the back side of the plaza near Chabot Drive."""
            # Use raw pickup_time for wonton orders
            formatted_pickup_time = pickup_time
        else:
            default_subject = "[Bentolicious] {item_name} Pick Up Reminder (Order #{order_number})"
            default_body = """Hi {full_name},

This is a reminder that your order '{item_name}' is scheduled for pickup at {pickup_time}.

Thank you,
Bentolicious Team

Pick up Location: Bentolicious (4833 Hopyard Road, E#3 Pleasanton)
The store is located at the back side of the plaza near Chabot Drive."""
            # Use formatted pickup time for non-wonton orders
            formatted_pickup_time = format_pickup_time(pickup_time)

        subject = custom_subject.format(full_name=full_name, order_number=order_number, item_name=item_name, pickup_time=formatted_pickup_time) if custom_subject else default_subject.format(order_number=order_number, item_name=item_name)
        body = custom_body.format(full_name=full_name, order_number=order_number, item_name=item_name, pickup_time=formatted_pickup_time) if custom_body else default_body.format(full_name=full_name, item_name=item_name, pickup_time=formatted_pickup_time)
        try:
            yag.send(to=email, subject=subject, contents=[body, "\n", yagmail.inline("bento.png")])
            cursor.execute('UPDATE orders SET status = "sent" WHERE id = ?', (order_id,))
            conn.commit()
        except Exception as e:
            print(f"Error sending email for order {order_id}: {e}")
            flash(f"Error sending email for order {order_id}: {e}", 'error')
    conn.close()

def parse_date_from_item_name(item_name):
    # Extract date like 8/18 or 6/30/2025 from item_name
    match = re.search(r'(\d{1,2}/\d{1,2}(?:/\d{4})?)', item_name)
    if match:
        date_str = match.group(1)
        try:
            if len(date_str.split('/')) == 2:  # MM/DD format
                month, day = map(int, date_str.split('/'))
                year = datetime.now(tz=LOCAL_TZ).year
            else:  # MM/DD/YYYY format
                month, day, year = map(int, date_str.split('/'))
            return datetime(year, month, day).date()
        except ValueError as e:
            raise ValueError(f"Could not parse date from item_name: {item_name}") from e
    raise ValueError(f"Could not parse date from item_name: {item_name}")

def parse_pickup_time(pickup_str):
    # Parse "1:11PM" or "Lunch: 11:00pm-2:00pm" to datetime.time
    try:
        if ':' in pickup_str and '-' in pickup_str:  # Handle range format
            pickup_str = pickup_str.split('-')[0].strip()  # Take start time
            if 'Lunch' in pickup_str or 'Dinner' in pickup_str:
                pickup_str = pickup_str.split(': ')[1].strip()  # Extract time after "Lunch: " or "Dinner: "
        return datetime.strptime(pickup_str, '%I:%M%p').time()
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
    csv_format = request.form.get('csv_format', 'familymeal')  # Default to familymeal

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

            # Define column mappings for each CSV format
            column_mappings = {
                'familymeal': {
                    'email': 'Email',
                    'order_number': 'Order Number',
                    'pickup_time': 'Pick Up',
                    'item_name': 'Item Name',
                    'full_name': 'Full Name'
                },
                'wonton': {
                    'email': 'Billing: E-mail Address',
                    'order_number': 'Purchase ID',
                    'pickup_time': 'PU Time',
                    'item_name': 'Order Items: SKU',  # Will combine with Order Items: Category
                    'full_name': 'Billing: Full Name'
                }
            }

            mapping = column_mappings.get(csv_format, column_mappings['familymeal'])

            for _, row in df.iterrows():
                try:
                    email = row[mapping['email']]
                    order_number = str(row[mapping['order_number']])
                    pickup_time_str = row[mapping['pickup_time']]
                    # Combine SKU and Category for wonton format
                    item_name = row[mapping['item_name']]
                    if csv_format == 'wonton':
                        item_name = f"{row['Order Items: SKU']} {row['Order Items: Category']}"
                    full_name = row[mapping['full_name']]
                    
                    pickup_time = parse_pickup_time(pickup_time_str)
                    date = parse_date_from_item_name(item_name)
                    pickup_datetime = datetime.combine(date, pickup_time).replace(tzinfo=LOCAL_TZ)
                    
                    send_datetime = pickup_datetime - timedelta(hours=4)
                    
                    cursor.execute('''
                        INSERT INTO orders (email, order_number, pickup_time, item_name, full_name, send_time, status, custom_subject, custom_body)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (email, order_number, pickup_time_str, item_name, full_name, send_datetime, 'pending', custom_subject, custom_body))
                    order_id = cursor.lastrowid
                    
                    job_id = None
                    if send_datetime > datetime.now(tz=LOCAL_TZ):
                        trigger = DateTrigger(run_date=send_datetime)
                        job = scheduler.add_job(send_reminder_email, trigger, args=[order_id])
                        job_id = job.id
                    cursor.execute('UPDATE orders SET job_id = ? WHERE id = ?', (job_id, order_id))
                    success_count += 1
                except Exception as e:
                    print(f"Error processing row {row.to_dict()}: {e}")
                    flash(f"Error processing row for {row.get(mapping['email'], 'unknown')}: {e}", 'error')
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
        SELECT id, full_name, email, item_name, pickup_time, send_time, status 
        FROM orders 
        ORDER BY send_time DESC
    ''')
    rows = cursor.fetchall()
    # Convert send_time strings to datetime objects
    rows = [
        (row[0], row[1], row[2], row[3], row[4], datetime.fromisoformat(row[5]) if isinstance(row[5], str) else row[5], row[6])
        for row in rows
    ]
    conn.close()
    return render_template('scheduled.html', rows=rows, now=datetime.now(tz=LOCAL_TZ))

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