#!/usr/bin/env bash
# Start/stop the Home Assistant dev container and check that its ports are free.
#
#   dev/ha.sh up       start (refuses if HA_PORT/DEBUGPY_PORT are taken by something else)
#   dev/ha.sh down     stop and remove the container
#   dev/ha.sh restart  restart Home Assistant (needed after code changes)
#   dev/ha.sh logs     follow the Home Assistant log
#   dev/ha.sh status   show container state and who holds the ports
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi
HA_PORT="${HA_PORT:-8123}"
DEBUGPY_PORT="${DEBUGPY_PORT:-5678}"
CONTAINER="ha-battaxi"

own_container_running() {
  [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || true)" = "true" ]
}

port_in_use() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

describe_port_holder() {
  local port="$1" container
  container="$(docker ps --filter "publish=$port" --format '{{.Names}} ({{.Image}})' 2>/dev/null | head -n1)"
  if [ -n "$container" ]; then
    echo "Docker container $container"
  else
    lsof -nP -iTCP:"$port" -sTCP:LISTEN | awk 'NR==2 {print $1 " (pid " $2 ")"}'
  fi
}

check_ports_free() {
  local busy=0 port
  for port in "$HA_PORT" "$DEBUGPY_PORT"; do
    if port_in_use "$port"; then
      echo "✖ Port $port is already in use by: $(describe_port_holder "$port")" >&2
      busy=1
    fi
  done
  if [ "$busy" -ne 0 ]; then
    echo "  Stop it (e.g. 'docker stop <name>') or set HA_PORT/DEBUGPY_PORT in .env" >&2
    exit 1
  fi
}

wait_for_debugpy() {
  local timeout="${1:-180}" waited=0
  printf 'Waiting for debugpy on localhost:%s ' "$DEBUGPY_PORT"
  until nc -z localhost "$DEBUGPY_PORT" >/dev/null 2>&1; do
    if ! own_container_running; then
      echo
      echo "✖ Container $CONTAINER stopped unexpectedly. Last log lines:" >&2
      docker logs --tail 50 "$CONTAINER" >&2 || true
      exit 1
    fi
    if [ "$waited" -ge "$timeout" ]; then
      echo
      echo "✖ debugpy did not come up within ${timeout}s. See: dev/ha.sh logs" >&2
      exit 1
    fi
    sleep 2
    waited=$((waited + 2))
    printf '.'
  done
  echo " ready"
  echo "✔ Home Assistant: http://localhost:$HA_PORT  (debugpy on $DEBUGPY_PORT)"
}

case "${1:-}" in
  up)
    if own_container_running; then
      echo "✔ $CONTAINER is already running"
    else
      check_ports_free
      docker compose up -d
    fi
    wait_for_debugpy
    ;;
  down)
    docker compose down
    ;;
  restart)
    docker compose restart
    wait_for_debugpy
    ;;
  logs)
    docker compose logs -f --tail 200
    ;;
  status)
    docker compose ps
    for port in "$HA_PORT" "$DEBUGPY_PORT"; do
      if port_in_use "$port"; then
        echo "port $port: $(describe_port_holder "$port")"
      else
        echo "port $port: free"
      fi
    done
    ;;
  *)
    sed -n '2,9p' "$0"
    exit 2
    ;;
esac
