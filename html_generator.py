"""
html_generator.py  —  TXT → HTML

Supported TXT formats
─────────────────────
Format A  (brackets):
    [Batch Thumbnail] Batch Name : https://img.jpg
    [Subject]  Title : https://url

Format B  (pipe-separated, no brackets):
    Class-01 | Eng | Introduction : https://video.m3u8
    Voice Detecting Errors : https://file.pdf
    Class-30 | Tense : https://youtube.com/embed/xxx

Format C  (mixed – both in same file)
"""

import os
import re
from collections import OrderedDict

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "subject_template.html")


# ── URL type classifier ────────────────────────────────────────────────────────
def _url_type(url: str) -> str:
    u = url.lower()
    if (u.endswith(".pdf") or "/pdfs/" in u or "class-attachment" in u):
        return "pdf"
    if (".m3u8" in u or ".mp4" in u or "brightcove" in u
            or "cloudfront" in u or "edge.api" in u
            or "recordedmp4" in u or "selectionwaylive" in u
            or "youtube.com" in u or "youtu.be" in u):
        return "video"
    return "other"


# ── Infer subject from pipe-separated title ────────────────────────────────────
def _infer_subject(title: str, url: str) -> str:
    """
    'Class-01 | Eng | Introduction' → 'Eng'
    'Class-30 | Tense'              → 'Tense'
    'Voice Detecting Errors'        → 'PDFs' / 'Videos' (from URL)
    """
    parts = [p.strip() for p in title.split("|")]
    if len(parts) >= 3:
        return parts[1]
    if len(parts) == 2:
        candidate = parts[1].strip()
        if len(candidate) > 1 and not candidate.isdigit():
            return candidate
    t = _url_type(url)
    return {"pdf": "PDFs", "video": "Videos"}.get(t, "Others")


# ── Batch name from filename ───────────────────────────────────────────────────
def _batch_from_filename(fname: str) -> str:
    """'Eng_Spl___Live_VOD_-33_.txt' → 'Eng Spl Live VOD -33'"""
    base = os.path.splitext(os.path.basename(fname))[0]
    name = re.sub(r'[_]+', ' ', base).strip()
    name = re.sub(r'\s+', ' ', name)
    return name


# ══════════════════════════════════════════════════════════════════════════════
def parse_txt(text: str, filename: str = "") -> tuple[str, OrderedDict]:
    """
    Returns (batch_name, subjects_ordered_dict).
    subjects = { subject_name: {videos:[], pdfs:[], others:[]} }
    """
    batch_name = ""
    subjects: OrderedDict = OrderedDict()

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        # Split on last " : https?://"
        m = re.search(r'\s*:\s*(https?://\S+)\s*$', line)
        if not m:
            continue

        url   = m.group(1).strip()
        title = line[:m.start()].strip()

        # ── Format A: [Subject] Title ─────────────────────────────────────────
        bracket = re.match(r'^\[(.+?)\]\s*(.*)$', title)
        if bracket:
            topic = bracket.group(1).strip()
            name  = bracket.group(2).strip()

            if topic.lower() in ("batch thumbnail", "thumbnail"):
                if not batch_name:          # first one wins
                    batch_name = name
                continue

            subject = topic
            title   = name or topic

        # ── Format B: no brackets ─────────────────────────────────────────────
        else:
            subject = _infer_subject(title, url)

        if subject not in subjects:
            subjects[subject] = {"videos": [], "pdfs": [], "others": []}

        bucket = _url_type(url) + "s"       # 'videos' / 'pdfs' / 'others'
        subjects[subject][bucket].append((title, url))

    # Fallback batch name from filename
    if not batch_name:
        batch_name = _batch_from_filename(filename) if filename else "Batch"

    return batch_name, subjects


# ── HTML helpers ───────────────────────────────────────────────────────────────
def _esc(t: str) -> str:
    return (t.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace("'", "&#39;").replace('"', "&quot;"))


def _subjects_html(subjects: OrderedDict) -> str:
    return "".join(
        f'<div class="subject-folder" data-subject="{_esc(s.lower())}" '
        f'onclick="openFolder({i})">📁 {_esc(s)}</div>'
        for i, s in enumerate(subjects)
    )


def _folders_html(subjects: OrderedDict) -> str:
    parts = []
    for i, (subj, data) in enumerate(subjects.items()):
        videos = data.get("videos", [])
        pdfs   = data.get("pdfs",   [])
        others = data.get("others", [])

        def video_link(t, url):
            ext = "m3u8" if ".m3u8" in url.lower() else "mp4"
            return (
                f'<a href="#" onclick="playVideo(&#39;{url}&#39;,&#39;{ext}&#39;)" '
                f'class="video-item">{_esc(t)}</a>'
            )

        v_html = "".join(video_link(t, u) for t, u in videos) \
                 or "<p class='empty-message'>No videos available</p>"
        p_html = "".join(
            f'<a href="{u}" target="_blank" class="pdf-item">📄 {_esc(t)}</a>'
            for t, u in pdfs
        ) or "<p class='empty-message'>No PDFs available</p>"
        o_html = "".join(
            f'<a href="{u}" target="_blank" class="other-item">{_esc(t)}</a>'
            for t, u in others
        ) or "<p class='empty-message'>No other files available</p>"

        parts.append(f"""
        <div id="folder-{i}" class="folder-content" data-subject-index="{i}">
            <div class="folder-header">
                <button class="back-btn" onclick="closeFolder()">🔙 Back</button>
                <h2>{_esc(subj)}</h2>
            </div>
            <div class="folder-search">
                <input type="text" id="folder-search-{i}" class="folder-search-input"
                       placeholder="🔍 Search in this subject..." onkeyup="searchInFolder({i})">
            </div>
            <div class="tab-container">
                <div class="tab" onclick="showCategory('videos-{i}')">📹 Videos ({len(videos)})</div>
                <div class="tab" onclick="showCategory('pdfs-{i}')">📄 PDFs ({len(pdfs)})</div>
                <div class="tab" onclick="showCategory('others-{i}')">📁 Others ({len(others)})</div>
            </div>
            <div id="videos-{i}" class="category-content">
                <h3>📹 Videos</h3>
                <div class="links-list" id="videos-list-{i}">{v_html}</div>
                <div id="videos-empty-{i}" class="category-empty-message" style="display:none;">❌ No matching videos found</div>
            </div>
            <div id="pdfs-{i}" class="category-content" style="display:none;">
                <h3>📄 PDFs</h3>
                <div class="links-list" id="pdfs-list-{i}">{p_html}</div>
                <div id="pdfs-empty-{i}" class="category-empty-message" style="display:none;">❌ No matching PDFs found</div>
            </div>
            <div id="others-{i}" class="category-content" style="display:none;">
                <h3>📁 Other Files</h3>
                <div class="links-list" id="others-list-{i}">{o_html}</div>
                <div id="others-empty-{i}" class="category-empty-message" style="display:none;">❌ No matching files found</div>
            </div>
        </div>
""")
    return "".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
def txt_to_html(txt_text: str, filename: str = "") -> tuple[str, str]:
    """
    Convert raw TXT → (batch_name, html_string).
    Pass filename so batch name can be inferred when not in file.
    """
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

    batch_name, subjects = parse_txt(txt_text, filename)

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    html = (
        template
        .replace("{{batch_name}}",        batch_name)
        .replace("{{subjects_content}}",  _subjects_html(subjects))
        .replace("{{folders_content}}",   _folders_html(subjects))
    )
    return batch_name, html
