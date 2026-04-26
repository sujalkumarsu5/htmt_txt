"""
html_to_txt.py  —  HTML → TXT

Handles ALL known HTML formats:

  Style A  — subject_template.html
             (folder-content divs, video-item / pdf-item / other-item classes)

  Style B  — tab-based crwill / Maths-Spl style
             (videos-tab / pdfs-tab, list-item class, onclick)

  Style C  — JS CONFIG object with base64-encoded URLs
             (GS_special_2 style — JSON data inside <script>)

  Style E  — CareerWill tab format
             (tab-content id='video'/'pdf'/'other', card video/pdf/other divs)

  Style F  — XOR + Base64 encrypted payload (Maths Special VOD style)
             <script> with `const encodedContent = '...'` and a
             `generateSecretKey()` function. The script does:
                base64 -> xor(key) -> base64 -> utf8
             We replicate that in Python and recurse on the inner HTML.

  Style G  — JS data array (SPARTAN style)
             <script> with `const data = [{topic, items: [{n, id, d}]}]`
             and an HTML render template that builds URLs from `${i.id}`.

  Style H  — subject-header / subject-content layout
             (used inside decrypted Style-F HTML; `.subject-header` +
              `.subject-content` containers with `.card` items —
              videos via <a class="media-title">, PDFs via
              <span class="media-title"> + chrome <button window.open(...)>)

  Style D  — Generic fallback
             (any HTML with onclick / href containing direct URLs)
"""

import re
import base64
from bs4 import BeautifulSoup


# ── Base64 helpers ─────────────────────────────────────────────────────────────
def _b64_decode(s: str) -> str:
    try:
        padded = s + "=" * (-len(s) % 4)
        result = base64.b64decode(padded).decode("utf-8")
        return result
    except Exception:
        return s


def _is_b64_url(s: str) -> bool:
    if not s or len(s) < 20:
        return False
    try:
        padded = s + "=" * (-len(s) % 4)
        decoded = base64.b64decode(padded).decode("utf-8")
        return decoded.startswith("http")
    except Exception:
        return False


# ── Extract URL from onclick string ───────────────────────────────────────────
def _onclick_url(onclick: str) -> str:
    for pat in [
        r"playVideo\(['\"]([^'\"]+)['\"]",
        r"playVideo\((?:&#39;|&quot;)([^'\"&]+)(?:&#39;|&quot;)",
        r"openPDF\(['\"]([^'\"]+)['\"]\)",
        r"window\.open\(['\"]([^'\"]+)['\"]",
    ]:
        m = re.search(pat, onclick)
        if m:
            return m.group(1).strip()
    return ""


def _clean_title(raw: str) -> str:
    """Strip leading icons, [Subject] prefix and trailing colon from card text."""
    t = raw.strip()
    # Strip common leading icons / emoji
    t = re.sub(r'^[\u2600-\u27BF\U0001F000-\U0001FFFF\u25B6\uFE0F\s]+', '', t).strip()
    m = re.match(r'^\[.+?\]\s*(.*)', t)
    if m:
        t = m.group(1).strip()
    t = t.rstrip(":").strip()
    return t or raw.strip()


def _clean_subject(header_text: str) -> str:
    """Strip leading folder/icon and trailing count like ' (163)' from header."""
    t = re.sub(r'\s*\(\d+\)\s*$', '', header_text).strip()
    t = re.sub(r'^[\u2600-\u27BF\U0001F000-\U0001FFFF\s]+', '', t).strip()
    return t


# ══════════════════════════════════════════════════════════════════════════════
# STYLE F — XOR + Base64 decryption (Maths Special VOD style)
# ══════════════════════════════════════════════════════════════════════════════
def _try_decrypt_xor_payload(html_text: str):
    """
    Detect and decrypt the XOR+Base64 wrapped payload used by the
    'Maths Special VOD' style HTML files. Returns inner HTML string
    on success, or None if this style is not present / decryption fails.
    """
    enc_match = re.search(
        r"const\s+encodedContent\s*=\s*['\"]([A-Za-z0-9+/=\s\\n\\r]+)['\"]",
        html_text,
    )
    if not enc_match:
        return None

    encoded = re.sub(r'[^A-Za-z0-9+/=]', '', enc_match.group(1))
    if len(encoded) < 100:
        return None

    func_match = re.search(
        r"function\s+generateSecretKey\s*\(\s*\)\s*\{([\s\S]*?)\}",
        html_text,
    )
    if not func_match:
        return None
    body = func_match.group(1)

    parts: dict[str, str] = {}
    for m in re.finditer(
        r'(?:let|const|var)\s+(\w+)\s*=\s*["\']([^"\']*)["\']',
        body,
    ):
        parts[m.group(1)] = m.group(2)

    fk = re.search(r'finalKey\s*=\s*([^;]+);', body)
    if not fk:
        return None
    expr = fk.group(1).strip()

    key = ""
    for tok in expr.split("+"):
        tok = tok.strip()
        rev_m = re.match(
            r'(\w+)\.split\(["\'][^"\']*["\']\)\.reverse\(\)\.join\(["\'][^"\']*["\']\)',
            tok,
        )
        if rev_m:
            key += parts.get(rev_m.group(1), "")[::-1]
        elif tok in parts:
            key += parts[tok]
        else:
            lit = re.match(r'^["\']([^"\']*)["\']$', tok)
            if lit:
                key += lit.group(1)

    if not key:
        return None

    try:
        encoded_padded = encoded + "=" * (-len(encoded) % 4)
        xor_bytes = base64.b64decode(encoded_padded)
        keyb = key.encode("latin-1")
        out = bytearray(len(xor_bytes))
        for i, b in enumerate(xor_bytes):
            out[i] = b ^ keyb[i % len(keyb)]
        b64_str = out.decode("latin-1", errors="ignore")
        cleaned = re.sub(r'[^A-Za-z0-9+/=]', '', b64_str)
        cleaned += "=" * (-len(cleaned) % 4)
        inner_bytes = base64.b64decode(cleaned)
        inner = inner_bytes.decode("utf-8", errors="ignore")
        if "<" not in inner:
            return None
        return inner
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# STYLE G — JS data array (SPARTAN style)
# ══════════════════════════════════════════════════════════════════════════════
def _pick_url_template(html_text: str):
    """
    Find the best URL template that uses ${i.id} (or ${item.id}).
    Prefer 720p when multiple resolutions are emitted side by side.
    """
    # Collect all template strings that interpolate the id
    candidates: list[str] = []
    for m in re.finditer(r'`(https?://[^`]*\$\{(?:i|item)\.id\}[^`]*)`', html_text):
        candidates.append(m.group(1))
    for m in re.finditer(r'href\s*=\s*"(https?://[^"]*\$\{(?:i|item)\.id\}[^"]*)"', html_text):
        candidates.append(m.group(1))
    for m in re.finditer(r"href\s*=\s*'(https?://[^']*\$\{(?:i|item)\.id\}[^']*)'", html_text):
        candidates.append(m.group(1))

    if not candidates:
        return None

    # Prefer 720, then 480, then 360, else first
    for q in ("720", "480", "360"):
        for c in candidates:
            if f"/{q}/" in c or f"_{q}" in c or f"={q}" in c:
                return c
    return candidates[0]


def _try_parse_js_data_array(html_text: str):
    """
    SPARTAN style: a JS literal array `const data = [...]` with topic+items
    and a render template that builds URLs from `${i.id}`.
    Returns a list of "[Topic] Title : URL" lines or None.
    """
    data_match = re.search(
        r'(?:const|let|var)\s+data\s*=\s*(\[[\s\S]*?\])\s*;',
        html_text,
    )
    if not data_match:
        return None
    arr_text = data_match.group(1)
    if 'topic' not in arr_text or 'items' not in arr_text:
        return None

    url_template = _pick_url_template(html_text)
    if not url_template:
        return None

    lines: list[str] = []
    for tm in re.finditer(
        r'\{\s*topic\s*:\s*["\']([^"\']+)["\']\s*,\s*items\s*:\s*\[([\s\S]*?)\]\s*\}',
        arr_text,
    ):
        topic_raw = tm.group(1).strip()
        items_text = tm.group(2)
        topic_label = re.sub(r'^[^\w]+\s*', '', topic_raw).strip() or topic_raw

        for im in re.finditer(
            r'\{\s*n\s*:\s*["\']([^"\']+)["\']\s*,\s*id\s*:\s*["\']([^"\']+)["\']\s*'
            r'(?:,\s*d\s*:\s*["\']([^"\']*)["\'])?\s*\}',
            items_text,
        ):
            name = im.group(1).strip()
            vid_id = im.group(2).strip()
            date = (im.group(3) or "").strip()
            url = url_template.replace("${i.id}", vid_id).replace("${item.id}", vid_id)
            title = f"{name} | {date}" if date else name
            lines.append(f"[{topic_label}] {title} : {url}")

    return lines or None


# ══════════════════════════════════════════════════════════════════════════════
# STYLE H — subject-header / subject-content layout
# ══════════════════════════════════════════════════════════════════════════════
def _parse_subject_header_layout(soup) -> list[str]:
    """
    Pattern (used inside decrypted Maths Special VOD HTML):

      <div class="subject">
        <div class="subject-header" onclick="toggleSubject('video_Advance', ...)">
          📂 Advance (241)
        </div>
        <div class="subject-content" id="subject-video_Advance">
          <div class="card">
            <a href="URL" class="media-title" onclick="playVideo('URL')">▶️ TITLE</a>
          </div>
          <div class="card pdf-card">
            <span class="media-title" onclick="togglePdfOptions(...)">📗 TITLE</span>
            <button class="pdf-open chrome" onclick="window.open('URL','_blank')">...</button>
          </div>
        </div>
      </div>
    """
    headers = soup.find_all("div", class_="subject-header")
    if not headers:
        return []

    lines: list[str] = []
    for sh in headers:
        onclick = sh.get("onclick", "")
        m = re.search(r"toggleSubject\(['\"]([^'\"]+)['\"]", onclick)

        # Try to derive a friendly subject name from id (e.g. video_Advance)
        subject_label = ""
        if m:
            sid = m.group(1)
            after_underscore = sid.split("_", 1)[1] if "_" in sid else sid
            subject_label = after_underscore.replace("_", " ").strip()
        if not subject_label:
            subject_label = _clean_subject(sh.get_text(strip=True))

        # Skip pure thumbnail folders (already added via batch thumbnail line)
        if "thumbnail" in subject_label.lower():
            continue

        sc = sh.find_next_sibling("div", class_="subject-content")
        if not sc:
            continue

        for card in sc.find_all("div", class_=re.compile(r"\bcard\b")):
            # Video / link card
            a = card.find("a", class_="media-title")
            if a:
                title = _clean_title(a.get_text(strip=True))
                url = a.get("href", "").strip()
                if not url or url in ("#", "javascript:void(0)"):
                    url = _onclick_url(a.get("onclick", ""))
                if url and title:
                    lines.append(f"[{subject_label}] {title} : {url}")
                continue

            # PDF card (URL is inside one of the <button> onclicks)
            span = card.find("span", class_="media-title")
            if span:
                title = _clean_title(span.get_text(strip=True))
                url = ""
                # Prefer the chrome button (raw URL), then any button
                btn = card.find("button", class_=re.compile(r"chrome"))
                if btn:
                    url = _onclick_url(btn.get("onclick", ""))
                if not url:
                    for b in card.find_all("button"):
                        u = _onclick_url(b.get("onclick", ""))
                        if u:
                            url = u
                            break
                if url and title:
                    lines.append(f"[{subject_label}] {title} : {url}")
                continue

    return lines


# ══════════════════════════════════════════════════════════════════════════════
def html_to_txt(html_text: str) -> tuple[str, str]:
    """Returns (batch_name, txt_string)."""

    # ── Style F runs FIRST: if the file is XOR-encrypted, decrypt and recurse ─
    decrypted = _try_decrypt_xor_payload(html_text)
    if decrypted:
        return html_to_txt(decrypted)

    soup = BeautifulSoup(html_text, "html.parser")
    lines: list[str] = []

    # ── Batch name ────────────────────────────────────────────────────────────
    batch_name = ""
    title_tag = soup.find("title")
    if title_tag:
        raw = title_tag.get_text(strip=True)
        batch_name = re.sub(r'_+', ' ', raw).strip()
    if not batch_name:
        for sel in ["h1", ".title-box h1", ".header h1", ".batch-title", "h2"]:
            el = soup.select_one(sel)
            if el:
                batch_name = el.get_text(strip=True)
                break
    if not batch_name:
        batch_name = "Batch"

    # ── Thumbnail URL ─────────────────────────────────────────────────────────
    thumbnail_url = ""
    for a in soup.find_all("a"):
        t = a.get_text(strip=True).lower()
        if "thumbnail" in t:
            href = a.get("href", "").strip()
            if href and href not in ("#", ""):
                thumbnail_url = href
                break
    if not thumbnail_url:
        og = soup.find("meta", property="og:image")
        if og:
            thumbnail_url = og.get("content", "")

    # ══════════════════════════════════════════════════════════════════════════
    # STYLE G — JS data array (SPARTAN style)
    # Try BEFORE BS4-driven styles because the data lives in <script>.
    # ══════════════════════════════════════════════════════════════════════════
    spartan_lines = _try_parse_js_data_array(html_text)
    if spartan_lines:
        if thumbnail_url:
            lines.append(f"[Batch Thumbnail] {batch_name} : {thumbnail_url}")
        lines.extend(spartan_lines)
        return batch_name, "\n".join(lines)

    # Standard thumbnail line (kept after Style G so we don't insert a fake URL)
    lines.append(
        f"[Batch Thumbnail] {batch_name} : "
        f"{thumbnail_url or 'https://example.com/thumbnail.jpg'}"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # STYLE C — JS CONFIG with base64 URLs
    # ══════════════════════════════════════════════════════════════════════════
    b64_items = re.findall(
        r'\{"title"\s*:\s*"([^"]+)"\s*,\s*"link"\s*:\s*"([A-Za-z0-9+/]{20,}=*)"\s*,\s*"type"\s*:\s*"([^"]+)"\}',
        html_text,
    )

    if b64_items:
        subj_order: list[str] = []
        subj_items: dict[str, list] = {}

        for subj_match in re.finditer(
            r'"([^"]{1,80})":\s*\[(\s*\{[^\]]*?\}[\s,]*)+\]',
            html_text,
        ):
            subj_name = subj_match.group(0).split('"')[1]
            block_items = re.findall(
                r'\{"title"\s*:\s*"([^"]+)"\s*,\s*"link"\s*:\s*"([A-Za-z0-9+/]{20,}=*)"\s*,\s*"type"\s*:\s*"([^"]+)"\}',
                subj_match.group(0),
            )
            if block_items:
                subj_items[subj_name] = block_items
                if subj_name not in subj_order:
                    subj_order.append(subj_name)

        if subj_order:
            for subj in subj_order:
                for title, link, typ in subj_items[subj]:
                    url = _b64_decode(link) if _is_b64_url(link) else link
                    lines.append(f"[{subj}] {title} : {url}")
        else:
            for title, link, typ in b64_items:
                url = _b64_decode(link) if _is_b64_url(link) else link
                subj = "Videos" if typ == "VIDEO" else "PDFs"
                lines.append(f"[{subj}] {title} : {url}")

        return batch_name, "\n".join(lines)

    # ══════════════════════════════════════════════════════════════════════════
    # STYLE H — subject-header / subject-content layout
    # ══════════════════════════════════════════════════════════════════════════
    sh_lines = _parse_subject_header_layout(soup)
    if sh_lines:
        lines.extend(sh_lines)
        return batch_name, "\n".join(lines)

    # ══════════════════════════════════════════════════════════════════════════
    # STYLE E — CareerWill tab format
    # ══════════════════════════════════════════════════════════════════════════
    video_tab = soup.find("div", class_="tab-content", id="video")
    pdf_tab = soup.find("div", class_="tab-content", id="pdf")
    other_tab = soup.find("div", class_="tab-content", id="other")

    if video_tab or pdf_tab:
        tabs = [
            (video_tab, "Videos"),
            (pdf_tab, "PDFs"),
            (other_tab, "Others"),
        ]
        for tab, default_subj in tabs:
            if not tab:
                continue
            for folder in tab.find_all("div", class_="folder"):
                header = folder.find("div", class_="folder-header")
                if header:
                    subject = _clean_subject(header.get_text(strip=True))
                else:
                    subject = default_subj

                if "thumbnail" in subject.lower():
                    continue

                content = folder.find("div", class_="folder-content")
                if not content:
                    continue

                for card in content.find_all("div", class_="card"):
                    raw_text = card.get_text(strip=True)
                    title = _clean_title(raw_text)
                    if not title:
                        continue

                    url = ""
                    parent = card.parent
                    if parent and parent.name == "a":
                        url = parent.get("href", "").strip()
                        if url in ("#", "javascript:void(0)", ""):
                            url = ""

                    if not url:
                        onclick = card.get("onclick", "")
                        url = _onclick_url(onclick)

                    if url:
                        lines.append(f"[{subject}] {title} : {url}")

        return batch_name, "\n".join(lines)

    # ══════════════════════════════════════════════════════════════════════════
    # STYLE A — subject_template.html (folder-content divs)
    # ══════════════════════════════════════════════════════════════════════════
    has_style_a = (
        soup.find(class_="video-item")
        or soup.find(class_="pdf-item")
        or soup.find(class_="other-item")
    )
    if has_style_a:
        folder_divs = soup.find_all("div", class_="folder-content")
        for folder in folder_divs:
            h2 = folder.find("h2")
            subject = h2.get_text(strip=True) if h2 else "Unknown"

            for a in folder.find_all("a", class_="video-item"):
                title = a.get_text(strip=True)
                onclick = a.get("onclick", "")
                url = _onclick_url(onclick)
                if url:
                    lines.append(f"[{subject}] {title} : {url}")

            for a in folder.find_all("a", class_="pdf-item"):
                title = a.get_text(strip=True).lstrip("📄").strip()
                href = a.get("href", "").strip()
                if href and href != "#":
                    lines.append(f"[{subject}] {title} : {href}")

            for a in folder.find_all("a", class_="other-item"):
                title = a.get_text(strip=True)
                href = a.get("href", "").strip()
                if href and href != "#":
                    lines.append(f"[{subject}] {title} : {href}")

        return batch_name, "\n".join(lines)

    # ══════════════════════════════════════════════════════════════════════════
    # STYLE B — tab-based HTML (videos-tab / pdfs-tab, list-item class)
    # ══════════════════════════════════════════════════════════════════════════
    videos_tab = soup.find(id="videos-tab")
    pdfs_tab = soup.find(id="pdfs-tab")

    if videos_tab or pdfs_tab:
        for tab, default_subj in [(videos_tab, "Videos"), (pdfs_tab, "PDFs")]:
            if not tab:
                continue
            for a in tab.find_all("a", class_="list-item"):
                text = a.get_text(strip=True)
                onclick = a.get("onclick", "")
                href = a.get("href", "").strip()

                sm = re.match(r'^\[(.+?)\]\s*(.+)$', text)
                subject = sm.group(1).strip() if sm else default_subj
                title = sm.group(2).strip() if sm else text

                url = _onclick_url(onclick) or (href if href != "#" else "")
                if url:
                    lines.append(f"[{subject}] {title} : {url}")

        return batch_name, "\n".join(lines)

    # ══════════════════════════════════════════════════════════════════════════
    # STYLE D — Generic fallback
    # ══════════════════════════════════════════════════════════════════════════
    seen: set[str] = set()

    for a in soup.find_all("a"):
        text = a.get_text(strip=True)
        onclick = a.get("onclick", "")
        href = a.get("href", "").strip()

        url = _onclick_url(onclick)
        if not url and href and href not in ("#", "javascript:void(0)", ""):
            url = href

        if not url or url in seen:
            continue
        seen.add(url)

        sm = re.match(r'^\[(.+?)\]\s*(.+)$', text)
        if sm:
            subject = sm.group(1).strip()
            title = sm.group(2).strip()
        else:
            ul = url.lower()
            if ".m3u8" in ul or ".mp4" in ul:
                subject = "Videos"
            elif ".pdf" in ul:
                subject = "PDFs"
            else:
                subject = "Others"
            title = text or url.split("/")[-1].split("?")[0]

        if title:
            lines.append(f"[{subject}] {title} : {url}")

    return batch_name, "\n".join(lines)
