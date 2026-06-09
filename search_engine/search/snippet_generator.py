# search/snippet_generator.py

import html
import re

from nltk.stem import PorterStemmer


TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


class SnippetGenerator:

    def __init__(
        self,
        max_words: int = 32
    ):

        self.max_words = max_words
        self.stemmer = PorterStemmer()

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

        raw_query_terms = {
            term.lower()
            for term in TOKEN_PATTERN.findall(query)
        }

        processed_query_terms = set(query_terms)

        match_index = self._find_first_match(
            words,
            raw_query_terms,
            processed_query_terms
        )

        if match_index is None:
            match_index = 0

        start = max(0, match_index - self.max_words // 2)
        end = min(len(words), start + self.max_words)
        start = max(0, end - self.max_words)

        snippet_words = [
            self._format_word(
                word,
                raw_query_terms,
                processed_query_terms
            )
            for word in words[start:end]
        ]

        prefix = "... " if start > 0 else ""
        suffix = " ..." if end < len(words) else ""

        return (
            prefix
            + " ".join(snippet_words)
            + suffix
        )

    def _find_first_match(
        self,
        words,
        raw_query_terms,
        processed_query_terms
    ):

        for index, word in enumerate(words):

            if self._matches(
                word,
                raw_query_terms,
                processed_query_terms
            ):
                return index

        return None

    def _format_word(
        self,
        word,
        raw_query_terms,
        processed_query_terms
    ):

        escaped_word = html.escape(word)

        if self._matches(
            word,
            raw_query_terms,
            processed_query_terms
        ):
            return f"<mark>{escaped_word}</mark>"

        return escaped_word

    def _matches(
        self,
        word,
        raw_query_terms,
        processed_query_terms
    ):

        tokens = TOKEN_PATTERN.findall(word)

        for token in tokens:

            normalized_token = token.lower()
            stemmed_token = self.stemmer.stem(
                normalized_token
            )

            if (
                normalized_token in raw_query_terms
                or stemmed_token in processed_query_terms
            ):
                return True

        return False
