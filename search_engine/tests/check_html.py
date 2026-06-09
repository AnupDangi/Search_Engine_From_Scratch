# tests/check_html.py

with open(
    "data/raw_html/1.html",
    "r",
    encoding="utf-8"
) as f:

    text = f.read()

print(text[:5000])