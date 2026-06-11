# indexing/preprocessor.py

import re
import unicodedata

from collections import Counter
from nltk.corpus import stopwords
from nltk.stem.snowball import SnowballStemmer

FALLBACK_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for",
        "from", "has", "in", "is", "it", "of", "on", "or", "that",
        "the", "to", "was", "were", "will", "with"
    }
)

try:
    STOPWORDS = frozenset(stopwords.words("english"))
except LookupError:
    STOPWORDS = FALLBACK_STOPWORDS

# Compile once
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class TextPreprocessor:
    """
    Search Engine NLP Pipeline

    Unicode Normalization
    ↓
    Lowercase
    ↓
    Tokenization
    ↓
    Stopword Removal
    ↓
    Snowball Stemming
    ↓
    Term Statistics
    """

    __slots__ = ("stemmer",)

    def __init__(self):
        self.stemmer = SnowballStemmer("english")

    def process(self, text: str) -> list[str]:
        """
        Returns processed tokens.
        """

        # Unicode normalization
        text = unicodedata.normalize("NFKC", text)

        # Lowercase
        text = text.lower()

        # Tokenize
        raw_tokens = TOKEN_PATTERN.findall(text)

        # Stopword removal + stemming in one pass
        tokens = [
            self.stemmer.stem(token)
            for token in raw_tokens
            if token not in STOPWORDS
        ]

        return tokens

    ## converts to token and return the term frequency, document length and unique terms in the document
    def analyze_document(self, text: str) -> dict:
        """
        Returns everything needed by the indexer.

        {
            tokens,
            term_freq,
            doc_length,
            unique_terms
        }
        """

        tokens = self.process(text)

        term_freq = Counter(tokens)

        return {
            "tokens": tokens,
            "term_freq": term_freq,
            "doc_length": len(tokens),
            "unique_terms": len(term_freq)
        }

    def term_frequencies(self, text: str) -> Counter:
        """
        Convenience method.
        """

        return Counter(self.process(text))

# p = TextPreprocessor()

# result = p.analyze_document(
#     """
#     Python functions are running faster.
#     Functions run every day.
#     """
# )

# print(result)
