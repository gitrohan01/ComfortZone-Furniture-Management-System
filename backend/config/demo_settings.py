"""Local academic-demo settings isolated from MySQL and test databases."""
from .settings import *


DEBUG = True

DEMO_DATA_DIR = BASE_DIR / '.demo-data'
DEMO_DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DEMO_DATA_DIR / 'showroom.sqlite3',
    },
}
PRIVATE_STORAGE_ROOT = DEMO_DATA_DIR / 'private-payment-files'
PRIVATE_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
MEDIA_ROOT = DEMO_DATA_DIR / 'media'
