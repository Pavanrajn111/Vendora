from flask import Flask, render_template, request, redirect, session, abort
from functools import wraps
import sqlite3
import os
import re
import base64
import io
import uuid
from urllib.parse import quote
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from PIL import Image

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import qrcode
except ImportError:
    qrcode = None

app = Flask(__name__)

# Enforce secure SECRET_KEY in production
flask_env = os.environ.get("FLASK_ENV", "development").lower()
secret_key = os.environ.get("SECRET_KEY")
if flask_env == "production":
    if not secret_key or secret_key in ("vendora-dev-secret-key-change-in-production", "change-me-to-a-long-random-string"):
        raise ValueError("CRITICAL: SECRET_KEY environment variable must be set to a secure unique value in production!")
app.secret_key = secret_key or "vendora-dev-secret-key-change-in-production"

# Configure maximum upload size (5 MB limit)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# CSRF Protection
csrf = CSRFProtect(app)

# Login & Auth Rate Limiting
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

# Date/datetime strings we may read from SQLite or legacy rows
_INDIAN_DISPLAY_DT = '%d/%m/%Y, %I:%M %p'
_INDIAN_DISPLAY_D = '%d/%m/%Y'
_PARSE_FORMATS_DT = [
    '%d/%m/%Y, %I:%M %p',
    '%d/%m/%Y, %I:%M%p',
    '%d/%m/%Y %I:%M %p',
    '%d-%m-%Y %H:%M',
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d %H:%M',
    '%Y-%m-%dT%H:%M:%S',
    '%Y-%m-%dT%H:%M:%S.%f',
]
_PARSE_FORMATS_D = [
    '%Y-%m-%d',
    '%d/%m/%Y',
    '%d-%m-%Y',
]


def _parse_datetime(date_str):
    """Return datetime or None."""
    if not date_str:
        return None
    s = str(date_str).strip()
    for fmt in _PARSE_FORMATS_DT:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    for fmt in _PARSE_FORMATS_D:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def format_indian_date(date_str):
    """Display in Indian format: DD/MM/YYYY, HH:MM AM/PM (date-only when no time in source)."""
    if not date_str:
        return ""
    s = str(date_str).strip()
    dt = _parse_datetime(s)
    if not dt:
        return s
    date_only = (
        (len(s) <= 10 and ' ' not in s and 'T' not in s and ',' not in s)
        or re.match(r'^\d{4}-\d{2}-\d{2}$', s)
    )
    if date_only:
        return dt.strftime(_INDIAN_DISPLAY_D)
    return dt.strftime(_INDIAN_DISPLAY_DT)


def to_input_date(date_str):
    """HTML date input value (YYYY-MM-DD) from stored order dates."""
    if not date_str:
        return ""
    dt = _parse_datetime(str(date_str).strip())
    if not dt:
        return ""
    return dt.strftime('%Y-%m-%d')


# Demo collect UPI VPA for QR (override with env COLLECT_UPI_VPA in production)
COLLECT_UPI_FALLBACK = os.environ.get('COLLECT_UPI_VPA', 'merchant.vendora@ptyes')

UPI_PLATFORM_SLUGS = {
    'gpay': 'Google Pay',
    'phonepe': 'PhonePe',
    'paytm': 'Paytm',
}


def _digits_only_amount(price_str):
    s = re.sub(r'[^\d.]', '', str(price_str or ''))
    try:
        return f'{float(s):.2f}' if s else '0.00'
    except ValueError:
        return '0.00'


def _luhn_valid(number_str):
    digits = [int(c) for c in re.sub(r'\D', '', number_str)]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _card_expiry_valid(mm_yy):
    if not mm_yy or not re.match(r'^\d{2}/\d{2}$', mm_yy.strip()):
        return False
    mm, yy = mm_yy.strip().split('/')
    try:
        m, y = int(mm), int(yy)
    except ValueError:
        return False
    if m < 1 or m > 12:
        return False
    y_full = 2000 + y if y < 100 else y
    now = datetime.now()
    if y_full > now.year + 20 or y_full < now.year - 1:
        return False
    if y_full < now.year or (y_full == now.year and m < now.month):
        return False
    return True


def _upi_format_valid(upi):
    upi = (upi or '').strip().lower()
    return bool(re.match(r'^[a-z0-9._-]{2,64}@[a-z0-9.-]{2,64}$', upi))


def _mask_upi_id(upi):
    upi = (upi or '').strip()
    if '@' not in upi:
        return '***'
    local, _, domain = upi.partition('@')
    if len(local) <= 3:
        masked = local[0] + '**' if local else '**'
    else:
        masked = local[:2] + '***' + local[-1]
    return f'{masked}@{domain}'


def _vendor_collect_vpa(conn, vendor_username):
    row = conn.execute(
        "SELECT upi_vpa FROM users WHERE username=?",
        (vendor_username,),
    ).fetchone()
    if row and row['upi_vpa'] and str(row['upi_vpa']).strip():
        return str(row['upi_vpa']).strip()
    return COLLECT_UPI_FALLBACK


def _build_upi_uri(vpa, payee_name, amount, note):
    return (
        'upi://pay?'
        f'pa={quote(vpa)}&pn={quote(payee_name)}&am={quote(amount)}&cu=INR&tn={quote(note)}'
    )


def _qr_data_uri(text):
    if not qrcode:
        return None
    try:
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
    except Exception:
        return None


def _payment_order_state(conn, order_id, customer):
    """Returns (order_row_or_None, state) where state is new|retry|awaiting|blocked|invalid."""
    o = conn.execute(
        "SELECT * FROM orders WHERE id=? AND customer=?",
        (order_id, customer),
    ).fetchone()
    if not o or o['status'] != 'Accepted':
        return None, 'invalid'
    pay = conn.execute("SELECT * FROM payments WHERE order_id=?", (order_id,)).fetchone()
    if not pay:
        return o, 'new'
    st = pay['status']
    if st == 'Payment Not Received':
        return o, 'retry'
    if st in ('Accepted', 'Verified', 'Refund Completed', 'Out Of Stock', 'Refund Pending'):
        return o, 'blocked'
    if st in ('Pending Vendor Verification', 'Completed'):
        return o, 'awaiting'
    return o, 'unknown'


def _finalize_customer_payment(
    conn,
    order_id,
    customer,
    vendor,
    product_name,
    amount,
    payment_method,
    upi_platform,
    upi_flow,
    card_last4,
    upi_masked,
):
    pm_store = (payment_method or '').strip().lower()
    if pm_store not in ('upi', 'card'):
        pm_store = 'legacy'
    payment_time = datetime.now().strftime('%d/%m/%Y, %I:%M %p')
    existing = conn.execute("SELECT * FROM payments WHERE order_id=?", (order_id,)).fetchone()
    if not existing:
        conn.execute(
            '''
            INSERT INTO payments(
                order_id, customer, vendor, product_name, amount, status, payment_date,
                payment_method, upi_platform, upi_flow, card_last4, upi_masked
            )
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ''',
            (
                order_id,
                customer,
                vendor,
                product_name,
                amount,
                'Pending Vendor Verification',
                payment_time,
                pm_store,
                upi_platform or '',
                upi_flow or '',
                card_last4 or '',
                upi_masked or '',
            ),
        )
    elif existing['status'] == 'Payment Not Received':
        conn.execute(
            '''
            UPDATE payments SET
                vendor=?, product_name=?, amount=?, status=?, payment_date=?,
                payment_method=?, upi_platform=?, upi_flow=?, card_last4=?, upi_masked=?
            WHERE order_id=?
            ''',
            (
                vendor,
                product_name,
                amount,
                'Pending Vendor Verification',
                payment_time,
                pm_store,
                upi_platform or '',
                upi_flow or '',
                card_last4 or '',
                upi_masked or '',
                order_id,
            ),
        )
    else:
        return False
    conn.commit()
    return True

UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.jfif'}

def allowed_image_file(filename):
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS

def validate_and_save_image(file_storage):
    """
    Safely validates and stores an uploaded product image.
    - Verifies allowed file extension (.jpg, .jpeg, .png, .webp, .jfif)
    - Verifies actual image content via Pillow
    - Generates collision-free, path-traversal safe filename
    Returns relative path ('uploads/filename.ext') or None if invalid.
    """
    if not file_storage or not file_storage.filename or file_storage.filename.strip() == '':
        return None

    if not allowed_image_file(file_storage.filename):
        return None

    # Validate actual image content
    try:
        file_storage.seek(0)
        with Image.open(file_storage) as img:
            img.verify()
        file_storage.seek(0)
    except Exception:
        try:
            file_storage.seek(0)
        except Exception:
            pass
        return None

    ext = os.path.splitext(file_storage.filename)[1].lower()
    clean_base = secure_filename(os.path.splitext(file_storage.filename)[0]) or 'product'
    unique_filename = f"{clean_base}_{uuid.uuid4().hex[:8]}{ext}"
    dest_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
    file_storage.save(dest_path)
    return f"uploads/{unique_filename}"

def validate_password_strength(password):
    """
    Unified server-side password validation policy:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number
    - At least one special character
    Returns (is_valid: bool, error_message: str)
    """
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number."
    if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?/~`' for c in password):
        return False, "Password must contain at least one special character."
    return True, ""

def validate_price(price_input):
    """
    Server-side price validation:
    - Must exist, be numeric, and strictly > 0
    - Enforces maximum upper limit (<= 10,000,000)
    - Returns (is_valid: bool, formatted_string_or_error: str)
    """
    if price_input is None:
        return False, "Price is required."
    clean = str(price_input).strip().replace('₹', '').replace('$', '').replace(',', '')
    if not clean:
        return False, "Price is required."
    try:
        val = float(clean)
        if val <= 0:
            return False, "Price must be greater than zero."
        if val > 10000000:
            return False, "Price cannot exceed ₹1,00,00,000."
        if val.is_integer():
            return True, str(int(val))
        return True, f"{val:.2f}"
    except (ValueError, TypeError):
        return False, "Invalid price. Please enter a valid positive numeric amount."

# ---------------------------------
# SMART IMAGE DETECTION
# ---------------------------------

def find_image_file(image_path):
    """
    Intelligently find image file with case-insensitive and extension-agnostic matching.
    
    Args:
        image_path: Path like "uploads/battery.jfif" or "battery" or "uploads/battery"
    
    Returns:
        Path to existing image file or default placeholder if not found
    """
    if not image_path:
        return 'images/product-placeholder.svg'
    
    # Extract base filename without extension
    image_path = str(image_path).strip()
    
    # Remove 'uploads/' prefix if present
    if image_path.startswith('uploads/'):
        base_name = image_path[8:]  # Remove 'uploads/' prefix
    else:
        base_name = image_path
    
    # Remove any existing extension
    if '.' in base_name:
        base_name = base_name.rsplit('.', 1)[0]
    
    # List of extensions to try, in order of preference
    extensions = ['.png', '.jpg', '.jpeg', '.jfif', '.webp']
    
    # Try to find the file in the uploads folder (case-insensitive)
    try:
        if os.path.isdir(UPLOAD_FOLDER):
            files_in_dir = os.listdir(UPLOAD_FOLDER)
            
            # First pass: exact case match
            for ext in extensions:
                filename = base_name + ext
                if filename in files_in_dir:
                    return f'uploads/{filename}'
            
            # Second pass: case-insensitive match
            base_name_lower = base_name.lower()
            for file in files_in_dir:
                file_lower = file.lower()
                # Check if file matches the base name with any of our extensions
                for ext in extensions:
                    if file_lower == base_name_lower + ext:
                        return f'uploads/{file}'
    except Exception as e:
        print(f"Error finding image file: {e}")
    
    # Return default placeholder if not found
    return 'images/product-placeholder.svg'


def resolve_image_path(image_path):
    """
    Flask filter to automatically resolve product image paths.
    Supports multiple formats and case variations.
    """
    return find_image_file(image_path)


# Register the filter for use in Jinja templates
app.jinja_env.filters['resolve_image'] = resolve_image_path

# ---------------------------------
# DATABASE CONNECTION
# ---------------------------------

def get_db():
    conn = sqlite3.connect("vendor.db")
    conn.row_factory = sqlite3.Row
    return conn

# ---------------------------------
# CREATE DATABASE TABLES
# ---------------------------------

conn = get_db()

conn.execute('''
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    role TEXT,
    mobile TEXT
)
''')

conn.execute('''
CREATE TABLE IF NOT EXISTS vendors(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    contact TEXT
)
''')

conn.execute('''
CREATE TABLE IF NOT EXISTS products(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor TEXT,
    name TEXT,
    price TEXT
)
''')

conn.execute('''
CREATE TABLE IF NOT EXISTS orders(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer TEXT,
    vendor TEXT,
    product_name TEXT,
    price TEXT,
    status TEXT
)
''')

conn.execute('''
CREATE TABLE IF NOT EXISTS payments(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    customer TEXT,
    vendor TEXT,
    product_name TEXT,
    amount TEXT,
    status TEXT,
    payment_date DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')

conn.execute('''
CREATE TABLE IF NOT EXISTS reviews(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor TEXT,
    rating TEXT,
    comment TEXT,
    customer TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
''')
conn.execute('''
CREATE TABLE IF NOT EXISTS connections(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer TEXT,
    vendor TEXT
)
''')

conn.commit()

# ---------------------------------
# APPLY SCHEMA MIGRATIONS
# ---------------------------------
try:
    conn.execute('ALTER TABLE products ADD COLUMN image TEXT DEFAULT ""')
except:
    pass
try:
    conn.execute('ALTER TABLE products ADD COLUMN availability TEXT DEFAULT "In Stock"')
except:
    pass
try:
    conn.execute('ALTER TABLE orders ADD COLUMN product_image TEXT DEFAULT ""')
except:
    pass
try:
    conn.execute('ALTER TABLE orders ADD COLUMN expected_delivery TEXT DEFAULT ""')
except:
    pass
try:
    conn.execute('ALTER TABLE orders ADD COLUMN delivered_date TEXT DEFAULT ""')
except:
    pass
def ensure_column_exists(conn, table, column, definition):
    columns = [row['name'] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def backfill_payment_method_codes(conn):
    """Normalize payment_method to upi | card | legacy. Idempotent; does not delete rows."""
    try:
        conn.execute(
            """
            UPDATE payments SET payment_method = 'card'
            WHERE TRIM(COALESCE(card_last4, '')) != ''
               OR LOWER(TRIM(COALESCE(payment_method, ''))) LIKE '%credit%'
               OR LOWER(TRIM(COALESCE(payment_method, ''))) LIKE '%debit%'
            """
        )
        conn.execute(
            """
            UPDATE payments SET payment_method = 'upi'
            WHERE TRIM(COALESCE(payment_method, '')) NOT IN ('card', 'upi', 'legacy')
              AND (
                    TRIM(COALESCE(upi_platform, '')) != ''
                 OR TRIM(COALESCE(upi_flow, '')) != ''
                 OR TRIM(COALESCE(upi_masked, '')) != ''
                 OR LOWER(TRIM(COALESCE(payment_method, ''))) LIKE '%upi%'
                  )
            """
        )
        conn.execute(
            """
            UPDATE payments SET payment_method = 'legacy'
            WHERE TRIM(COALESCE(payment_method, '')) NOT IN ('upi', 'card', 'legacy')
            """
        )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass

try:
    ensure_column_exists(conn, 'payments', 'payment_date', 'TEXT DEFAULT ""')
except:
    pass
try:
    ensure_column_exists(conn, 'reviews', 'created_at', 'DATETIME DEFAULT CURRENT_TIMESTAMP')
except:
    pass
for _col, _def in [
    ('payment_method', 'TEXT DEFAULT ""'),
    ('upi_platform', 'TEXT DEFAULT ""'),
    ('upi_flow', 'TEXT DEFAULT ""'),
    ('card_last4', 'TEXT DEFAULT ""'),
    ('upi_masked', 'TEXT DEFAULT ""'),
]:
    try:
        ensure_column_exists(conn, 'payments', _col, _def)
    except Exception:
        pass
try:
    ensure_column_exists(conn, 'users', 'upi_vpa', 'TEXT DEFAULT ""')
except Exception:
    pass
backfill_payment_method_codes(conn)

conn.commit()

# ---------------------------------
# CUSTOM FILTERS
# ---------------------------------

# Add Indian date format filter
@app.template_filter('indian_date')
def indian_date_filter(date_str):
    return format_indian_date(date_str)


@app.template_filter('input_date')
def input_date_filter(date_str):
    return to_input_date(date_str)


@app.template_filter('payment_method_label')
def payment_method_label_filter(code):
    c = (code or '').strip().lower()
    if c == 'upi':
        return 'Paid Through UPI'
    if c == 'card':
        return 'Paid Through Credit/Debit Card'
    return 'Recorded previously'


@app.template_filter('time_ago')
def time_ago(dt_str):
    if not dt_str:
        return ""
    try:
        dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
    except:
        return dt_str
    
    now = datetime.now()
    diff = now - dt
    
    if diff.days > 365:
        return f"{diff.days // 365} year{'s' if diff.days // 365 > 1 else ''} ago"
    elif diff.days > 30:
        return f"{diff.days // 30} month{'s' if diff.days // 30 > 1 else ''} ago"
    elif diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    elif diff.seconds > 3600:
        return f"{diff.seconds // 3600} hour{'s' if diff.seconds // 3600 > 1 else ''} ago"
    elif diff.seconds > 60:
        return f"{diff.seconds // 60} minute{'s' if diff.seconds // 60 > 1 else ''} ago"
    else:
        return "Just now"

# ---------------------------------
# AUTHENTICATION & ROLE DECORATORS
# ---------------------------------

def login_required(f):
    """
    Ensures user is authenticated in the current session.
    Redirects unauthenticated visitors to /login.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    """
    Ensures authenticated user possesses one of the specified roles.
    Redirects unauthenticated or unauthorized visitors to /login.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session:
                return redirect('/login')
            if session.get('role') not in roles:
                return redirect('/login')
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ---------------------------------
# LANDING PAGE
# ---------------------------------

@app.route('/')
def index():
    return render_template('index.html')

# ---------------------------------
# LOGIN & SETTINGS
# ---------------------------------

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    conn = get_db()
    error = ""
    success = ""
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_password':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            # Get user from database
            user = conn.execute("SELECT * FROM users WHERE username=?", (session['user'],)).fetchone()
            
            # Validate current password (supporting both hashed and legacy plaintext)
            stored_pwd = user['password'] if user else ''
            is_correct = False
            if stored_pwd == current_password:
                is_correct = True
            elif stored_pwd and (stored_pwd.startswith('pbkdf2:') or stored_pwd.startswith('scrypt:')):
                try:
                    is_correct = check_password_hash(stored_pwd, current_password)
                except Exception:
                    is_correct = False

            is_valid_pwd, pwd_err = validate_password_strength(new_password)
            if not is_correct:
                error = "Current password is incorrect"
            elif new_password != confirm_password:
                error = "New passwords do not match"
            elif not is_valid_pwd:
                error = pwd_err
            else:
                # Password is valid, update it with secure hash
                hashed_new = generate_password_hash(new_password)
                conn.execute("UPDATE users SET password=? WHERE username=?", (hashed_new, session['user']))
                conn.commit()
                success = "Password updated successfully"
            
        elif action == 'update_mobile':
            mobile = request.form.get('mobile', '')
            conn.execute("UPDATE users SET mobile=? WHERE username=?", (mobile, session['user']))
            conn.commit()
            success = "Mobile number updated successfully"
        
        if success:
            return redirect('/settings?success=1')
        
    user = conn.execute("SELECT * FROM users WHERE username=?", (session['user'],)).fetchone()
    return render_template('settings.html', user=user, error=error)

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute; 30 per hour", methods=["POST"])
def login():

    conn = get_db()
    error = ""

    if request.method == 'POST':

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = conn.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        ).fetchone()

        valid = False
        if user:
            stored_pwd = user['password']
            if stored_pwd == password:
                valid = True
                # Transparently upgrade legacy plaintext password to secure hash
                try:
                    hashed = generate_password_hash(password)
                    conn.execute("UPDATE users SET password=? WHERE id=?", (hashed, user['id']))
                    conn.commit()
                except Exception:
                    pass
            elif stored_pwd and (stored_pwd.startswith('pbkdf2:') or stored_pwd.startswith('scrypt:')):
                try:
                    valid = check_password_hash(stored_pwd, password)
                except Exception:
                    valid = False

        if valid:
            session['user'] = user['username']
            session['role'] = user['role']
            return redirect('/dashboard')
        else:
            error = "Invalid Username or Password"

    return render_template('login.html', error=error)

# ---------------------------------
# REGISTER
# ---------------------------------

@app.route('/register', methods=['GET', 'POST'])
def register():

    conn = get_db()
    error = ""

    if request.method == 'POST':

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'customer').strip().lower()
        mobile = request.form.get('mobile', '').strip()

        if not username or not password:
            error = "Username and password are required"
            return render_template('register.html', error=error)

        if role not in ('customer', 'vendor'):
            error = "Invalid account role. Allowed roles are 'customer' and 'vendor'."
            return render_template('register.html', error=error)

        is_valid_pwd, pwd_err = validate_password_strength(password)
        if not is_valid_pwd:
            error = pwd_err
            return render_template('register.html', error=error)

        existing_user = conn.execute(
            "SELECT * FROM users WHERE username=?",
            (username,)
        ).fetchone()

        if existing_user:
            error = "Username already exists"
            return render_template(
                'register.html',
                error=error
            )

        hashed_password = generate_password_hash(password)
        conn.execute(
            "INSERT INTO users(username,password,role,mobile) VALUES(?,?,?,?)",
            (username, hashed_password, role, mobile)
        )

        conn.commit()

        return redirect('/login')

    return render_template('register.html', error=error)

# ---------------------------------
# DASHBOARD
# ---------------------------------

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

# ---------------------------------
# PROFILE
# ---------------------------------

@app.route('/profile')
@login_required
def profile():
    conn = get_db()

    role = session['role']

    # -------------------------
    # VENDOR PROFILE
    # -------------------------

    if role == "vendor":

        total_customers = conn.execute(
            "SELECT COUNT(*) FROM connections WHERE vendor=?",
            (session['user'],)
        ).fetchone()[0]
        connected_customers = conn.execute(
            "SELECT customer FROM connections WHERE vendor=? ORDER BY id DESC",
            (session['user'],)
        ).fetchall()

        total_orders = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE vendor=?",
            (session['user'],)
        ).fetchone()[0]

        total_reviews = conn.execute(
            "SELECT COUNT(*) FROM reviews WHERE vendor=?",
            (session['user'],)
        ).fetchone()[0]

        return render_template(
            'vendor_profile.html',
            total_customers=total_customers,
            total_orders=total_orders,
            connected_customers=connected_customers,
            total_reviews=total_reviews
        )

    # -------------------------
    # CUSTOMER PROFILE
    # -------------------------

    else:

        total_vendors = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role='vendor'"
        ).fetchone()[0]

        connected_vendors = conn.execute(
            "SELECT vendor FROM connections WHERE customer=? ORDER BY id DESC",
            (session['user'],)
        ).fetchall()

        total_orders = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE customer=?",
            (session['user'],)
        ).fetchone()[0]

        total_payments = conn.execute(
            "SELECT COUNT(*) FROM payments WHERE customer=?",
            (session['user'],)
        ).fetchone()[0]

        return render_template(
            'customer_profile.html',
            total_vendors=total_vendors,
            total_orders=total_orders,
            connected_vendors=connected_vendors,
            total_payments=total_payments
        )
# ---------------------------------
# VENDORS
# ---------------------------------

@app.route('/vendors')
@login_required
def vendors():
    conn = get_db()

    vendors = conn.execute(
        "SELECT username,mobile FROM users WHERE role='vendor' ORDER BY id DESC"
    ).fetchall()

    connected = conn.execute(
        "SELECT vendor FROM connections WHERE customer=? ORDER BY id DESC",
        (session['user'],)
    ).fetchall()

    connected_vendors = [
        v['vendor'] for v in connected
    ]

    return render_template(
        'vendors.html',
        vendors=vendors,
        connected_vendors=connected_vendors
    )

@app.route('/products', methods=['GET', 'POST'])
@login_required
def products():
    conn = get_db()

    role = session['role']

    # -------------------------
    # VENDOR
    # -------------------------

    if role == "vendor":

        error = ""
        if request.method == 'POST':

            name = request.form.get('name', '').strip()
            price_raw = request.form.get('price', '')
            vendor = session['user']
            image_path = ""

            valid_price, formatted_price = validate_price(price_raw)
            if not name:
                error = "Product name is required."
            elif not valid_price:
                error = formatted_price
            else:
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename != '':
                        saved = validate_and_save_image(file)
                        if saved:
                            image_path = saved
                        else:
                            error = "Invalid image file. Only JPG, PNG, WEBP, and JFIF images under 5 MB are allowed."

                if not error:
                    conn.execute(
                        "INSERT INTO products(vendor,name,price,image,availability) VALUES(?,?,?,?,?)",
                        (vendor, name, formatted_price, image_path, "In Stock")
                    )
                    conn.commit()
                    return redirect('/products')

        products = conn.execute(
            "SELECT * FROM products WHERE vendor=? ORDER BY id DESC",
            (session['user'],)
        ).fetchall()

        return render_template(
            'products.html',
            products=products,
            error=error
        )

    # -------------------------
    # CUSTOMER
    # -------------------------

    else:

        connected_vendors = conn.execute(
            "SELECT vendor FROM connections WHERE customer=? ORDER BY id DESC",
            (session['user'],)
        ).fetchall()

        vendor_names = [v['vendor'] for v in connected_vendors]

        if vendor_names:

            placeholders = ",".join("?" * len(vendor_names))

            query = f"""
                SELECT * FROM products
                WHERE vendor IN ({placeholders})
                ORDER BY id DESC
            """

            products = conn.execute(
                query,
                vendor_names
            ).fetchall()

        else:
            products = []

        return render_template(
            'customer_products.html',
            products=products
        )

@app.route('/edit_product/<int:id>', methods=['POST'])
@login_required
@role_required('vendor')
def edit_product(id):
    conn = get_db()
    # Enforce vendor multi-tenant isolation
    prod = conn.execute("SELECT * FROM products WHERE id=? AND vendor=?", (id, session['user'])).fetchone()
    if not prod:
        return redirect('/products')

    name = request.form.get('name', '').strip() or prod['name']
    price_raw = request.form.get('price', '')
    availability = request.form.get('availability', 'In Stock')
    if availability not in ('In Stock', 'Out Of Stock'):
        availability = 'In Stock'

    valid_price, formatted_price = validate_price(price_raw)
    if not valid_price:
        formatted_price = prod['price']

    # Check if a new image was uploaded
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename != '':
            saved = validate_and_save_image(file)
            if saved:
                conn.execute(
                    "UPDATE products SET name=?, price=?, availability=?, image=? WHERE id=? AND vendor=?",
                    (name, formatted_price, availability, saved, id, session['user'])
                )
                conn.commit()
                return redirect('/products')

    conn.execute(
        "UPDATE products SET name=?, price=?, availability=? WHERE id=? AND vendor=?",
        (name, formatted_price, availability, id, session['user'])
    )
    conn.commit()
    return redirect('/products')

@app.route('/delete_product/<int:id>', methods=['POST'])
@login_required
@role_required('vendor')
def delete_product(id):
    conn = get_db()
    # Enforce multi-tenant isolation: only the owning vendor can delete this product
    conn.execute("DELETE FROM products WHERE id=? AND vendor=?", (id, session['user']))
    conn.commit()
    return redirect('/products')

@app.route('/orders')
@login_required
def orders():
    conn = get_db()

    role = session['role']

    # -------------------------
    # VENDOR
    # -------------------------

    if role == "vendor":

        orders = conn.execute(
            "SELECT * FROM orders WHERE vendor=? ORDER BY id DESC",
            (session['user'],)
        ).fetchall()

    # -------------------------
    # CUSTOMER
    # -------------------------

    else:

        orders = conn.execute(
            "SELECT * FROM orders WHERE customer=? ORDER BY id DESC",
            (session['user'],)
        ).fetchall()

    return render_template(
        'orders.html',
        orders=orders
    )
# ---------------------------------
# DELIVERY
# ---------------------------------

@app.route('/delivery')
@login_required
def delivery():
    conn = get_db()

    if session['role'] == 'vendor':

        orders = conn.execute(
            "SELECT * FROM orders WHERE vendor=? ORDER BY id DESC",
            (session['user'],)
        ).fetchall()

    else:

        orders = conn.execute(
            "SELECT * FROM orders WHERE customer=? ORDER BY id DESC",
            (session['user'],)
        ).fetchall()

    return render_template(
        'delivery.html',
        orders=orders
    )
# ---------------------------------
# PAYMENTS
# ---------------------------------

@app.route('/payment/order/<int:order_id>')
@login_required
@role_required('customer')
def payment_checkout(order_id):
    conn = get_db()
    o, state = _payment_order_state(conn, order_id, session['user'])
    if state == 'invalid':
        return redirect('/payments?pay=invalid')
    if state == 'blocked':
        return redirect('/payments?pay=done')
    if state == 'awaiting':
        return redirect('/payments?pay=pending')
    return render_template('payment_checkout.html', order=o)


@app.route('/payment/order/<int:order_id>/card', methods=['GET', 'POST'])
@login_required
@role_required('customer')
def payment_card(order_id):
    conn = get_db()
    o, state = _payment_order_state(conn, order_id, session['user'])
    if state not in ('new', 'retry'):
        return redirect('/payments?pay=invalid')
    err = ''
    if request.method == 'POST':
        holder = (request.form.get('card_holder') or '').strip()
        pan = re.sub(r'\D', '', request.form.get('card_number') or '')
        exp = (request.form.get('expiry') or '').strip()
        cvv = (request.form.get('cvv') or '').strip()
        if len(holder) < 2:
            err = 'Enter the card holder name.'
        elif not _luhn_valid(pan):
            err = 'Invalid card number.'
        elif not _card_expiry_valid(exp):
            err = 'Invalid or expired card (use MM/YY).'
        elif not re.match(r'^\d{3,4}$', cvv):
            err = 'CVV must be 3 or 4 digits.'
        else:
            last4 = pan[-4:]
            ok = _finalize_customer_payment(
                conn,
                order_id,
                session['user'],
                o['vendor'],
                o['product_name'],
                o['price'],
                'card',
                '',
                '',
                last4,
                '',
            )
            if ok:
                return redirect('/payments?pay=success')
            err = 'Unable to record payment. Please try again.'
    return render_template('payment_card.html', order=o, error=err)


@app.route('/payment/order/<int:order_id>/upi')
@login_required
@role_required('customer')
def payment_upi_platforms(order_id):
    conn = get_db()
    o, state = _payment_order_state(conn, order_id, session['user'])
    if state not in ('new', 'retry'):
        return redirect('/payments?pay=invalid')
    return render_template('payment_upi_platforms.html', order=o)


@app.route('/payment/order/<int:order_id>/upi/<platform>')
@login_required
@role_required('customer')
def payment_upi_flow(order_id, platform):
    if platform not in UPI_PLATFORM_SLUGS:
        return redirect('/payments?pay=invalid')
    conn = get_db()
    o, state = _payment_order_state(conn, order_id, session['user'])
    if state not in ('new', 'retry'):
        return redirect('/payments?pay=invalid')
    label = UPI_PLATFORM_SLUGS[platform]
    return render_template(
        'payment_upi_flow.html',
        order=o,
        platform=platform,
        platform_label=label,
    )


@app.route('/payment/order/<int:order_id>/upi/<platform>/qr', methods=['GET', 'POST'])
@login_required
@role_required('customer')
def payment_upi_qr(order_id, platform):
    if platform not in UPI_PLATFORM_SLUGS:
        return redirect('/payments?pay=invalid')
    conn = get_db()
    o, state = _payment_order_state(conn, order_id, session['user'])
    if state not in ('new', 'retry'):
        return redirect('/payments?pay=invalid')
    label = UPI_PLATFORM_SLUGS[platform]
    vpa = _vendor_collect_vpa(conn, o['vendor'])
    amt = _digits_only_amount(o['price'])
    uri = _build_upi_uri(vpa, o['vendor'], amt, f"{o['product_name'][:80]} — Order #{order_id}")
    qr_src = _qr_data_uri(uri)
    err = ''
    if request.method == 'POST':
        ok = _finalize_customer_payment(
            conn,
            order_id,
            session['user'],
            o['vendor'],
            o['product_name'],
            o['price'],
            'upi',
            label,
            'QR',
            '',
            '',
        )
        if ok:
            return redirect('/payments?pay=success')
        err = 'Unable to record payment.'
    return render_template(
        'payment_upi_qr.html',
        order=o,
        platform=platform,
        platform_label=label,
        qr_src=qr_src,
        upi_uri=uri,
        amount_display=amt,
        error=err,
    )


@app.route('/payment/order/<int:order_id>/upi/<platform>/upi-id', methods=['GET', 'POST'])
@login_required
@role_required('customer')
def payment_upi_id(order_id, platform):
    if platform not in UPI_PLATFORM_SLUGS:
        return redirect('/payments?pay=invalid')
    conn = get_db()
    o, state = _payment_order_state(conn, order_id, session['user'])
    if state not in ('new', 'retry'):
        return redirect('/payments?pay=invalid')
    label = UPI_PLATFORM_SLUGS[platform]
    err = ''
    if request.method == 'POST':
        u1 = (request.form.get('upi_id') or '').strip().lower()
        u2 = (request.form.get('upi_id_confirm') or '').strip().lower()
        if not u1 or not u2:
            err = 'Enter and confirm your UPI ID.'
        elif u1 != u2:
            err = 'UPI IDs do not match.'
        elif not _upi_format_valid(u1):
            err = 'Invalid UPI ID format (e.g. name@ybl).'
        else:
            masked = _mask_upi_id(u1)
            ok = _finalize_customer_payment(
                conn,
                order_id,
                session['user'],
                o['vendor'],
                o['product_name'],
                o['price'],
                'upi',
                label,
                'UPI ID',
                '',
                masked,
            )
            if ok:
                return redirect('/payments?pay=success')
            err = 'Unable to record payment.'
    return render_template(
        'payment_upi_id.html',
        order=o,
        platform=platform,
        platform_label=label,
        error=err,
    )


@app.route('/payments', methods=['GET'])
@login_required
def payments():
    conn = get_db()

    # CUSTOMER VIEW
    if session['role'] == 'customer':
        payments = conn.execute(
            '''
            SELECT p.*, o.product_image, o.status as delivery_status, o.delivered_date 
            FROM payments p
            LEFT JOIN orders o ON p.order_id = o.id
            WHERE p.customer=?
            ORDER BY p.id DESC
            ''',
            (session['user'],)
        ).fetchall()

        orders = conn.execute(
            '''
            SELECT * FROM orders
            WHERE customer=?
            ORDER BY id DESC
            ''',
            (session['user'],)
        ).fetchall()

    # VENDOR VIEW
    else:
        payments = conn.execute(
            '''
            SELECT p.*, o.product_image, o.status as delivery_status, o.delivered_date 
            FROM payments p
            LEFT JOIN orders o ON p.order_id = o.id
            WHERE p.vendor=?
            ORDER BY p.id DESC
            ''',
            (session['user'],)
        ).fetchall()

        orders = []

    return render_template(
        'payments.html',
        payments=payments,
        orders=orders,
        pay_notice=request.args.get('pay', ''),
    )


@app.route('/update_payment', methods=['POST'])
@login_required
@role_required('vendor')
def update_payment():
    payment_id = request.form['payment_id']
    status = request.form['status']
    conn = get_db()

    # Get the payment record
    payment = conn.execute(
        "SELECT * FROM payments WHERE id=? AND vendor=?",
        (payment_id, session['user']),
    ).fetchone()
    
    if payment:
        current_time = datetime.now().strftime('%d/%m/%Y, %I:%M %p')
        
        if status in ('Payment Verified Successfully', 'Accepted'):
            conn.execute(
                '''
                UPDATE payments
                SET status=?, payment_date=?
                WHERE id=?
                ''',
                ('Accepted', current_time, payment_id)
            )
        elif status == 'Payment Not Received':
            conn.execute(
                '''
                UPDATE payments
                SET status=?, payment_date=?
                WHERE id=?
                ''',
                ('Payment Not Received', current_time, payment_id)
            )
        else:
            conn.execute(
                '''
                UPDATE payments
                SET status=?, payment_date=?
                WHERE id=?
                ''',
                (status, current_time, payment_id)
            )
        
        conn.commit()

    return redirect('/payments')


@app.route('/process_refund', methods=['POST'])
@login_required
@role_required('vendor')
def process_refund():
    payment_id = request.form['payment_id']
    conn = get_db()
    ts = datetime.now().strftime('%d/%m/%Y, %I:%M %p')
    conn.execute(
        "UPDATE payments SET status='Refund Completed', payment_date=? WHERE id=? AND vendor=?",
        (ts, payment_id, session['user']),
    )
    conn.commit()
    return redirect('/payments')
# ---------------------------------
# REVIEWS
# ---------------------------------

@app.route('/reviews', methods=['GET', 'POST'])
@login_required
def reviews():
    conn = get_db()

    role = session['role']

    # -------------------------
    # CUSTOMER ADDS REVIEW
    # -------------------------

    if request.method == 'POST' and role == "customer":

        vendor = request.form['vendor']
        rating = request.form['rating']
        comment = request.form['comment']

        conn.execute(
            """
            INSERT INTO reviews(vendor,rating,comment,customer)
            VALUES(?,?,?,?)
            """,
            (vendor, rating, comment, session['user'])
        )

        conn.commit()

    # -------------------------
    # CUSTOMER VIEW
    # -------------------------

    if role == "customer":

        connected_vendors = conn.execute(
            """
            SELECT vendor
            FROM connections
            WHERE customer=?
            ORDER BY id DESC
            """,
            (session['user'],)
        ).fetchall()

        reviews = conn.execute(
            "SELECT * FROM reviews ORDER BY id DESC"
        ).fetchall()

        return render_template(
            'reviews.html',
            reviews=reviews,
            vendors=connected_vendors
        )

    # -------------------------
    # VENDOR VIEW
    # -------------------------

    else:

        reviews = conn.execute(
            """
            SELECT * FROM reviews
            WHERE vendor=?
            ORDER BY id DESC
            """,
            (session['user'],)
        ).fetchall()

        return render_template(
            'reviews.html',
            reviews=reviews,
            vendors=[]
        )
# ---------------------------------
# VENDOR SELECTION & ORDERS
# ---------------------------------

@app.route('/select_vendor', methods=['POST'])
@login_required
def select_vendor():
    customer = session['user']

    vendor = request.form['vendor']

    conn = get_db()

    existing = conn.execute(
        "SELECT * FROM connections WHERE customer=? AND vendor=?",
        (customer, vendor)
    ).fetchone()

    if not existing:

        conn.execute(
            "INSERT INTO connections(customer,vendor) VALUES(?,?)",
            (customer, vendor)
        )

        conn.commit()

    return redirect('/vendors')

@app.route('/add_order', methods=['POST'])
@login_required
@role_required('customer')
def add_order():
    product_id = request.form.get('product_id')
    if not product_id:
        return redirect('/products')

    customer = session['user']
    conn = get_db()

    product = conn.execute(
        "SELECT * FROM products WHERE id=?",
        (product_id,)
    ).fetchone()

    if not product or product['availability'] == 'Out Of Stock':
        return redirect('/products')

    vendor = product['vendor']
    product_name = product['name']
    price = product['price']

    conn.execute(
        '''
        INSERT INTO orders(
            customer,
            vendor,
            product_name,
            price,
            status,
            product_image
        )
        VALUES(?,?,?,?,?,?)
        ''',
        (
            customer,
            vendor,
            product_name,
            price,
            'Pending',
            product['image']
        )
    )

    conn.commit()

    return redirect('/orders')

@app.route('/update_order', methods=['POST'])
@login_required
@role_required('vendor')
def update_order():
    order_id = request.form.get('order_id')
    status = request.form.get('status')
    expected_delivery = request.form.get('expected_delivery', '')
    delivered_date = request.form.get('delivered_date', '')

    if not order_id or not status:
        return redirect('/orders')

    conn = get_db()
    
    # Enforce vendor multi-tenant isolation: vendor can only update their own orders
    order = conn.execute("SELECT * FROM orders WHERE id=? AND vendor=?", (order_id, session['user'])).fetchone()
    if not order:
        return redirect('/orders')

    if order['status'] == 'Out Of Stock':
        # Cannot change status of Out Of Stock order
        return redirect('/orders')
    
    # Format delivery date in Indian format if provided
    if delivered_date:
        try:
            dt = datetime.strptime(delivered_date, '%Y-%m-%d')
            delivered_date = dt.strftime('%d/%m/%Y')
        except Exception:
            pass
    
    if expected_delivery:
        try:
            dt = datetime.strptime(expected_delivery, '%Y-%m-%d')
            expected_delivery = dt.strftime('%d/%m/%Y')
        except Exception:
            pass

    conn.execute(
        "UPDATE orders SET status=?, expected_delivery=?, delivered_date=? WHERE id=? AND vendor=?",
        (status, expected_delivery, delivered_date, order_id, session['user'])
    )

    if status == "Out Of Stock":
        existing_payment = conn.execute("SELECT * FROM payments WHERE order_id=?", (order_id,)).fetchone()
        
        # Format current time in Indian format
        current_time = datetime.now().strftime('%d/%m/%Y, %I:%M %p')
        
        if not existing_payment:
            conn.execute(
                '''
                INSERT INTO payments(
                    order_id, customer, vendor, product_name, amount, status, payment_date,
                    payment_method, upi_platform, upi_flow, card_last4, upi_masked
                )
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ''',
                (
                    order['id'],
                    order['customer'],
                    order['vendor'],
                    order['product_name'],
                    order['price'],
                    'Out Of Stock',
                    current_time,
                    'legacy',
                    '',
                    '',
                    '',
                    '',
                ),
            )
        else:
            conn.execute("UPDATE payments SET status='Out Of Stock', payment_date=? WHERE order_id=?", (current_time, order_id))

    conn.commit()
    return redirect('/orders')


@app.route('/cancel_order', methods=['POST'])
@login_required
def cancel_order():
    order_id = request.form['order_id']
    conn = get_db()
    
    order = conn.execute("SELECT * FROM orders WHERE id=? AND customer=?", (order_id, session['user'])).fetchone()
    if order and order['status'] not in ['Shipped', 'Out For Delivery', 'Delivered', 'Cancelled']:
        conn.execute("UPDATE orders SET status='Cancelled' WHERE id=?", (order_id,))
        
        # Check if payment exists
        payment = conn.execute("SELECT * FROM payments WHERE order_id=?", (order_id,)).fetchone()
        if payment and payment['status'] in ['Completed', 'Pending Vendor Verification', 'Accepted']:
            conn.execute(
                "UPDATE payments SET status='Refund Pending', payment_date=? WHERE order_id=?",
                (datetime.now().strftime('%d/%m/%Y, %I:%M %p'), order_id),
            )
            
        conn.commit()

    return redirect('/orders')
# ---------------------------------
# VIEW VENDOR PRODUCTS
# ---------------------------------

@app.route('/vendor_products/<vendor_name>')
@login_required
def vendor_products(vendor_name):
    conn = get_db()

    # CHECK CONNECTION

    connection = conn.execute(
        '''
        SELECT * FROM connections
        WHERE customer=? AND vendor=?
        ''',
        (session['user'], vendor_name)
    ).fetchone()

    connected = False

    if connection:
        connected = True

    # GET PRODUCTS OF THAT VENDOR

    products = conn.execute(
        '''
        SELECT * FROM products
        WHERE vendor=?
        ORDER BY id DESC
        ''',
        (vendor_name,)
    ).fetchall()

    return render_template(
        'vendor_products.html',
        products=products,
        vendor_name=vendor_name,
        connected=connected
    )
# ---------------------------------
# VIEW SINGLE VENDOR REVIEWS
# ---------------------------------

@app.route('/vendor_reviews/<vendor_name>')
@login_required
def vendor_reviews(vendor_name):
    conn = get_db()

    reviews = conn.execute(
        '''
        SELECT * FROM reviews
        WHERE vendor=?
        ORDER BY id DESC
        ''',
        (vendor_name,)
    ).fetchall()

    return render_template(
        'vendor_reviews.html',
        vendor_name=vendor_name,
        reviews=reviews
    )

# ---------------------------------
# LOGOUT
# ---------------------------------

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    return render_template('error.html', code=400, message=f"CSRF validation failed: {e.description}. Please refresh and try again."), 400


@app.errorhandler(400)
def bad_request(e):
    return render_template('error.html', code=400, message="Bad request. Please verify your submitted data."), 400


@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', code=404, message="The page you are looking for does not exist."), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return render_template('error.html', code=405, message="The requested HTTP method is not allowed for this endpoint."), 405


@app.errorhandler(413)
def request_entity_too_large(e):
    return render_template('error.html', code=413, message="The uploaded file exceeds the 5 MB limit. Please choose a smaller image."), 413


@app.errorhandler(429)
def ratelimit_handler(e):
    return render_template('error.html', code=429, message="Too many requests. Please slow down and try again later."), 429


@app.errorhandler(403)
def forbidden(e):
    return render_template('error.html', code=403, message="You do not have permission to access this resource."), 403


@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', code=500, message="An internal server error occurred. Please try again."), 500


# ---------------------------------
# RUN APP
# ---------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)