#!/usr/bin/env bash
# Deploy e backup do Lastro numa VPS compartilhada.
# Uso: ./scripts/vps.sh {preflight|budget|deploy|backup|restore|rollback|status}
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-$ROOT/.env}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
VOLUME_NAME="${VOLUME_NAME:-lastro_carteira}"
IMAGES=(lastro-backend lastro-ai-engine lastro-frontend)

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

# A tag de publicação é sempre current. O .env não redefine o rollback.
export LASTRO_TAG=current

log() { printf '%s\n' "$*"; }
die() { printf 'erro: %s\n' "$*" >&2; exit 1; }

compose() {
  local -a args=(docker compose -f "$ROOT/compose.yaml")
  if [[ -f "$ENV_FILE" ]]; then
    args+=(--env-file "$ENV_FILE")
  fi
  "${args[@]}" "$@"
}

to_mb() {
  local raw="${1//[[:space:]]/}"
  if [[ "$raw" =~ ^([0-9]+)([GgMm])$ ]]; then
    local n="${BASH_REMATCH[1]}"
    local unit="${BASH_REMATCH[2]}"
    case "$unit" in
      G|g) echo $((n * 1024)) ;;
      M|m) echo "$n" ;;
    esac
    return 0
  fi
  die "limite de memória inválido ($1). Use um inteiro seguido de M ou G, por exemplo 1536M."
}

to_milli() {
  local raw="$1"
  awk -v v="$raw" 'BEGIN {
    if (v !~ /^[0-9]+([.][0-9]+)?$/) exit 2
    printf "%d\n", v * 1000
  }' || die "limite de CPU inválido ($raw). Use um número, por exemplo 1.0 ou 0.25."
}

budget() {
  local ai_mb be_mb fe_mb sum_mb host_mb
  local ai_cpu be_cpu fe_cpu sum_cpu host_cpu
  ai_mb="$(to_mb "${AI_MEMORY_LIMIT:-1536M}")"
  be_mb="$(to_mb "${BACKEND_MEMORY_LIMIT:-384M}")"
  fe_mb="$(to_mb "${FRONTEND_MEMORY_LIMIT:-512M}")"
  sum_mb=$((ai_mb + be_mb + fe_mb))
  host_mb=$(( $(awk '/MemTotal:/ {print $2}' /proc/meminfo) / 1024 ))
  ai_cpu="$(to_milli "${AI_CPU_LIMIT:-1.0}")"
  be_cpu="$(to_milli "${BACKEND_CPU_LIMIT:-0.50}")"
  fe_cpu="$(to_milli "${FRONTEND_CPU_LIMIT:-0.50}")"
  sum_cpu=$((ai_cpu + be_cpu + fe_cpu))
  host_cpu="$(nproc)"

  log "Host agora: ${host_cpu} vCPU, ${host_mb} MiB de RAM."
  log "Teto do stack: $(awk -v m="$sum_cpu" 'BEGIN{printf "%.2f", m/1000}') CPU e ${sum_mb} MiB."
  log "Motor de leitura: $(awk -v m="$ai_cpu" 'BEGIN{printf "%.2f", m/1000}') CPU e ${ai_mb} MiB."

  local mem_fail=0 cpu_fail=0
  if (( sum_mb * 100 > host_mb * 70 )); then
    log "O teto de RAM passa de 70% do host. Reduza AI_MEMORY_LIMIT, BACKEND_MEMORY_LIMIT e FRONTEND_MEMORY_LIMIT."
    mem_fail=1
  elif (( sum_mb * 100 > host_mb * 45 )); then
    log "Aviso: o teto de RAM passa de 45% do host. Os outros processos da VPS ficam com menos folga."
  else
    log "RAM: o teto cabe em até 45% do host."
  fi

  if (( sum_cpu * 100 > host_cpu * 1000 * 80 )); then
    log "O teto de CPU passa de 80% das vCPUs. Reduza AI_CPU_LIMIT antes de subir o motor."
    cpu_fail=1
  elif (( sum_cpu * 100 > host_cpu * 1000 * 50 )); then
    log "Aviso: o teto de CPU passa de metade das vCPUs."
  else
    log "CPU: o teto cabe em até metade das vCPUs."
  fi

  if (( mem_fail || cpu_fail )); then
    if [[ "${ALLOW_TIGHT_BUDGET:-0}" == "1" ]]; then
      log "ALLOW_TIGHT_BUDGET=1 segue mesmo assim."
      return 0
    fi
    return 1
  fi
}

os_note() {
  if [[ ! -r /etc/os-release ]]; then
    log "Aviso: /etc/os-release ausente. A premissa deste stack é Ubuntu 24.04 LTS."
    return
  fi
  local pretty id
  pretty="$(. /etc/os-release && printf '%s' "$PRETTY_NAME")"
  id="$(. /etc/os-release && printf '%s' "$ID")"
  log "SO do host: $pretty"
  if [[ "$id" != "ubuntu" ]]; then
    log "Aviso: o procedimento foi escrito para Ubuntu. O host declara ID=$id."
  fi
}

require_docker() {
  command -v docker >/dev/null 2>&1 || die "Docker não está no PATH."
  docker compose version >/dev/null 2>&1 || die "Instale o plugin Docker Compose v2 (pacote docker-compose-v2)."
}

preflight() {
  os_note
  log "Premissa deste repositório: Ubuntu 24.04 LTS e um envelope que deixa a maior parte da VPS para o que já roda nela."
  log "Confira o SO acima e, se a RAM ou as vCPUs forem outras, edite o .env antes do deploy."
  budget
  require_docker
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"
  local avail_kb
  avail_kb="$(df -Pk "$BACKUP_DIR" | awk 'NR==2 {print $4}')"
  if (( avail_kb < 512000 )); then
    log "Aviso: menos de 500 MiB livres no disco de $BACKUP_DIR."
  fi
  log "Preflight ok."
}

with_lock() {
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"
  exec 9>"$BACKUP_DIR/.deploy.lock"
  flock -n 9 || die "já existe um deploy ou backup em andamento."
}

service_id() {
  local name="$1"
  compose ps -aq "$name" | head -n 1
}

assert_capped() {
  local name="$1"
  local id bytes nanos
  id="$(service_id "$name")"
  if [[ -z "$id" ]]; then
    log "contêiner de $name não existe."
    return 1
  fi
  bytes="$(docker inspect -f '{{.HostConfig.Memory}}' "$id")"
  nanos="$(docker inspect -f '{{.HostConfig.NanoCpus}}' "$id")"
  if [[ "$bytes" -le 0 || "$nanos" -le 0 ]]; then
    log "$name subiu sem teto de memória ou CPU (memory=$bytes, nano_cpus=$nanos)."
    return 1
  fi
  log "$name limitado: $((bytes / 1024 / 1024)) MiB, $(awk -v n="$nanos" 'BEGIN{printf "%.2f", n/1000000000}') CPU."
}

wait_healthy() {
  local name="$1"
  local id status i
  id="$(service_id "$name")"
  [[ -n "$id" ]] || return 1
  status="missing"
  for i in $(seq 1 60); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$id" 2>/dev/null || echo missing)"
    if [[ "$status" == "healthy" ]]; then
      log "$name saudável."
      return 0
    fi
    sleep 2
  done
  log "$name não ficou saudável (último estado: $status)."
  return 1
}

tag_previous() {
  local image
  for image in "${IMAGES[@]}"; do
    if docker image inspect "${image}:current" >/dev/null 2>&1; then
      docker tag "${image}:current" "${image}:previous"
      log "Imagem anterior preservada: ${image}:previous"
    fi
  done
}

rollback() {
  require_docker
  local image missing=0
  for image in "${IMAGES[@]}"; do
    if docker image inspect "${image}:previous" >/dev/null 2>&1; then
      docker tag "${image}:previous" "${image}:current"
    else
      log "Sem ${image}:previous para voltar."
      missing=1
    fi
  done
  if (( missing )); then
    die "Rollback incompleto."
  fi
  compose up -d --no-build
  log "Stack republicado a partir das imagens anteriores."
}

backup_body() {
  require_docker
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"
  if ! docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1; then
    log "Volume $VOLUME_NAME ainda não existe. Nada para arquivar."
    return 0
  fi
  if ! docker image inspect lastro-backend:current >/dev/null 2>&1; then
    log "Volume presente, mas lastro-backend:current não existe. Backup adiado."
    return 0
  fi
  local stamp archive
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  archive="$BACKUP_DIR/lastro-${stamp}.tar.gz"
  docker run --rm --user 0:0 --network none \
    --entrypoint tar \
    -v "${VOLUME_NAME}:/data:ro" \
    -v "${BACKUP_DIR}:/backup" \
    lastro-backend:current \
    -C /data -czf "/backup/$(basename "$archive")" .
  sha256sum "$archive" > "${archive}.sha256"
  chmod 600 "$archive" "${archive}.sha256"
  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'lastro-*.tar.gz' -mtime +"$RETENTION_DAYS" -delete
  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'lastro-*.tar.gz.sha256' -mtime +"$RETENTION_DAYS" -delete
  log "Backup em $archive"
}

restore() {
  require_docker
  local archive="" yes=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --yes) yes=1 ;;
      -*) die "opção desconhecida: $1" ;;
      *) archive="$1" ;;
    esac
    shift
  done
  [[ -n "$archive" && -f "$archive" ]] || die "informe o arquivo .tar.gz existente."
  archive="$(readlink -f "$archive")"
  if [[ -z "$(service_id backend)" ]]; then
    die "suba o stack com deploy antes de restaurar."
  fi
  if [[ "$yes" -ne 1 ]]; then
    cat <<EOF
Isto substitui o conteúdo do volume ${VOLUME_NAME} (o SQLite da carteira) pelo arquivo:
  $archive
As posições que estão nesse volume deixam de existir.
Repita o comando com --yes para executar.
EOF
    exit 1
  fi
  local dir base
  dir="$(dirname "$archive")"
  base="$(basename "$archive")"
  compose stop frontend backend
  docker run --rm --user 0:0 --network none \
    --entrypoint tar \
    -v "${VOLUME_NAME}:/data" \
    -v "${dir}:/backup:ro" \
    lastro-backend:current \
    -C /data -xzf "/backup/${base}"
  docker run --rm --user 0:0 --network none \
    --entrypoint chown \
    -v "${VOLUME_NAME}:/data" \
    lastro-backend:current \
    -R 1001:1001 /data
  compose start backend frontend
  log "Volume ${VOLUME_NAME} restaurado a partir de $archive"
}

deploy() {
  preflight
  with_lock
  if docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1; then
    backup_body
  else
    log "Primeiro deploy: ainda não há volume para arquivar."
  fi
  tag_previous
  compose build
  if ! compose up -d --no-build; then
    compose logs --tail 60 || true
    log "compose up falhou."
    rollback || true
    exit 1
  fi
  local name failed=0
  for name in ai-engine backend frontend; do
    if ! assert_capped "$name"; then
      failed=1
    fi
  done
  if (( failed )); then
    log "Teto de recurso ausente. Voltando para a imagem anterior, se existir."
    rollback || true
    exit 1
  fi
  for name in ai-engine backend frontend; do
    if ! wait_healthy "$name"; then
      failed=1
    fi
  done
  if (( failed )); then
    compose logs --tail 60 || true
    log "Saúde falhou. Voltando para a imagem anterior, se existir."
    rollback || true
    exit 1
  fi
  log "Deploy no ar. Mesa em 127.0.0.1:${HOST_WEB_PORT:-4181} e API em 127.0.0.1:${HOST_API_PORT:-8091}."
}

status() {
  require_docker
  compose ps
}

usage() {
  cat <<EOF
Uso: ./scripts/vps.sh <comando>

  preflight   Mostra SO, RAM e CPU do host e recusa teto apertado demais
  budget      Só a conta de RAM e CPU, sem exigir o restante do preflight
  deploy      Backup do volume, build e subida com checagem de teto
  backup      Arquiva o volume lastro_carteira em ./backups
  restore     Restaura um .tar.gz no volume (exige --yes)
  rollback    Republica as imagens :previous
  status      docker compose ps
EOF
}

main() {
  local cmd="${1:-}"
  if [[ $# -gt 0 ]]; then
    shift
  fi
  case "$cmd" in
    preflight) preflight ;;
    budget) budget ;;
    deploy) deploy ;;
    backup) with_lock; backup_body ;;
    restore) with_lock; restore "$@" ;;
    rollback) rollback ;;
    status) status ;;
    ""|-h|--help|help) usage ;;
    *) usage >&2; exit 2 ;;
  esac
}

main "$@"
