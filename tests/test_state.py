from ccreader.state import Store, decode, encode


def test_encode_roundtrip():
    obj = {"a": ["Tiếng Việt", 1]}
    data = encode(obj)
    assert b"Ti" not in data
    assert decode(data) == obj


def test_bookmark_and_cache(sample_txt, tmp_path):
    store = Store()
    book = store.open_book(sample_txt)
    store.set_bookmark(book.book_id, 2, 5)
    assert Store().get_bookmark(book.book_id) == (2, 5)
    # last book can be reopened from the cache without the file
    again = Store().open_book(None)
    assert again == book
    # nothing on disk reveals the title or file name
    for f in (tmp_path / "cache").iterdir():
        assert "ngon" not in f.name and "hai" not in f.name
        assert "Mũi Gió".encode() not in f.read_bytes()
