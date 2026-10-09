# MIKO Manga Universe — Website UI Prototype

A responsive, premium dark-theme manga/manhwa/webtoon website **frontend prototype**. This is a working static UI demo, not a live content-hosting service.

## Included
- Responsive landing page and original CSS cover art
- Manga / Manhwa / Webtoon / 18+ category filters
- Search, chapter-list dialogs, demo vertical reader
- Admin dashboard *UI mock* with non-secret preferences stored in browser localStorage
- Mobile navigation, keyboard-accessible cards, closeable dialogs

All manga names and covers in the demo are fictional placeholders. No third-party chapter images or PDFs are bundled.

## Run locally / on VPS

```bash
cd Miko-Manga-Web && python3 -m http.server 8080 --bind 0.0.0.0
```

Open `http://YOUR_SERVER_IP:8080` in your browser. For public deployment, put the site behind HTTPS and a reverse proxy; avoid exposing the development server to the internet.

## Next development phase (not implemented)
- FastAPI authenticated backend and role-based admin access
- MongoDB manga/chapter collections and unique indexes
- Sc bot uploads authorized PDFs to a private Telegram channel; save channel ID, message ID, file ID and metadata
- Secure Telegram retrieval service with server-side caching and PDF.js reader
- Chapter publishing workflows, metadata management and production-grade error handling

**Security:** Never put Telegram bot tokens, API hashes or MongoDB passwords in frontend JS, HTML or localStorage. Store credentials server-side in environment variables. Admin dashboard in this demo is not access-controlled and must not be used for production operations.

**Rights:** Only host manga and other content you have permission to publish.
