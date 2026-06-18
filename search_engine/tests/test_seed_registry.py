import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from crawler.seed_registry import match_seeds


def test_python3_matches_python_seeds():
    seeds = match_seeds("Python3 programming tutorial")
    assert any("python" in s.lower() or "realpython" in s.lower() for s in seeds), \
        f"Expected python seeds, got: {seeds}"


def test_movie_query_matches_entertainment():
    seeds = match_seeds("cocktail2 hindi movie")
    assert any("imdb" in s or "themoviedb" in s or "bollywood" in s.lower() for s in seeds), \
        f"Expected imdb/tmdb seeds, got: {seeds}"


def test_fallback_returns_non_empty():
    seeds = match_seeds("xyzzy frobble qux")
    assert len(seeds) > 0, "Fallback must return seeds"


def test_linux_architecture_matches():
    seeds = match_seeds("linux architecture diagram")
    assert any("kernel" in s or "linux" in s.lower() or "tldp" in s for s in seeds), \
        f"Expected linux seeds, got: {seeds}"
