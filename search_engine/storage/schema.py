DOCUMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE,
    title TEXT,
    content TEXT,
    author TEXT,
    doc_type TEXT DEFAULT 'HTML',
    html_file TEXT,
    content_hash TEXT,
    crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    indexed_at TIMESTAMP
);
"""

IMAGES_TABLE = """
CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_url TEXT,
    image_url TEXT UNIQUE,
    alt_text TEXT,
    surrounding_text TEXT,
    page_title TEXT,
    width INTEGER,
    height INTEGER,
    file_hash TEXT,
    file_size INTEGER,
    local_path TEXT,
    downloaded_at TIMESTAMP,
    crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    indexed_at TIMESTAMP
);
"""

LINKS_TABLE = """
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url TEXT,
    target_url TEXT,
    UNIQUE(source_url, target_url)
);
"""

QUERY_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS query_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    result_count INTEGER,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

QUERY_CACHE_TABLE = """
CREATE TABLE IF NOT EXISTS query_cache (
    query TEXT PRIMARY KEY,
    response_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""