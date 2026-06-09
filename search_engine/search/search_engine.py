# search/search_engine.py

from search.query_processor import (
    QueryProcessor
)

from search.index_reader import (
    IndexReader
)

from search.retriever import (
    Retriever
)

from storage.database import (
    Database
)

from search.bm25_ranker import (
    BM25Ranker
)

from search.snippet_generator import (
    SnippetGenerator
)


class SearchEngine:

    def __init__(self):

        self.query_processor = (
            QueryProcessor()
        )

        self.index_reader = (
            IndexReader()
        )

        self.retriever = (
            Retriever(
                self.index_reader
            )
        )

        self.ranker = (
            BM25Ranker(
                self.index_reader
            )
        )

        self.snippet_generator = (
            SnippetGenerator()
        )

        self.db = Database()

    def search(
        self,
        query,
        limit=20
    ):

        query_terms = (
            self.query_processor
            .process(query)
        )

        candidates = (
            self.retriever
            .retrieve(query_terms)
        )
        
        if not candidates:
            return []

        scores = self.ranker.score(
            query_terms,
            candidates
        )

        sorted_docs = sorted(
            scores.items(),
            key=lambda x: x[1],
            reverse=True
        )

        top_docs = sorted_docs[:limit]

        doc_ids = [
            int(doc_id)
            for doc_id, score
            in top_docs
        ]

        documents = (
            self.db
            .get_documents_by_ids(
                doc_ids
            )
        )

        score_lookup = {
            int(doc_id): score 
            for doc_id, score in top_docs
        }

        results = []

        for row in documents:

            try:

                doc_id = row["id"]
                title = row["title"]
                url = row["url"]
                content = row["content"]

            except Exception:

                doc_id = row[0]
                title = row[1]
                url = row[2]
                content = row[3]

            snippet = (
                self.snippet_generator
                .generate(
                    content,
                    query,
                    query_terms
                )
            )

            results.append(
                {
                    "doc_id": doc_id,
                    "title": title,
                    "url": url,
                    "score": score_lookup.get(doc_id, 0.0),
                    "snippet": snippet
                }
            )
        
        results.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        return results
