# pdf_generator.py
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from datetime import datetime
from reportlab.platypus import  PageBreak
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
import mysql.connector
from database import db_connection
import os
from io import BytesIO



# Configuration cohérente avec les autres fichiers
SCHOOL_LOGO = "static/school_logo.png"
PDF_CONFIG = {
    'font_name': 'Helvetica',
    'title_size': 16,
    'header_size': 12,
    'body_size': 10,
    'margin': 2*cm,
    'table_header_color': colors.HexColor('#2c3e50'),
    'accent_color': colors.HexColor('#3498db')
}

def generate_grades_report(class_id: int, requester_role: str) -> bytes:
    """Génère un rapport détaillé de toutes les notes d'une classe"""
    conn = db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Récupération des informations de la classe
        cursor.execute(
            """SELECT c.id, c.name, c.level, c.academic_year 
            FROM classes c 
            WHERE c.id = %s""",
            (class_id,)
        )
        class_info = cursor.fetchone()
        if not class_info:
            raise ValueError("Classe non trouvée")

        # Génération du fichier PDF
        filename = f"reports/class_grades_{class_id}_{datetime.now().strftime('%Y%m%d%H%M')}.pdf"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # Utilisation de la fonction interne existante pour générer le rapport
        _generate_detailed_report(cursor, class_info, class_id, filename)
        
        return open(filename, 'rb').read()

    finally:
        cursor.close()
        conn.close()


def generate_student_transcript(student_id, requester_role):
    """Génère un bulletin scolaire pour un étudiant"""
    conn = db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Vérification des permissions
        cursor.execute(
            """SELECT u.*, c.name as class_name 
            FROM users u
            LEFT JOIN classes c ON u.class_id = c.id
            WHERE u.id = %s AND u.role = 'student'""",
            (student_id,)
        )
        student = cursor.fetchone()
        if not student:
            raise ValueError("Étudiant non trouvé")

        # Récupération des notes
        cursor.execute(
            """SELECT s.name as subject, g.grade, g.comments, g.evaluation_date, 
                   t.nom as teacher_name, t.prenom as teacher_firstname
            FROM grades g
            JOIN subjects s ON g.subject_id = s.id
            JOIN users t ON s.teacher_id = t.id
            WHERE g.student_id = %s
            ORDER BY s.name, g.evaluation_date""",
            (student_id,)
        )
        grades = cursor.fetchall()

        # Création du PDF
        filename = f"reports/transcript_{student_id}_{datetime.now().strftime('%Y%m%d%H%M')}.pdf"
        doc = SimpleDocTemplate(filename, pagesize=A4, 
                              leftMargin=PDF_CONFIG['margin'],
                              rightMargin=PDF_CONFIG['margin'])
        
        elements = []
        styles = _create_styles()
        
        # En-tête
        elements.append(_create_header(student))
        elements.append(Spacer(1, 0.5*cm))
        
        # Informations étudiant
        student_info = [
            ["Classe:", student['class_name'] or "Non attribuée"],
            ["Date de génération:", datetime.now().strftime('%d/%m/%Y %H:%M')],
            ["Généré par:", f"{requester_role}"]
        ]
        elements.append(_create_info_table(student_info))
        elements.append(Spacer(1, 1*cm))
        
        # Tableau des notes
        if grades:
            grade_data = [["Matière", "Note", "Commentaires", "Date", "Enseignant"]]
            for grade in grades:
                grade_data.append([
                    grade['subject'],
                    str(grade['grade']),
                    grade['comments'][:50] + '...' if grade['comments'] else '',
                    grade['evaluation_date'].strftime('%d/%m/%Y'),
                    f"{grade['teacher_firstname']} {grade['teacher_name']}"
                ])
            
            table = Table(grade_data, colWidths=[4*cm, 2*cm, 6*cm, 3*cm, 5*cm])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), PDF_CONFIG['table_header_color']),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (1,0), (1,-1), 'CENTER'),
                ('FONTNAME', (0,0), (-1,0), PDF_CONFIG['font_name']+'-Bold'),
                ('FONTSIZE', (0,0), (-1,0), PDF_CONFIG['body_size']),
                ('BOTTOMPADDING', (0,0), (-1,0), 12),
                ('BACKGROUND', (0,1), (-1,-1), colors.beige),
                ('GRID', (0,0), (-1,-1), 1, colors.lightgrey)
            ]))
            elements.append(table)
        else:
            elements.append(Paragraph("Aucune note enregistrée", styles['BodyText']))
        
        doc.build(elements)
        return open(filename, 'rb').read()

    finally:
        cursor.close()
        conn.close()

def generate_class_report(class_id: int, report_type: str = 'summary') -> str:
    """Génère un rapport PDF et retourne le chemin du fichier"""
    filename = f"reports/class_{class_id}_{datetime.now().strftime('%Y%m%d%H%M')}.pdf"
    
    # Création du répertoire si inexistant
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    doc = SimpleDocTemplate(filename, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []
    
    conn = db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Récupération info classe (version optimisée)
        cursor.execute("""
            SELECT c.id, c.name, c.level, c.academic_year,
                   COUNT(u.id) AS student_count
            FROM classes c
            LEFT JOIN users u ON c.id = u.class_id AND u.role = 'student'
            WHERE c.id = %s
            GROUP BY c.id
        """, (class_id,))
        class_info = cursor.fetchone()
        
        if not class_info:
            raise ValueError("Classe non trouvée")
        # Construction du PDF (identique à la nouvelle version)
        title_text = f"Rapport de Classe - {class_info['name']}"
        elements.append(Paragraph(title_text, styles['Title']))
        elements.append(Spacer(1, 12))
        meta_data = [
            ["Niveau", class_info['level']],
            ["Année Scolaire", class_info['academic_year']],
            ["Nombre d'Élèves", class_info['student_count']]
        ]
        meta_table = Table(meta_data, colWidths=[100, 300])
        meta_table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
            ('BACKGROUND', (0,0), (-1,-1), colors.lightgrey),
            ('TEXTCOLOR', (0,0), (-1,-1), colors.black),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('BOX', (0,0), (-1,-1), 1, colors.black)
        ]))
        elements.append(meta_table)
        elements.append(Spacer(1, 24))
        if report_type == 'detailed':
            cursor.execute("""
                SELECT u.nom, u.prenom, AVG(g.grade) AS average
                FROM users u
                LEFT JOIN grades g ON u.id = g.student_id
                WHERE u.class_id = %s AND u.role = 'student'
                GROUP BY u.id
                ORDER BY u.nom, u.prenom
            """, (class_id,))
            students = cursor.fetchall()
            student_data = [["Nom", "Prénom", "Moyenne Générale"]]
            for student in students:
                avg = f"{student['average']:.2f}" if student['average'] else "N/A"
                student_data.append([student['nom'], student['prenom'], avg])
        elif report_type == 'summary':
            cursor.execute("""
                SELECT 
                    MAX(g.grade) AS max_grade,
                    MIN(g.grade) AS min_grade,
                    AVG(g.grade) AS avg_grade,
                    COUNT(g.id) AS grade_count
                FROM grades g
                JOIN users u ON g.student_id = u.id
                WHERE u.class_id = %s
            """, (class_id,))
            stats = cursor.fetchone()
            student_data = [
                ["Moyenne de Classe", f"{stats['avg_grade']:.2f}" if stats['avg_grade'] else "N/A"],
                ["Meilleure Note", stats['max_grade'] or "N/A"],
                ["Plus Basse Note", stats['min_grade'] or "N/A"],
                ["Total Notes", stats['grade_count'] or "0"]
            ]
        else:
            raise ValueError("Type de rapport non valide")
        table = Table(student_data, colWidths=[120, 120, 140] if report_type == 'detailed' else [200, 200])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.darkblue),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 12),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('BACKGROUND', (0,1), (-1,-1), colors.beige),
            ('GRID', (0,0), (-1,-1), 1, colors.black)
        ]))
        elements.append(table)
        doc.build(elements)
        return filename
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


def _create_header(student):
    """Crée l'en-tête commun à tous les documents"""
    styles = _create_styles()
    header = []
    
    # Logo et titre
    logo = Image(SCHOOL_LOGO, width=2*cm, height=2*cm)
    title = Paragraph(
        f"<b>BULLETIN SCOLAIRE</b><br/>"
        f"{student['prenom']} {student['nom']}",
        styles['Title']
    )
    
    header_table = Table([
        [logo, title]
    ], colWidths=[3*cm, 15*cm])
    
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 15)
    ]))
    
    return header_table

def _create_info_table(data):
    """Crée un tableau d'informations formaté"""
    style = TableStyle([
        ('FONTNAME', (0,0), (-1,-1), PDF_CONFIG['font_name']),
        ('FONTSIZE', (0,0), (-1,-1), PDF_CONFIG['body_size']),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (0,0), (0,-1), 'RIGHT'),
        ('TEXTCOLOR', (0,0), (0,-1), PDF_CONFIG['accent_color']),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 5)
    ])
    
    table = Table(data, colWidths=[4*cm, 12*cm])
    table.setStyle(style)
    return table

def _create_styles():
    """Définit les styles de paragraphe"""
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='Title',
        fontName=PDF_CONFIG['font_name']+'-Bold',
        fontSize=PDF_CONFIG['title_size'],
        alignment=1,
        spaceAfter=20
    ))
    return styles

def _generate_class_summary(cursor, class_info, class_id, filename):
    """Génère un rapport sommaire de classe"""
    try:
        # Récupération des données de la classe
        cursor.execute(
            """SELECT u.id, u.nom, u.prenom, COUNT(g.id) as nb_notes, AVG(g.grade) as moyenne
            FROM users u
            LEFT JOIN grades g ON u.id = g.student_id
            WHERE u.class_id = %s AND u.role = 'student'
            GROUP BY u.id""",
            (class_id,))
        students_data = cursor.fetchall()
        # Statistiques générales
        cursor.execute(
            """SELECT 
                COUNT(DISTINCT u.id) as total_eleves,
                COUNT(g.id) as total_notes,
                AVG(g.grade) as moyenne_classe,
                MAX(g.grade) as meilleure_note,
                MIN(g.grade) as plus_basse_note
            FROM users u
            LEFT JOIN grades g ON u.id = g.student_id
            WHERE u.class_id = %s AND u.role = 'student'""",
            (class_id,))
        stats = cursor.fetchone()
        # Préparation du PDF
        doc = SimpleDocTemplate(filename, pagesize=A4, 
                              leftMargin=PDF_CONFIG['margin'],
                              rightMargin=PDF_CONFIG['margin'])
        elements = []
        styles = _create_styles()
        # En-tête
        elements.append(_create_class_header(class_info))
        elements.append(Spacer(1, 0.5*cm))
        # Statistiques globales
        elements.append(Paragraph("Statistiques Globales", styles['Heading2']))
        stats_table = Table([
            ["Élèves inscrits", stats['total_eleves'] or 0],
            ["Notes enregistrées", stats['total_notes'] or 0],
            ["Moyenne de classe", f"{stats['moyenne_classe']:.2f}" if stats['moyenne_classe'] else "N/A"],
            ["Meilleure note", stats['meilleure_note'] or "N/A"],
            ["Plus basse note", stats['plus_basse_note'] or "N/A"]
        ], colWidths=[6*cm, 6*cm])
        stats_table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,-1), PDF_CONFIG['font_name']),
            ('FONTSIZE', (0,0), (-1,-1), PDF_CONFIG['body_size']),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BACKGROUND', (0,0), (-1,0), PDF_CONFIG['table_header_color']),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('GRID', (0,0), (-1,-1), 1, colors.lightgrey)
        ]))
        elements.append(stats_table)
        elements.append(Spacer(1, 1*cm))
        # Graphique des moyennes
        if students_data:
            drawing = Drawing(400, 200)
            bc = VerticalBarChart()
            bc.x = 50
            bc.y = 50
            bc.height = 150
            bc.width = 350
            bc.data = [[s['moyenne'] or 0 for s in students_data]]
            bc.strokeColor = colors.black
            bc.valueAxis.valueMin = 0
            bc.valueAxis.valueMax = 20
            bc.categoryAxis.labels.boxAnchor = 'ne'
            bc.categoryAxis.labels.dx = 8
            bc.categoryAxis.labels.dy = -2
            bc.categoryAxis.labels.angle = 45
            bc.categoryAxis.categoryNames = [f"{s['prenom']} {s['nom'][0]}." for s in students_data]
            drawing.add(bc)
            elements.append(Paragraph("Moyennes par élève", styles['Heading2']))
            elements.append(drawing)
            elements.append(PageBreak())
        # Classement des élèves
        sorted_students = sorted(
            [s for s in students_data if s['moyenne'] is not None],
            key=lambda x: x['moyenne'], 
            reverse=True
        )[:5]
        if sorted_students:
            elements.append(Paragraph("Top 5 des élèves", styles['Heading2']))
            rank_data = [["Position", "Élève", "Moyenne"]]
            for idx, student in enumerate(sorted_students, start=1):
                rank_data.append([
                    str(idx),
                    f"{student['prenom']} {student['nom']}",
                    f"{student['moyenne']:.2f}"
                ])
            
            rank_table = Table(rank_data, colWidths=[2*cm, 10*cm, 4*cm])
            rank_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), PDF_CONFIG['accent_color']),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('FONTNAME', (0,0), (-1,0), PDF_CONFIG['font_name']+'-Bold'),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('GRID', (0,0), (-1,-1), 1, colors.lightgrey)
            ]))
            elements.append(rank_table)
        doc.build(elements)
        return filename
    except Exception as e:
        raise RuntimeError(f"Erreur de génération du rapport: {str(e)}")

def _generate_detailed_report(cursor, class_info, class_id, filename):
    """Génère un rapport détaillé avec toutes les notes"""
    try:
        # Récupération des données
        cursor.execute(
            """SELECT 
                u.id as student_id,
                u.nom,
                u.prenom,
                s.name as subject,
                g.grade,
                g.comments,
                g.evaluation_date
            FROM users u
            LEFT JOIN grades g ON u.id = g.student_id
            LEFT JOIN subjects s ON g.subject_id = s.id
            WHERE u.class_id = %s AND u.role = 'student'
            ORDER BY u.nom, u.prenom, s.name""",
            (class_id,))
        grades_data = cursor.fetchall()
        # Préparation du PDF
        doc = SimpleDocTemplate(filename, pagesize=A4, 
                              leftMargin=PDF_CONFIG['margin'],
                              rightMargin=PDF_CONFIG['margin'])
        elements = []
        styles = _create_styles()
        # En-tête
        elements.append(_create_class_header(class_info))
        elements.append(Spacer(1, 1*cm))
        current_student = None
        student_grades = []
        for record in grades_data:
            if record['student_id'] != current_student:
                if current_student is not None:
                    # Ajouter le tableau de l'élève précédent
                    elements.append(_create_student_grade_table(student_grades))
                    elements.append(Spacer(1, 1*cm))
                
                # Nouvel élève
                current_student = record['student_id']
                student_grades = []
                elements.append(Paragraph(
                    f"Élève: {record['prenom']} {record['nom']}",
                    style=styles['Heading2']
                ))
                elements.append(Spacer(1, 0.5*cm))
            
            if record['subject']:
                student_grades.append([
                    record['subject'],
                    str(record['grade']),
                    record['comments'][:100] if record['comments'] else '',
                    record['evaluation_date'].strftime('%d/%m/%Y') if record['evaluation_date'] else ''
                ])
        # Ajouter le dernier élève
        if student_grades:
            elements.append(_create_student_grade_table(student_grades))
        doc.build(elements)
        return filename
    except Exception as e:
        raise RuntimeError(f"Erreur de génération du rapport détaillé: {str(e)}")
def _create_class_header(class_info):
    """En-tête spécifique pour les rapports de classe"""
    styles = _create_styles()
    header = []
    
    logo = Image(SCHOOL_LOGO, width=2*cm, height=2*cm)
    title_text = (
        f"<b>RAPPORT DE CLASSE</b><br/>"
        f"Classe: {class_info['name']}<br/>"
        f"Niveau: {class_info['level']} | Année scolaire: {class_info['academic_year']}"
    )
    title = Paragraph(title_text, styles['Title'])
    
    header_table = Table([
        [logo, title]
    ], colWidths=[3*cm, 15*cm])
    
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 15)
    ]))
    
    return header_table

def _create_student_grade_table(grades_data):
    """Crée un tableau de notes pour un élève"""
    headers = ["Matière", "Note", "Commentaires", "Date"]
    table_data = [headers] + grades_data
    
    table = Table(table_data, colWidths=[5*cm, 3*cm, 7*cm, 4*cm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), PDF_CONFIG['table_header_color']),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('FONTNAME', (0,0), (-1,0), PDF_CONFIG['font_name']+'-Bold'),
        ('FONTSIZE', (0,0), (-1,0), PDF_CONFIG['body_size']),
        ('ALIGN', (1,0), (1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 1, colors.lightgrey),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige)
    ]))
    
    return table