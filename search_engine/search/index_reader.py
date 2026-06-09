# search/index_reader.py

import json


class IndexReader:

    def __init__(self):

        with open(
            "data/index/postings.json",
            "r",
            encoding="utf-8"
        ) as f:
            self.postings = json.load(f)

        with open(
            "data/index/term_stats.json",
            "r",
            encoding="utf-8"
        ) as f:
            self.term_stats = json.load(f)

        with open(
            "data/index/doc_stats.json",
            "r",
            encoding="utf-8"
        ) as f:
            self.doc_stats = json.load(f)

        with open(
            "data/index/corpus_stats.json",
            "r",
            encoding="utf-8"
        ) as f:
            self.corpus_stats = json.load(f)

    def get_postings(self, term):

        return self.postings.get(term, {})

    def get_df(self, term):

        stats = self.term_stats.get(term)

        if not stats:
            return 0

        return stats["df"]

    def get_doc_stats(self, doc_id):

        return self.doc_stats.get(
            str(doc_id)
        )

    def get_corpus_stats(self):

        return self.corpus_stats