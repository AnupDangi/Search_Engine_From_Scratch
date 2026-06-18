# search/query_understanding.py

import re

_PDF_KEYWORDS = frozenset([
    "pdf", "paper", "research", "thesis", "arxiv", "survey",
    "notes", "handbook", "textbook", "lecture", "slides", "ebook",
    "whitepaper", "documentation", "spec", "rfc",
])

_IMAGE_KEYWORDS = frozenset([
    "image", "photo", "picture", "diagram", "chart", "graph",
    "screenshot", "logo", "icon", "illustration", "poster",
    "architecture", "flowchart", "wallpaper",
])

_EDUCATIONAL_KEYWORDS = frozenset([
    "tutorial", "course", "learn", "guide", "how to", "howto",
    "introduction", "beginner", "example", "exercise", "practice",
    "notes", "lecture", "syllabus", "curriculum",
])

_MOVIE_KEYWORDS = frozenset([
    "movie", "film", "cinema", "hindi", "bollywood", "hollywood",
    "actor", "actress", "director", "cast", "plot", "trailer",
    "review", "rating", "sequel", "prequel", "watch", "streaming",
    "netflix", "amazon prime", "hotstar", "ott",
])

_NEWS_KEYWORDS = frozenset([
    "news", "latest", "today", "breaking", "report", "update",
    "current", "2024", "2025", "2026",
])

# Domain hints: keyword -> domain fragment to boost
_DOMAIN_HINTS: dict[str, str] = {
    "github": "github.com",
    "stackoverflow": "stackoverflow.com",
    "arxiv": "arxiv.org",
    "wikipedia": "wikipedia.org",
    "imdb": "imdb.com",
    "tmdb": "themoviedb.org",
    "youtube": "youtube.com",
    "pypi": "pypi.org",
    "npm": "npmjs.com",
    "docker": "hub.docker.com",
    "huggingface": "huggingface.co",
    "kaggle": "kaggle.com",
    "mdn": "developer.mozilla.org",
}


class QueryUnderstanding:

    def detect_intent(self, query: str) -> dict:
        q_lower = query.lower()
        tokens = set(re.findall(r"[a-z0-9]+", q_lower))

        doc_type_preference = None
        domain_boost = None
        educational = False
        movie_intent = False

        if tokens & _PDF_KEYWORDS:
            doc_type_preference = "PDF"
        elif tokens & _IMAGE_KEYWORDS:
            doc_type_preference = "IMAGE"

        if tokens & _EDUCATIONAL_KEYWORDS:
            educational = True

        if tokens & _MOVIE_KEYWORDS:
            movie_intent = True
            # Boost imdb and tmdb for movie queries
            if "imdb" not in tokens and "tmdb" not in tokens:
                domain_boost = "imdb.com"

        for hint, domain in _DOMAIN_HINTS.items():
            if hint in tokens:
                domain_boost = domain
                break

        return {
            "doc_type_preference": doc_type_preference,
            "domain_boost": domain_boost,
            "educational": educational,
            "movie_intent": movie_intent,
        }

    # Alias for compatibility with code that calls analyze()
    analyze = detect_intent
