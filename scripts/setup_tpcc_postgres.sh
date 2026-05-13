#!/usr/bin/env bash
set -euo pipefail

TPCC_DB="${TPCC_DB:-benchbase}"
TPCC_USER="${TPCC_USER:-admin}"
TPCC_PASSWORD="${TPCC_PASSWORD:-password}"
POSTGRES_PIN_CORES="${POSTGRES_PIN_CORES:-0 1 2 3 4 5 6 7 8 9}"
POSTGRES_MAX_WORKER_PROCESSES="${POSTGRES_MAX_WORKER_PROCESSES:-44}"
POSTGRES_MAX_PARALLEL_WORKERS="${POSTGRES_MAX_PARALLEL_WORKERS:-42}"

if [[ ! "$TPCC_DB" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "TPCC_DB must be a simple PostgreSQL identifier, got: $TPCC_DB" >&2
  exit 1
fi

if [[ ! "$TPCC_USER" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "TPCC_USER must be a simple PostgreSQL identifier, got: $TPCC_USER" >&2
  exit 1
fi

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

run_as_postgres() {
  if [[ "${EUID}" -eq 0 ]]; then
    runuser -u postgres -- "$@"
  else
    sudo -u postgres "$@"
  fi
}

start_postgres() {
  if command -v systemctl >/dev/null 2>&1; then
    "${SUDO[@]}" systemctl enable --now postgresql || "${SUDO[@]}" service postgresql start
  else
    "${SUDO[@]}" service postgresql start
  fi
}

restart_postgres() {
  if command -v systemctl >/dev/null 2>&1; then
    "${SUDO[@]}" systemctl daemon-reload || true
    "${SUDO[@]}" systemctl restart postgresql || "${SUDO[@]}" service postgresql restart
  else
    "${SUDO[@]}" service postgresql restart
  fi
}

set_postgres_conf() {
  local key="$1"
  local value="$2"
  local file="$3"

  if grep -qE "^[#[:space:]]*${key}[[:space:]]*=" "$file"; then
    "${SUDO[@]}" sed -i -E "s|^[#[:space:]]*${key}[[:space:]]*=.*|${key} = ${value}|" "$file"
  else
    printf "\n%s = %s\n" "$key" "$value" | "${SUDO[@]}" tee -a "$file" >/dev/null
  fi
}

echo "Ensuring PostgreSQL packages are installed..."
if ! command -v psql >/dev/null 2>&1 || ! dpkg -s postgresql postgresql-contrib >/dev/null 2>&1; then
  "${SUDO[@]}" apt-get update
  "${SUDO[@]}" apt-get install -y postgresql postgresql-contrib
fi

echo "Starting PostgreSQL..."
start_postgres

if command -v pg_lsclusters >/dev/null 2>&1; then
  CLUSTER_LINE="$(pg_lsclusters --no-header | awk '$4 == "online" { print $1, $2; found=1; exit } END { if (!found) exit 1 }' || true)"
  if [[ -z "$CLUSTER_LINE" ]]; then
    CLUSTER_LINE="$(pg_lsclusters --no-header | awk 'NR == 1 { print $1, $2; exit }')"
  fi
  read -r PG_CLUSTER_VERSION PG_CLUSTER_NAME <<< "$CLUSTER_LINE"
else
  PG_CLUSTER_VERSION="${PG_CLUSTER_VERSION:-14}"
  PG_CLUSTER_NAME="${PG_CLUSTER_NAME:-main}"
fi

CONF_FILE="/etc/postgresql/${PG_CLUSTER_VERSION}/${PG_CLUSTER_NAME}/postgresql.conf"
if [[ ! -f "$CONF_FILE" ]]; then
  echo "Could not find PostgreSQL config file: $CONF_FILE" >&2
  exit 1
fi

SERVICE_NAME="postgresql@${PG_CLUSTER_VERSION}-${PG_CLUSTER_NAME}.service"
if command -v systemctl >/dev/null 2>&1 && systemctl cat "$SERVICE_NAME" >/dev/null 2>&1; then
  echo "Writing CPU affinity override for ${SERVICE_NAME}: ${POSTGRES_PIN_CORES}"
  OVERRIDE_DIR="/etc/systemd/system/${SERVICE_NAME}.d"
  "${SUDO[@]}" mkdir -p "$OVERRIDE_DIR"
  printf "[Service]\nCPUAffinity=%s\n" "$POSTGRES_PIN_CORES" \
    | "${SUDO[@]}" tee "${OVERRIDE_DIR}/override.conf" >/dev/null
else
  echo "Skipping CPU affinity override; ${SERVICE_NAME} is not available on this host."
fi

echo "Setting PostgreSQL worker counts in ${CONF_FILE}..."
set_postgres_conf "max_worker_processes" "$POSTGRES_MAX_WORKER_PROCESSES" "$CONF_FILE"
set_postgres_conf "max_parallel_workers" "$POSTGRES_MAX_PARALLEL_WORKERS" "$CONF_FILE"

ESCAPED_PASSWORD="${TPCC_PASSWORD//\'/\'\'}"

echo "Creating/updating role ${TPCC_USER} and database ${TPCC_DB}..."
run_as_postgres psql -v ON_ERROR_STOP=1 <<SQL
SELECT 'CREATE DATABASE "${TPCC_DB}"'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${TPCC_DB}')\gexec

DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${TPCC_USER}') THEN
    CREATE ROLE "${TPCC_USER}" WITH SUPERUSER LOGIN PASSWORD '${ESCAPED_PASSWORD}';
  ELSE
    ALTER ROLE "${TPCC_USER}" WITH SUPERUSER LOGIN PASSWORD '${ESCAPED_PASSWORD}';
  END IF;
END
\$\$;

ALTER DATABASE "${TPCC_DB}" OWNER TO "${TPCC_USER}";
GRANT ALL PRIVILEGES ON DATABASE "${TPCC_DB}" TO "${TPCC_USER}";
SQL

run_as_postgres psql -v ON_ERROR_STOP=1 -d "$TPCC_DB" <<SQL
ALTER SCHEMA public OWNER TO "${TPCC_USER}";
GRANT ALL ON SCHEMA public TO "${TPCC_USER}";
SQL

echo "Restarting PostgreSQL..."
restart_postgres

echo "Verifying PostgreSQL connectivity..."
PGPASSWORD="$TPCC_PASSWORD" psql -h localhost -U "$TPCC_USER" -d "$TPCC_DB" -c "select 1;"

echo "TPCC PostgreSQL setup complete: ${TPCC_USER}@localhost/${TPCC_DB}"
