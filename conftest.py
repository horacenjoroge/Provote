"""
Root-level conftest.py to ensure fixtures are discovered when running from root.
This imports fixtures from backend/conftest.py.
"""
# Import all fixtures from backend/conftest.py
from backend.conftest import *  # noqa: F403, F401
