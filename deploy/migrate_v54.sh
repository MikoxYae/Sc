#!/usr/bin/env bash
# v54 layout migration: remove ONLY retired root-level source copies.
# Preserves config.py, .venv/, data/, MongoDB, Caddy, and other VPS services.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f miko.py || ! -f sc_core/bot.py || ! -f sc_core/website_server.py || ! -f sc_core/scraper.py ]]; then
    echo 'Missing files in sc_core/: extraction may be incomplete. Aborting.' >&2
    exit 1
fi

# Verify new layout works before removing the old Python files.
PYTHON="$PWD/.venv/bin/python3"
if [[ ! -x "$PYTHON" ]]; then
    echo 'Missing .venv/bin/python3; install requirements before migration.' >&2
    exit 1
fi
"$PYTHON" -m compileall -q miko.py sc_core
# Existing root files are retired below; run layout regression after cleanup.

old=(
    Miko.py sc.py semico.py config.example.py
    adult_access.py catalog_db.py catalog_metadata.py chapter_reader.py
    cover_proxy.py metadata_engine.py metadata_override.py metadata_sync.py
    owner_setup.py publication_check.py publish_recovery.py reader_prefetch.py
    site_adapters.py storage_sync.py web_auth.py website_server.py
    README_WEBSITE.md 'to commit."'
)

# Keep a dated backup outside the Git repo in case manual rollback is needed.
backup_files=()
for file in "${old[@]}"; do
    [[ -f "$file" ]] && backup_files+=("$file")
done
if ((${#backup_files[@]})); then
    backup_dir="${SC_MIGRATE_BACKUP_DIR:-/root}"
    mkdir -p "$backup_dir"
    backup="$backup_dir/Sc-root-before-v54-$(date +%Y%m%d-%H%M%S).tar.gz"
    tar -czf "$backup" -- "${backup_files[@]}"
    chmod 600 "$backup"
    echo "Legacy root files backed up: $backup"
    rm -f -- "${backup_files[@]}"
fi

"$PYTHON" -m unittest discover -s tests -p 'test_project_structure_v54.py' -q
echo 'Organized Sc root now contains a single launcher: miko.py'
echo 'Core Python modules are in sc_core/.'
if [[ "${SC_MIGRATE_NO_RESTART:-0}" == 1 ]]; then
    echo 'Dry run: skipped service restart.'
elif systemctl list-unit-files sc-miko.service --no-legend 2>/dev/null | grep -q 'sc-miko.service'; then
    systemctl restart sc-miko.service
    ready=0
    for _ in $(seq 1 20); do
        if curl -fsS --max-time 2 http://127.0.0.1:1276/api/health >/dev/null 2>&1; then
            ready=1
            break
        fi
        sleep 2
    done
    if [[ "$ready" != 1 ]]; then
        echo 'Sc service did not become healthy. See: journalctl -u sc-miko -n 60 --no-pager' >&2
        exit 1
    fi
    echo 'sc-miko.service: active; website HTTP health: 200'
else
    echo 'No sc-miko.service found. Start with: python3 miko.py (from an activated venv)'
fi
