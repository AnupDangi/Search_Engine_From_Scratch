from collections import defaultdict
from pathlib import Path
import json

from indexing.tokenizer import TextPreprocessor
from storage.database import Database


class IndexBuilder:

    def __init__(self):

        self.preprocessor = TextPreprocessor()
        self.db = Database()

        # term -> {doc_id: term_frequency}
        self.postings = defaultdict(dict)

        # doc_id -> statistics
        self.doc_stats = {}

        # term -> statistics
        self.term_stats = {}

        # corpus-wide statistics
        self.corpus_stats = {}

        self.index_dir = Path("data/index")

        self.index_dir.mkdir(
            parents=True,
            exist_ok=True
        )

    def build(self):

        documents = self.db.get_all_documents()

        print(
            f"[INFO] Found {len(documents)} documents"
        )

        total_doc_length = 0

        for row in documents:

            # Supports both sqlite Row and tuple
            try:

                doc_id = row["id"]
                title = row["title"]
                content = row["content"]

            except Exception:

                doc_id = row[0]
                title = row[1]
                content = row[2]

            full_text = f"{title} {content}"

            analysis = (
                self.preprocessor
                .analyze_document(full_text)
            )

            self.doc_stats[str(doc_id)] = {
                "length": analysis["doc_length"],
                "unique_terms": analysis[
                    "unique_terms"
                ]
            }

            total_doc_length += (
                analysis["doc_length"]
            )

            for term, freq in (
                analysis["term_freq"].items()
            ):

                self.postings[
                    term
                ][str(doc_id)] = freq

        print(
            f"[INFO] Generated postings for "
            f"{len(self.postings)} terms"
        )

        self._build_term_stats()

        self._build_corpus_stats(
            total_doc_length,
            len(documents)
        )

    def _build_term_stats(self):

        for term, posting_list in (
            self.postings.items()
        ):

            self.term_stats[term] = {
                "df": len(posting_list)
            }

    def _build_corpus_stats(
        self,
        total_doc_length,
        num_docs
    ):

        avg_doc_length = 0

        if num_docs > 0:

            avg_doc_length = (
                total_doc_length / num_docs
            )

        self.corpus_stats = {
            "num_docs": num_docs,
            "avg_doc_length": avg_doc_length,
            "num_terms": len(
                self.postings
            )
        }

    def save(self):

        print(
            "[INFO] Saving index files..."
        )

        with open(
            self.index_dir /
            "postings.json",
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                self.postings,
                f,
                ensure_ascii=False
            )

        with open(
            self.index_dir /
            "term_stats.json",
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                self.term_stats,
                f,
                ensure_ascii=False
            )

        with open(
            self.index_dir /
            "doc_stats.json",
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                self.doc_stats,
                f,
                ensure_ascii=False
            )

        with open(
            self.index_dir /
            "corpus_stats.json",
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                self.corpus_stats,
                f,
                ensure_ascii=False
            )

        print(
            "[INFO] Index saved successfully."
        )

    def summary(self):

        print("\n========== INDEX SUMMARY ==========")

        print(
            f"Documents      : "
            f"{self.corpus_stats['num_docs']}"
        )

        print(
            f"Vocabulary Size: "
            f"{self.corpus_stats['num_terms']}"
        )

        print(
            f"Avg Doc Length : "
            f"{self.corpus_stats['avg_doc_length']:.2f}"
        )

        print("===================================\n")

    def close(self):

        self.db.close()


if __name__ == "__main__":

    builder = IndexBuilder()

    builder.build()

    builder.save()

    builder.summary()

    builder.close()