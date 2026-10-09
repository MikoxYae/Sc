#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "Deployment failed at line $LINENO. Existing files were not deleted. Check systemctl status sc-miko caddy." >&2' ERR
[[ $(id -u) -eq 0 ]] || { echo 'Run as root.'; exit 1; }
cd /root/Sc
[[ -x .venv/bin/python3 ]] || { echo 'Existing /root/Sc/.venv is missing.'; exit 1; }
[[ -f config.py ]] || { echo 'Private config.py is missing. Restore your existing VPS configuration.'; exit 1; }
.venv/bin/python3 -m py_compile miko.py Miko.py website_server.py
# Discover public IPv4; allow explicit override when the discovery endpoint is unavailable.
IP="${SC_PUBLIC_IP:-$(curl -4fsS --connect-timeout 5 --max-time 12 https://api.ipify.org)}"
[[ "$IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || { echo 'Could not determine public IPv4. Export SC_PUBLIC_IP.'; exit 1; }
HOST="${SC_DOMAIN:-${IP}.sslip.io}"
[[ "$HOST" =~ ^[A-Za-z0-9.-]+$ ]] || { echo 'Invalid hostname.'; exit 1; }
if ! getent ahostsv4 "$HOST" | awk '{print $1}' | grep -Fxq "$IP"; then
  echo "DNS mismatch: $HOST must resolve to $IP"; exit 1
fi
# Never steal ports belonging to other projects or unknown manual processes.
for port in 80 443 1980 1982; do
  owners="$(ss -H -ltnp "sport = :$port" || true)"
  [[ -z "$owners" ]] && continue
  if [[ "$port" == 80 || "$port" == 443 || "$port" == 1980 ]]; then
    if systemctl is-active --quiet caddy && [[ -f /etc/caddy/Caddyfile ]] && grep -q '^# SC-MIKO-MANAGED$' /etc/caddy/Caddyfile; then
      continue
    fi
  fi
  if [[ "$port" == 1982 ]] && systemctl is-active --quiet sc-miko.service; then continue; fi
  echo "Port $port already has a listener. Refusing to interrupt an unknown process:"; echo "$owners"; exit 1
done
if [[ -s /etc/caddy/Caddyfile ]] && ! grep -q '^# SC-MIKO-MANAGED$' /etc/caddy/Caddyfile; then
  echo 'Existing unrelated Caddy configuration found. Refusing to overwrite it.'; exit 1
fi
if ! command -v caddy >/dev/null; then
  echo 'Installing Caddy once (no Python dependency reinstall).'
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y caddy
fi
mkdir -p /etc/caddy
if [[ -f /etc/caddy/Caddyfile ]]; then cp -a /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.sc-backup.$(date +%Y%m%d%H%M%S)"; fi
cat > /etc/caddy/Caddyfile <<CADDY
# SC-MIKO-MANAGED
$HOST {
    encode zstd gzip
    reverse_proxy 127.0.0.1:1982
}
http://:1980 {
    redir https://$HOST{uri} 308
}
CADDY
caddy fmt --overwrite /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile
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
Environment=SC_WEB_PORT=1982
Environment=SC_TRUST_LOCAL_PROXY=1
Environment=SC_TLS_CERT=
Environment=SC_TLS_KEY=
ExecStart=/root/Sc/.venv/bin/python3 /root/Sc/miko.py
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
SERVICE
systemctl daemon-reload
systemctl enable sc-miko.service caddy.service
systemctl restart sc-miko.service
systemctl restart caddy.service
sleep 3
# Fail visibly when services or the local website are not healthy.
for unit in sc-miko.service caddy.service; do
  if ! systemctl is-active --quiet "$unit"; then
    echo "ERROR: $unit failed to start. Recent logs:" >&2
    journalctl -u "$unit" -n 25 --no-pager | sed -E 's#(bot[0-9]+:)[^/ ]+#\1[REDACTED]#g' >&2
    exit 1
  fi
done
if ! curl -fsS --max-time 10 http://127.0.0.1:1982/ -o /dev/null; then
  echo 'ERROR: website backend did not return HTTP 2xx.' >&2
  journalctl -u sc-miko.service -n 25 --no-pager | sed -E 's#(bot[0-9]+:)[^/ ]+#\1[REDACTED]#g' >&2
  exit 1
fi
printf '\nSC service: '; systemctl is-active sc-miko.service
printf 'Caddy service: '; systemctl is-active caddy.service
printf 'Local backend HTTP status: '; curl -s -o /dev/null -w '%{http_code}\n' --max-time 8 http://127.0.0.1:1982/ || true
printf '\nWebsite: https://%s\nHTTP redirect: http://%s:1980\n' "$HOST" "$IP"
echo 'Trusted TLS requires public inbound TCP 80 and 443 and working DNS.'
echo 'Check: journalctl -u sc-miko -u caddy -n 30 --no-pager'

# HTTPS validation may take longer while Caddy obtains a certificate.
echo 'HTTPS check (certificate provisioning may still be in progress):'
if curl --silent --show-error --fail --max-time 20 "https://$HOST/" -o /dev/null; then
  echo 'HTTPS: verified from this VPS.'
else
  echo 'HTTPS not yet verified. Check inbound 80/443, DNS, and Caddy certificate logs.'
  echo 'Run: journalctl -u caddy -n 50 --no-pager'
fi
echo 'Firewall note: ensure your VPS provider firewall allows inbound TCP 80 and 443.'
