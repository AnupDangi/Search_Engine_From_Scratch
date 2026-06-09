# inspect_db.py

import sqlite3

conn = sqlite3.connect("data/search.db")

cursor = conn.cursor()

cursor.execute("""
SELECT title
FROM documents
LIMIT 10
""")

for row in cursor.fetchall():
    print(row[0])

conn.close()