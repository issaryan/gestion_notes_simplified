from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import jwt
import mysql.connector
from urllib.parse import urlparse, parse_qs
import bcrypt
import cgi
from csv_processor import process_csv, process_grades_csv
from pdf_generator import generate_grades_report, generate_student_transcript, generate_class_report
from database import init_db
from datetime import datetime, timedelta
from config import DB_CONFIG

# Configuration JWT
SECRET_KEY = "votre_secret_key_complexe"
TOKEN_EXPIRATION = 3600  # 1 heure

class RESTRequestHandler(BaseHTTPRequestHandler):
    def _set_headers(self, status_code=200, content_type='application/json'):
        self.send_response(status_code)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', 'http://localhost')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type, X-Requested-With')
        self.send_header('Access-Control-Allow-Credentials', 'true')
        self.end_headers()

    def _parse_json(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8')
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None

    def _get_token(self):
        auth = self.headers.get('Authorization')
        if auth and auth.startswith('Bearer '):
            return auth.split(' ')[1]
        return None

    def _verify_token(self, roles=None):
        token = self._get_token()
        if not token:
            return False
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
            if payload.get('exp', 0) < datetime.utcnow().timestamp():
                return False
            if roles and payload.get('role') not in roles:
                return False
            return payload
        except jwt.PyJWTError:
            return False

    def _db_connection(self):
        return mysql.connector.connect(**DB_CONFIG)

    def _send_response(self, code, data, content_type='application/json'):
        self._set_headers(code, content_type)
        if content_type == 'application/json':
            self.wfile.write(json.dumps(data).encode('utf-8'))
        else:
            self.wfile.write(data)

    def do_OPTIONS(self):
        self._set_headers(204)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # Static files
        if path.startswith('/static/'):
            try:
                with open(f"/app/frontend{path}", 'rb') as f:
                    mime = self._guess_mime_type(path)
                    self._send_response(200, f.read(), content_type=mime)
                return
            except FileNotFoundError:
                return self._send_response(404, {'error': 'Fichier non trouvé'})

        # Health check
        if path == '/api/health':
            return self._send_response(200, {'status': 'OK'})

        # Protected
        payload = self._verify_token()
        if not payload:
            return self._send_response(401, {'error': 'Non autorisé'})

        conn = self._db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            # Admin: list users
            if path == '/api/users' and payload['role'] == 'admin':
                term = query.get('search', [''])[0]
                cursor.execute(
                    """
                    SELECT id, username, role, nom, prenom, email, class_id,
                           CASE WHEN last_login > DATE_SUB(NOW(), INTERVAL 6 MONTH) THEN 'Actif' ELSE 'Inactif' END AS status
                    FROM users
                    WHERE username LIKE %s OR nom LIKE %s OR prenom LIKE %s
                    """, (f"%{term}%", f"%{term}%", f"%{term}%"))
                return self._send_response(200, cursor.fetchall())

            # Student: grades
            if path == '/api/grades' and payload['role'] == 'student':
                cursor.execute(
                    """
                    SELECT s.name AS subject, g.grade, g.evaluation_date,
                           CONCAT(t.prenom,' ',t.nom) AS teacher, c.name AS class_name
                    FROM grades g
                             JOIN subjects s ON g.subject_id=s.id
                             JOIN users t ON s.teacher_id=t.id
                             JOIN classes c ON s.class_id=c.id
                    WHERE g.student_id=%s
                    """, (payload['sub'],))
                return self._send_response(200, cursor.fetchall())

            # Student: schedule
            if path == '/api/schedule' and payload['role'] == 'student':
                cursor.execute(
                    """
                    SELECT s.name, sch.day, sch.start_time, sch.end_time
                    FROM schedule sch
                             JOIN subjects s ON sch.subject_id=s.id
                             JOIN classes c ON s.class_id=c.id
                    WHERE c.id=(SELECT class_id FROM users WHERE id=%s)
                    """, (payload['sub'],))
                return self._send_response(200, cursor.fetchall())

            # Teacher: subjects
            if path == '/api/subjects' and payload['role'] == 'teacher':
                cursor.execute(
                    """
                    SELECT s.id, s.name, c.name AS class_name,
                           (SELECT COUNT(*) FROM users WHERE class_id=c.id AND role='student') AS student_count
                    FROM subjects s
                             JOIN classes c ON s.class_id=c.id
                    WHERE s.teacher_id=%s
                    """, (payload['sub'],))
                return self._send_response(200, cursor.fetchall())

            # Admin: classes
            if path == '/api/classes' and payload['role'] == 'admin':
                cursor.execute(
                    """
                    SELECT id, name, level, academic_year,
                           (SELECT COUNT(*) FROM users WHERE class_id=classes.id AND role='student') AS student_count
                    FROM classes
                    """
                )
                return self._send_response(200, cursor.fetchall())

            # Teacher: students in their subjects
            if path == '/api/students' and payload['role'] == 'teacher':
                cursor.execute(
                    """
                    SELECT DISTINCT u.id, u.nom, u.prenom, u.email, c.name AS class_name
                    FROM users u
                             JOIN classes c ON u.class_id=c.id
                             JOIN subjects s ON c.id=s.class_id
                    WHERE s.teacher_id=%s AND u.role='student'
                    """, (payload['sub'],))
                return self._send_response(200, cursor.fetchall())

            # Report: student transcript
            if path.startswith('/api/report/student/') and payload['role'] in ['teacher','admin']:
                student_id = path.split('/')[-1]
                report = generate_student_transcript(student_id, payload['role'])
                with open(report,'rb') as f:
                    return self._send_response(200, f.read(), content_type='application/pdf')

            # Admin: list teachers
            if path == '/api/teachers' and payload['role'] == 'admin':
                cursor.execute(
                    """
                    SELECT id, nom, prenom, email,
                           (SELECT COUNT(*) FROM subjects WHERE teacher_id=users.id) AS subject_count
                    FROM users WHERE role='teacher'
                    """
                )
                return self._send_response(200, cursor.fetchall())

            # Admin: class report (summary or detailed)
            if path == '/api/class-report' and payload['role'] == 'admin':
                class_id = query.get('class_id',[None])[0]
                rpt_type = query.get('type',['summary'])[0]
                if not class_id:
                    return self._send_response(400, {'error':'class_id requis'})
                report = generate_class_report(class_id, rpt_type)
                with open(report,'rb') as f:
                    return self._send_response(200, f.read(), content_type='application/pdf')

            # Not found
            return self._send_response(404, {'error':'Endpoint non trouvé'})
        finally:
            cursor.close()
            conn.close()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Login
        if path == '/api/login':
            data = self._parse_json()
            if not data or not all(k in data for k in ('username','password')):
                return self._send_response(400, {'error':'username et password requis'})
            conn = self._db_connection()
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute('SELECT id,password_hash,role FROM users WHERE username=%s',
                               (data['username'],))
                user = cursor.fetchone()
                if not user or not bcrypt.checkpw(data['password'].encode(), user['password_hash'].encode()):
                    return self._send_response(401, {'error':'Non autorisé'})
                exp = datetime.utcnow() + timedelta(seconds=TOKEN_EXPIRATION)
                token = jwt.encode({'sub':user['id'],'role':user['role'],'exp':exp}, SECRET_KEY)
                cursor.execute('UPDATE users SET last_login=NOW() WHERE id=%s',(user['id'],))
                conn.commit()
                return self._send_response(200, {'token':token})
            finally:
                cursor.close()
                conn.close()

        # File upload
        if path == '/api/upload':
            payload = self._verify_token(['teacher','admin'])
            if not payload:
                return self._send_response(401, {'error':'Non autorisé'})
            ctype, pdict = cgi.parse_header(self.headers.get('Content-Type',''))
            if ctype != 'multipart/form-data':
                return self._send_response(400, {'error':'multipart/form-data requis'})
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                                    environ={'REQUEST_METHOD':'POST'})
            file_item = form['file'] if 'file' in form else None
            if not file_item or not file_item.file:
                return self._send_response(400, {'error':'Fichier manquant'})
            data = file_item.file.read().decode('utf-8')
            try:
                if payload['role']=='admin':
                    result = process_csv(data)
                else:
                    result = process_grades_csv(data, payload['sub'])
                return self._send_response(201, result)
            except Exception as e:
                return self._send_response(500, {'error':str(e)})

        # Create class (admin)
        if path == '/api/classes':
            payload = self._verify_token(['admin'])
            data = self._parse_json()
            if not payload or not data or not all(k in data for k in ('name','level','academic_year')):
                return self._send_response(400, {'error':'Données manquantes'})
            try:
                cid = add_class(data['name'], data['level'], data['academic_year'])
                return self._send_response(201, {'id':cid})
            except Exception as e:
                return self._send_response(500, {'error':str(e)})

        # Create subject (admin)
        if path == '/api/subjects':
            payload = self._verify_token(['admin'])
            data = self._parse_json()
            if not payload or not data or not all(k in data for k in ('name','teacher_id','class_id')):
                return self._send_response(400, {'error':'Données manquantes'})
            try:
                sid = add_subject(data['name'], data['teacher_id'], data['class_id'])
                return self._send_response(201, {'id':sid})
            except Exception as e:
                return self._send_response(500, {'error':str(e)})

        # Add grade (teacher)
        if path == '/api/grades':
            payload = self._verify_token(['teacher'])
            data = self._parse_json()
            if not payload or not data or not all(k in data for k in ('student_id','subject_id','grade')):
                return self._send_response(400, {'error':'Données manquantes'})
            try:
                gid = add_grade(data['student_id'], data['subject_id'], data['grade'], data.get('comments',''))
                return self._send_response(201, {'id':gid})
            except Exception as e:
                return self._send_response(500, {'error':str(e)})

        return self._send_response(404, {'error':'Endpoint non trouvé'})

    def _guess_mime_type(self, path):
        if path.endswith('.js'):
            return 'application/javascript'
        if path.endswith('.css'):
            return 'text/css'
        if path.endswith('.html'):
            return 'text/html'
        if path.endswith('.png'):
            return 'image/png'
        if path.endswith(('.jpg', '.jpeg')):
            return 'image/jpeg'
        return 'application/octet-stream'

if __name__ == '__main__':
    init_db()
    server = HTTPServer(('0.0.0.0', 8000), RESTRequestHandler)
    print("Serveur démarré sur http://0.0.0.0:8000")
    server.serve_forever()