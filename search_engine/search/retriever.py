# search/retriever.py

from collections import defaultdict


class Retriever:

    def __init__(self, index_reader):
        self.index_reader = index_reader

    def retrieve(self, query_terms):

        candidates = defaultdict(
            lambda: {
                "matched_terms": 0,
                "term_frequencies": {}
            }
        )

        for term in query_terms:
            postings = self.index_reader.get_postings(term)

            for doc_id, tf in postings.items():
                candidates[doc_id]["matched_terms"] += 1
                candidates[doc_id]["term_frequencies"][term] = tf

        # --- THE FIX: MINIMUM MATCH THRESHOLD ---
        # Filter out documents that only match noise words.
        # For example, require at least 50% of query terms to match.
        
        filtered_candidates = {}
        threshold = max(1, len(query_terms) // 2) 

        for doc_id, info in candidates.items():
            if info["matched_terms"] >= threshold:
                filtered_candidates[doc_id] = info

        return filtered_candidates