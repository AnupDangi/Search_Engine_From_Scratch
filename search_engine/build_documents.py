import json
from pathlib import Path

from parser.parser import HTMLParser


RAW_HTML_DIR = Path("data/raw_html")
PARSED_DOC_DIR = Path("data/parsed_docs")

PARSED_DOC_DIR.mkdir(
    parents=True,
    exist_ok=True
)

parser = HTMLParser()


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

    for item in metadata:

        doc_id = item["id"]
        url = item["url"]
        html_file = item["html_file"]

        html_path = (
            RAW_HTML_DIR /
            html_file
        )

        if not html_path.exists():
            continue

        with open(
            html_path,
            "r",
            encoding="utf-8"
        ) as f:

            html = f.read()

        parsed = parser.parse(html)

        document = {
            "id": doc_id,
            "url": url,
            "title": parsed["title"],
            "content": parsed["content"]
        }

        output_file = (
            PARSED_DOC_DIR /
            f"{doc_id}.json"
        )

        with open(
            output_file,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                document,
                f,
                ensure_ascii=False,
                indent=4
            )

        print(
            f"[PARSED] {doc_id}"
        )


if __name__ == "__main__":
    process_documents()