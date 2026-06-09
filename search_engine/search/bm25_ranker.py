# search/bm25_ranker.py

import math


class BM25Ranker:

    def __init__(
        self,
        index_reader,
        k1=1.5,
        b=0.75):

        self.index_reader = index_reader

        self.k1 = k1
        self.b = b

        self.corpus_stats = (
            self.index_reader
            .get_corpus_stats()
        )

    def score(self,query_terms,candidates):

        N = self.corpus_stats[
            "num_docs"
        ]

        avgdl = self.corpus_stats[
            "avg_doc_length"
        ]

        scores = {}

        for doc_id, info in candidates.items():

            doc_score = 0.0

            doc_stats = (
                self.index_reader
                .get_doc_stats(doc_id)
            )

            if not doc_stats:
                continue

            dl = doc_stats["length"]

            for term, tf in (
                info["term_frequencies"]
                .items()
            ):

                df = (
                    self.index_reader
                    .get_df(term)
                )

                if df == 0:
                    continue

                idf = math.log(
                    (
                        N - df + 0.5
                    )
                    /
                    (
                        df + 0.5
                    )
                    + 1
                )

                numerator = (
                    tf *
                    (
                        self.k1 + 1
                    )
                )

                denominator = (
                    tf
                    +
                    self.k1
                    *
                    (
                        1
                        -
                        self.b
                        +
                        self.b
                        *
                        (
                            dl / avgdl
                        )
                    )
                )

                doc_score += (
                    idf *
                    (
                        numerator /
                        denominator
                    )
                )

            coverage_boost = (
                info["matched_terms"]
                /
                len(query_terms)
            )

            doc_score *= (
                1 + coverage_boost
            )

            scores[doc_id] = doc_score
            
        return scores