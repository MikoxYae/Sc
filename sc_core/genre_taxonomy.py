"""Browsable genre vocabulary for MIKO (never assigned to titles automatically).

AniList's GenreCollection contains broad media genres.  Many community manga
labels (School Life, Isekai, Josei, etc.) are *tags/themes* rather than AniList
core genres. Keep them separate internally while making both searchable.
The metadata saved for an individual work remains its actual verified genres/tags.
"""
from __future__ import annotations

# Baseline from AniList's documented GenreCollection.  AniList can change these;
# the published-series labels from MongoDB are also merged at runtime.
ANILIST_GENRES = (
    'Action', 'Adventure', 'Comedy', 'Drama', 'Ecchi', 'Fantasy', 'Horror',
    'Mahou Shoujo', 'Mecha', 'Music', 'Mystery', 'Psychological', 'Romance',
    'Sci-Fi', 'Slice of Life', 'Sports', 'Supernatural', 'Thriller',
)

# Screenshot labels + common manga/manhwa/manhua/webtoon tags and demographics.
# These are selectable filters, NOT fabricated metadata on individual titles.
OTHER_LABELS = (
    'Adult', 'Age Gap', 'Aliens', 'Apocalypse', 'Arts', 'Boys Love',
    'Business', 'College', 'Cooking', 'Crime', 'Cultivation', 'Cyberpunk',
    'Demons', 'Detective', 'Doujinshi', 'Dragons', 'Dystopia', 'Education', 'Erotica',
    'Family', 'Full Color', 'Game', 'Gender Bender', 'Girls Love', 'Gore',
    'Harem', 'Hentai', 'Historical', 'Isekai', 'Josei', 'Magic', 'Martial Arts',
    'Mature', 'Medical', 'Military', 'Monster Girls', 'Monsters',
    'Mythology', 'Office Workers', 'Parody', 'Philosophy', 'Police',
    'Politics', 'Post-Apocalyptic', 'Reincarnation', 'Revenge',
    'Reverse Harem', 'Robots', 'Royalty', 'Samurai', 'School Life',
    'Seinen', 'Shoujo', 'Shoujo Ai', 'Shounen', 'Shounen Ai', 'Smut',
    'Space', 'Super Power', 'Survival', 'Suspense', 'Swordplay',
    'System', 'Time Travel', 'Tragedy', 'Vampires', 'Video Games',
    'Villainess', 'Virtual Reality', 'War', 'Webtoon', 'Wuxia',
    'Xianxia', 'Xuanhuan', 'Yaoi', 'Yuri', 'Zombies',
)

# Only near-equivalent spelling/display labels. Avoid collapsing related but
# distinct demographics or content ratings (e.g. Yaoi != Shounen Ai).
ALIASES = {
    'School Life': ('School', 'School Life', 'School Setting'),
    'Gender Bender': ('Gender Bender', 'Gender Bending'),
    'Sci-Fi': ('Sci-Fi', 'SciFi', 'Science Fiction', 'Science-Fiction'),
    'Full Color': ('Full Color', 'Full Colour', 'Full-Color', 'Full-Colour'),
    'Post-Apocalyptic': ('Post-Apocalyptic', 'Post Apocalyptic', 'PostApocalyptic'),
    'Boys Love': ('Boys Love', 'BL'),
    'Girls Love': ('Girls Love', 'GL'),
    'Mahou Shoujo': ('Mahou Shoujo', 'Magical Girl', 'Magical Girls'),
    'Time Travel': ('Time Travel', 'Time-Travel'),
    'Super Power': ('Super Power', 'Superpowers', 'Super Powers'),
    'Vampires': ('Vampires', 'Vampire'),
    'Zombies': ('Zombies', 'Zombie'),
    'Office Workers': ('Office Workers', 'Workplace', 'Office Life'),
    'Virtual Reality': ('Virtual Reality', 'VR'),
    'Doujinshi': ('Doujinshi', 'Doujin'),
    'Webtoon': ('Webtoon', 'Webtoons'),
}


def vocabulary():
    """Return canonical, predictable options even if no titles exist yet."""
    return sorted(set(ANILIST_GENRES) | set(OTHER_LABELS), key=str.casefold)


def alternatives(label):
    """Safe, literal full-value matching synonyms (no substring matches)."""
    return ALIASES.get(label, (label,))


def canonical(label):
    if not isinstance(label, str):
        return ''
    text = ' '.join(label.split()).casefold()
    for main, synonyms in ALIASES.items():
        if any(text == s.casefold() for s in synonyms):
            return main
    for main in vocabulary():
        if text == main.casefold():
            return main
    return ' '.join(label.split())


def is_anilist_genre(label):
    return canonical(label) in ANILIST_GENRES
