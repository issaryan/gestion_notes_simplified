#!/bin/bash
# setup.sh — script complet mis à jour avec debug et retry pour login

set -euo pipefail
IFS=$'\n\t'

# --- Configuration ---
ADMIN_USER="admin"
ADMIN_PASS="adminpassword"
DB_ROOT_USER="root"
DB_ROOT_PASS="rootpassword"
MYSQL_SERVICE="mysql"       # Nom du service DB dans docker-compose.yml
API_URL="http://localhost:8000/api"
REQUIRED=(docker docker-compose curl jq)
LOGIN_RETRIES=5
LOGIN_WAIT=2

# --- Fonctions utilitaires ---
die() {
  echo "ERREUR: $1" >&2
  exit 1
}

check_tools() {
  echo "=== Vérification des dépendances ==="
  for cmd in "${REQUIRED[@]}"; do
    command -v "$cmd" &>/dev/null || die "$cmd n'est pas installé"
  done
}

start_containers() {
  echo "=== Démarrage des conteneurs Docker ==="
  docker-compose up -d
}

wait_mysql() {
  echo "=== Attente de MySQL (service : $MYSQL_SERVICE) ==="
  until docker-compose exec -T "$MYSQL_SERVICE" mysqladmin ping -u"$DB_ROOT_USER" -p"$DB_ROOT_PASS" --silent &>/dev/null; do
    sleep 2
  done
  echo "MySQL prêt !"
}

init_database() {
  echo "=== Initialisation de la base academy_db ==="
  docker-compose exec -T "$MYSQL_SERVICE" mysql -u"$DB_ROOT_USER" -p"$DB_ROOT_PASS" <<SQL
CREATE DATABASE IF NOT EXISTS academy_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'academy'@'%' IDENTIFIED BY 'securepassword';
GRANT ALL PRIVILEGES ON academy_db.* TO 'academy'@'%';
FLUSH PRIVILEGES;
SET GLOBAL time_zone = 'Europe/Paris';
SQL
}

create_admin() {
  echo "=== Création de l'utilisateur admin ==="
  ADMIN_HASH=$(docker run --rm python:3.9-slim \
    sh -c "pip install bcrypt==4.0.0 >/dev/null && python - <<PY
import bcrypt
print(bcrypt.hashpw(b'$ADMIN_PASS', bcrypt.gensalt()).decode())
PY")

  docker-compose exec -T "$MYSQL_SERVICE" mysql -uacademy -psecurepassword academy_db <<SQL
INSERT INTO users (username, password_hash, role, nom, prenom, email, class_id)
VALUES ('$ADMIN_USER', '$ADMIN_HASH', 'admin', 'Admin', 'System', 'admin@academy.local', NULL)
ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash);
SQL
}

get_token_admin() {
  echo "=== Authentification admin (max $LOGIN_RETRIES essais) ==="
  local attempt=1
  local resp
  while (( attempt <= LOGIN_RETRIES )); do
    echo "-- Essai $attempt..."
    resp=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/login" \
      -H "Content-Type: application/json" \
      -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}")
    http_code=$(tail -n1 <<< "$resp")
    body=$(sed '$ d' <<< "$resp")
    echo "Réponse HTTP: $http_code"
    echo "Body: $body"
    if [[ "$http_code" == "200" ]]; then
      ADMIN_TOKEN=$(jq -r '.token' <<< "$body")
      [[ -n "$ADMIN_TOKEN" && "$ADMIN_TOKEN" != "null" ]] && break
    fi
    ((attempt++))
    sleep $LOGIN_WAIT
  done
  if [[ -z "${ADMIN_TOKEN:-}" ]]; then
    die "Impossible de récupérer le token admin après $LOGIN_RETRIES essais"
  fi
  echo "Token admin obtenu : $ADMIN_TOKEN"
}

create_class() {
  echo "=== Création d'une classe Terminale A ==="
  CLASS_ID=$(curl -s -X POST "$API_URL/classes" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"name":"Terminale A","level":"Lycée","academic_year":"2023-2024"}' \
    | jq -r '.id')
  [[ -n "$CLASS_ID" && "$CLASS_ID" != "null" ]] || die "Échec création de la classe"
  echo "Classe ID=$CLASS_ID"
}

import_teachers() {
  echo "=== Import des enseignants via CSV ==="
  cat > teachers.csv <<EOF
username,password,role,nom,prenom,email,class_id
prof_maths,PassProf123!,teacher,Dupont,Pierre,p.dupont@ecole.fr,$CLASS_ID
EOF
  curl -s -X POST "$API_URL/upload" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -F "file=@teachers.csv" | jq . || die "Import enseignants échoué"
  rm teachers.csv
  TEACHER_ID=$(curl -s -X GET "$API_URL/teachers" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    | jq -r '.[] | select(.email=="p.dupont@ecole.fr") | .id')
  [[ -n "$TEACHER_ID" ]] || die "Impossible de récupérer l'ID du prof"
  echo "Prof ID=$TEACHER_ID"
}

create_subject() {
  echo "=== Création de la matière Mathématiques ==="
  SUBJECT_ID=$(curl -s -X POST "$API_URL/subjects" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"Mathématiques\",\"teacher_id\":$TEACHER_ID,\"class_id\":$CLASS_ID}" \
    | jq -r '.id')
  [[ -n "$SUBJECT_ID" ]] || die "Échec création de la matière"
  echo "Subject ID=$SUBJECT_ID"
}

import_students() {
  echo "=== Import des étudiants via CSV ==="
  cat > students.csv <<EOF
username,password,role,nom,prenom,email,class_id
etudiant1,PassStudent123!,student,Martin,Alice,a.martin@ecole.fr,$CLASS_ID
EOF
  curl -s -X POST "$API_URL/upload" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -F "file=@students.csv" | jq . || die "Import étudiants échoué"
  rm students.csv
  STUDENT_ID=$(curl -s -X GET "$API_URL/students" \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    | jq -r '.[] | select(.email=="a.martin@ecole.fr") | .id')
  [[ -n "$STUDENT_ID" ]] || die "Impossible de récupérer l'ID de l'étudiant"
  echo "Student ID=$STUDENT_ID"
}

interactive_menu() {
  while true; do
    echo
    echo "1) Ajouter une note (15.5) pour l'étudiant"
    echo "2) Lister les notes de l'étudiant"
    echo "3) Quitter"
    read -rp "Choix> " CHOICE
    case "$CHOICE" in
      1)
        echo "Ajout de la note..."
        TEACHER_TOKEN=$(curl -s -X POST "$API_URL/login" \
          -H "Content-Type: application/json" \
          -d '{"username":"prof_maths","password":"PassProf123!"}' \
          | jq -r '.token')
        curl -s -X POST "$API_URL/grades" \
          -H "Authorization: Bearer $TEACHER_TOKEN" \
          -H "Content-Type: application/json" \
          -d "{\"student_id\":$STUDENT_ID,\"subject_id\":$SUBJECT_ID,\"grade\":15.5}" \
          | jq .
        ;;
      2)
        echo "Récupération des notes..."
        STUD_TOKEN=$(curl -s -X POST "$API_URL/login" \
          -H "Content-Type: application/json" \
          -d '{"username":"etudiant1","password":"PassStudent123!"}' \
          | jq -r '.token')
        curl -s -X GET "$API_URL/grades" \
          -H "Authorization: Bearer $STUD_TOKEN" \
          | jq .
        ;;
      3) exit 0 ;;
      *) echo "Choix invalide." ;;
    esac
  done
}

# --- Exécution principale ---
check_tools
start_containers
wait_mysql
init_database
create_admin
get_token_admin
create_class
import_teachers
create_subject
import_students

echo -e "
=== Initialisation terminée ! ==="
interactive_menu
```
