# tests/test_search.py

from search.search_engine import SearchEngine

engine = SearchEngine()

queries = {
    "MULTI-WORD": "asyncio code block example",
    "SINGLE-1": "asyncio",
    "SINGLE-2": "generator",
    "SINGLE-3": "decorator"
}

for label, query in queries.items():
    results = engine.search(query)
    
    print(f"\n{'='*50}")
    print(f"QUERY: '{query}' | TOTAL RESULTS: {len(results)}")
    print(f"{'='*50}")

    for result in results[:5]:  # Just printing top 5 to keep it clean
        print(f"\nDOC: {result['doc_id']}")
        print(f"SCORE: {result['score']:.4f}")
        print(f"TITLE: {result['title']}")
        print(f"URL: {result['url']}")