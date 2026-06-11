# search/query_understanding.py


_PDF_KEYWORDS = {
    "pdf", "paper", "research", "survey", "thesis", "preprint", "publication", "arxiv",
    "notes", "guide", "handbook", "tutorial", "textbook", "lecture", "slides", "whitepaper",
    "ebook", "report", "documentation", "manual",
}
_IMAGE_KEYWORDS = {"image", "photo", "logo", "diagram", "picture", "icon", "screenshot", "photo", "img", "figure"}
_DOMAIN_HINTS = {
    "github": "github.com",
    "arxiv": "arxiv.org",
    "wikipedia": "wikipedia.org",
    "stackoverflow": "stackoverflow.com",
    "reddit": "reddit.com",
    "youtube": "youtube.com",
}


class QueryUnderstanding:

    def detect_intent(self, query: str) -> dict:
        tokens = set(query.lower().split())

        doc_type = None
        if tokens & _PDF_KEYWORDS:
            doc_type = "PDF"
        elif tokens & _IMAGE_KEYWORDS:
            doc_type = "IMAGE"

        domain_boost = None
        for kw, domain in _DOMAIN_HINTS.items():
            if kw in tokens:
                domain_boost = domain
                break

        return {
            "doc_type_preference": doc_type,
            "domain_boost": domain_boost,
        }
