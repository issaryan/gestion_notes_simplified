# backend/config.py
import os

DB_CONFIG = {
    'host': os.getenv('MYSQL_HOST', 'mysql'),  
    'user': os.getenv('MYSQL_USER', 'academy'),
    'password': os.getenv('MYSQL_PASSWORD', 'securepassword'),
    'database': os.getenv('MYSQL_DB', 'academy_db'),
    'port': os.getenv('MYSQL_PORT', 3306),
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci'
}
