DOCUMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS documents (

    id INTEGER PRIMARY KEY,

    url TEXT UNIQUE,

    title TEXT,

    content TEXT,

    html_file TEXT,

    crawled_at TIMESTAMP
);
"""