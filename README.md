# claude-reader (`ccreader`)

Trình đọc truyện trong terminal, trông và hoạt động như một phiên Claude Code CLI.
Nội dung truyện được "stream" ra như output của agent, xen kẽ các tool call mờ
(`Read(...)`, `Search(...)`, `Update(...)`) lấy từ một repo code thật của bạn.
Thỉnh thoảng app dừng lại chờ bạn tương tác (duyệt edit, chọn phương án, gõ prompt)
và có boss key để giấu truyện ngay lập tức.

Không dùng mạng. Mọi dữ liệu nằm trên máy.

## Cài đặt

```bash
pipx install .            # hoặc: pip install .
ccreader truyen.epub --repo ~/code/payment-core
# hoặc chạy trực tiếp từ source:
python -m ccreader samples/ngon-hai-dang.txt
```

Cần Python 3.11+. Lần sau chỉ cần `ccreader` (không tham số): app mở lại truyện
đang đọc từ cache, đúng chỗ đã dừng.

Tuỳ chọn dòng lệnh: `--repo PATH`, `--rescan`, `--chapter N`, `--wpm N`, `--instant`,
`--config FILE`, `--init-config`, `--list-chapters`, `--transcript`.

## Phím tắt

| Phím | Tác dụng |
| --- | --- |
| `Space` | Hiện hết đoạn đang stream / bỏ qua lúc chờ / sang lượt mới |
| `Enter` | Gửi prompt (để trống = "continue") |
| `+` / `-` | Tăng / giảm tốc độ đọc (WPM) |
| `Ctrl+T` | Đổi giữa `stream` và `instant` |
| `Esc Esc` | **Boss key**: thu gọn truyện, đổ ra một khối output công việc (test, git log, diff) rồi dừng ở permission prompt. Bấm lại `Esc Esc` hoặc gõ `continue` để đọc tiếp |
| `Ctrl+O` | Transcript: chỉ có truyện, không noise. `j/k`, `PgUp/PgDn`, `g/G`, `[`/`]` đổi chương, `q` thoát |
| `Ctrl+\` | Thoát ngay (alternate screen, không để lại scrollback) |
| `Shift+Tab` | Đổi chế độ hiển thị trên thanh trạng thái (ngụy trang) |
| click | Mở rộng / thu gọn một khối truyện đã collapse |

Lệnh: `/resume` (danh sách chương, ngụy trang thành các phiên làm việc cũ),
`/compact`, `/cost`, `/help`, `/clear`, `/exit`.

Khi được hỏi (permission prompt / câu hỏi chọn phương án), bấm số `1`–`3` hoặc
`↑/↓` + `Enter`; `Esc` = "No". Với prompt trống, gõ phím bất kỳ sẽ "gõ ra" một prompt
có sẵn từng ký tự một, `Enter` để gửi.

Khi terminal mất focus (nếu terminal hỗ trợ focus reporting), boss key tự kích hoạt.

## Cấu hình

`~/.config/ccreader/config.toml` (tạo mẫu bằng `ccreader --init-config`):

```toml
wpm = 250
stream_mode = "stream"          # hoặc "instant"
interaction_min_minutes = 5.0
interaction_max_minutes = 10.0
paragraphs_per_turn = [3, 6]
max_width = 78
repo = "~/code/payment-core"
proc_title = "node"
theme = "dark"                  # "dark" | "light"; màu nền theo terminal
boss_on_blur = true
collapse_previous_turns = true
# chapter_regex = "^(Chương|Chapter)\\s+\\d+"
```

## Riêng tư

- Bookmark (book id, chương, đoạn) được lưu sau mỗi đoạn.
- Cache truyện, bookmark và noise corpus nằm ở `~/.cache/ccreader/`, nén gzip + base64,
  tên file là hash: không có tên truyện hay tên file trong cache.
- Tên tiến trình đổi thành `node` (cấu hình bằng `proc_title`).
- Các lượt cũ chỉ hiện ở dạng thu gọn `⎿ … +N lines`.

## Phát triển

```bash
pip install -e '.[test]'
pytest
```

Mã nguồn trong `ccreader/`: `book.py` (đọc txt/epub, tách chương/đoạn), `state.py`
(cache, bookmark), `noise.py` + `fakes.py` (noise corpus từ repo), `turns.py`
(dựng một lượt agent), `scheduler.py` (lịch tương tác), `boss.py`, và giao diện
Textual trong `main_screen.py`, `transcript.py`, `resume.py`, `widgets.py`.

`samples/ngon-hai-dang.txt` là truyện ngắn mẫu tự viết cho dự án (cùng giấy phép
Apache-2.0 của repo); `samples/make_epub.py` tạo bản `.epub` từ đó.
