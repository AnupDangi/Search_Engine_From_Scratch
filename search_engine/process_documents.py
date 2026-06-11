# process_documents.py

import json
import hashlib
from pathlib import Path
import datetime
import mimetypes
from urllib.parse import urlparse
import requests
import pypdf
from concurrent.futures import ThreadPoolExecutor, as_completed

from parser.parser import HTMLParser
from storage.database import Database

RAW_HTML_DIR = Path("data/raw_html")
STORAGE_PDF_DIR = Path("storage/pdfs")
STORAGE_IMG_DIR = Path("storage/images")

DOWNLOAD_IMAGES = True

parser = HTMLParser()

def load_metadata():
    metadata_file = RAW_HTML_DIR / "metadata.json"
    with open(metadata_file, "r", encoding="utf-8") as f:
        return json.load(f)

def download_image_file(image_url):
    # Wikimedia requires a descriptive User-Agent — generic ones get 429
    headers = {
        "User-Agent": "MiniSearchBot/1.0 (https://github.com/AnupDangi/Search_Engine_From_Scratch; contact@minisearch.local) Python/requests"
    }
    # Skip tiny icon images (SVG icons, small PNGs used as UI decorations)
    low = image_url.lower()
    if any(skip in low for skip in ["/favicon", "icon", "logo", "badge", "button", "arrow", "sprite"]):
        skip_ext = Path(urlparse(image_url).path).suffix.lower()
        if skip_ext in {".svg", ".ico", ".gif"}:
            return None

    try:
        response = requests.get(image_url, headers=headers, timeout=10)
        response.raise_for_status()
        content = response.content

        # Skip tiny files (< 2KB) — likely icons/spacers
        if len(content) < 2048:
            return None

        file_hash = hashlib.sha256(content).hexdigest()
        file_size = len(content)

        path = urlparse(image_url).path
        ext = Path(path).suffix.lower()
        if not ext:
            content_type = response.headers.get("Content-Type", "")
            ext = mimetypes.guess_extension(content_type.split(";")[0]) or ".png"

        if not ext.startswith("."):
            ext = f".{ext}"

        STORAGE_IMG_DIR.mkdir(parents=True, exist_ok=True)
        local_path = f"storage/images/{file_hash}{ext}"

        dest_path = Path(local_path)
        if not dest_path.exists():
            with open(dest_path, "wb") as f:
                f.write(content)

        downloaded_at = datetime.datetime.now().isoformat()
        return file_hash, file_size, local_path, downloaded_at

    except Exception as e:
        print(f"[ERROR] Failed to download image {image_url}: {e}")
        return None

def _process_pdf_task(db: Database, url: str, html_file: str):
    pdf_path = STORAGE_PDF_DIR / html_file
    if not pdf_path.exists():
        return {"status": "missing"}

    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        file_hash = hashlib.sha256(pdf_bytes).hexdigest()

        with db.lock:
            db.cursor.execute("SELECT content_hash FROM documents WHERE url = ?", (url,))
            row = db.cursor.fetchone()
            existing_hash = row[0] if row else None

        if existing_hash == file_hash:
            return {"status": "skipped", "type": "doc"}

        reader = pypdf.PdfReader(pdf_path)
        content_list = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                content_list.append(text)
        content = " ".join(content_list).strip()

        if len(content) < 50:
            return {"status": "skipped_length"}

        author = None
        title = None
        if reader.metadata:
            author = reader.metadata.get("/Author")
            title = reader.metadata.get("/Title")

        if not title or not isinstance(title, str) or not title.strip():
            title = Path(html_file).stem.replace("_", " ").replace("-", " ").title()
        else:
            title = title.strip()

        if not author or not isinstance(author, str) or not author.strip():
            author = None
        else:
            author = author.strip()

        db.insert_document(
            url=url,
            title=title,
            content=content,
            html_file=html_file,
            content_hash=file_hash,
            author=author,
            doc_type='PDF'
        )
        return {"status": "inserted", "type": "doc"}

    except Exception as e:
        print(f"[ERROR] Failed to process PDF {html_file}: {e}")
        return {"status": "error"}

def _process_html_task(db: Database, url: str, html_file: str):
    html_path = RAW_HTML_DIR / html_file
    if not html_path.exists():
        return {"status": "missing"}

    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        parsed = parser.parse(html, url)
        title = parsed["title"]
        heading = parsed.get("heading", "")
        meta_desc = parsed.get("meta_description", "")
        content = parsed["content"]

        # Prepend meta description so snippet generator can find it easily
        if meta_desc and meta_desc not in content:
            content = meta_desc + " " + content

        if len(content) < 200:
            return {"status": "skipped_length"}

        content_str = f"{title}\n{content}"
        content_hash = hashlib.sha256(content_str.encode("utf-8")).hexdigest()

        with db.lock:
            db.cursor.execute("SELECT content_hash FROM documents WHERE url = ?", (url,))
            row = db.cursor.fetchone()
            existing_hash = row[0] if row else None

        result = {"status": "skipped", "type": "doc", "images_inserted": 0, "images_skipped": 0}

        if existing_hash != content_hash:
            db.insert_document(
                url=url,
                title=title,
                content=content,
                html_file=html_file,
                content_hash=content_hash,
                author=None,
                doc_type='HTML',
                heading=heading or None,
            )
            result["status"] = "inserted"

        # Insert images incrementally
        for img in parsed.get("images", []):
            img_url = img["image_url"]
            alt = img["alt_text"]
            surr = img["surrounding_text"]
            w = img["width"]
            h = img["height"]

            with db.lock:
                db.cursor.execute(
                    "SELECT alt_text, surrounding_text, page_title, width, height, file_hash FROM images WHERE image_url = ?",
                    (img_url,)
                )
                img_row = db.cursor.fetchone()
                
            img_metadata_changed = True
            existing_download_info = None

            if img_row:
                if (img_row[0] == alt and 
                    img_row[1] == surr and 
                    img_row[2] == title and 
                    img_row[3] == w and 
                    img_row[4] == h):
                    img_metadata_changed = False
                
                if img_row[5]:
                    with db.lock:
                        db.cursor.execute(
                            "SELECT file_hash, file_size, local_path, downloaded_at FROM images WHERE image_url = ?",
                            (img_url,)
                        )
                        existing_download_info = db.cursor.fetchone()

            file_hash, file_size, local_path, downloaded_at = None, None, None, None
            download_performed = False

            if DOWNLOAD_IMAGES:
                if existing_download_info:
                    file_hash, file_size, local_path, downloaded_at = existing_download_info
                else:
                    down_res = download_image_file(img_url)
                    if down_res:
                        file_hash, file_size, local_path, downloaded_at = down_res
                        download_performed = True

            if img_metadata_changed or download_performed:
                db.insert_image(
                    page_url=url,
                    image_url=img_url,
                    alt_text=alt,
                    surrounding_text=surr,
                    page_title=title,
                    width=w,
                    height=h,
                    file_hash=file_hash,
                    file_size=file_size,
                    local_path=local_path,
                    downloaded_at=downloaded_at
                )
                result["images_inserted"] += 1
            else:
                result["images_skipped"] += 1

        return result

    except Exception as e:
        print(f"[ERROR] Failed to process HTML {html_file}: {e}")
        return {"status": "error"}

def process_documents():
    db = Database()
    try:
        metadata = load_metadata()
    except FileNotFoundError:
        print("Metadata not found. Skipping document processing.")
        return

    print(f"Loaded metadata for {len(metadata)} pages.")

    inserted_docs = 0
    skipped_docs = 0
    inserted_imgs = 0
    skipped_imgs = 0

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for doc_id, details in metadata.items():
            url = details["url"]
            html_file = details["html_file"]
            is_pdf = details.get("is_pdf", False)

            if is_pdf:
                futures.append(executor.submit(_process_pdf_task, db, url, html_file))
            else:
                futures.append(executor.submit(_process_html_task, db, url, html_file))

        for future in as_completed(futures):
            res = future.result()
            if res.get("status") == "inserted":
                inserted_docs += 1
            elif res.get("status") == "skipped":
                skipped_docs += 1
            
            if "images_inserted" in res:
                inserted_imgs += res["images_inserted"]
            if "images_skipped" in res:
                skipped_imgs += res["images_skipped"]

    print(f"\nProcessed documents: inserted/updated {inserted_docs}, skipped {skipped_docs}.")
    print(f"Processed images: inserted/updated {inserted_imgs}, skipped {skipped_imgs}.")
    print(f"Database now contains {db.count_documents()} documents.")

    db.close()

if __name__ == "__main__":
    process_documents()