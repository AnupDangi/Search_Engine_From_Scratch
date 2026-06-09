Background Research:
Build your own Search Engine
CSS: A search engine in CSS
https://stories.algolia.com/a-search-engine-in-css-b5ec4e902e97
Python: Building a search engine using Redis and redis-py
https://www.dr-josiah.com/2010/07/building-search-engine-using-redis-and.html

Python: Building a Vector Space Indexing Engine in Python
https://boyter.org/2010/08/build-vector-space-search-engine-python/

Python: Building A Python-Based Search Engine [\[video\]](https://www.youtube.com/watch?v=cY7pE7vX6MU)

Python: Making text search learn from feedback
https://medium.com/filament-ai/making-text-search-learn-from-feedback-4fe210fd87b0

Python: Finding Important Words in Text Using TF-IDF
https://stevenloria.com/tf-idf/

## Search Engine V1

V1 includes crawling, HTML parsing, SQLite storage, text preprocessing,
inverted indexing, BM25 ranking, snippet generation, and a FastAPI search
endpoint.

Architecture diagram:

- [Search Engine V1 Architecture](docs/v1-architecture.md)

Run the API from the `search_engine` directory:

```bash
uvicorn api.app:app --reload
```

Search endpoint:

```text
GET /search?q=asyncio&limit=10
```
