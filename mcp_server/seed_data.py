"""Offline catalogue for seed_watchlist_items(source="mock").

Real titles with hand-checked runtimes and genres so the seeder — and the watch
time / genre aggregations in get_watchlist_stats — work without a TMDB key.

runtime_minutes for a series is the whole run (episodes x episode length), which
is what "total watch time" means for a watchlist.
"""

PLATFORMS = ["Netflix", "HBO Max", "Disney+", "Prime Video", "Apple TV+", "Hulu"]

CATALOG = [
    # --- Movies ---
    {"title": "Avengers: Infinity War", "media_type": "movie", "year": 2018, "runtime_minutes": 149,
     "genres": ["Action", "Adventure", "Science Fiction"], "platform": "Disney+"},
    {"title": "The Dark Knight", "media_type": "movie", "year": 2008, "runtime_minutes": 152,
     "genres": ["Action", "Crime", "Drama"], "platform": "HBO Max"},
    {"title": "Parasite", "media_type": "movie", "year": 2019, "runtime_minutes": 133,
     "genres": ["Comedy", "Thriller", "Drama"], "platform": "Hulu"},
    {"title": "Dune: Part Two", "media_type": "movie", "year": 2024, "runtime_minutes": 167,
     "genres": ["Science Fiction", "Adventure"], "platform": "HBO Max"},
    {"title": "Everything Everywhere All at Once", "media_type": "movie", "year": 2022, "runtime_minutes": 139,
     "genres": ["Action", "Adventure", "Science Fiction"], "platform": "Prime Video"},
    {"title": "Spirited Away", "media_type": "movie", "year": 2001, "runtime_minutes": 125,
     "genres": ["Animation", "Family", "Fantasy"], "platform": "Netflix"},
    {"title": "Blade Runner 2049", "media_type": "movie", "year": 2017, "runtime_minutes": 164,
     "genres": ["Science Fiction", "Drama"], "platform": "Prime Video"},
    {"title": "Whiplash", "media_type": "movie", "year": 2014, "runtime_minutes": 106,
     "genres": ["Drama", "Music"], "platform": "Netflix"},
    {"title": "Mad Max: Fury Road", "media_type": "movie", "year": 2015, "runtime_minutes": 120,
     "genres": ["Action", "Adventure", "Science Fiction"], "platform": "HBO Max"},
    {"title": "Knives Out", "media_type": "movie", "year": 2019, "runtime_minutes": 130,
     "genres": ["Comedy", "Crime", "Mystery"], "platform": "Prime Video"},
    {"title": "Oppenheimer", "media_type": "movie", "year": 2023, "runtime_minutes": 181,
     "genres": ["Drama", "History"], "platform": "Prime Video"},
    {"title": "Arrival", "media_type": "movie", "year": 2016, "runtime_minutes": 116,
     "genres": ["Science Fiction", "Drama", "Mystery"], "platform": "Hulu"},

    # --- Series (runtime_minutes = full run) ---
    {"title": "Peaky Blinders", "media_type": "tv", "year": 2013, "runtime_minutes": 1680,
     "genres": ["Drama", "Crime"], "platform": "Netflix"},
    {"title": "Breaking Bad", "media_type": "tv", "year": 2008, "runtime_minutes": 3050,
     "genres": ["Drama", "Crime"], "platform": "Netflix"},
    {"title": "The Bear", "media_type": "tv", "year": 2022, "runtime_minutes": 1050,
     "genres": ["Drama", "Comedy"], "platform": "Hulu"},
    {"title": "Severance", "media_type": "tv", "year": 2022, "runtime_minutes": 1140,
     "genres": ["Drama", "Mystery", "Science Fiction"], "platform": "Apple TV+"},
    {"title": "Chernobyl", "media_type": "tv", "year": 2019, "runtime_minutes": 330,
     "genres": ["Drama", "History"], "platform": "HBO Max"},
    {"title": "Arcane", "media_type": "tv", "year": 2021, "runtime_minutes": 810,
     "genres": ["Animation", "Action", "Fantasy"], "platform": "Netflix"},
    {"title": "The Last of Us", "media_type": "tv", "year": 2023, "runtime_minutes": 560,
     "genres": ["Drama", "Science Fiction"], "platform": "HBO Max"},
    {"title": "Andor", "media_type": "tv", "year": 2022, "runtime_minutes": 570,
     "genres": ["Science Fiction", "Adventure", "Drama"], "platform": "Disney+"},
    {"title": "Succession", "media_type": "tv", "year": 2018, "runtime_minutes": 2400,
     "genres": ["Drama"], "platform": "HBO Max"},
    {"title": "Dark", "media_type": "tv", "year": 2017, "runtime_minutes": 1560,
     "genres": ["Drama", "Mystery", "Science Fiction"], "platform": "Netflix"},
]
