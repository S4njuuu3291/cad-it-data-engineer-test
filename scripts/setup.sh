#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
command -v openssl >/dev/null 2>&1 || { echo "OpenSSL diperlukan untuk setup." >&2; exit 1; }
umask 077

if [ ! -f .env ]; then
    cp .env.example .env
    echo ".env dibuat dari .env.example"
fi
set -a
. ./.env
set +a
: "${POSTGRES_PASSWORD_FILE:?Isi POSTGRES_PASSWORD_FILE di .env}"
chmod 600 .env

mkdir -p certs "$(dirname "$POSTGRES_PASSWORD_FILE")"
if [ ! -s "$POSTGRES_PASSWORD_FILE" ]; then
    openssl rand -hex 24 > "$POSTGRES_PASSWORD_FILE"
    echo "Password lokal dibuat."
fi
chmod 600 "$POSTGRES_PASSWORD_FILE"

cert_tmp_dir=$(mktemp -d)
trap 'rm -rf "$cert_tmp_dir"' EXIT
new_ca=0
# Pasangan yang belum lengkap dibuat ulang; pasangan lengkap dipertahankan.
if [ ! -s certs/ca.key ] || [ ! -s certs/ca.crt ]; then
    openssl genrsa -out certs/ca.key 3072
    openssl req -x509 -new -sha256 -days 3650 \
        -key certs/ca.key -out certs/ca.crt \
        -subj '/CN=Movies PostgreSQL Local CA' \
        -addext 'basicConstraints=critical,CA:TRUE' \
        -addext 'keyUsage=critical,keyCertSign,cRLSign'
    new_ca=1
    echo "CA lokal dibuat."
fi

if [ "$new_ca" -eq 1 ] || [ ! -s certs/server.key ] || [ ! -s certs/server.crt ]; then
    openssl genrsa -out certs/server.key 3072
    openssl req -new -sha256 -key certs/server.key \
        -out "$cert_tmp_dir/server.csr" -subj '/CN=localhost'
    cat > "$cert_tmp_dir/server.ext" <<'EOF'
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:localhost,DNS:postgres,IP:127.0.0.1,IP:::1
EOF
    openssl x509 -req -sha256 -days 365 \
        -in "$cert_tmp_dir/server.csr" -out certs/server.crt \
        -CA certs/ca.crt -CAkey certs/ca.key \
        -set_serial "0x$(openssl rand -hex 16)" \
        -extfile "$cert_tmp_dir/server.ext"
    echo "Sertifikat server lokal dibuat."
fi
chmod 600 certs/ca.key certs/server.key
chmod 644 certs/ca.crt certs/server.crt
openssl verify -CAfile certs/ca.crt -verify_hostname localhost certs/server.crt
echo "Setup selesai. Jalankan: make docker-up"
