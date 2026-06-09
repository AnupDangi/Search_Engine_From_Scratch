# Search Engine V1 Architecture

```mermaid
flowchart TD
    seed["Seed URL"] --> crawler["Crawler"]
    crawler --> normalize["URL Normalization\nstrip fragments, constrain domain/path"]
    normalize --> raw_html["Raw HTML Files\nmetadata.json"]
    raw_html --> parser["HTML Parser\nBeautifulSoup"]
    parser --> store["SQLite Document Store\nurl, title, content, html_file"]
    store --> preprocessor["Text Preprocessing\ntokenize, stopword removal, stemming"]
    preprocessor --> indexer["Index Builder"]
    indexer --> inverted["Inverted Index\npostings + doc stats + corpus stats"]
    inverted --> reader["Index Reader"]
    query["User Query"] --> query_processor["Query Processor"]
    query_processor --> retriever["Retriever\ncandidate documents"]
    reader --> retriever
    retriever --> ranker["BM25 Ranker"]
    reader --> ranker
    ranker --> snippets["Snippet Generator"]
    store --> snippets
    snippets --> results["Search Results\ntitle, url, score, snippet"]
    results --> api["FastAPI\nGET /search?q=..."]
```

## V1 Scope

- Crawl and normalize web pages.
- Parse HTML into title and searchable text.
- Store documents in SQLite.
- Build an inverted index with corpus and document statistics.
- Retrieve candidates from query terms.
- Rank candidates with BM25.
- Generate snippets for search results.
- Serve results through `GET /search?q=python`.

## Deferred To V2

- Positional index.
- Exact phrase search.
- Field weighting with BM25F.
- Link graph and PageRank.
- Incremental indexing.

## Deferred To V3

- Dense embeddings.
- Hybrid lexical/vector retrieval.
- Cross-encoder re-ranking.
