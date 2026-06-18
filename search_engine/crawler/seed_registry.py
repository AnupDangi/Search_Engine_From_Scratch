"""
seed_registry.py — curated, intent-aware seed URLs for discovery + bootstrap.

The dynamic-crawl fallback used to lean on Wikipedia -> DuckDuckGo -> Bing, which
biased results toward Wikipedia. This registry maps topic keywords to high-quality
documentation / reference / research domains so that, e.g., "python notes" leads with
docs.python.org and realpython.com instead of a Catalan Wikipedia category.

Usage:
    from crawler.seed_registry import match_seeds, all_seeds
    seeds = match_seeds("python lecture notes", max_seeds=6)
"""

import re
from nltk.stem.snowball import SnowballStemmer

_stemmer = SnowballStemmer("english")


def _tokens(text: str) -> list[str]:
    """Lowercase, split on non-alpha boundaries and digit/letter boundaries, then stem.

    Splitting at letter/digit boundaries ensures tokens like "Python3" produce
    both "python" and "3" as separate tokens, so stemmed "python" matches the
    "python" keyword in the registry.
    """
    raw = re.findall(r"[a-zA-Z0-9]+", text.lower())
    # Split each chunk at letter<->digit boundaries: "python3" -> ["python", "3"]
    expanded: list[str] = []
    for chunk in raw:
        expanded.extend(re.findall(r"[a-z]+|[0-9]+", chunk))
    return [_stemmer.stem(t) for t in expanded if len(t) > 1]


def _stem_keywords(kws: list) -> set:
    return {_stemmer.stem(k) for k in kws}


# topic -> {"keywords": list of trigger tokens, "seeds": ordered seed URLs}
_REGISTRY = {
    "python": {
        "keywords": ["python", "py", "pip", "asyncio", "django", "flask", "pandas", "numpy"],
        "seeds": [
            "https://docs.python.org/3/",
            "https://realpython.com/",
            "https://www.geeksforgeeks.org/python-programming-language/",
            "https://www.tutorialspoint.com/python/index.htm",
        ],
    },
    "javascript": {
        "keywords": ["javascript", "js", "typescript", "node", "nodejs", "react", "vue", "angular"],
        "seeds": [
            "https://developer.mozilla.org/en-US/docs/Web/JavaScript",
            "https://javascript.info/",
            "https://react.dev/",
        ],
    },
    "programming": {
        "keywords": ["algorithm", "algorithms", "data", "structure", "structures", "code",
                     "coding", "leetcode", "recursion", "sorting", "complexity"],
        "seeds": [
            "https://www.geeksforgeeks.org/",
            "https://stackoverflow.com/questions",
            "https://www.tutorialspoint.com/",
        ],
    },
    "devops": {
        "keywords": ["docker", "kubernetes", "k8s", "container", "ci", "cd", "terraform", "ansible"],
        "seeds": [
            "https://docs.docker.com/",
            "https://kubernetes.io/docs/home/",
        ],
    },
    "research": {
        "keywords": ["paper", "papers", "research", "survey", "preprint", "arxiv",
                     "thesis", "publication", "citation", "pdf"],
        "seeds": [
            "https://arxiv.org/list/cs.LG/recent",
            "https://paperswithcode.com/",
        ],
    },
    "ml_ai": {
        "keywords": ["ml", "ai", "machine", "learning", "deep", "neural", "network",
                     "transformer", "transformers", "attention", "llm", "rag",
                     "embedding", "embeddings", "gpt", "diffusion", "cnn", "nlp"],
        "seeds": [
            "https://paperswithcode.com/",
            "https://huggingface.co/docs",
            "https://pytorch.org/docs/stable/index.html",
            "https://www.tensorflow.org/learn",
        ],
    },
    "agents": {
        "keywords": ["langchain", "langgraph", "agent", "agents", "agentic", "crewai", "autogen"],
        "seeds": [
            "https://python.langchain.com/docs/introduction/",
            "https://langchain-ai.github.io/langgraph/",
        ],
    },
    "education": {
        "keywords": ["notes", "tutorial", "lecture", "course", "study", "guide",
                     "handbook", "textbook", "cheatsheet", "syllabus", "exam"],
        "seeds": [
            "https://www.geeksforgeeks.org/",
            "https://www.tutorialspoint.com/",
            "https://ocw.mit.edu/",
        ],
    },
    "linux_os": {
        "keywords": ["linux", "unix", "kernel", "os", "operating system",
                     "shell", "bash", "ubuntu", "fedora", "debian", "arch",
                     "filesystem", "process", "thread", "cpu", "memory"],
        "seeds": [
            "https://www.kernel.org/",
            "https://linux.die.net/",
            "https://tldp.org/",
            "https://www.gnu.org/software/bash/manual/bash.html",
            "https://en.wikipedia.org/wiki/Linux",
            "https://www.digitalocean.com/community/tutorials",
        ],
    },
    "databases": {
        "keywords": ["sql", "database", "mysql", "postgresql", "sqlite",
                     "nosql", "mongodb", "redis", "query", "schema",
                     "index", "transaction", "orm"],
        "seeds": [
            "https://www.postgresql.org/docs/current/",
            "https://dev.mysql.com/doc/",
            "https://sqlite.org/docs.html",
            "https://www.mongodb.com/docs/",
            "https://redis.io/docs/",
            "https://en.wikipedia.org/wiki/Database",
        ],
    },
    "networking": {
        "keywords": ["network", "tcp", "ip", "http", "https", "dns",
                     "protocol", "socket", "api", "rest", "grpc",
                     "firewall", "router", "subnet"],
        "seeds": [
            "https://developer.mozilla.org/en-US/docs/Web/HTTP",
            "https://www.cloudflare.com/learning/",
            "https://en.wikipedia.org/wiki/Internet_protocol_suite",
            "https://www.ietf.org/rfc/",
        ],
    },
    "movies_entertainment": {
        "keywords": ["movie", "film", "cinema", "actor", "director",
                     "bollywood", "hollywood", "hindi", "trailer",
                     "imdb", "tmdb", "cast", "plot", "review",
                     "streaming", "netflix", "series", "tv"],
        "seeds": [
            "https://www.imdb.com/",
            "https://www.themoviedb.org/",
            "https://en.wikipedia.org/wiki/Cinema_of_India",
            "https://en.wikipedia.org/wiki/Bollywood",
            "https://www.rottentomatoes.com/",
        ],
    },
    "cloud_devops": {
        "keywords": ["aws", "gcp", "azure", "cloud", "docker", "kubernetes",
                     "k8s", "terraform", "ci", "cd", "devops", "deploy",
                     "container", "microservice", "serverless", "lambda"],
        "seeds": [
            "https://docs.aws.amazon.com/",
            "https://cloud.google.com/docs",
            "https://docs.microsoft.com/en-us/azure/",
            "https://docs.docker.com/",
            "https://kubernetes.io/docs/",
        ],
    },
    "security": {
        "keywords": ["security", "cybersecurity", "cve", "exploit",
                     "vulnerability", "malware", "phishing", "encryption",
                     "tls", "ssl", "oauth", "authentication", "xss", "csrf",
                     "penetration", "pentest", "ctf"],
        "seeds": [
            "https://owasp.org/",
            "https://cve.mitre.org/",
            "https://www.exploit-db.com/",
            "https://en.wikipedia.org/wiki/Computer_security",
            "https://krebsonsecurity.com/",
        ],
    },
}

# Generic fallback when nothing matches — still better-quality than Wikipedia-only.
_FALLBACK_SEEDS: list[str] = [
    "https://en.wikipedia.org/wiki/Main_Page",
    "https://www.geeksforgeeks.org/",
    "https://stackoverflow.com/questions",
    "https://www.britannica.com/",
    "https://www.imdb.com/",
    "https://www.themoviedb.org/",
    "https://github.com/trending",
    "https://developer.mozilla.org/en-US/",
]


def match_seeds(query: str, max_seeds: int = 8) -> list[str]:
    """
    Return curated seed URLs for the query, ordered by topic match strength.

    Topics whose keyword set overlaps the query more strongly come first. Returns
    fallback seeds when no topic matches.
    """
    q_tokens = set(_tokens(query))
    scored = []
    for topic, entry in _REGISTRY.items():
        kw_stems = _stem_keywords(entry["keywords"])
        overlap = len(q_tokens & kw_stems)
        if overlap > 0:
            scored.append((overlap, entry["seeds"]))
    scored.sort(key=lambda x: -x[0])
    seen, result = set(), []
    for _, seeds in scored:
        for s in seeds:
            if s not in seen:
                seen.add(s)
                result.append(s)
                if len(result) >= max_seeds:
                    return result
    if not result:
        return list(_FALLBACK_SEEDS)[:max_seeds]
    return result


def all_seeds() -> list[str]:
    """Every curated seed URL (deduped) — used to bootstrap the corpus offline."""
    seen: list[str] = []
    seen_set: set[str] = set()
    for spec in _REGISTRY.values():
        for url in spec["seeds"]:
            if url not in seen_set:
                seen_set.add(url)
                seen.append(url)
    for url in _FALLBACK_SEEDS:
        if url not in seen_set:
            seen_set.add(url)
            seen.append(url)
    return seen
