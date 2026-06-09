import sqlite3

from storage.schema import DOCUMENTS_TABLE


class Database:

    def __init__(
        self,
        db_path="data/search.db"
    ):

        self.conn = sqlite3.connect(
            db_path
        )

        self.cursor = self.conn.cursor()

        self.initialize()

    def initialize(self):

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
        
        self.cursor.execute(
            """
            SELECT COUNT(*)
            FROM documents
            """
        )

        return self.cursor.fetchone()[0]

    def get_all_documents(self):

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

    def close(self):
        self.conn.close()
