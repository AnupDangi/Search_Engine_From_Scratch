from collections import defaultdict
from pathlib import Path
import json
from urllib.parse import urlparse
import datetime

from indexing.tokenizer import TextPreprocessor
from storage.database import Database


class IndexBuilder:

    def __init__(self, db_path=None, index_dir=None):

        self.preprocessor = TextPreprocessor()
        self.db = Database() if db_path is None else Database(db_path=db_path)

        # term -> doc_id -> field -> [positions]
        self.postings = {}
        self.doc_stats = {}
        self.term_stats = {}
        self.corpus_stats = {}

        # Image indexing structures
        self.image_postings = {}
        self.image_doc_stats = {}
        self.image_term_stats = {}
        self.image_corpus_stats = {}

        self.index_dir = Path(index_dir) if index_dir else Path("data/index")

        self.index_dir.mkdir(
            parents=True,
            exist_ok=True
        )

    def build(self, incremental=True):
        self.build_document_index(incremental)
        self.build_image_index(incremental)

    def build_document_index(self, incremental=True):
        # 1. Load existing index if incremental is requested
        if incremental and (self.index_dir / "postings.json").exists():
            print("[INFO] Loading existing document index for incremental update...")
            try:
                with open(self.index_dir / "postings.json", "r", encoding="utf-8") as f:
                    self.postings = json.load(f)
                with open(self.index_dir / "doc_stats.json", "r", encoding="utf-8") as f:
                    self.doc_stats = json.load(f)
            except Exception as e:
                print(f"[WARNING] Failed to load existing index: {e}. Rebuilding from scratch.")
                self.postings = {}
                self.doc_stats = {}
        else:
            self.postings = {}
            self.doc_stats = {}

        # 2. Get documents needing indexing
        dirty_docs = self.db.get_docs_to_index()

        # If we need a full rebuild (no index or forced full rebuild)
        if not self.postings or not incremental:
            print("[INFO] Rebuilding document index from scratch...")
            self.postings = {}
            self.doc_stats = {}
            with self.db.lock:
                self.db.cursor.execute("SELECT id, url, title, content, author, doc_type, heading FROM documents")
                dirty_docs = self.db.cursor.fetchall()

        if not dirty_docs:
            print("[INFO] Document index is up-to-date. No documents require indexing.")
            self._build_term_stats()
            self._build_corpus_stats()
            return

        print(f"[INFO] Found {len(dirty_docs)} documents to index/re-index.")

        # 3. For each dirty document, if it was previously indexed, remove it from the postings first
        for row in dirty_docs:
            doc_id = str(row[0])
            if doc_id in self.doc_stats:
                for term in list(self.postings.keys()):
                    if doc_id in self.postings[term]:
                        del self.postings[term][doc_id]
                        if not self.postings[term]:
                            del self.postings[term]
                del self.doc_stats[doc_id]

        # 4. Tokenize and index each dirty document
        indexed_ids = []
        for row in dirty_docs:
            doc_id = row[0]
            url = row[1]
            title = row[2]
            content = row[3]
            author = row[4] if len(row) > 4 else None
            # doc_type = row[5] if len(row) > 5 else "HTML"
            heading = row[6] if len(row) > 6 else None

            # Tokenize fields separately
            title_tokens = self.preprocessor.process(title)
            content_tokens = self.preprocessor.process(content)
            author_tokens = self.preprocessor.process(author) if author else []
            heading_tokens = self.preprocessor.process(heading) if heading else []

            # Tokenize URL components
            parsed_url = urlparse(url)
            url_text = f"{parsed_url.netloc} {parsed_url.path}"
            url_tokens = self.preprocessor.process(url_text)

            self.doc_stats[str(doc_id)] = {
                "title_length": len(title_tokens),
                "content_length": len(content_tokens),
                "url_length": len(url_tokens),
                "author_length": len(author_tokens),
                "heading_length": len(heading_tokens),
            }

            # Helper to insert positions for a field
            def _add_positions(term, doc_key, field, pos):
                if term not in self.postings:
                    self.postings[term] = {}
                if doc_key not in self.postings[term]:
                    self.postings[term][doc_key] = {}
                if field not in self.postings[term][doc_key]:
                    self.postings[term][doc_key][field] = []
                self.postings[term][doc_key][field].append(pos)

            doc_key = str(doc_id)
            for pos, term in enumerate(heading_tokens):
                _add_positions(term, doc_key, "heading", pos)
            for pos, term in enumerate(title_tokens):
                _add_positions(term, doc_key, "title", pos)
            for pos, term in enumerate(content_tokens):
                _add_positions(term, doc_key, "content", pos)
            for pos, term in enumerate(url_tokens):
                _add_positions(term, doc_key, "url", pos)
            for pos, term in enumerate(author_tokens):
                _add_positions(term, doc_key, "author", pos)

            indexed_ids.append(doc_id)

        print(
            f"[INFO] Generated postings for {len(self.postings)} document terms"
        )

        self._build_term_stats()
        self._build_corpus_stats()

        # 5. Update database indexed_at timestamps
        if indexed_ids:
            now = datetime.datetime.now().isoformat()
            self.db.update_docs_indexed_at(indexed_ids, now)

    def build_image_index(self, incremental=True):
        # 1. Load existing image index if incremental is requested
        if incremental and (self.index_dir / "image_postings.json").exists():
            print("[INFO] Loading existing image index for incremental update...")
            try:
                with open(self.index_dir / "image_postings.json", "r", encoding="utf-8") as f:
                    self.image_postings = json.load(f)
                with open(self.index_dir / "image_doc_stats.json", "r", encoding="utf-8") as f:
                    self.image_doc_stats = json.load(f)
            except Exception as e:
                print(f"[WARNING] Failed to load existing image index: {e}. Rebuilding from scratch.")
                self.image_postings = {}
                self.image_doc_stats = {}
        else:
            self.image_postings = {}
            self.image_doc_stats = {}

        # 2. Get images needing indexing
        dirty_imgs = self.db.get_images_to_index()

        # If we need a full rebuild (no index or forced full rebuild)
        if not self.image_postings or not incremental:
            print("[INFO] Rebuilding image index from scratch...")
            self.image_postings = {}
            self.image_doc_stats = {}
            with self.db.lock:
                self.db.cursor.execute("SELECT id, page_url, image_url, alt_text, surrounding_text, page_title FROM images")
                dirty_imgs = self.db.cursor.fetchall()

        if not dirty_imgs:
            print("[INFO] Image index is up-to-date. No images require indexing.")
            self._build_image_term_stats()
            self._build_image_corpus_stats()
            return

        print(f"[INFO] Found {len(dirty_imgs)} images to index/re-index.")

        # 3. For each dirty image, remove its old occurrences
        for row in dirty_imgs:
            img_id = str(row[0])
            if img_id in self.image_doc_stats:
                for term in list(self.image_postings.keys()):
                    if img_id in self.image_postings[term]:
                        del self.image_postings[term][img_id]
                        if not self.image_postings[term]:
                            del self.image_postings[term]
                del self.image_doc_stats[img_id]

        # 4. Tokenize and index each dirty image
        indexed_ids = []
        for row in dirty_imgs:
            img_id = row[0]
            page_url = row[1]
            image_url = row[2]
            alt_text = row[3] or ""
            surrounding_text = row[4] or ""
            page_title = row[5] or ""

            # Tokenize image fields
            alt_tokens = self.preprocessor.process(alt_text)
            surr_tokens = self.preprocessor.process(surrounding_text)
            title_tokens = self.preprocessor.process(page_title)

            # Tokenize image URL components
            parsed_img_url = urlparse(image_url)
            img_url_text = f"{parsed_img_url.netloc} {parsed_img_url.path}"
            url_tokens = self.preprocessor.process(img_url_text)

            # Extract and tokenize filename separately (e.g. "python-logo.png" → ["python", "logo"])
            raw_stem = Path(parsed_img_url.path).stem
            filename_text = raw_stem.replace("-", " ").replace("_", " ")
            filename_tokens = self.preprocessor.process(filename_text)

            self.image_doc_stats[str(img_id)] = {
                "alt_text_length": len(alt_tokens),
                "surrounding_text_length": len(surr_tokens),
                "page_title_length": len(title_tokens),
                "image_url_length": len(url_tokens),
                "filename_length": len(filename_tokens)
            }

            # Helper to insert positions for an image field
            def _add_img_positions(term, img_key, field, pos):
                if term not in self.image_postings:
                    self.image_postings[term] = {}
                if img_key not in self.image_postings[term]:
                    self.image_postings[term][img_key] = {}
                if field not in self.image_postings[term][img_key]:
                    self.image_postings[term][img_key][field] = []
                self.image_postings[term][img_key][field].append(pos)

            img_key = str(img_id)
            for pos, term in enumerate(alt_tokens):
                _add_img_positions(term, img_key, "alt_text", pos)
            for pos, term in enumerate(surr_tokens):
                _add_img_positions(term, img_key, "surrounding_text", pos)
            for pos, term in enumerate(title_tokens):
                _add_img_positions(term, img_key, "page_title", pos)
            for pos, term in enumerate(url_tokens):
                _add_img_positions(term, img_key, "image_url", pos)
            for pos, term in enumerate(filename_tokens):
                _add_img_positions(term, img_key, "filename", pos)

            indexed_ids.append(img_id)

        print(
            f"[INFO] Generated image postings for {len(self.image_postings)} image terms"
        )

        self._build_image_term_stats()
        self._build_image_corpus_stats()

        # 5. Update database indexed_at timestamps
        if indexed_ids:
            now = datetime.datetime.now().isoformat()
            self.db.update_images_indexed_at(indexed_ids, now)

    def _build_term_stats(self):

        self.term_stats = {}
        for term, posting_list in self.postings.items():
            self.term_stats[term] = {
                "df": len(posting_list)
            }

    def _build_corpus_stats(self):

        num_docs = len(self.doc_stats)
        if num_docs == 0:
            self.corpus_stats = {
                "num_docs": 0,
                "avg_title_length": 0.0,
                "avg_content_length": 0.0,
                "avg_url_length": 0.0,
                "num_terms": len(self.postings)
            }
            return

        total_title_len = sum(stats.get("title_length", 0) for stats in self.doc_stats.values())
        total_content_len = sum(stats.get("content_length", 0) for stats in self.doc_stats.values())
        total_url_len = sum(stats.get("url_length", 0) for stats in self.doc_stats.values())
        total_author_len = sum(stats.get("author_length", 0) for stats in self.doc_stats.values())
        total_heading_len = sum(stats.get("heading_length", 0) for stats in self.doc_stats.values())

        self.corpus_stats = {
            "num_docs": num_docs,
            "avg_title_length": total_title_len / num_docs,
            "avg_content_length": total_content_len / num_docs,
            "avg_url_length": total_url_len / num_docs,
            "avg_author_length": total_author_len / num_docs,
            "avg_heading_length": total_heading_len / num_docs,
            "num_terms": len(self.postings),
        }

    def _build_image_term_stats(self):
        self.image_term_stats = {}
        for term, posting_list in self.image_postings.items():
            self.image_term_stats[term] = {
                "df": len(posting_list)
            }

    def _build_image_corpus_stats(self):
        num_images = len(self.image_doc_stats)
        if num_images == 0:
            self.image_corpus_stats = {
                "num_docs": 0,
                "avg_alt_text_length": 0.0,
                "avg_surrounding_text_length": 0.0,
                "avg_page_title_length": 0.0,
                "avg_image_url_length": 0.0,
                "num_terms": len(self.image_postings)
            }
            return

        total_alt = sum(stats.get("alt_text_length", 0) for stats in self.image_doc_stats.values())
        total_surr = sum(stats.get("surrounding_text_length", 0) for stats in self.image_doc_stats.values())
        total_title = sum(stats.get("page_title_length", 0) for stats in self.image_doc_stats.values())
        total_url = sum(stats.get("image_url_length", 0) for stats in self.image_doc_stats.values())
        total_fn = sum(stats.get("filename_length", 0) for stats in self.image_doc_stats.values())

        self.image_corpus_stats = {
            "num_docs": num_images,
            "avg_alt_text_length": total_alt / num_images,
            "avg_surrounding_text_length": total_surr / num_images,
            "avg_page_title_length": total_title / num_images,
            "avg_image_url_length": total_url / num_images,
            "avg_filename_length": total_fn / num_images,
            "num_terms": len(self.image_postings)
        }

    def save(self):

        print(
            "[INFO] Saving document index files..."
        )

        with open(
            self.index_dir /
            "postings.json",
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                self.postings,
                f,
                ensure_ascii=False
            )

        with open(
            self.index_dir /
            "term_stats.json",
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                self.term_stats,
                f,
                ensure_ascii=False
            )

        with open(
            self.index_dir /
            "doc_stats.json",
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                self.doc_stats,
                f,
                ensure_ascii=False
            )

        with open(
            self.index_dir /
            "corpus_stats.json",
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                self.corpus_stats,
                f,
                ensure_ascii=False
            )

        # Save image index if present
        if hasattr(self, "image_postings") and self.image_postings:
            print("[INFO] Saving image index files...")
            with open(self.index_dir / "image_postings.json", "w", encoding="utf-8") as f:
                json.dump(self.image_postings, f, ensure_ascii=False)
            with open(self.index_dir / "image_term_stats.json", "w", encoding="utf-8") as f:
                json.dump(self.image_term_stats, f, ensure_ascii=False)
            with open(self.index_dir / "image_doc_stats.json", "w", encoding="utf-8") as f:
                json.dump(self.image_doc_stats, f, ensure_ascii=False)
            with open(self.index_dir / "image_corpus_stats.json", "w", encoding="utf-8") as f:
                json.dump(self.image_corpus_stats, f, ensure_ascii=False)

        print(
            "[INFO] Index saved successfully."
        )

    def summary(self):

        print("\n========== INDEX SUMMARY ==========")

        print(
            f"Documents      : "
            f"{self.corpus_stats['num_docs']}"
        )

        print(
            f"Vocabulary Size: "
            f"{self.corpus_stats['num_terms']}"
        )

        print(
            f"Avg Title Len  : "
            f"{self.corpus_stats['avg_title_length']:.2f}"
        )

        print(
            f"Avg Content Len: "
            f"{self.corpus_stats['avg_content_length']:.2f}"
        )

        print(
            f"Avg URL Len    : "
            f"{self.corpus_stats['avg_url_length']:.2f}"
        )

        if hasattr(self, "image_corpus_stats") and self.image_corpus_stats.get("num_docs", 0) > 0:
            print("\n========== IMAGE INDEX SUMMARY ==========")
            print(
                f"Images         : "
                f"{self.image_corpus_stats['num_docs']}"
            )
            print(
                f"Vocabulary Size: "
                f"{self.image_corpus_stats['num_terms']}"
            )
            print(
                f"Avg Alt Text   : "
                f"{self.image_corpus_stats['avg_alt_text_length']:.2f}"
            )
            print(
                f"Avg Surrounding: "
                f"{self.image_corpus_stats['avg_surrounding_text_length']:.2f}"
            )

        print("===================================\n")

    def close(self):

        self.db.close()


if __name__ == "__main__":

    builder = IndexBuilder()

    builder.build(incremental=True)

    builder.save()

    builder.summary()

    builder.close()