import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from search.query_understanding import QueryUnderstanding

qu = QueryUnderstanding()

def test_pdf_intent():
    r = qu.analyze("python notes pdf")
    assert r["doc_type_preference"] == "PDF"

def test_image_intent():
    r = qu.analyze("linux architecture diagram")
    assert r["doc_type_preference"] == "IMAGE"

def test_movie_intent():
    r = qu.analyze("cocktail2 hindi movie")
    assert r["movie_intent"] is True
    assert r["domain_boost"] == "imdb.com"

def test_github_domain_hint():
    r = qu.analyze("deepfake detection github")
    assert r["domain_boost"] == "github.com"

def test_educational_intent():
    r = qu.analyze("python asyncio tutorial")
    assert r["educational"] is True

def test_no_intent():
    r = qu.analyze("xyzzy frobble")
    assert r["doc_type_preference"] is None
    assert r["movie_intent"] is False
