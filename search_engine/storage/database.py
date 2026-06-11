import sqlite3
from threading import RLock
from typing import Optional

from storage.schema import DOCUMENTS_TABLE, IMAGES_TABLE, LINKS_TABLE, QUERY_LOGS_TABLE, QUERY_CACHE_TABLE


class Database:

    def __init__(
        self,
        db_path="data/search.db"
    ):

        self.conn = sqlite3.connect(
            db_path,
            check_same_thread=False
        )

        self.cursor = self.conn.cursor()
        self.lock = RLock()

        self.initialize()

    def initialize(self):

        with self.lock:

            self.cursor.execute(
                DOCUMENTS_TABLE
            )

            # Drop and recreate images table if it's the old schema (missing file_hash)
            self.cursor.execute("PRAGMA table_info(images)")
            cols_img = [col[1] for col in self.cursor.fetchall()]
            if cols_img and "file_hash" not in cols_img:
                self.cursor.execute("DROP TABLE IF EXISTS images")
                
            self.cursor.execute(
                IMAGES_TABLE
            )

            self.cursor.execute(
                LINKS_TABLE
            )

            self.cursor.execute(
                QUERY_LOGS_TABLE
            )

            self.cursor.execute(
                QUERY_CACHE_TABLE
            )

            # Alter documents table if missing author or doc_type columns
            self.cursor.execute("PRAGMA table_info(documents)")
            cols_doc = [col[1] for col in self.cursor.fetchall()]
            if "author" not in cols_doc:
                try:
                    self.cursor.execute("ALTER TABLE documents ADD COLUMN author TEXT")
                except sqlite3.OperationalError:
                    pass
            if "doc_type" not in cols_doc:
                try:
                    self.cursor.execute("ALTER TABLE documents ADD COLUMN doc_type TEXT DEFAULT 'HTML'")
                except sqlite3.OperationalError:
                    pass
            if "content_hash" not in cols_doc:
                try:
                    self.cursor.execute("ALTER TABLE documents ADD COLUMN content_hash TEXT")
                except sqlite3.OperationalError:
                    pass
            if "indexed_at" not in cols_doc:
                try:
                    self.cursor.execute("ALTER TABLE documents ADD COLUMN indexed_at TIMESTAMP")
                except sqlite3.OperationalError:
                    pass
            if "pagerank" not in cols_doc:
                try:
                    self.cursor.execute("ALTER TABLE documents ADD COLUMN pagerank REAL DEFAULT 0.0")
                except sqlite3.OperationalError:
                    pass
            if "heading" not in cols_doc:
                try:
                    self.cursor.execute("ALTER TABLE documents ADD COLUMN heading TEXT")
                except sqlite3.OperationalError:
                    pass

            self.conn.commit()

    def insert_document(
        self,
        url,
        title,
        content,
        html_file,
        content_hash=None,
        author=None,
        doc_type='HTML',
        heading=None,
    ):

        with self.lock:

            self.cursor.execute(
                """
                INSERT INTO documents
                (
                    url,
                    title,
                    content,
                    author,
                    doc_type,
                    html_file,
                    content_hash,
                    heading,
                    indexed_at
                )
                VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(url) DO UPDATE SET
                    title = excluded.title,
                    content = excluded.content,
                    author = excluded.author,
                    doc_type = excluded.doc_type,
                    html_file = excluded.html_file,
                    content_hash = excluded.content_hash,
                    heading = excluded.heading,
                    indexed_at = NULL,
                    crawled_at = CURRENT_TIMESTAMP
                """,
                (
                    url,
                    title,
                    content,
                    author,
                    doc_type,
                    html_file,
                    content_hash,
                    heading,
                )
            )

            self.conn.commit()

    def count_documents(self):
        
        with self.lock:
            
            self.cursor.execute(
                """
                SELECT COUNT(*)
                FROM documents
                """
            )

            return self.cursor.fetchone()[0]

    def get_all_documents(self):

        with self.lock:

            self.cursor.execute(
                """
                SELECT
                    id,
                    title,
                    content
                FROM documents
                """
            )

            return self.cursor.fetchall()

    def get_documents_by_ids(
        self,
        doc_ids
        ):

        if not doc_ids:
            return []

        placeholders = ",".join(
            "?"
            for _ in doc_ids
        )

        query = f"""
        SELECT
            id,
            title,
            url,
            content,
            author,
            doc_type,
            html_file,
            pagerank
        FROM documents
        WHERE id IN ({placeholders})
        """

        with self.lock:

            self.cursor.execute(
                query,
                tuple(doc_ids)
            )

            return self.cursor.fetchall()

    def get_docs_to_index(self):
        with self.lock:
            self.cursor.execute(
                """
                SELECT id, url, title, content, author, doc_type, heading
                FROM documents
                WHERE indexed_at IS NULL OR indexed_at < crawled_at
                """
            )
            return self.cursor.fetchall()

    def update_docs_indexed_at(self, doc_ids, timestamp):
        if not doc_ids:
            return
        placeholders = ",".join("?" for _ in doc_ids)
        query = f"UPDATE documents SET indexed_at = ? WHERE id IN ({placeholders})"
        with self.lock:
            self.cursor.execute(query, [timestamp] + list(doc_ids))
            self.conn.commit()

    def insert_image(
        self,
        page_url,
        image_url,
        alt_text,
        surrounding_text,
        page_title,
        width=None,
        height=None,
        file_hash=None,
        file_size=None,
        local_path=None,
        downloaded_at=None
    ):
        with self.lock:
            self.cursor.execute(
                """
                INSERT INTO images
                (
                    page_url,
                    image_url,
                    alt_text,
                    surrounding_text,
                    page_title,
                    width,
                    height,
                    file_hash,
                    file_size,
                    local_path,
                    downloaded_at,
                    indexed_at
                )
                VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(image_url) DO UPDATE SET
                    page_url = excluded.page_url,
                    alt_text = excluded.alt_text,
                    surrounding_text = excluded.surrounding_text,
                    page_title = excluded.page_title,
                    width = excluded.width,
                    height = excluded.height,
                    file_hash = excluded.file_hash,
                    file_size = excluded.file_size,
                    local_path = excluded.local_path,
                    downloaded_at = excluded.downloaded_at,
                    indexed_at = NULL,
                    crawled_at = CURRENT_TIMESTAMP
                """,
                (
                    page_url,
                    image_url,
                    alt_text,
                    surrounding_text,
                    page_title,
                    width,
                    height,
                    file_hash,
                    file_size,
                    local_path,
                    downloaded_at
                )
            )
            self.conn.commit()

    def get_images_to_index(self):
        with self.lock:
            self.cursor.execute(
                """
                SELECT id, page_url, image_url, alt_text, surrounding_text, page_title
                FROM images
                WHERE indexed_at IS NULL OR indexed_at < crawled_at
                """
            )
            return self.cursor.fetchall()

    def update_images_indexed_at(self, img_ids, timestamp):
        if not img_ids:
            return
        placeholders = ",".join("?" for _ in img_ids)
        query = f"UPDATE images SET indexed_at = ? WHERE id IN ({placeholders})"
        with self.lock:
            self.cursor.execute(query, [timestamp] + list(img_ids))
            self.conn.commit()

    def insert_link(self, source_url, target_url):
        with self.lock:
            self.cursor.execute(
                """
                INSERT OR IGNORE INTO links (source_url, target_url)
                VALUES (?, ?)
                """,
                (source_url, target_url)
            )
            self.conn.commit()

    def get_all_links(self):
        with self.lock:
            self.cursor.execute("SELECT source_url, target_url FROM links")
            return self.cursor.fetchall()

    def update_pageranks(self, pagerank_scores):
        if not pagerank_scores:
            return
        with self.lock:
            self.cursor.execute("BEGIN TRANSACTION")
            try:
                for url, score in pagerank_scores.items():
                    self.cursor.execute(
                        "UPDATE documents SET pagerank = ? WHERE url = ?",
                        (score, url)
                    )
                self.conn.commit()
            except Exception as e:
                self.conn.rollback()
                raise e

    def get_all_pageranks(self):
        with self.lock:
            self.cursor.execute("SELECT id, pagerank FROM documents")
            return dict(self.cursor.fetchall())

    def log_query(self, query: str, result_count: int) -> None:
        with self.lock:
            self.cursor.execute(
                "INSERT INTO query_logs (query, result_count) VALUES (?, ?)",
                (query.strip().lower(), result_count)
            )
            self.conn.commit()

    def get_cached_response(self, query: str, ttl_hours: int = 24) -> Optional[str]:
        with self.lock:
            self.cursor.execute(
                """
                SELECT response_json FROM query_cache
                WHERE query = ?
                AND created_at > datetime('now', ? || ' hours')
                """,
                (query.strip().lower(), f"-{ttl_hours}")
            )
            row = self.cursor.fetchone()
            return row[0] if row else None

    def set_cached_response(self, query: str, response_json: str) -> None:
        with self.lock:
            self.cursor.execute(
                """
                INSERT INTO query_cache (query, response_json, created_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(query) DO UPDATE SET
                    response_json = excluded.response_json,
                    created_at = excluded.created_at
                """,
                (query.strip().lower(), response_json)
            )
            self.conn.commit()

    def get_suggestions(self, prefix: str, limit: int = 5) -> list:
        with self.lock:
            self.cursor.execute(
                """
                SELECT query, COUNT(*) as cnt
                FROM query_logs
                WHERE query LIKE ?
                GROUP BY query
                ORDER BY cnt DESC
                LIMIT ?
                """,
                (prefix.strip().lower() + "%", limit)
            )
            return [row[0] for row in self.cursor.fetchall()]

    def get_documents_by_ids_with_crawled_at(self, doc_ids):
        if not doc_ids:
            return []
        placeholders = ",".join("?" for _ in doc_ids)
        query = f"""
        SELECT
            id,
            title,
            url,
            content,
            author,
            doc_type,
            html_file,
            pagerank,
            crawled_at
        FROM documents
        WHERE id IN ({placeholders})
        """
        with self.lock:
            self.cursor.execute(query, tuple(doc_ids))
            return self.cursor.fetchall()

    def close(self):
        with self.lock:
            self.conn.close()
