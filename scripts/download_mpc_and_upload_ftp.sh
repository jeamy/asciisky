#!/usr/bin/env bash
set -euo pipefail

# Required environment variables:
#   FTP_SERVER   (e.g. ftp.example.com)
#   FTP_USER
#   FTP_PASSWD
#   FTP_UPLOAD   (remote directory, e.g. /incoming/asciisky)
#
# Optional environment variables:
#   FTP_PORT     (default: 21)
#   FTP_SCHEME   (default: ftp, alternatives: ftps)
#   COMET_URL    (default: MPC comet elements URL)
#   MPCORB_URL   (default: MPC asteroid elements URL)

: "${FTP_SERVER:?FTP_SERVER is required}"
: "${FTP_USER:?FTP_USER is required}"
: "${FTP_PASSWD:?FTP_PASSWD is required}"
: "${FTP_UPLOAD:?FTP_UPLOAD is required}"

FTP_PORT="${FTP_PORT:-21}"
FTP_SCHEME="${FTP_SCHEME:-ftp}"
COMET_URL="${COMET_URL:-https://www.minorplanetcenter.net/iau/MPCORB/CometEls.txt}"
MPCORB_URL="${MPCORB_URL:-https://www.minorplanetcenter.net/iau/MPCORB/MPCORB.DAT.gz}"

TMP_DIR="/tmp"
COMET_FILE="${TMP_DIR}/COMET_ELEMENTS.txt"
MPCORB_FILE="${TMP_DIR}/MPCORB.DAT.gz"

# Normalize remote upload path to avoid duplicate slashes
REMOTE_DIR="${FTP_UPLOAD#/}"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

download() {
  local url="$1"
  local out="$2"
  local tmp
  tmp="${out}.part"

  log "Download: ${url} -> ${out}"
  curl -fL --retry 5 --retry-delay 2 --connect-timeout 30 --max-time 1800 \
    -o "${tmp}" "${url}"
  mv "${tmp}" "${out}"
  log "Downloaded $(basename "${out}") ($(du -h "${out}" | awk '{print $1}'))"
}

upload_ftp() {
  local file="$1"
  local remote_name
  remote_name="$(basename "${file}")"
  local remote_url="${FTP_SCHEME}://${FTP_SERVER}:${FTP_PORT}/${REMOTE_DIR}/${remote_name}"

  log "Upload: ${file} -> ${remote_url}"
  curl -f --ftp-create-dirs --user "${FTP_USER}:${FTP_PASSWD}" \
    --upload-file "${file}" "${remote_url}"
  log "Uploaded ${remote_name}"
}

main() {
  download "${COMET_URL}" "${COMET_FILE}"
  download "${MPCORB_URL}" "${MPCORB_FILE}"

  upload_ftp "${COMET_FILE}"
  upload_ftp "${MPCORB_FILE}"

  log "All done"
}

main "$@"
