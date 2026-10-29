"""Build samples/ngon-hai-dang.epub from the .txt sample (used to try the epub loader).

Usage: python samples/make_epub.py
"""

from pathlib import Path
from xml.sax.saxutils import escape

from ebooklib import epub

from ccreader.book import parse_txt

HERE = Path(__file__).parent


def build(txt: Path, out: Path) -> Path:
    chapters = [c for c in parse_txt(txt.read_text(encoding="utf-8")) if c.title != "Preface"]
    book = epub.EpubBook()
    book.set_identifier("ccreader-sample")
    book.set_title("Người Giữ Đèn Ở Mũi Gió")
    book.set_language("vi")
    items = []
    for i, ch in enumerate(chapters, 1):
        item = epub.EpubHtml(title=ch.title, file_name=f"chap_{i}.xhtml", lang="vi")
        body = "".join(f"<p>{escape(p)}</p>" for p in ch.paragraphs)
        item.content = f"<h1>{escape(ch.title)}</h1>{body}"
        book.add_item(item)
        items.append(item)
    book.toc = items
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]
    epub.write_epub(str(out), book)
    return out


if __name__ == "__main__":
    print(build(HERE / "ngon-hai-dang.txt", HERE / "ngon-hai-dang.epub"))
