"""
tools/seed_corpus.py — one-shot corpus bootstrap from the curated seed registry.

Grows the corpus from a handful of pages to ~1000+ by crawling every domain in
crawler/seed_registry.py, then runs the same Process -> PageRank -> Index chain as
the live fallback. PageRank and authority signals only become meaningful once the
corpus is this size — run this before judging search quality.

Run from the repo root:
    python search_engine/tools/seed_corpus.py [--max-pages 1000] [--topic python]

Paths are relative to CWD (like run_pipeline.py), so we chdir to the repo root.
"""

import os
import sys
import asyncio
import argparse
from pathlib import Path

workspace_root = Path(__file__).resolve().parents[2]
search_engine_dir = workspace_root / "search_engine"
sys.path.insert(0, str(search_engine_dir))

# Crawler writes data/raw_html and storage/* relative to CWD — match run_pipeline.
os.chdir(workspace_root)
(workspace_root / "data/raw_html").mkdir(parents=True, exist_ok=True)

from crawler.crawler import WebCrawler
from crawler.seed_registry import all_seeds, match_seeds, _REGISTRY
import process_documents
from indexing.index_builder import IndexBuilder
from search.pagerank import PageRankCalculator


async def _crawl(seeds, max_pages):
    # Cross-domain crawl: curated seeds span many trusted sites, so don't restrict.
    crawler = WebCrawler(
        seed_url=seeds,
        max_pages=max_pages,
        restrict_domain=False,
        restrict_path=False,
    )
    await crawler.crawl()


def main():
    parser = argparse.ArgumentParser(description="Bootstrap MINISEARCH corpus from curated seeds")
    parser.add_argument("--max-pages", type=int, default=1000,
                        help="Total pages to crawl across all seeds (default 1000)")
    parser.add_argument("--topic", default=None,
                        help="Restrict to one topic's seeds (matches a registry keyword, or 'all' for all topics)")
    parser.add_argument("--domains", nargs="+", default=None,
                        help="Specific domains/URLs to crawl (bypasses seed registry)")
    parser.add_argument("--incremental", action="store_true",
                        help="Incremental index build (default: full rebuild)")
    args = parser.parse_args()

    # Determine seeds based on --domains, --topic all, or --topic <keyword>
    if args.domains:
        seeds = args.domains
    elif args.topic == "all":
        seeds = all_seeds()
    elif args.topic:
        seeds = match_seeds(args.topic, max_seeds=20)
    else:
        seeds = all_seeds()

    if not seeds:
        print(f"No curated seeds matched topic {args.topic!r}. Use --topic with a known keyword.")
        sys.exit(1)

    print(f"=== Seeding corpus from {len(seeds)} curated domains (max_pages={args.max_pages}) ===")
    for s in seeds:
        print(f"  • {s}")

    print("\n=== Crawling ===")
    asyncio.run(_crawl(seeds, args.max_pages))

    print("\n=== Processing documents ===")
    process_documents.process_documents()

    print("\n=== Calculating PageRank ===")
    PageRankCalculator().calculate_and_save()

    print("\n=== Building index ===")
    builder = IndexBuilder()
    builder.build(incremental=args.incremental)
    builder.save()
    builder.summary()
    builder.close()

    print("\n=== Corpus bootstrap complete ===")


if __name__ == "__main__":
    main()
