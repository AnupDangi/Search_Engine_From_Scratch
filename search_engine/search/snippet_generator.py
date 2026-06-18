# search/snippet_generator.py

import html
import re

from nltk.stem.snowball import SnowballStemmer


TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
WINDOW_CHARS = 200


class SnippetGenerator:

    def __init__(self):
        self.stemmer = SnowballStemmer("english")

    def generate(
        self,
        content: str,
        query: str,
        query_terms: list[str]
    ) -> str:

        if not content:
            return ""

        words = re.findall(r"\S+", content)
        if not words:
            return ""

        raw_query_terms = {t.lower() for t in TOKEN_PATTERN.findall(query)}
        processed_query_terms = set(query_terms)

        best_start, best_end = self._best_window(
            words, raw_query_terms, processed_query_terms
        )

        snippet_words = [
            self._format_word(w, raw_query_terms, processed_query_terms)
            for w in words[best_start:best_end]
        ]

        prefix = "... " if best_start > 0 else ""
        suffix = " ..." if best_end < len(words) else ""

        return prefix + " ".join(snippet_words) + suffix

    def _best_window(self, words, raw_terms, processed_terms):
        """Return (start, end) indices of the 200-char window with max unique query term hits."""
        n = len(words)
        best_start, best_end, best_score = 0, min(n, 40), -1

        start_idx = min(50, n // 4)  # skip likely nav area, but not for short docs
        scan_end = min(n, start_idx + 500)  # cap scan for performance

        for i in range(start_idx, scan_end):
            # Grow window from position i until char budget exceeded
            char_count = 0
            j = i
            while j < n:
                char_count += len(words[j]) + 1
                if char_count > WINDOW_CHARS and j > i:
                    break
                j += 1

            # Score = number of unique stemmed query terms present in this window
            matched = set()
            for w in words[i:j]:
                for token in TOKEN_PATTERN.findall(w):
                    t = token.lower()
                    stemmed = self.stemmer.stem(t)
                    if t in raw_terms or stemmed in processed_terms:
                        matched.add(stemmed)

            score = len(matched)
            if score > best_score:
                best_score = score
                best_start = i
                best_end = j

            # Early exit once all terms matched
            if score == len(processed_terms):
                break

        # Fallback: if nothing matched after skip, scan from beginning
        if best_score <= 0 and start_idx > 0:
            for i in range(min(start_idx, n)):
                # Grow window from position i until char budget exceeded
                char_count = 0
                j = i
                while j < n:
                    char_count += len(words[j]) + 1
                    if char_count > WINDOW_CHARS and j > i:
                        break
                    j += 1

                # Score = number of unique stemmed query terms present in this window
                matched = set()
                for w in words[i:j]:
                    for token in TOKEN_PATTERN.findall(w):
                        t = token.lower()
                        stemmed = self.stemmer.stem(t)
                        if t in raw_terms or stemmed in processed_terms:
                            matched.add(stemmed)

                score = len(matched)
                if score > best_score:
                    best_score = score
                    best_start = i
                    best_end = j

                # Early exit once all terms matched
                if score == len(processed_terms):
                    break

        return best_start, best_end

    def _format_word(self, word, raw_query_terms, processed_query_terms):
        escaped = html.escape(word)
        if self._matches(word, raw_query_terms, processed_query_terms):
            return f"<mark>{escaped}</mark>"
        return escaped

    def _matches(self, word, raw_query_terms, processed_query_terms):
        for token in TOKEN_PATTERN.findall(word):
            t = token.lower()
            if t in raw_query_terms or self.stemmer.stem(t) in processed_query_terms:
                return True
        return False
