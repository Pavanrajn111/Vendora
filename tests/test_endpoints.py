"""Quick smoke test for key endpoints using Flask test client."""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app import app


class EndpointSmokeTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    def test_smoke_endpoints(self):
        # 1. Test unauthenticated landing and login
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200, f"Landing failed: {r.status_code}")

        # 2. Login as vendor
        r = self.client.post('/login', data={'username': 'TechNova Electronics', 'password': 'pass123'}, follow_redirects=True)
        self.assertEqual(r.status_code, 200, f"Vendor login failed: {r.status_code}")

        # 3. Get products
        r = self.client.get('/products')
        self.assertEqual(r.status_code, 200, f"Products error: {r.status_code}")

        # 4. Get vendor orders
        r = self.client.get('/orders')
        self.assertEqual(r.status_code, 200, f"Vendor orders error: {r.status_code}")

        self.client.get('/logout')

        # 5. Login as customer
        r = self.client.post('/login', data={'username': 'Rahul Sharma', 'password': 'pass123'}, follow_redirects=True)
        self.assertEqual(r.status_code, 200, f"Customer login failed: {r.status_code}")

        # 6. Get customer orders
        r = self.client.get('/orders')
        self.assertEqual(r.status_code, 200, f"Customer orders error: {r.status_code}")


if __name__ == '__main__':
    unittest.main()

