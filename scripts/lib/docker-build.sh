#!/usr/bin/env bash
# Shared multi-stage Docker build helpers for asciisky.
# Sourced by hybrid-setup / setup-production / update-production.

# Runtime user baked into Dockerfile (USER appuser)
ASCIISKY_APP_UID="${ASCIISKY_APP_UID:-10001}"
ASCIISKY_APP_GID="${ASCIISKY_APP_GID:-10001}"
ASCIISKY_IMAGE="${ASCIISKY_IMAGE:-asciisky-web:latest}"

# Default: use cache. Set BUILD_NO_CACHE=1 for full rebuild.
BUILD_NO_CACHE="${BUILD_NO_CACHE:-0}"

asciisky_require_docker() {
  if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker is not running / not reachable" >&2
    return 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    echo "❌ docker compose v2 not found" >&2
    return 1
  fi
}

asciisky_require_dockerfile() {
  local root="${1:-.}"
  if [[ ! -f "${root}/Dockerfile" ]]; then
    echo "❌ Dockerfile not found in ${root}" >&2
    return 1
  fi
  if ! grep -qE 'AS builder|AS runtime|FROM .* AS builder' "${root}/Dockerfile"; then
    echo "⚠️  Dockerfile does not look multi-stage (missing builder/runtime stages)" >&2
  fi
  if grep -qE '^\s*docker\.io\s*\\?$' "${root}/Dockerfile" || grep -qE 'apt-get install.*docker\.io' "${root}/Dockerfile"; then
    echo "⚠️  Dockerfile still references docker.io — multi-stage hardening incomplete" >&2
  fi
}

# Ensure host bind-mount dirs are writable by container appuser (uid 10001).
# Safe no-op when dirs already match or chown is not permitted (warn only).
asciisky_prepare_data_dirs() {
  local root="${1:-.}"
  local d
  for d in data cache; do
    mkdir -p "${root}/${d}"
  done
  # user_settings.json may be bind-mounted read-write in production
  if [[ ! -f "${root}/user_settings.json" ]]; then
    : # optional
  fi

  if [[ "$(id -u)" -eq 0 ]]; then
    chown -R "${ASCIISKY_APP_UID}:${ASCIISKY_APP_GID}" "${root}/data" "${root}/cache" 2>/dev/null || true
    return 0
  fi

  # Non-root: try chown; if it fails, warn (common on first multi-stage deploy)
  if ! chown -R "${ASCIISKY_APP_UID}:${ASCIISKY_APP_GID}" "${root}/data" "${root}/cache" 2>/dev/null; then
    local owner
    owner="$(stat -c '%u:%g' "${root}/data" 2>/dev/null || stat -f '%u:%g' "${root}/data" 2>/dev/null || echo unknown)"
    if [[ "$owner" != "${ASCIISKY_APP_UID}:${ASCIISKY_APP_GID}" ]]; then
      echo "⚠️  ${root}/data owner is ${owner}, container runs as ${ASCIISKY_APP_UID}:${ASCIISKY_APP_GID}"
      echo "   If workers cannot write cache/data, run: sudo chown -R ${ASCIISKY_APP_UID}:${ASCIISKY_APP_GID} data cache"
    fi
  fi
}

asciisky_compose_build_args() {
  # prints extra args for `docker compose build`
  if [[ "${BUILD_NO_CACHE}" == "1" || "${BUILD_NO_CACHE}" == "true" ]]; then
    printf '%s\n' "--no-cache"
  fi
  # Always pull base images when possible (python slim security patches)
  printf '%s\n' "--pull"
}

# Build all images defined in a compose file (multi-stage Dockerfile via build: .)
# Usage: asciisky_compose_build <compose-file> [project-dir]
asciisky_compose_build() {
  local compose_file="$1"
  local project_dir="${2:-.}"
  local -a extra=()
  local arg

  asciisky_require_docker || return 1
  asciisky_require_dockerfile "$project_dir" || return 1

  while IFS= read -r arg; do
    [[ -n "$arg" ]] && extra+=("$arg")
  done < <(asciisky_compose_build_args)

  echo "🔨 Multi-stage build via ${compose_file} (image target: runtime)"
  echo "   BUILD_NO_CACHE=${BUILD_NO_CACHE}  PYTHON base pulled if --pull supported"
  (
    cd "$project_dir" || exit 1
    # Compose builds final stage by default; Dockerfile last stage is runtime.
    docker compose -f "$compose_file" build "${extra[@]}"
  )
}

# Verify built image: non-root user, no docker CLI, imports work
# Usage: asciisky_verify_image [image-name]
asciisky_verify_image() {
  local image="${1:-$ASCIISKY_IMAGE}"
  echo "🔍 Verifying image ${image} ..."

  if ! docker image inspect "$image" >/dev/null 2>&1; then
    echo "❌ Image not found: $image" >&2
    return 1
  fi

  local user
  user="$(docker image inspect -f '{{.Config.User}}' "$image")"
  if [[ -z "$user" || "$user" == "root" || "$user" == "0" ]]; then
    echo "❌ Image still runs as root (User='${user}')" >&2
    return 1
  fi
  echo "   User: ${user}"

  # docker CLI must not exist in runtime
  if docker run --rm --entrypoint /bin/sh "$image" -c 'command -v docker' >/dev/null 2>&1; then
    echo "❌ docker CLI present in runtime image" >&2
    return 1
  fi
  echo "   docker CLI: absent (ok)"

  # compilers should not be in runtime
  if docker run --rm --entrypoint /bin/sh "$image" -c 'command -v gcc || command -v g++' >/dev/null 2>&1; then
    echo "⚠️  compiler toolchain still present in runtime image" >&2
  else
    echo "   compilers: absent (ok)"
  fi

  docker run --rm --entrypoint python "$image" -c 'import sys; mods=["fastapi","uvicorn","numpy","pandas","psycopg","pika","skyfield"];
[__import__(m) for m in mods]; print("imports_ok", sys.version.split()[0])'
  echo "✅ Image verification passed"
}

# Tag compose-built image aliases if needed
asciisky_tag_aliases() {
  local primary="${1:-asciisky-web:latest}"
  # Dev compose historically used asciisky-worker — keep as alias of same multi-stage image
  if docker image inspect "$primary" >/dev/null 2>&1; then
    docker tag "$primary" asciisky-web:latest 2>/dev/null || true
    docker tag "$primary" asciisky-worker:latest 2>/dev/null || true
    docker tag "$primary" asciisky-web 2>/dev/null || true
    docker tag "$primary" asciisky-worker 2>/dev/null || true
  fi
}
