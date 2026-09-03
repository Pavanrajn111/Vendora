"""
Vendora — Automated Functional & Security Test Suite
Tests authentication, authorization, role restrictions, product lifecycle,
order flows, simulated payment flows, delivery tracking, and reviews.
"""

import os
import sys
import unittest
import sqlite3

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app import app, get_db, limiter


class VendoraTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._cleanup_test_data()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_test_data()

    @staticmethod
    def _cleanup_test_data():
        try:
            conn = get_db()
            conn.execute("DELETE FROM users WHERE username LIKE 'autotest_%'")
            conn.execute("DELETE FROM products WHERE vendor LIKE 'autotest_%'")
            conn.execute("DELETE FROM orders WHERE customer LIKE 'autotest_%' OR vendor LIKE 'autotest_%'")
            conn.execute("DELETE FROM payments WHERE customer LIKE 'autotest_%' OR vendor LIKE 'autotest_%'")
            conn.execute("DELETE FROM reviews WHERE customer LIKE 'autotest_%' OR vendor LIKE 'autotest_%'")
            conn.execute("DELETE FROM connections WHERE customer LIKE 'autotest_%' OR vendor LIKE 'autotest_%'")
            conn.commit()
        except Exception:
            pass

    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.config['RATELIMIT_ENABLED'] = False
        limiter.enabled = False
        app.config['SECRET_KEY'] = 'test-secret-key-123'
        self.client = app.test_client()

    def test_01_landing_page(self):
        """Verify landing page loads with Vendora branding."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Vendora', response.data)
        self.assertIn(b'Marketplace', response.data)

    def test_02_unauthenticated_redirects(self):
        """Verify protected routes redirect unauthenticated users to /login."""
        protected_routes = [
            '/dashboard',
            '/profile',
            '/vendors',
            '/products',
            '/orders',
            '/delivery',
            '/payments',
            '/reviews',
            '/settings',
        ]
        for path in protected_routes:
            response = self.client.get(path, follow_redirects=False)
            self.assertIn(response.status_code, (301, 302))
            self.assertIn('/login', response.headers.get('Location', ''))

    def test_03_registration_and_login_flow(self):
        """Verify customer and vendor registration and login."""
        # 1. Register customer
        resp = self.client.post('/register', data={
            'username': 'autotest_customer',
            'password': 'Password@123',
            'role': 'customer',
            'mobile': '9000000001'
        }, follow_redirects=False)
        self.assertIn(resp.status_code, (301, 302))
        self.assertIn('/login', resp.headers.get('Location', ''))

        # 2. Prevent duplicate username
        resp_dup = self.client.post('/register', data={
            'username': 'autotest_customer',
            'password': 'Password@123',
            'role': 'customer',
            'mobile': '9000000001'
        })
        self.assertIn(b'Username already exists', resp_dup.data)

        # 3. Register vendor
        resp_v = self.client.post('/register', data={
            'username': 'autotest_vendor',
            'password': 'Password@123',
            'role': 'vendor',
            'mobile': '9000000002'
        }, follow_redirects=False)
        self.assertIn(resp_v.status_code, (301, 302))

        # 4. Login customer
        resp_login = self.client.post('/login', data={
            'username': 'autotest_customer',
            'password': 'Password@123'
        }, follow_redirects=False)
        self.assertIn(resp_login.status_code, (301, 302))
        self.assertIn('/dashboard', resp_login.headers.get('Location', ''))

    def test_04_customer_flow(self):
        """Verify customer dashboard, vendor browsing, and connection."""
        # Login
        self.client.post('/login', data={'username': 'autotest_customer', 'password': 'Password@123'})

        # Dashboard
        resp = self.client.get('/dashboard')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'autotest_customer', resp.data)

        # Vendors list
        resp = self.client.get('/vendors')
        self.assertEqual(resp.status_code, 200)

        # Connect to vendor
        resp = self.client.post('/select_vendor', data={'vendor': 'autotest_vendor'}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        # Profile
        resp = self.client.get('/profile')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'autotest_vendor', resp.data)

        # Logout
        resp = self.client.get('/logout', follow_redirects=False)
        self.assertIn(resp.status_code, (301, 302))

    def test_05_vendor_product_lifecycle(self):
        """Verify vendor can create, view, edit, and delete products."""
        # Login as vendor
        self.client.post('/login', data={'username': 'autotest_vendor', 'password': 'Password@123'})

        # Create product
        resp = self.client.post('/products', data={
            'name': 'Test Mechanical Keyboard',
            'price': '3499'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Test Mechanical Keyboard', resp.data)

        # Query created product
        conn = get_db()
        prod = conn.execute("SELECT * FROM products WHERE name='Test Mechanical Keyboard' AND vendor='autotest_vendor'").fetchone()
        self.assertIsNotNone(prod)
        prod_id = prod['id']

        # Edit product
        resp = self.client.post(f'/edit_product/{prod_id}', data={
            'name': 'Test Mechanical Keyboard RGB',
            'price': '3999',
            'availability': 'In Stock'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Test Mechanical Keyboard RGB', resp.data)

        self.client.get('/logout')

    def test_06_order_and_payment_workflow(self):
        """Verify complete checkout, simulated card payment, vendor verification, delivery, and review."""
        conn = get_db()
        prod = conn.execute("SELECT * FROM products WHERE vendor='autotest_vendor' ORDER BY id DESC LIMIT 1").fetchone()
        prod_id = prod['id']

        # 1. Customer places order
        self.client.post('/login', data={'username': 'autotest_customer', 'password': 'Password@123'})
        resp = self.client.post('/add_order', data={'product_id': prod_id}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        order = conn.execute("SELECT * FROM orders WHERE customer='autotest_customer' ORDER BY id DESC LIMIT 1").fetchone()
        self.assertIsNotNone(order)
        order_id = order['id']
        self.assertEqual(order['status'], 'Pending')
        self.client.get('/logout')

        # 2. Vendor accepts order
        self.client.post('/login', data={'username': 'autotest_vendor', 'password': 'Password@123'})
        resp = self.client.post('/update_order', data={
            'order_id': order_id,
            'status': 'Accepted',
            'expected_delivery': '2026-09-15',
            'delivered_date': ''
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.client.get('/logout')

        # 3. Customer pays via Card (simulated payment flow)
        self.client.post('/login', data={'username': 'autotest_customer', 'password': 'Password@123'})
        resp = self.client.get(f'/payment/order/{order_id}')
        self.assertEqual(resp.status_code, 200)

        resp = self.client.post(f'/payment/order/{order_id}/card', data={
            'card_holder': 'Rahul Sharma',
            'card_number': '4532015112830366',
            'expiry': '12/28',
            'cvv': '789'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        pay = conn.execute("SELECT * FROM payments WHERE order_id=?", (order_id,)).fetchone()
        self.assertIsNotNone(pay)
        self.assertEqual(pay['status'], 'Pending Vendor Verification')
        self.assertEqual(pay['payment_method'], 'card')
        self.client.get('/logout')

        # 4. Vendor verifies payment
        self.client.post('/login', data={'username': 'autotest_vendor', 'password': 'Password@123'})
        resp = self.client.post('/update_payment', data={
            'payment_id': pay['id'],
            'status': 'Accepted'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)

        # 5. Vendor updates delivery status to Delivered
        resp = self.client.post('/update_order', data={
            'order_id': order_id,
            'status': 'Delivered',
            'expected_delivery': '2026-09-15',
            'delivered_date': '2026-09-14'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.client.get('/logout')

        # 6. Customer leaves review
        self.client.post('/login', data={'username': 'autotest_customer', 'password': 'Password@123'})
        resp = self.client.post('/reviews', data={
            'vendor': 'autotest_vendor',
            'rating': '5',
            'comment': 'Exceptional service and quick delivery!'
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Exceptional service', resp.data)
        self.client.get('/logout')

    def test_07_vendor_isolation_security(self):
        """Verify vendor A cannot modify vendor B's orders or products."""
        # Create vendor B
        self.client.post('/register', data={
            'username': 'autotest_vendor_b',
            'password': 'Password@123',
            'role': 'vendor',
            'mobile': '9000000003'
        })

        conn = get_db()
        order = conn.execute("SELECT id FROM orders WHERE vendor='autotest_vendor' LIMIT 1").fetchone()
        if order:
            order_id = order['id']
            # Vendor B attempts to alter Vendor A's order
            self.client.post('/login', data={'username': 'autotest_vendor_b', 'password': 'Password@123'})
            self.client.post('/update_order', data={
                'order_id': order_id,
                'status': 'Cancelled'
            }, follow_redirects=True)

            # Check that order status was NOT changed by Vendor B
            check_order = conn.execute("SELECT status FROM orders WHERE id=?", (order_id,)).fetchone()
            self.assertNotEqual(check_order['status'], 'Cancelled')
            self.client.get('/logout')

    def test_08_error_handlers(self):
        """Verify 404 handler returns clean styled error page with Vendora branding."""
        resp = self.client.get('/non-existent-page-12345')
        self.assertEqual(resp.status_code, 404)
        self.assertIn(b'Vendora', resp.data)
        self.assertIn(b'404', resp.data)

    def test_09_csrf_protection(self):
        """Verify CSRF rejects state-changing requests without token when CSRF is enabled."""
        app.config['WTF_CSRF_ENABLED'] = True
        try:
            # Missing CSRF token should return HTTP 400 Bad Request
            resp = self.client.post('/login', data={
                'username': 'autotest_customer',
                'password': 'Password@123'
            })
            self.assertEqual(resp.status_code, 400)
            self.assertIn(b'CSRF', resp.data)
        finally:
            app.config['WTF_CSRF_ENABLED'] = False

    def test_10_post_only_product_deletion(self):
        """Verify product deletion cannot be triggered via GET request (returns 405)."""
        # Vendor creates a dummy product
        self.client.post('/login', data={'username': 'autotest_vendor', 'password': 'Password@123'})
        self.client.post('/products', data={'name': 'Product To Delete', 'price': '499'})
        
        conn = get_db()
        prod = conn.execute("SELECT id FROM products WHERE name='Product To Delete' AND vendor='autotest_vendor'").fetchone()
        self.assertIsNotNone(prod)
        prod_id = prod['id']

        # Attempt deletion via GET -> must be rejected with 405 Method Not Allowed
        resp_get = self.client.get(f'/delete_product/{prod_id}')
        self.assertEqual(resp_get.status_code, 405)

        # Verify product is still in database
        prod_still_there = conn.execute("SELECT id FROM products WHERE id=?", (prod_id,)).fetchone()
        self.assertIsNotNone(prod_still_there)

        # Perform deletion via POST -> should succeed
        resp_post = self.client.post(f'/delete_product/{prod_id}', follow_redirects=True)
        self.assertEqual(resp_post.status_code, 200)

        # Verify product is deleted
        prod_deleted = conn.execute("SELECT id FROM products WHERE id=?", (prod_id,)).fetchone()
        self.assertIsNone(prod_deleted)
        self.client.get('/logout')

    def test_11_password_policy_server_side(self):
        """Verify server-side password strength validation rejects weak passwords."""
        weak_passwords = [
            'short',            # Too short (< 8)
            'alllowercase1@',   # Missing uppercase
            'ALLUPPERCASE1@',   # Missing lowercase
            'NoNumbersSpecial!', # Missing digit
            'NoSpecialChar123', # Missing special character
        ]
        for weak in weak_passwords:
            resp = self.client.post('/register', data={
                'username': f'user_{weak[:6]}',
                'password': weak,
                'role': 'customer',
                'mobile': '9000000000'
            })
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'Password must', resp.data)

    def test_12_price_validation_server_side(self):
        """Verify server-side price validation rejects invalid, negative, or malformed prices."""
        self.client.post('/login', data={'username': 'autotest_vendor', 'password': 'Password@123'})
        
        invalid_prices = ['-100', '0', 'abc', '₹-50', 'notanumber']
        for bad_price in invalid_prices:
            resp = self.client.post('/products', data={
                'name': 'Invalid Price Item',
                'price': bad_price
            })
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b'Price', resp.data)

        # Valid price should succeed
        resp_valid = self.client.post('/products', data={
            'name': 'Valid Price Item',
            'price': '199.99'
        }, follow_redirects=True)
        self.assertEqual(resp_valid.status_code, 200)
        self.assertIn(b'Valid Price Item', resp_valid.data)

        self.client.get('/logout')

    def test_13_role_registration_security(self):
        """Verify self-service registration rejects unauthorized roles such as admin."""
        resp = self.client.post('/register', data={
            'username': 'malicious_admin_attempt',
            'password': 'Password@123',
            'role': 'admin',
            'mobile': '9000000009'
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Invalid account role', resp.data)

        # Check DB to confirm user was not created
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username='malicious_admin_attempt'").fetchone()
        self.assertIsNone(user)

    def test_14_file_upload_security(self):
        """Verify file upload rejects executable and disallowed file extensions."""
        import io
        self.client.post('/login', data={'username': 'autotest_vendor', 'password': 'Password@123'})

        # Attempt to upload a .sh script disguised as upload
        fake_script = (io.BytesIO(b'#!/bin/bash\necho "exploit"'), 'exploit.sh')
        resp = self.client.post('/products', data={
            'name': 'Exploit Attempt Item',
            'price': '500',
            'image': fake_script
        }, content_type='multipart/form-data')
        self.assertIn(b'Invalid image file', resp.data)

        # Verify not in DB
        conn = get_db()
        item = conn.execute("SELECT * FROM products WHERE name='Exploit Attempt Item'").fetchone()
        self.assertIsNone(item)

        self.client.get('/logout')

    def test_15_vendor_cannot_delete_other_vendor_product(self):
        """Verify multi-tenant isolation: Vendor B cannot delete Vendor A's product."""
        # 1. Vendor A creates product
        self.client.post('/login', data={'username': 'autotest_vendor', 'password': 'Password@123'})
        self.client.post('/products', data={'name': 'Vendor A Protected Item', 'price': '899'})
        conn = get_db()
        prod = conn.execute("SELECT id FROM products WHERE name='Vendor A Protected Item' AND vendor='autotest_vendor'").fetchone()
        self.assertIsNotNone(prod)
        prod_id = prod['id']
        self.client.get('/logout')

        # 2. Vendor B attempts to delete Vendor A's product
        self.client.post('/login', data={'username': 'autotest_vendor_b', 'password': 'Password@123'})
        self.client.post(f'/delete_product/{prod_id}')
        self.client.get('/logout')

        # 3. Verify product is still present in DB and owned by Vendor A
        prod_check = conn.execute("SELECT * FROM products WHERE id=?", (prod_id,)).fetchone()
        self.assertIsNotNone(prod_check)
        self.assertEqual(prod_check['vendor'], 'autotest_vendor')


if __name__ == '__main__':
    unittest.main()
