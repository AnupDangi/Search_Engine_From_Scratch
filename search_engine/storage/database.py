import sqlite3
from threading import RLock

from storage.schema import DOCUMENTS_TABLE


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

            self.conn.commit()

    def insert_document(
        self,
        url,
        title,
        content,
        html_file
    ):

        with self.lock:

            self.cursor.execute(
                """
                INSERT OR REPLACE
                INTO documents
                (
                    url,
                    title,
                    content,
                    html_file
                )
                VALUES
                (?, ?, ?, ?)
                """,
                (
                    url,
                    title,
                    content,
                    html_file
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
            content
        FROM documents
        WHERE id IN ({placeholders})
        """

        with self.lock:

            self.cursor.execute(
                query,
                tuple(doc_ids)
            )

            return self.cursor.fetchall()

    def close(self):
        with self.lock:
            self.conn.close()
