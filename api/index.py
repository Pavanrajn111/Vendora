import os
import sys

# Add repository root directory to Python path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Set Vercel environment flag
os.environ.setdefault("VERCEL", "1")

from app import app

# Export WSGI application for Vercel Python runtime
app = app
