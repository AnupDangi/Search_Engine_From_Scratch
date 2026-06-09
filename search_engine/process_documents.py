# process_documents.py

import json
from pathlib import Path

from parser.parser import HTMLParser
from storage.database import Database


RAW_HTML_DIR = Path("data/raw_html")

parser = HTMLParser()

db = Database()


def load_metadata():

    metadata_file = (
        RAW_HTML_DIR /
        "metadata.json"
    )

    with open(
        metadata_file,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def process_documents():

    metadata = load_metadata()

    print(
        f"Loaded metadata for {len(metadata)} pages."
    )

    inserted = 0

    for doc_id, details in metadata.items():

        url = details["url"]

        html_file = details["html_file"]

        html_path = (
            RAW_HTML_DIR /
            html_file
        )

        if not html_path.exists():

            print(
                f"Missing file: {html_file}"
            )

            continue

        with open(
            html_path,
            "r",
            encoding="utf-8"
        ) as f:

            html = f.read()

        parsed = parser.parse(html)

        title = parsed["title"]

        content = parsed["content"]

        if len(content) < 200:

            continue

        db.insert_document(
            url=url,
            title=title,
            content=content,
            html_file=html_file
        )

        inserted += 1

        print(
            f"[INSERTED] {title[:60]}"
        )

    print(
        f"\nInserted {inserted} documents."
    )

    print(
        f"Database now contains "
        f"{db.count_documents()} documents."
    )

    db.close()


if __name__ == "__main__":

    process_documents()