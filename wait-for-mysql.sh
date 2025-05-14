#!/bin/sh

host="$1"
shift
cmd="$@"

# Ajouter les variables d'environnement
export MYSQL_PWD="${MYSQL_PASSWORD}"

until mysqladmin ping -h "$host" -u "${MYSQL_USER}" --silent; do
  >&2 echo "MySQL is unavailable - sleeping"
  sleep 1
done

>&2 echo "MySQL is up - executing command"
exec $cmd
