import os
from datetime import timedelta

SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-secret-key')
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'change-this-jwt-secret-key')
USERNAME = os.environ.get('PANEL_USERNAME', 'admin')
PASSWORD = os.environ.get('PANEL_PASSWORD', 'change-me')
PANEL_DATA_DIR = os.environ.get('PANEL_DATA_DIR', '/qlpanel/data')


class Config:
    """Flask config class"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-secret-key')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'change-this-jwt-secret-key')
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=30)
    PANEL_DATA_DIR = os.environ.get('PANEL_DATA_DIR', '/qlpanel/data')
