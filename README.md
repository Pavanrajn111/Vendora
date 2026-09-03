# Vendora

**A Vendor & Customer Marketplace Platform**

Vendora is a modern, full-stack marketplace web application built with Python (Flask), SQLite, Jinja2, Tailwind CSS, and custom glassmorphic UI components. It enables seamless product discovery, vendor connections, ordering, delivery tracking, simulated payment verification, and review workflows for customers and vendors.

---

## Overview

Vendora provides an intuitive, responsive multi-vendor platform where:
- **Customers** can browse trusted vendors, explore product catalogues, connect with preferred merchants, place orders, complete checkout via simulated UPI or Card payments, track order deliveries, and submit merchant ratings and feedback.
- **Vendors** can manage their storefront, upload and edit product listings (with automated image detection and fallback handling), manage incoming orders, verify payments, update delivery timelines, and monitor customer reviews and analytics.

---

## Features

### 🛍️ Customer Workflow
- **Discovery & Connections**: Explore active vendor storefronts and connect with suppliers.
- **Product Catalog**: Browse real-time products categorized by connected vendors with pricing in INR (₹).
- **Order Placement**: Place orders with automatic status tracking.
- **Simulated Payment Gateway**:
  - **UPI Flow**: Dynamic QR code generation, platform selection (Google Pay, PhonePe, Paytm), and UPI ID verification.
  - **Card Payment**: Luhn-validated card input with expiry and CVV checks.
- **Delivery Tracking**: Track order milestones from *Pending* to *Accepted*, *Shipped*, *Out For Delivery*, and *Delivered*.
- **Reviews & Ratings**: Submit 1–5 star ratings and written reviews for verified vendors.
- **Account Settings**: Update mobile number and change password with security validation.

### 🏢 Vendor Workflow
- **Vendor Dashboard**: Real-time business metrics including total connected customers, active orders, and customer reviews.
- **Product Management**: Add new products with image uploads, update stock availability (*In Stock* / *Out Of Stock*), and edit or remove listings.
- **Order Processing**: Accept customer orders, assign estimated delivery dates, and mark deliveries complete.
- **Payment Verification**: Review incoming customer payment submissions, verify receipts, or process refunds.
- **Multi-Tenant Isolation**: Server-side tenancy enforcement ensuring vendors can only access and modify their own products and orders.

### 🎨 Design & Experience
- **Glassmorphism UI**: Modern frosted-glass aesthetic with smooth transitions and CSS animations.
- **Dark / Light Theme Toggle**: Persistent theme switching with automatic system preference detection.
- **Smart Image Resolver**: Case-insensitive and multi-extension (.png, .jpg, .jpeg, .jfif, .webp) asset discovery with SVG fallback.

---

## Tech Stack

- **Backend**: Python 3.10+, Flask 3.0
- **Database**: SQLite3 (auto-initializing schema and migrations with parameterized queries)
- **Security**: Flask-WTF (CSRF Protection), Flask-Limiter (Rate Limiting), Werkzeug password hashing (PBKDF2/scrypt), Pillow (Image validation), session-based role authorization
- **Frontend**: Jinja2 Templates, HTML5, Vanilla JavaScript, Tailwind CSS, FontAwesome 6, Google Fonts (Inter)
- **Utilities**: qrcode[pil] (Dynamic UPI QR generation), python-dotenv
- **WSGI / Deployment**: Gunicorn, GitHub Actions CI

---

## Project Structure

```text
Vendora/
├── .github/workflows/      # Automated CI pipeline (GitHub Actions)
├── app.py                  # Main Flask application entry point, routes & database handlers
├── requirements.txt        # Production & runtime dependencies
├── Procfile                # Deployment process declaration (Gunicorn)
├── .env.example            # Environment variable template
├── .gitignore              # Git ignore rules (ignores .env, databases, bytecode)
├── LICENSE                 # MIT License
├── README.md               # Project documentation
├── seed_demo_data.py       # Idempotent demo dataset seeder
├── static/
│   ├── css/
│   │   ├── main.css        # Core stylesheet
│   │   └── style.css       # Glassmorphic UI theme & variables
│   ├── images/             # Backgrounds & SVG product placeholder
│   └── uploads/            # Product image catalogue
├── templates/
│   ├── base.html           # Master layout with navbar, theme toggle & footer
│   ├── index.html          # Public landing page
│   ├── login.html          # Authentication / Sign In
│   ├── register.html       # Account Registration
│   ├── dashboard.html      # Role-aware dashboard (Customer / Vendor)
│   ├── products.html       # Vendor product management
│   ├── customer_products.html # Customer product browsing
│   ├── orders.html         # Order tracking & management
│   ├── delivery.html       # Delivery progress monitoring
│   ├── payments.html       # Payment records & vendor verification
│   ├── payment_*.html      # Checkout, Card & UPI payment templates
│   ├── reviews.html        # Customer reviews & ratings
│   ├── settings.html       # User profile & security settings
│   └── error.html          # Custom 404 / 403 / 405 / 413 / 429 / 500 error pages
├── tests/
│   ├── test_vendora.py     # Automated end-to-end unittest suite (15+ tests)
│   ├── test_endpoints.py   # Endpoint smoke tests
│   ├── test_image_detection.py # Image resolver tests
│   └── test_url_for.py     # Static asset URL builder test
└── scripts/                # Database utilities & migration helpers
```

---

## Security Highlights

Vendora implements defense-in-depth security practices suitable for production portfolio deployment:

1. **CSRF Protection**: Comprehensive CSRF defense across all state-changing endpoints and forms using `Flask-WTF`.
2. **POST-Only Destructive Actions**: Product deletion is strictly POST-only with confirmation dialogs and tenant ownership verification.
3. **Password Security**: Werkzeug PBKDF2/scrypt password hashing with server-side strength validation (8+ characters, uppercase, lowercase, digit, special symbol).
4. **Login Rate Limiting**: Anti-brute-force rate limiting on `/login` via `Flask-Limiter`.
5. **Secure File Uploads**: Strict whitelist (`.jpg`, `.jpeg`, `.png`, `.webp`), 5 MB file size ceiling (`MAX_CONTENT_LENGTH`), and in-memory Pillow image verification to prevent malicious file uploads.
6. **SQL Injection Defense**: 100% parameterized SQL queries via SQLite3.
7. **Multi-Tenant Isolation**: Server-side authorization checks ensure vendors cannot access, edit, or delete another vendor's products or orders.
8. **Input & Price Validation**: Server-side price validation enforces numeric positive values with appropriate decimal formatting.

---

## Installation & Quickstart

### 1. Clone Repository
```bash
git clone https://github.com/Pavanrajn111/Vendora.git
cd Vendora
```

### 2. Create Virtual Environment
```bash
# On Linux / macOS:
python3 -m venv .venv
source .venv/bin/activate

# On Windows (PowerShell):
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
```bash
# Copy example environment configuration
cp .env.example .env
```

Edit `.env` to set your custom secret key:
```env
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=your-secure-random-secret-key
COLLECT_UPI_VPA=merchant.vendora@ptyes
```

### 5. Seed Demo Data (Optional)
```bash
python seed_demo_data.py
```

### 6. Run Application
```bash
python app.py
```
Open your browser and navigate to: **http://localhost:5000**

---

## Demo Credentials

For quick evaluation, the following pre-configured demo accounts can be used (password: `pass123` for all seeded accounts):

| Role | Username | Password | Purpose |
|---|---|---|---|
| **Vendor** | TechNova Electronics | pass123 | Electronics catalog, incoming orders & UPI verification |
| **Vendor** | Urban Fashion Hub | pass123 | Apparel & footwear storefront |
| **Customer** | Rahul Sharma | pass123 | Active customer with order history |
| **Customer** | Priya Verma | pass123 | Customer connected to multiple vendors |

*You can also register any new Customer or Vendor account directly from /register.*

---

## Testing

Run the automated test suite with Python's built-in unittest runner:

```bash
# Run full test suite (16 tests)
python -m unittest discover -s tests

# Or run individual test modules
python -m unittest tests/test_vendora.py
python -m unittest tests/test_endpoints.py
python -m unittest tests/test_image_detection.py
```

---

## Production Deployment

### Deploying to Vercel (Recommended)

Vendora is pre-configured for seamless serverless deployment on **[Vercel](https://vercel.com/)**:

1. Push this repository to your GitHub account.
2. Log in to [Vercel](https://vercel.com/) and click **"Add New Project"**.
3. Import your `Vendora` repository.
4. Framework Preset: Choose **"Other"** (Vercel automatically detects `vercel.json` and `@vercel/python`).
5. (Optional) In **Environment Variables**, add:
   - `SECRET_KEY`: A cryptographically secure random string.
   - `COLLECT_UPI_VPA`: `merchant.vendora@ptyes`
6. Click **Deploy**. Your marketplace will be live in seconds!

### Deploying with Gunicorn (Render / Railway / VPS)

To run using Gunicorn:

```bash
gunicorn app:app --bind 0.0.0.0:5000 --workers 4
```

Set the following environment variables on your hosting provider:
- `SECRET_KEY`: A cryptographically secure random string.
- `COLLECT_UPI_VPA`: Merchant UPI VPA for payment simulations (e.g. `merchant.vendora@ptyes`).

---

## Limitations & Notes

- **Simulated Payment Gateway**: Payments in Vendora (Card and UPI) simulate standard e-commerce transaction workflows and vendor verification without charging actual bank accounts or credit cards.
- **Database Engine**: Uses SQLite for simplicity, portability, and zero-configuration local deployment.

---

## License

This project is open-source and available under the [MIT License](LICENSE).
