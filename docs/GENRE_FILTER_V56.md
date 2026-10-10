# MIKO v56 - Complete Genres & Theme Filters

This release expands the v55 multi-select filter without changing authentication,
Telegram publishing, the PDF reader, routing, site design or VPS deployment.

## Genres versus themes

AniList exposes a `GenreCollection` of **18 broad genres** (Action, Adventure,
Comedy, Drama, Ecchi, Fantasy, Horror, Mahou Shoujo, Mecha, Music, Mystery,
Psychological, Romance, Sci-Fi, Slice of Life, Sports, Supernatural and Thriller).
Additional labels such as School Life, Isekai, Josei, Doujinshi, Gender Bender,
Mature, Reincarnation and Yaoi are not all AniList core genres. They are offered
as **themes & other labels**. This distinction is made explicit in the UI.

`sc_core/genre_taxonomy.py` contains an offline vocabulary (the 18 AniList
baseline genres + 77 common community themes). An updated label can also be
read from actual published title metadata, even if it is not in that vocabulary.
**These options do not create tags on books.** Filters will only return a
published title with matching genres/tags, or a Webtoon when filtering by its
publication format. Empty results are normal for topics with no tagged titles.

All labels from the user's reference screenshot are selectable on Home and all
seven category pages. Search, Apply, Clear, 16-choice cap, matching ANY choice
(OR), the 10-item pagination, and recently published sort are preserved.

## Published title metadata

Provider metadata `genres` and `tags` remain separate arrays. AniList tags and
MangaDex genre/theme tags are eligible for verified enrichment of existing
records. The metadata engine will never infer a missing tag from the series
name or a selected filter. Owner-curated metadata still takes precedence.

For older uploaded series whose tags were not previously saved, run an optional
refresh (requires your VPS MongoDB connection and provider access):

```bash
cd /root/Sc && .venv/bin/python3 miko.py metadata-sync --all --force
```

No database migrations or new Python packages required.

## Deploy

Upload the ZIP to `/root/`, then run:

```bash
cd /root && unzip -o Sc-Bot-Website-Genres-v56.zip -d /root && systemctl restart sc-miko.service
```

The ZIP deliberately contains no private config.py, certificates, secrets,
storage files, user records or reader cache. Current data/ and .venv/ remain
on the VPS. Test at /api/genres and on a category page.

References:
- https://docs.anilist.co/guide/graphql/pagination (GenreCollection)
- https://docs.anilist.co/reference/query (genre vs tag querying)
