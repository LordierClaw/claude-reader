import unicodedata

from ebooklib import epub

from ccreader.book import (
    Book,
    load_book,
    parse_txt,
    split_long,
    split_paragraphs,
    split_sentences,
)


def test_sample_txt_chapters(sample_txt):
    book = load_book(sample_txt)
    titles = [c.title for c in book.chapters]
    assert titles[0] == "Preface"
    assert titles[1].startswith("Chương 1")
    assert len([t for t in titles if t.startswith("Chương")]) == 4
    assert all(c.paragraphs for c in book.chapters)


def test_chapter_regex_english_and_custom():
    text = "Intro line\n\nChapter 1\n\nA.\n\nB.\n\nChapter 2 The End\n\nC.\n"
    chapters = parse_txt(text)
    assert [c.title for c in chapters] == ["Preface", "Chapter 1", "Chapter 2 The End"]
    assert chapters[1].paragraphs == ["A.", "B."]
    custom = parse_txt("## One\nx\n## Two\ny\n", chapter_regex=r"^## \w+")
    assert [c.title for c in custom] == ["## One", "## Two"]


def test_no_headings_makes_pseudo_chapters():
    text = "\n".join(f"Line {i}." for i in range(130))
    chapters = parse_txt(text)
    assert len(chapters) == 3
    assert chapters[0].title == "Part 1"


def test_line_per_paragraph_vs_hard_wrapped():
    assert split_paragraphs("One.\nTwo.\nThree.\n") == ["One.", "Two.", "Three."]
    wrapped = "This is a hard\nwrapped paragraph.\n\nSecond\none.\n"
    assert split_paragraphs(wrapped) == ["This is a hard wrapped paragraph.", "Second one."]


def test_split_long_only_at_sentence_boundaries():
    sentences = [f"Câu số {i} kết thúc ở đây." for i in range(80)]
    para = " ".join(sentences)
    chunks = split_long(para, max_chars=300, target=200)
    assert len(chunks) > 1
    assert " ".join(chunks) == para
    for chunk in chunks:
        assert chunk.endswith(".")
    assert split_long("short.") == ["short."]


def test_split_sentences_handles_quotes_and_ellipsis():
    assert split_sentences('Anh hỏi: "Đi đâu?" Cô im lặng… Rồi đi.') == [
        'Anh hỏi: "Đi đâu?"', "Cô im lặng…", "Rồi đi."]


def test_nfc_normalization():
    decomposed = unicodedata.normalize("NFD", "Chương 1\n\nTiếng Việt.")
    chapters = parse_txt(decomposed)
    assert chapters[0].title == "Chương 1"
    assert chapters[0].paragraphs == [unicodedata.normalize("NFC", "Tiếng Việt.")]


def _make_epub(path):
    book = epub.EpubBook()
    book.set_identifier("t")
    book.set_title("T")
    items = []
    for i in (1, 2):
        it = epub.EpubHtml(title=f"Chapter {i}", file_name=f"c{i}.xhtml")
        it.content = f"<h1>Heading {i}</h1><p>First {i}.</p><p>Second <b>{i}</b>.</p>"
        book.add_item(it)
        items.append(it)
    book.toc = items
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]
    epub.write_epub(str(path), book)


def test_epub_spine_chapters(tmp_path):
    path = tmp_path / "b.epub"
    _make_epub(path)
    book = load_book(path)
    assert book.kind == "epub"
    assert [c.title for c in book.chapters] == ["Chapter 1", "Chapter 2"]
    assert book.chapters[1].paragraphs == ["First 2.", "Second 2 ."]


def test_positions_and_progress(sample_txt):
    book = load_book(sample_txt)
    assert book.clamp(99, 99) == (len(book.chapters) - 1, len(book.chapters[-1].paragraphs) - 1)
    assert book.next_pos(0, len(book.chapters[0].paragraphs) - 1) == (1, 0)
    last = len(book.chapters) - 1
    assert book.next_pos(last, len(book.chapters[last].paragraphs) - 1) is None
    assert book.chapter_progress(1, 3) == 4 / len(book.chapters[1].paragraphs)
    assert Book.from_dict(book.to_dict()) == book
