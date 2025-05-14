# csv_processor.py
import csv
import io
import mysql.connector
import bcrypt
from datetime import datetime
from database import db_connection

# Configuration compatible avec server.py
from config import DB_CONFIG


CSV_CONFIG = {
    'user_required_fields': ['username', 'password', 'role', 'nom', 'prenom', 'email'],
    'class_required_fields': ['name', 'level', 'academic_year'],
    'grade_required_fields': ['student_email', 'subject_name', 'grade', 'comments'],
    'max_grade': 20,
    'min_grade': 0
}

def process_csv(csv_data, actor_role=None):
    """Gère l'importation de données massives pour les administrateurs"""
    try:
        # Détection du type de CSV
        reader = csv.DictReader(io.StringIO(csv_data))
        fieldnames = [fn.lower() for fn in reader.fieldnames]
        
        if all(field in fieldnames for field in CSV_CONFIG['user_required_fields']):
            return _process_user_csv(reader)
        elif all(field in fieldnames for field in CSV_CONFIG['class_required_fields']):
            return _process_class_csv(reader)
        else:
            raise ValueError("Format CSV non reconnu")

    except Exception as e:
        return {
            'success': False,
            'message': f"Erreur de traitement : {str(e)}",
            'processed': 0
        }

def process_grades_csv(csv_data, teacher_id):
    """Gère l'importation de notes par les enseignants"""
    conn = db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        reader = csv.DictReader(io.StringIO(csv_data))
        reader.fieldnames = [fn.lower() for fn in reader.fieldnames]
        
        # Validation des entrées
        if not all(field in reader.fieldnames for field in CSV_CONFIG['grade_required_fields']):
            raise ValueError("En-têtes CSV manquants")

        grades_to_insert = []
        errors = []
        
        for idx, row in enumerate(reader, start=2):  # Ligne 1 = en-têtes
            try:
                # Validation de la note
                grade = float(row['grade'])
                if not CSV_CONFIG['min_grade'] <= grade <= CSV_CONFIG['max_grade']:
                    raise ValueError(f"Note invalide ({CSV_CONFIG['min_grade']}-{CSV_CONFIG['max_grade']})")

                # Récupération ID étudiant
                cursor.execute(
                    "SELECT id FROM users WHERE email = %s AND role = 'student'",
                    (row['student_email'].lower(),)
                )
                student = cursor.fetchone()
                if not student:
                    raise ValueError("Étudiant non trouvé")

                # Vérification association matière/enseignant
                cursor.execute(
                    """SELECT s.id 
                    FROM subjects s
                    WHERE s.name = %s AND s.teacher_id = %s""",
                    (row['subject_name'].strip(), teacher_id)
                )
                subject = cursor.fetchone()
                if not subject:
                    raise ValueError("Matière non attribuée à l'enseignant")

                grades_to_insert.append((
                    student['id'],
                    subject['id'],
                    grade,
                    row['comments'][:255],  # Troncature des commentaires
                    datetime.now().date()
                ))

            except Exception as e:
                errors.append({
                    'ligne': idx,
                    'erreur': str(e),
                    'donnees': row
                })

        # Insertion en masse si aucune erreur
        if errors:
            return {
                'success': False,
                'message': f"{len(errors)} erreurs détectées",
                'errors': errors,
                'inserted': 0
            }

        cursor.executemany(
            """INSERT INTO grades 
            (student_id, subject_id, grade, comments, evaluation_date)
            VALUES (%s, %s, %s, %s, %s)""",
            grades_to_insert
        )
        conn.commit()

        return {
            'success': True,
            'inserted': cursor.rowcount,
            'errors': []
        }

    finally:
        cursor.close()
        conn.close()

def _process_user_csv(reader):
    """Traitement spécifique pour les imports d'utilisateurs"""
    conn = db_connection()
    cursor = conn.cursor()
    
    try:
        inserted = 0
        errors = []
        
        for idx, row in enumerate(reader, start=2):
            try:
                # Validation des données
                if not all(row.values()):
                    raise ValueError("Champs manquants")

                # Hachage du mot de passe
                hashed_pw = bcrypt.hashpw(
                    row['password'].encode(), 
                    bcrypt.gensalt()
                ).decode()

                # Insertion utilisateur
                cursor.execute(
                    """INSERT INTO users 
                    (username, password_hash, role, nom, prenom, email, class_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (
                        row['username'].lower(),
                        hashed_pw,
                        row['role'].lower(),
                        row['nom'].strip().title(),
                        row['prenom'].strip().title(),
                        row['email'].lower(),
                        row.get('class_id')  # Optionnel
                    )
                )
                inserted += 1

            except mysql.connector.IntegrityError as e:
                errors.append({
                    'ligne': idx,
                    'erreur': "Doublon détecté",
                    'donnees': row
                })
            except Exception as e:
                errors.append({
                    'ligne': idx,
                    'erreur': str(e),
                    'donnees': row
                })

        conn.commit()
        
        return {
            'success': len(errors) == 0,
            'inserted': inserted,
            'errors': errors
        }

    finally:
        cursor.close()
        conn.close()

def _process_class_csv(reader):
    """Traitement spécifique pour les imports de classes"""
    conn = db_connection()
    cursor = conn.cursor()
    
    try:
        inserted = 0
        errors = []
        
        for idx, row in enumerate(reader, start=2):
            try:
                cursor.execute(
                    """INSERT INTO classes 
                    (name, level, academic_year)
                    VALUES (%s, %s, %s)""",
                    (
                        row['name'].strip().upper(),
                        row['level'].strip().title(),
                        row['academic_year']
                    )
                )
                inserted += 1
                
            except mysql.connector.IntegrityError:
                errors.append({
                    'ligne': idx,
                    'erreur': "Classe déjà existante",
                    'donnees': row
                })
            except Exception as e:
                errors.append({
                    'ligne': idx,
                    'erreur': str(e),
                    'donnees': row
                })

        conn.commit()
        
        return {
            'success': len(errors) == 0,
            'inserted': inserted,
            'errors': errors
        }

    finally:
        cursor.close()
        conn.close()
