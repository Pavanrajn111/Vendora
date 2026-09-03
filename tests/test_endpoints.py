"""Quick smoke test for key endpoints using Flask test client."""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app import app

client = app.test_client()

# 1. Test unauthenticated landing and login
r = client.get('/')
assert r.status_code == 200, f"Landing failed: {r.status_code}"
print("[PASS] Landing page OK")

# 2. Login as vendor
r = client.post('/login', data={'username': 'TechNova Electronics', 'password': 'pass123'}, follow_redirects=True)
assert r.status_code == 200, f"Vendor login failed: {r.status_code}"
print("[PASS] Vendor login OK")

# 3. Get products
r = client.get('/products')
assert r.status_code == 200, f"Products error: {r.status_code}"
print("[PASS] Vendor products OK")

# 4. Get vendor orders
r = client.get('/orders')
assert r.status_code == 200, f"Vendor orders error: {r.status_code}"
print("[PASS] Vendor orders OK")

client.get('/logout')

# 5. Login as customer
r = client.post('/login', data={'username': 'Rahul Sharma', 'password': 'pass123'}, follow_redirects=True)
assert r.status_code == 200, f"Customer login failed: {r.status_code}"
print("[PASS] Customer login OK")

# 6. Get customer orders
r = client.get('/orders')
assert r.status_code == 200, f"Customer orders error: {r.status_code}"
print("[PASS] Customer orders OK")

print("[PASS] All endpoint smoke tests completed successfully!")
