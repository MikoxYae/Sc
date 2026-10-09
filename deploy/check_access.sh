#!/usr/bin/env bash
set -u
HOST="${SC_DOMAIN:-159.195.245.129.sslip.io}"
echo '== SERVICES =='
systemctl is-active sc-miko caddy || true
echo '== LISTENERS =='
ss -ltnp | grep -E ':(80|443|1276)\b' || true
echo '== LOCAL BACKEND =='
curl -sS --max-time 6 -o /dev/null -w '1276 backend: %{http_code}\n' http://127.0.0.1:1276/api/health || true
echo '== HTTPS FROM VPS =='
curl -sS --max-time 12 -o /dev/null -w 'HTTPS: %{http_code}; remote IP: %{remote_ip}\n' "https://$HOST/" || true
echo '== DNS =='
getent ahostsv4 "$HOST" | head -3 || true
echo '== FIREWALL =='
if command -v ufw >/dev/null; then ufw status | head -15; fi
if command -v iptables >/dev/null; then iptables -S INPUT | grep -E 'dport (80|443|1276)' || true; fi
echo '== SERVICE RESTARTS =='
systemctl show sc-miko -p NRestarts -p Result -p MainPID || true
echo 'If all local checks pass but phone fails, test mobile data versus Wi-Fi and provider firewall. Do not share tokens in logs.'
