# search/retriever.py

from collections import defaultdict


class Retriever:

    def __init__(self, index_reader):
        self.index_reader = index_reader

    def retrieve(self, query_terms):

        candidates = defaultdict(
            lambda: {
                "matched_terms": 0,
                "term_frequencies": {},
                "positions": {}
            }
        )

        for term in query_terms:
            postings = self.index_reader.get_postings(term)

            for doc_id, fields_positions in postings.items():
                candidates[doc_id]["matched_terms"] += 1
                # tf is the total count of times the term occurs across all fields in this document
                tf = sum(len(pos_list) for pos_list in fields_positions.values())
                candidates[doc_id]["term_frequencies"][term] = tf
                candidates[doc_id]["positions"][term] = fields_positions

        # For 3+ term queries require at least half terms to match, improving precision.
        # Fall back to 1 for short queries; if strict threshold filters everything, relax.
        threshold = max(1, len(query_terms) // 2) if len(query_terms) >= 3 else 1

        filtered_candidates = {
            doc_id: info
            for doc_id, info in candidates.items()
            if info["matched_terms"] >= threshold
        }

        if not filtered_candidates:
            filtered_candidates = {
                doc_id: info
                for doc_id, info in candidates.items()
                if info["matched_terms"] >= 1
            }

        return filtered_candidates