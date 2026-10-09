# Sc v41 - Mobile full-width reader

This patch fixes the narrow left-aligned manga reader on phones. Only the reader route uses the full-width layout; catalog, bot, Telegram storage, MongoDB, and VPS ports remain unchanged.

- Reader images occupy the full mobile viewport width, retaining original aspect ratio.
- Reader toolbar is responsive and remains sticky.
- The catalog header/footer are hidden only while reading on mobile.
- CSS and JS asset versions are bumped to 41 to avoid old browser cache.

Deploy by extracting over /root/Sc and restarting the existing sc-miko systemd service. Do not recreate the venv or reinstall requirements.

Verify: open a chapter on mobile, ensure the image and toolbar span the screen, scroll through multiple pages, and navigate back to chapters. Test desktop and catalog too.
