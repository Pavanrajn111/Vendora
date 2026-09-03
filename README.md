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
- **Responsive Layout**: Designed for mobile, tablet, and desktop viewports.
- **Smart Image Resolver**: Case-insensitive and multi-extension (.png, .jpg, .jpeg, .jfif, .webp) asset discovery with SVG fallback.

---

## Tech Stack

- **Backend**: Python 3.10+, Flask 3.0
- **Database**: SQLite3 (auto-initializing schema and migrations)
- **Security**: Werkzeug password hashing (PBKDF2/scrypt), session-based role authorization, environment configuration
- **Frontend**: Jinja2 Templates, HTML5, Vanilla JavaScript, Tailwind CSS, FontAwesome 6, Google Fonts (Inter)
- **Utilities**: qrcode[pil] (Dynamic UPI QR generation), python-dotenv
- **WSGI / Deployment**: Gunicorn

---

## Project Structure

`	ext
vendora-marketplace/
├── app.py                  # Main Flask application entry point, routes & database handlers
├── requirements.txt        # Production & runtime dependencies
├── Procfile                # Deployment process declaration (Gunicorn)
├── .env.example            # Environment variable template
├── .gitignore              # Git ignore rules (ignores .env, databases, bytecode)
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
│   └── error.html          # Custom 404 / 403 / 500 error pages
├── tests/
│   ├── test_vendora.py     # Automated end-to-end unittest suite
│   ├── test_endpoints.py   # Endpoint smoke tests
│   ├── test_image_detection.py # Image resolver tests
│   └── test_url_for.py     # Static asset URL builder test
└── scripts/                # Database utilities & migration helpers
`

---

## Installation & Quickstart

### 1. Clone Repository
`ash
git clone https://github.com/<your-username>/vendora-marketplace.git
cd vendora-marketplace
`

### 2. Create Virtual Environment
`ash
# On Linux / macOS:
python3 -m venv .venv
source .venv/bin/activate

# On Windows (PowerShell):
python -m venv .venv
.venv\Scripts\Activate.ps1
`

### 3. Install Dependencies
`ash
pip install -r requirements.txt
`

### 4. Configure Environment
`ash
# Copy example environment configuration
cp .env.example .env
`

Edit .env to set your custom secret key:
`env
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=your-secure-random-secret-key
COLLECT_UPI_VPA=merchant.vendora@ptyes
`

### 5. Seed Demo Data (Optional)
`ash
python seed_demo_data.py
`

### 6. Run Application
`ash
python app.py
`
Open your browser and navigate to: **http://localhost:5000**

---

## Demo Credentials

For quick evaluation, the following pre-configured demo accounts can be used (password: pass123 for all seeded accounts):

| Role | Username | Password | Purpose |
|---|---|---|---|
| **Vendor** | TechNova Electronics | pass123 | Electronics catalog, incoming orders & UPI verification |
| **Vendor** | Urban Fashion Hub | pass123 | Apparel & footwear storefront |
| **Customer** | Rahul Sharma | pass123 | Active customer with order history |
| **Customer** | Priya Verma | pass123 | Customer connected to multiple vendors |

*You can also register any new Customer or Vendor account directly from /register.*

---

## Testing

Run the automated test suite with Python's built-in unittest runner or pytest:

`ash
# Run full test suite
python -m unittest tests/test_vendora.py

# Run endpoint smoke tests
python tests/test_endpoints.py

# Run image detection tests
python tests/test_image_detection.py
`

---

## Production Deployment

To run in production using Gunicorn:

`ash
gunicorn app:app --bind 0.0.0.0:5000 --workers 4
`

Set the following environment variables on your hosting provider (e.g. Render, Railway, AWS, DigitalOcean):
- SECRET_KEY: A cryptographically secure random string.
- COLLECT_UPI_VPA: Merchant UPI VPA for payment simulations (e.g. merchant.vendora@ptyes).

---

## Limitations & Notes

- **Simulated Payment Gateway**: Payments in Vendora (Card and UPI) simulate standard e-commerce transaction workflows and vendor verification without charging actual bank accounts or credit cards.
- **Database Engine**: Uses SQLite for simplicity, portability, and zero-configuration local deployment.

---

## License

This project is open-source and available under the [MIT License](LICENSE).
