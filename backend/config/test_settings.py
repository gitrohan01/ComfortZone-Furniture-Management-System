"""Isolated SQLite settings for local API and model tests."""
from .settings import *

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'test.sqlite3'}}
PRIVATE_STORAGE_ROOT = BASE_DIR / 'test-private-payment-files'
