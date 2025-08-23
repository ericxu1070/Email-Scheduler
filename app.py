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
            custom_body TEXT,
            total TEXT,
            invoice_url TEXT,
            csv_format TEXT
        )
    ''')
    
    # Check if total, invoice_url, and csv_format columns exist, and add them if not
    cursor.execute("PRAGMA table_info(orders)")
    columns = [info[1] for info in cursor.fetchall()]
    
    if 'total' not in columns:
        cursor.execute('ALTER TABLE orders ADD COLUMN total TEXT')
    if 'invoice_url' not in columns:
        cursor.execute('ALTER TABLE orders ADD COLUMN invoice_url TEXT')
    if 'csv_format' not in columns:
        cursor.execute('ALTER TABLE orders ADD COLUMN csv_format TEXT')
    
    conn.commit()
    conn.close()

init_db()

# Scheduler with timezone
scheduler = BackgroundScheduler(timezone=str(LOCAL_TZ))
scheduler.start()

# Email configuration
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'orderbentolicious@gmail.com')  # Fallback for meals
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD', 'ttys iklb sbcw zvlt')  # Fallback for meals
DANCE_SENDER_EMAIL = 'usa.tvda@gmail.com'
DANCE_SENDER_PASSWORD = 'dntq izxf zqhr vyce'  # Temporary app password for Dance Invoice

def parse_pickup_time(pickup_str):
    if pickup_str is None:
        return datetime.min.time()
    try:
        pickup_str = pickup_str.strip().upper().replace("AM", " AM").replace("PM", " PM")
        pickup_str = re.sub(r'[^0-9: AMPM-]', '', pickup_str)  # Clean extra chars
        if '-' in pickup_str:
            pickup_str = pickup_str.split('-')[0].strip()  # Take start time
        return datetime.strptime(pickup_str, "%I:%M %p").time()
    except Exception:
        return datetime.min.time()  # Fallback

def parse_date_from_item_name(item_name):
    if item_name is None:
        return datetime.now(tz=LOCAL_TZ).date()
    match = re.search(r'(\d{1,2}/\d{1,2})(/\d{4})?', item_name)
    if match:
        date_str = match.group(1)
        year = match.group(2)[1:] if match.group(2) else str(datetime.now(tz=LOCAL_TZ).year)
        return datetime.strptime(f"{date_str}/{year}", "%m/%d/%Y").date()
    return datetime.now(tz=LOCAL_TZ).date()

def format_pickup_time(pickup_str):
    if pickup_str is None:
        return ''
    try:
        pickup_str = pickup_str.strip().upper().replace("AM", " AM").replace("PM", " PM")
        pickup_str = pickup_str.replace("  ", " ")
        if '-' in pickup_str:
            pickup_str = pickup_str.split('-')[0].strip()
        pickup_dt = datetime.strptime(pickup_str, "%I:%M %p")
        return pickup_dt.strftime("%I:%M %p")
    except Exception:
        return pickup_str

def send_reminder_email(order_id, csv_format='familymeal'):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT email, full_name, pickup_time, item_name, order_number, custom_subject, custom_body, total, invoice_url, csv_format FROM orders WHERE id = ?', (order_id,))
    row = cursor.fetchone()

    if row:
        email, full_name, pickup_time, item_name, order_number, custom_subject, custom_body, total, invoice_url, stored_csv_format = row
        csv_format = stored_csv_format or csv_format

        sender_email = DANCE_SENDER_EMAIL if csv_format == 'dance_invoice' else SENDER_EMAIL
        sender_password = DANCE_SENDER_PASSWORD if csv_format == 'dance_invoice' else SENDER_PASSWORD
        yag = yagmail.SMTP(sender_email, sender_password)
        full_name = full_name.split()[0] if full_name else ''
        
        formatted_pickup_time = format_pickup_time(pickup_time)
        
        if csv_format == 'dance_invoice':
            student_name = pickup_time
            invoice_desp = item_name
            invoice_num = order_number
            parent_name = full_name
            default_subject = "[TVDA] {invoice_desp}_{student_name}_#({invoice_num})"
            default_body = """Dear {parent_name},

Attached, please find {student_name}'s {invoice_desp} in the amount of {total}:

{invoice_url}

Payment is due upon receipt.

Payment method:
- Zelle: 510-988-8666
- PayPal: 510-988-8666
- Check pay to the order of Tri-Valley Dance Academy 
- Cash

Please include invoice # {invoice_num} in the payment memo.

Thanks for your attention.

Best regards,

TVDA admin"""
        else:
            if 'Wonton' in item_name:
                date_str = item_name.split()[0]
                default_subject = "[Bentolicious] {item_name} Pick Up Reminder (Order #{order_number})"
                default_body = """Hi {full_name},

This is a reminder for your wonton order on {date_str} scheduled for pickup around {pickup_time}.

Thank you,
Bentolicious Team

Pick up Location: Bentolicious (4833 Hopyard Road, E#3 Pleasanton)
The store is located at the back side of the plaza near Chabot Drive.
"""
            else:
                default_subject = "[Bentolicious] {item_name} Pick Up Reminder (Order #{order_number})"
                default_body = """Hi {full_name},

This is a reminder that your order '{item_name}' is scheduled for pickup at {pickup_time}.

Thank you,
Bentolicious Team

Pick up Location: Bentolicious (4833 Hopyard Road, E#3 Pleasanton)
The store is located at the back side of the plaza near Chabot Drive.
"""

        subject = custom_subject if custom_subject else default_subject
        body = custom_body if custom_body else default_body

        format_dict = {
            'parent_name': parent_name if 'parent_name' in locals() else '',
            'student_name': student_name if 'student_name' in locals() else '',
            'invoice_num': invoice_num if 'invoice_num' in locals() else order_number or '',
            'invoice_desp': invoice_desp if 'invoice_desp' in locals() else item_name or '',
            'total': total or '',
            'invoice_url': invoice_url or '',
            'full_name': full_name or '',
            'order_number': order_number or '',
            'item_name': item_name or '',
            'pickup_time': formatted_pickup_time or pickup_time or '',
            'date_str': date_str if 'date_str' in locals() else ''
        }

        try:
            subject = subject.format(**format_dict)
            body = body.format(**format_dict)
        except Exception as e:
            print(f"Error formatting subject/body for order {order_id}: {e}")
            flash(f"Error formatting email for order {order_id}: {e}", 'error')
            conn.close()
            return

        try:
            contents = [body, "\n"]
            if csv_format != 'dance_invoice':
                try:
                    contents.append(yagmail.inline("bento.png"))
                except Exception:
                    pass
            yag.send(to=email, subject=subject, contents=contents)
            print(f"Email sent to {email}")
            cursor.execute('UPDATE orders SET status = "sent" WHERE id = ?', (order_id,))
            conn.commit()
        except Exception as e:
            print(f"Error sending email for order {order_id}: {e}")
            flash(f"Error sending email for order {order_id}: {e}", 'error')
    conn.close()

def send_dance_invoice(email, full_name, student_name, invoice_desp, invoice_num, total, invoice_url, custom_subject=None, custom_body=None):
    yag = yagmail.SMTP(DANCE_SENDER_EMAIL, DANCE_SENDER_PASSWORD)

    default_subject = "[TVDA] {invoice_desp}_{student_name}_#({invoice_num})"
    default_body = """Dear {parent_name},

Attached, please find {student_name}'s {invoice_desp} in the amount of {total}:

{invoice_url}

Payment is due upon receipt.

Payment method:
- Zelle: 510-988-8666
- PayPal: 510-988-8666
- Check pay to the order of Tri-Valley Dance Academy 
- Cash

Please include invoice # {invoice_num} in the payment memo.

Thanks for your attention.

Best regards,

TVDA admin"""

    subject = custom_subject if custom_subject else default_subject
    body = custom_body if custom_body else default_body

    format_dict = {
        'parent_name': full_name,
        'student_name': student_name,
        'invoice_num': invoice_num,
        'invoice_desp': invoice_desp,
        'total': total,
        'invoice_url': invoice_url
    }

    try:
        subject = subject.format(**format_dict)
        body = body.format(**format_dict)
    except Exception as e:
        print(f"Error formatting dance invoice: {e}")
        return

    try:
        yag.send(to=email, subject=subject, contents=[body])
        print(f"Dance invoice sent to {email}")
    except Exception as e:
        print(f"Error sending dance invoice to {email}: {e}")

@app.template_filter('format_datetime')
def format_datetime(dt):
    if dt is None:
        return ''
    return dt.strftime('%m-%d %I:%M:%S %p')

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        csv_format = request.form.get('csv_format', 'familymeal')
        custom_subject = request.form.get('custom_subject')
        custom_body = request.form.get('custom_body')
        file = request.files.get('csv_file')
        if file and file.filename.endswith('.csv'):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            try:
                df = pd.read_csv(filepath)
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                success_count = 0
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
                        'item_name': 'Order Items: Category',  # Will construct
                        'full_name': 'Billing: Full Name'
                    },
                    'dance_invoice': {
                        'email': 'Email',
                        'order_number': 'invoice_num',
                        'pickup_time': 'Student_Name',  # Repurpose for student_name
                        'item_name': 'Invoice desp',    # Repurpose for invoice_desp
                        'full_name': 'Parent Name',
                        'total': 'total',
                        'invoice_url': 'Invoice URL'
                    }
                }

                mapping = column_mappings.get(csv_format, column_mappings['familymeal'])

                for _, row in df.iterrows():
                    try:
                        email = row[mapping['email']]
                        order_number = str(row[mapping['order_number']])
                        pickup_time_str = row[mapping['pickup_time']]
                        item_name = row[mapping['item_name']]
                        full_name = row[mapping['full_name']]
                        
                        total = None
                        invoice_url = None

                        if csv_format == 'wonton':
                            sku = row.get('Order Items: SKU', '')
                            item_name = f"{sku} {item_name}"
                        elif csv_format == 'dance_invoice':
                            total = row[mapping['total']]
                            invoice_url = row[mapping['invoice_url']]

                            send_time = datetime.now(tz=LOCAL_TZ)

                            cursor.execute('''
                                INSERT INTO orders (email, order_number, pickup_time, item_name, full_name, send_time, status, custom_subject, custom_body, total, invoice_url, csv_format)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (email, order_number, pickup_time_str, item_name, full_name, send_time.isoformat(), 'sent', custom_subject, custom_body, total, invoice_url, csv_format))
                            conn.commit()

                            send_dance_invoice(email=email, full_name=full_name, student_name=pickup_time_str, invoice_desp=item_name, invoice_num=order_number, total=total, invoice_url=invoice_url, custom_subject=custom_subject, custom_body=custom_body)
                            success_count += 1
                            continue

                        pickup_date = parse_date_from_item_name(item_name)
                        pickup_time_obj = parse_pickup_time(pickup_time_str)
                        pickup_datetime = datetime.combine(pickup_date, pickup_time_obj).replace(tzinfo=LOCAL_TZ)
                        send_time = pickup_datetime - timedelta(hours=4)

                        cursor.execute('''
                            INSERT INTO orders (email, order_number, pickup_time, item_name, full_name, send_time, status, custom_subject, custom_body, total, invoice_url, csv_format)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (email, order_number, pickup_time_str, item_name, full_name, send_time.isoformat(), 'pending', custom_subject, custom_body, total, invoice_url, csv_format))
                        order_id = cursor.lastrowid

                        job_id = None
                        if send_time > datetime.now(tz=LOCAL_TZ):
                            trigger = DateTrigger(run_date=send_time)
                            job = scheduler.add_job(send_reminder_email, trigger, args=[order_id, csv_format])
                            job_id = job.id
                        cursor.execute('UPDATE orders SET job_id = ? WHERE id = ?', (job_id, order_id))
                        success_count += 1
                    except Exception as e:
                        print(f"Error processing row {row.to_dict()}: {e}")
                        flash(f"Error processing row for {row.get(mapping['email'], 'unknown')}: {e}", 'error')
                conn.commit()
                conn.close()
                os.remove(filepath)
                flash(f'Successfully processed {success_count} orders', 'success')
            except Exception as e:
                flash(f"Error reading CSV file: {e}", 'error')
                if os.path.exists(filepath):
                    os.remove(filepath)
            return redirect(url_for('index'))
        flash('Invalid file', 'error')
    return render_template('index.html')

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
    cursor.execute('SELECT status, job_id, csv_format FROM orders WHERE id = ?', (order_id,))
    row = cursor.fetchone()
    if row:
        status, job_id, stored_csv_format = row
        if status == 'pending':
            if job_id:
                try:
                    scheduler.remove_job(job_id)
                except:
                    pass
            csv_format = stored_csv_format or 'familymeal'
            send_reminder_email(order_id, csv_format)
            flash('Email sent successfully', 'success')
    conn.close()
    return redirect(url_for('scheduled'))

@app.route('/delete_bulk', methods=['POST'])
def delete_bulk():
    orders = request.form.getlist('orders[]')
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    deleted_count = 0
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
            deleted_count += 1
    conn.commit()
    conn.close()
    flash(f'Deleted {deleted_count} orders successfully', 'success')
    return redirect(url_for('scheduled'))

@app.route('/send_bulk', methods=['POST'])
def send_bulk():
    orders = request.form.getlist('orders[]')
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    sent_count = 0
    for order_id in orders:
        cursor.execute('SELECT status, job_id, csv_format FROM orders WHERE id = ?', (order_id,))
        row = cursor.fetchone()
        if row:
            status, job_id, csv_format = row
            if status == 'pending':
                if job_id:
                    try:
                        scheduler.remove_job(job_id)
                    except:
                        pass
                send_reminder_email(int(order_id), csv_format)
                sent_count += 1
    conn.close()
    flash(f'Sent {sent_count} emails successfully', 'success')
    return redirect(url_for('scheduled'))

if __name__ == '__main__':
    app.run(debug=True)