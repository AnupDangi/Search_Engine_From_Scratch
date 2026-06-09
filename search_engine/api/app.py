# api/app.py

from fastapi import FastAPI, Query

from search.search_engine import SearchEngine


app = FastAPI(
    title="Search Engine V1",
    version="1.0.0"
)

engine = SearchEngine()


@app.get("/health")
def health():

    return {
        "status": "ok"
    }


@app.get("/search")
def search(
    q: str = Query(
        ...,
        min_length=1,
        description="Search query"
    ),
    limit: int = Query(
        10,
        ge=1,
        le=20,
        description="Maximum number of results"
    )
):

    results = engine.search(
        q,
        limit=limit
    )

    return {
        "query": q,
        "count": len(results),
        "results": results
    }
