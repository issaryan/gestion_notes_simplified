# backend/database.py
import mysql.connector
import logging
import os
from contextlib import contextmanager
from typing import Optional, Dict, Union
from config import DB_CONFIG

logger = logging.getLogger(__name__)

@contextmanager
def db_connection():
    """Contexte de connexion MySQL avec gestion automatique"""
    conn = mysql.connector.connect(**DB_CONFIG)
    try:
        yield conn
    except mysql.connector.Error as e:
        logger.error(f"Erreur MySQL: {str(e)}")
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    """Initialise la structure de la base de données"""
    with db_connection() as conn:
        cursor = conn.cursor()
        
        # Table des classes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS classes (
                id INT PRIMARY KEY AUTO_INCREMENT,
                name VARCHAR(255) UNIQUE NOT NULL,
                level VARCHAR(50) NOT NULL,
                academic_year VARCHAR(9) NOT NULL,
                INDEX idx_academic_year (academic_year)
            ) ENGINE=InnoDB
        ''')

        # Création de la table users
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT PRIMARY KEY AUTO_INCREMENT,
                username VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role ENUM('admin', 'teacher', 'student') NOT NULL,
                nom VARCHAR(255),
                prenom VARCHAR(255),
                email VARCHAR(255) UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP NULL,
                class_id INT,
                INDEX idx_class_id (class_id),
                FOREIGN KEY (class_id) 
                    REFERENCES classes(id)
                    ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        ''')
        
        # Table des matières
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subjects (
                id INT PRIMARY KEY AUTO_INCREMENT,
                name VARCHAR(255) NOT NULL,
                teacher_id INT NOT NULL,
                class_id INT NOT NULL,
                INDEX idx_teacher (teacher_id),
                INDEX idx_class (class_id),
                FOREIGN KEY (teacher_id) 
                    REFERENCES users(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (class_id) 
                    REFERENCES classes(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedule (
                id INT PRIMARY KEY AUTO_INCREMENT,
                subject_id INT NOT NULL,
                day ENUM('LUNDI','MARDI','MERCREDI','JEUDI','VENDREDI','SAMEDI'),
                start_time TIME NOT NULL,
                end_time TIME NOT NULL,
                INDEX idx_subject (subject_id),
                FOREIGN KEY (subject_id) 
                    REFERENCES subjects(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB
        ''')


        # Table des notes
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS grades (
                id INT PRIMARY KEY AUTO_INCREMENT,
                student_id INT NOT NULL,
                subject_id INT NOT NULL,
                grade DECIMAL(4,2) CHECK (grade BETWEEN 0 AND 20),
                evaluation_date DATE DEFAULT (CURRENT_DATE),
                comments TEXT,
                INDEX idx_student (student_id),
                INDEX idx_subject (subject_id),
                FOREIGN KEY (student_id) 
                    REFERENCES users(id)
                    ON DELETE CASCADE,
                FOREIGN KEY (subject_id) 
                    REFERENCES subjects(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB
        ''')
        conn.commit()

def add_user(
    username: str, 
    password_hash: str, 
    role: str, 
    nom: Optional[str] = None, 
    prenom: Optional[str] = None, 
    email: Optional[str] = None,
    class_id: Optional[int] = None
) -> int:
    """Ajoute un nouvel utilisateur en base de données"""
    with db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO users 
                (username, password_hash, role, nom, prenom, email, class_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (username, password_hash, role.lower(), nom, prenom, email, class_id))
            conn.commit()
            return cursor.lastrowid
        except mysql.connector.IntegrityError as e:
            logger.warning(f"Doublon utilisateur: {username}")
            raise ValueError(f"L'utilisateur {username} existe déjà") from e

def get_user_by_username(username: str) -> Optional[Dict]:
    """Récupère un utilisateur par son username"""
    with db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT id, username, password_hash, role, nom, prenom, email, class_id 
            FROM users 
            WHERE username = %s
        ''', (username,))
        return cursor.fetchone()

# ... (les autres fonctions existantes restent inchangées jusqu'à log_user_login)

def add_class(name: str, level: str, academic_year: str) -> int:
    """Ajoute une nouvelle classe"""
    with db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO classes (name, level, academic_year)
                VALUES (%s, %s, %s)
            ''', (name, level, academic_year))
            conn.commit()
            return cursor.lastrowid
        except mysql.connector.IntegrityError as e:
            logger.warning(f"Classe existe déjà: {name}")
            raise ValueError(f"La classe {name} existe déjà") from e

def get_class_students(class_id: int) -> list:
    """Récupère tous les étudiants d'une classe"""
    with db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT id, username, nom, prenom, email 
            FROM users 
            WHERE role = 'student' AND class_id = %s
        ''', (class_id,))
        return cursor.fetchall()

def add_subject(name: str, teacher_id: int, class_id: int) -> int:
    """Ajoute une nouvelle matière"""
    with db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO subjects (name, teacher_id, class_id)
                VALUES (%s, %s, %s)
            ''', (name, teacher_id, class_id))
            conn.commit()
            return cursor.lastrowid
        except mysql.connector.Error as e:
            logger.error(f"Erreur création matière: {str(e)}")
            raise

def add_grade(student_id: int, subject_id: int, grade: float, comments: str = "") -> int:
    """Ajoute une note pour un étudiant"""
    with db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO grades (student_id, subject_id, grade, comments)
                VALUES (%s, %s, %s, %s)
            ''', (student_id, subject_id, grade, comments))
            conn.commit()
            return cursor.lastrowid
        except mysql.connector.Error as e:
            logger.error(f"Erreur ajout note: {str(e)}")
            raise

def get_student_grades(student_id: int) -> list:
    """Récupère toutes les notes d'un étudiant"""
    with db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT s.name AS subject, g.grade, g.evaluation_date, t.nom AS teacher_name
            FROM grades g
            JOIN subjects s ON g.subject_id = s.id
            JOIN users t ON s.teacher_id = t.id
            WHERE g.student_id = %s
        ''', (student_id,))
        return cursor.fetchall()

def get_teacher_subjects(teacher_id: int) -> list:
    """Récupère les matières enseignées par un professeur"""
    with db_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT s.id, s.name, c.name AS class_name 
            FROM subjects s
            JOIN classes c ON s.class_id = c.id
            WHERE s.teacher_id = %s
        ''', (teacher_id,))
        return cursor.fetchall()

if __name__ == "__main__":
    # Initialisation de la base pour les tests
    init_db()
    print("Base de données MySQL initialisée avec succès")
