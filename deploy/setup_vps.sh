#!/usr/bin/env bash
# Sc v38: keep Python on loopback, Caddy on public ports. Never stop other containers.
set -Eeuo pipefail
[[ $(id -u) -eq 0 ]] || { echo 'Run as root.' >&2; exit 1; }
cd /root/Sc
[[ -x .venv/bin/python3 ]] || { echo 'Missing .venv; install dependencies once.' >&2; exit 1; }
[[ -f config.py ]] || { echo 'Missing private config.py.' >&2; exit 1; }
.venv/bin/python3 -m py_compile miko.py sc_core/bot.py sc_core/website_server.py
IP="${SC_PUBLIC_IP:-$(curl -4fsS --connect-timeout 5 --max-time 10 https://api.ipify.org)}"
[[ "$IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || { echo 'Invalid public IP.' >&2; exit 1; }
HOST="${SC_DOMAIN:-${IP}.sslip.io}"
[[ "$HOST" =~ ^[A-Za-z0-9.-]+$ ]] || { echo 'Invalid hostname.' >&2; exit 1; }
if ! command -v caddy >/dev/null 2>&1; then
  echo 'Installing Caddy (Python packages are unchanged)...'
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y caddy
fi
mkdir -p /etc/caddy /etc/systemd/system
# Existing unmanaged Caddy configurations may host other projects; do not overwrite them.
CADDYFILE=/etc/caddy/Caddyfile
if [[ -s "$CADDYFILE" ]] && ! grep -q '^# SC-MIKO-MANAGED' "$CADDYFILE"; then
  # Permit replacement only for a simple one-site config previously created for this Sc host.
  if ! grep -Fq "$HOST" "$CADDYFILE" || ! grep -Eq 'reverse_proxy[[:space:]]+127\.0\.0\.1:(1276|1256|1982)' "$CADDYFILE"; then
    echo 'Existing Caddyfile is not Sc-managed. Refusing to replace other sites.' >&2
    echo 'See deploy/README.md for manual integration.' >&2
    exit 1
  fi
  echo 'Found existing Sc Caddy site; backing it up before migration.'
fi
# Check public ports before changing configuration. Caddy may already own them.
for port in 80 443 1276; do
  owner="$(ss -H -ltnp "sport = :$port" || true)"
  if [[ -n "$owner" ]] && ! grep -q 'caddy' <<< "$owner"; then
    if [[ "$port" == 1276 ]] && grep -q '127.0.0.1:1276' <<< "$owner" && systemctl is-active --quiet sc-miko.service; then continue; fi
    echo "Port $port is used by a non-Caddy service; not interrupting it." >&2
    echo "$owner" >&2
    exit 1
  fi
done
backup="$(mktemp /tmp/sc-caddy-backup.XXXXXXXX)"
if [[ -f "$CADDYFILE" ]]; then cp -a "$CADDYFILE" "$backup"; else : > "$backup"; fi
cat > "$CADDYFILE" <<CADDY
# SC-MIKO-MANAGED v38
$HOST {
    encode gzip zstd
    reverse_proxy 127.0.0.1:1276
}
http://$IP:1276 {
    bind $IP
    redir https://$HOST{uri} 308
}
CADDY
caddy fmt --overwrite "$CADDYFILE" >/dev/null
if ! caddy validate --config "$CADDYFILE" >/dev/null; then
  cp -a "$backup" "$CADDYFILE"
  echo 'Caddy validation failed; restored previous config.' >&2
  exit 1
fi
cat > /etc/systemd/system/sc-miko.service <<'SERVICE'
[Unit]
Description=Sc Telegram Bot and Manga Website
Wants=network-online.target
After=network-online.target
[Service]
Type=simple
User=root
WorkingDirectory=/root/Sc
Environment=PYTHONUNBUFFERED=1
Environment=SC_WEB_HOST=127.0.0.1
Environment=SC_WEB_PORT=1276
Environment=SC_TRUST_LOCAL_PROXY=1
Environment=SC_TLS_CERT=
Environment=SC_TLS_KEY=
ExecStart=/root/Sc/.venv/bin/python3 /root/Sc/miko.py
Restart=always
RestartSec=6
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
SERVICE
systemctl daemon-reload
systemctl enable sc-miko.service caddy.service >/dev/null
systemctl restart sc-miko.service
if ! systemctl reload caddy.service 2>/dev/null; then systemctl restart caddy.service; fi
# Allow web traffic at the OS firewall if iptables is active. Never flush rules.
if command -v iptables >/dev/null 2>&1; then
  for port in 80 443 1276; do
    iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null || iptables -I INPUT 1 -p tcp --dport "$port" -j ACCEPT
  done
  if command -v netfilter-persistent >/dev/null 2>&1; then netfilter-persistent save >/dev/null || true; fi
fi
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q '^Status: active'; then
  for port in 80 443 1276; do ufw allow "$port/tcp" >/dev/null; done
fi
ready=0
for i in $(seq 1 20); do
  if curl -fsS --max-time 2 http://127.0.0.1:1276/api/health >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
if [[ "$ready" != 1 ]]; then
  echo 'Sc backend failed. Check journalctl -u sc-miko -n 50.' >&2
  exit 1
fi
printf 'SC service: '; systemctl is-active sc-miko.service
printf 'Caddy service: '; systemctl is-active caddy.service
printf 'Backend health: '; curl -fsS http://127.0.0.1:1276/api/health; echo
printf 'HTTPS local check: '; curl -sS -o /dev/null -w '%{http_code}\n' --max-time 15 "https://$HOST/" || true
printf 'HTTP IP redirect: '; curl -sS -o /dev/null -w '%{http_code}\n' --max-time 5 "http://$IP:1276/" || true
printf '\nPublic website: https://%s\nIP redirect: http://%s:1276\n' "$HOST" "$IP"
echo 'If phone still cannot connect, run: bash deploy/check_access.sh'
echo 'Provider-level firewall, mobile ISP DNS filtering, and external connectivity cannot be verified from this VPS alone.'
