# MIKO Manga Website — Genre Filters (v55)

The collection now lets readers select multiple genres on **Home** and on each
format's category page: Manga, Manhwa, Manhua, Webtoon, 18+ Manga, 18+ Manhwa,
and 18+ Webtoon. The selection persists while navigating between catalog
categories and can be cleared at any time.

## Selection behavior

1. Open the **Genres** control above the story cards.
2. Search for genres or select several checkboxes.
3. Press **Apply Filters** to update the list and total/pagination.
4. Any chosen genre can match (**OR**): selecting *Psychological* and *Action*
   returns all titles with either tag; it does not require both.
5. Use **Clear** or **Clear All** to see unfiltered titles again.

The interface shows up to three real genre tags on each title card. It does
not invent tags for titles without metadata. The genre list is populated
from genres on **published** MongoDB titles with at least one chapter.
Tags such as *School Life* appear when they are present on any eligible title.
Use the existing `metadata-sync` command to fill in missing metadata when
a verified source provides it; otherwise approved manual metadata can be set
using existing owner tools.

## API

- `GET /api/genres` — available genres across categories.
- `GET /api/genres?category=manhwa` — genres on published Manhwa titles.
- `GET /api/catalog?category=manhwa&genre=Psychological&genre=Action&page=1`
  — OR-filtered results, sorted by most recent update, paginated by 10.

Genre values are normalized, escaped for safe case-insensitive exact
MongoDB comparisons, capped at 16 selections and are never interpolated into
regex patterns unescaped. Partial category outages still show any available
results. No database schema migration or new dependencies are needed.

## Deployment

After placing the v55 ZIP in `/root`, run:

```sh
cd /root && unzip -o Sc-Bot-Website-Genre-Filters-v55.zip -d /root && cd /root/Sc && systemctl restart sc-miko.service
```

User accounts, MongoDB connection settings, Telegram storage, reader cache,
PDF handling, systemd and Caddy settings are untouched by this update.
