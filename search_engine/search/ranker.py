# search/ranker.py

import math


class TFIDFRanker:

    def __init__(
        self,
        index_reader
    ):
        self.index_reader = index_reader

        self.corpus_stats = (
            self.index_reader
            .get_corpus_stats()
        )

    def score(
        self,
        query_terms,
        candidates
    ):

        N = self.corpus_stats[
            "num_docs"
        ]

        scores = {}

        for doc_id, info in (
            candidates.items()
        ):

            score = 0

            for term, tf in (
                info[
                    "term_frequencies"
                ].items()
            ):

                df = (
                    self.index_reader
                    .get_df(term)
                )

                if df == 0:
                    continue

                idf = math.log(
                    N / df
                )

                score += (
                    tf * idf
                )

            scores[
                doc_id
            ] = score

        return scores