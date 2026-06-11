# search/index_reader.py

import json
from pathlib import Path


class IndexReader:

    def __init__(self, index_dir="data/index", index_type="document"):
        self.index_dir = index_dir
        self.index_type = index_type
        self.reload()

    def reload(self):
        prefix = "" if self.index_type == "document" else "image_"
        
        self.postings = {}
        self.term_stats = {}
        self.doc_stats = {}
        if self.index_type == "document":
            self.corpus_stats = {
                "num_docs": 0,
                "avg_title_length": 0.0,
                "avg_content_length": 0.0,
                "avg_url_length": 0.0,
                "num_terms": 0
            }
        else:
            self.corpus_stats = {
                "num_docs": 0,
                "avg_alt_length": 0.0,
                "avg_surrounding_length": 0.0,
                "avg_title_length": 0.0,
                "avg_url_length": 0.0,
                "num_terms": 0
            }
            
        index_path = Path(self.index_dir)
        try:
            with open(index_path / f"{prefix}postings.json", "r", encoding="utf-8") as f:
                self.postings = json.load(f)
            with open(index_path / f"{prefix}term_stats.json", "r", encoding="utf-8") as f:
                self.term_stats = json.load(f)
            with open(index_path / f"{prefix}doc_stats.json", "r", encoding="utf-8") as f:
                self.doc_stats = json.load(f)
            with open(index_path / f"{prefix}corpus_stats.json", "r", encoding="utf-8") as f:
                self.corpus_stats = json.load(f)
        except FileNotFoundError:
            print(f"[WARNING] Index files for '{self.index_type}' not found. Please build the index first.")

    def get_postings(self, term):
        return self.postings.get(term, {})

    def get_df(self, term):
        stats = self.term_stats.get(term)
        if not stats:
            return 0
        return stats["df"]

    def get_doc_stats(self, doc_id):
        return self.doc_stats.get(str(doc_id))

    def get_corpus_stats(self):
        return self.corpus_stats