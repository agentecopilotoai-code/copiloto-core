#!/usr/bin/env bash
# SEC-010 — helper para separar password del DATABASE_URL antes de pasarlo a
# psql / pg_dump / pg_restore. Sin esto, el password queda visible en
# `ps aux` para CUALQUIER usuario del host mientras el comando corre — y la
# ventana es lo suficientemente larga (dump/restore tardan minutos) para que
# un proceso adversarial muestree.
#
# Patrón seguro:
#   source scripts/lib/postgres-url.sh
#   parse_db_url "$DATABASE_URL"
#   export PGPASSWORD="$DB_PASSWORD"
#   docker compose exec -T -e PGPASSWORD postgres psql "$DB_URL_NO_PASSWORD" ...
#
# `docker compose exec -e PGPASSWORD` (sin valor) inherita del shell padre, así
# que el password tampoco aparece en el argv de `docker`. La variable solo es
# visible via `/proc/<pid>/environ` que requiere mismo uid (defense razonable
# en boxes de developer).
#
# Limitaciones: el parser asume que el password no contiene `@` literal sin
# URL-encoding. Para passwords con caracteres especiales, usar URL-encoding
# (RFC 3986) en el .env — el connection libpq lo decodifica del lado server.
set -euo pipefail

# parse_db_url <url>
#
# Setea las variables globales:
#   DB_PASSWORD            — password extraído (vacío si la URL no tiene)
#   DB_URL_NO_PASSWORD     — URL con el `:password` removido
#
# Mantiene el resto de la URL intacta (scheme, user, host, port, dbname,
# query string). Si la URL ya viene sin password, DB_PASSWORD='' y
# DB_URL_NO_PASSWORD == input.
parse_db_url() {
  local url="$1"
  if [[ -z "$url" ]]; then
    DB_PASSWORD=''
    DB_URL_NO_PASSWORD=''
    return 0
  fi

  # Formato esperado: <scheme>://[<user>[:<password>]@]<host>[:<port>]/<dbname>[?<opts>]
  local scheme rest
  if [[ "$url" == *"://"* ]]; then
    scheme="${url%%://*}://"
    rest="${url#*://}"
  else
    # Sin scheme, devolver tal cual (no podemos parsear).
    DB_PASSWORD=''
    DB_URL_NO_PASSWORD="$url"
    return 0
  fi

  # Separar userinfo del resto en el último `@` (el password puede contener `@`
  # solo si está URL-encoded; usamos el último `@` como heurística para que un
  # `%40` literal en password no rompa el split).
  local userinfo hostpart
  if [[ "$rest" == *"@"* ]]; then
    userinfo="${rest%@*}"
    hostpart="${rest##*@}"
  else
    # Sin userinfo, no hay password que extraer.
    DB_PASSWORD=''
    DB_URL_NO_PASSWORD="$url"
    return 0
  fi

  # Userinfo es `user[:password]`. Si no hay `:`, no hay password.
  local user_only password_only
  if [[ "$userinfo" == *":"* ]]; then
    user_only="${userinfo%%:*}"
    password_only="${userinfo#*:}"
    DB_PASSWORD="$password_only"
    DB_URL_NO_PASSWORD="${scheme}${user_only}@${hostpart}"
  else
    DB_PASSWORD=''
    DB_URL_NO_PASSWORD="$url"
  fi
}

# Exporta las dos funciones para subshells (algunos callers usan subshells).
export -f parse_db_url 2>/dev/null || true
