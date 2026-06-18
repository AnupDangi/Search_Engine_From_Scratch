# search/bm25_ranker.py

import math


class BM25Ranker:

    def __init__(
        self,
        index_reader,
        k1=1.5,
        weights=None,
        b_map=None
    ):
        self.index_reader = index_reader
        self.k1 = k1

        # Field weights for BM25F
        self.weights = weights or {
            "heading": 6.0,
            "title": 4.0,
            "content": 1.0,
            "url": 2.0,
            "author": 2.0,
        }
        self.b_map = b_map or {
            "heading": 0.3,
            "title": 0.5,
            "content": 0.75,
            "url": 0.5,
            "author": 0.5,
        }

        self.corpus_stats = self.index_reader.get_corpus_stats()

    def score(self, query_terms, candidates, strict_phrases=None):
        """
        Returns dict: doc_id -> (bm25f_score, phrase_proximity_score)

        bm25f_score        — BM25F across all fields (no phrase modification)
        phrase_proximity_score — phrase match count + distance-decay proximity sum
        """
        N = self.corpus_stats.get("num_docs", 0)
        if N == 0:
            return {}

        avg_lens = {}
        for field in self.weights.keys():
            avg_lens[field] = self.corpus_stats.get(f"avg_{field}_length", 0.0)

        results = {}

        for doc_id, info in candidates.items():
            doc_stats = self.index_reader.get_doc_stats(doc_id)
            if not doc_stats:
                continue

            # ── BM25F ──────────────────────────────────────────────────────
            bm25f = 0.0
            for term in query_terms:
                df = self.index_reader.get_df(term)
                if df == 0:
                    continue

                idf = math.log((N - df + 0.5) / (df + 0.5) + 1.0)

                tf_weighted = 0.0
                term_positions = info["positions"].get(term, {})

                for field, weight in self.weights.items():
                    tf_f = len(term_positions.get(field, []))
                    if tf_f == 0:
                        continue

                    len_f = doc_stats.get(f"{field}_length", 0)
                    avg_len_f = avg_lens.get(field, 0.0)
                    if avg_len_f < 0.5:  # field is essentially empty corpus-wide
                        continue         # skip this field to avoid noisy normalization
                    b_f = self.b_map.get(field, 0.75)

                    len_norm = 1.0 - b_f + b_f * (len_f / avg_len_f if avg_len_f > 0 else 0.0)
                    tf_weighted += weight * (tf_f / len_norm)

                bm25f += idf * (tf_weighted / (self.k1 + tf_weighted))

            # ── Phrase + Proximity Score ───────────────────────────────────
            phrase_prox = 0.0

            # Strict phrase match count
            if strict_phrases:
                for phrase_terms in strict_phrases:
                    if len(phrase_terms) < 2:
                        continue
                    for field in self.weights.keys():
                        field_positions = {
                            t: info["positions"].get(t, {}).get(field, [])
                            for t in phrase_terms
                        }
                        if _phrase_found(phrase_terms, field_positions):
                            phrase_prox += 0.25
                            break  # count once per phrase regardless of field

            # Distance-decay proximity for consecutive term pairs
            if len(query_terms) > 1:
                pairs = [
                    (query_terms[i], query_terms[i + 1])
                    for i in range(len(query_terms) - 1)
                ]
                for term1, term2 in pairs:
                    min_dist = _min_term_distance(
                        term1, term2, info["positions"], self.weights.keys()
                    )
                    if min_dist is not None:
                        phrase_prox += 1.0 / (min_dist + 1)

            results[doc_id] = (bm25f, phrase_prox)

        return results


def _phrase_found(phrase_terms, field_positions):
    """Check whether phrase_terms appear consecutively in field_positions."""
    if any(not field_positions.get(t) for t in phrase_terms):
        return False
    first_positions = field_positions[phrase_terms[0]]
    rest_sets = [set(field_positions[t]) for t in phrase_terms[1:]]
    return any(
        all((p + i + 1) in rest_sets[i] for i in range(len(rest_sets)))
        for p in first_positions
    )


def _min_term_distance(term1, term2, all_positions, fields):
    """Return minimum token distance between term1 and term2 across all fields."""
    min_dist = None
    pos1_by_field = all_positions.get(term1, {})
    pos2_by_field = all_positions.get(term2, {})

    for field in fields:
        p1_list = pos1_by_field.get(field, [])
        p2_list = pos2_by_field.get(field, [])
        if not p1_list or not p2_list:
            continue
        p2_set_sorted = sorted(p2_list)
        for p in p1_list:
            # Binary-search-style: find closest p2 to p
            for p2 in p2_set_sorted:
                d = abs(p2 - p)
                if min_dist is None or d < min_dist:
                    min_dist = d
                if p2 > p:
                    break  # remaining are farther

    return min_dist
