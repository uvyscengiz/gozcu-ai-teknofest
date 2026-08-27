"""Teslim dokümanlarını (docs/teslim/*.md) basılabilir PDF'e çevirir.

Neden tarayıcı: diyagramların tamamı ASCII kutu çizimi ve tek şey kritik —
**sütunların kayMAMASI.** Kutu çizim karakterlerinin (`─│┌╔`) ASCII ile aynı
genişlikte olduğu bir monospace font gerekiyor; Consolas bunu garanti ediyor
ve Windows'ta her makinede var. reportlab'ın Platypus akışıyla aynı şeyi
kurmak, tabloları ve satır içi biçimlendirmeyi elde yeniden yazmak demekti.

Neden iki aşama: Chrome CSS sayfalı ortam kenar kutularını (`@bottom-center`)
desteklemiyor, yani sayfa numarası CSS ile konamıyor. Tarayıcı gövdeyi
diziyor, ikinci aşamada reportlab + pypdf altbilgiyi damgalıyor.

    uv run --with markdown --with reportlab --with pypdf \
        python scripts/build-doc-pdf.py docs/teslim/01-*.md
"""

import argparse
import html as html_mod
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from io import BytesIO
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GITHUB = "https://github.com/uvyscengiz/gozcu-ai-teknofest/blob/main"

#: Tarayıcı adayları. Edge Windows 11'de her zaman var; Chrome varsa o da olur.
BROWSERS = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]

FOOTER_LEFT = "Gözcü · Takım FERASET (team37) · TEKNOFEST 2026, 3. Senaryo"

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }

:root {
  --ink:    #14202e;
  --muted:  #5b6b7c;
  --accent: #b84a1f;
  --deep:   #0f4c75;
  --rule:   #d9e0e7;
  --code:   #f5f7f9;
}

* { box-sizing: border-box; }

body {
  font-family: "Segoe UI", "Calibri", sans-serif;
  font-size: 10pt;
  line-height: 1.55;
  color: var(--ink);
  margin: 0;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}

/* ---------------------------------------------------------------- kapak */

.cover { height: 245mm; display: flex; flex-direction: column; }
.cover-rule { height: 6mm; background: var(--deep); border-bottom: 2mm solid var(--accent); }
.cover-body { flex: 1; display: flex; flex-direction: column; justify-content: center; }

.cover .kicker {
  font-size: 9.5pt; letter-spacing: .16em; text-transform: uppercase;
  color: var(--accent); font-weight: 700; margin-bottom: 6mm;
}
.cover h1 {
  font-size: 30pt; line-height: 1.15; font-weight: 700;
  margin: 0 0 5mm 0; color: var(--deep); letter-spacing: -.01em;
  border: none; padding: 0;
}
.cover .sub {
  font-size: 13pt; color: var(--ink); font-weight: 400;
  margin: 0 0 9mm 0; padding-bottom: 9mm; border-bottom: 1px solid var(--rule);
}
.cover .meta { font-size: 10.5pt; color: var(--muted); line-height: 1.9; }
.cover .meta b { color: var(--ink); }
.cover .abstract {
  margin-top: 10mm; padding: 5mm 6mm; background: var(--code);
  border-left: 3px solid var(--accent); font-size: 9.5pt; color: var(--ink);
}
.cover .abstract p { margin: 0; }
.cover-foot {
  font-size: 8.5pt; color: var(--muted);
  border-top: 1px solid var(--rule); padding-top: 3mm;
}

/* ------------------------------------------------------------ içindekiler */

/* Sınıf adı `toc` DEĞİL: python-markdown kendi çıktısını da
   `<div class="toc">` ile sarıyor ve aynı seçici iç div'e de uyunca
   `break-before: page` orada bir kez daha tetikleniyor — başlık bir
   sayfada, liste bir sonrakinde kalıyordu. */
.toc-page { break-before: page; }
.toc-page h2 {
  break-before: avoid;
  font-size: 17pt; color: var(--deep); border: none; padding: 0;
  margin: 0 0 6mm 0;
}
.toc-page ul { list-style: none; margin: 0; padding: 0; }
.toc-page > .toc > ul > li { margin: 0 0 1.2mm 0; }
.toc-page a { text-decoration: none; border-bottom: none; color: var(--ink); }
.toc-page > .toc > ul > li > a { font-weight: 600; }
.toc-page ul ul { margin: .8mm 0 2mm 7mm; }
.toc-page ul ul a { color: var(--muted); font-size: 9pt; font-weight: 400; }

/* --------------------------------------------------------------- başlıklar */

h1 { font-size: 20pt; color: var(--deep); }

h2 {
  break-before: page; break-after: avoid;
  font-size: 16pt; font-weight: 700; color: var(--deep);
  margin: 0 0 5mm 0; padding: 0 0 2.5mm 0;
  border-bottom: 2px solid var(--accent);
}

h3 {
  break-after: avoid;
  font-size: 11.5pt; font-weight: 700; color: var(--ink);
  margin: 7mm 0 2mm 0;
}

h4 { break-after: avoid; font-size: 10pt; margin: 5mm 0 1.5mm 0; }

p { margin: 0 0 3mm 0; orphans: 2; widows: 2; }

/* ------------------------------------------------------------------ metin */

strong { font-weight: 700; }
a { color: var(--deep); text-decoration: none; border-bottom: .5px solid #b9cbd9; }

code {
  font-family: Consolas, "Cascadia Mono", monospace;
  font-size: 8.6pt; background: var(--code);
  padding: .3mm 1mm; border-radius: 1.5px; color: #0b3d5c;
}

ul, ol { margin: 0 0 3mm 0; padding-left: 6mm; }
li { margin-bottom: 1.2mm; }
li > p { margin-bottom: 1.5mm; }

hr { border: none; border-top: 1px solid var(--rule); margin: 6mm 0; }

/* ---------------------------------------------------------------- diyagram */

pre {
  break-inside: avoid;
  font-family: Consolas, "Cascadia Mono", monospace;
  font-size: 7.6pt; line-height: 1.28;
  background: #fbfcfd; border: 1px solid var(--rule);
  border-left: 3px solid var(--deep);
  padding: 3.5mm 4mm; margin: 0 0 4mm 0;
  white-space: pre; overflow: visible;
}
pre code { background: none; padding: 0; font-size: inherit; color: var(--ink); }

/* ------------------------------------------------------------------ tablo */

table {
  break-inside: avoid;
  width: 100%; border-collapse: collapse;
  font-size: 8.8pt; margin: 0 0 4mm 0;
}
thead { background: var(--deep); }
th {
  color: #fff; font-weight: 600; text-align: left;
  padding: 1.8mm 2.2mm; border: none;
}
td { padding: 1.6mm 2.2mm; border-bottom: .5px solid var(--rule); vertical-align: top; }
tbody tr:nth-child(even) { background: #f7f9fb; }
td code { font-size: 8pt; }

/* -------------------------------------------------------------- alıntılar */

blockquote {
  break-inside: avoid;
  margin: 0 0 4mm 0; padding: 3mm 4mm;
  background: #f2f6fa; border-left: 3px solid var(--deep);
  font-size: 9.5pt;
}
blockquote p { margin: 0 0 2mm 0; }
blockquote p:last-child { margin-bottom: 0; }

blockquote.warn { background: #fdf4ec; border-left-color: var(--accent); }
blockquote.thesis {
  background: #fff; border: none; border-left: 4px solid var(--accent);
  font-size: 13pt; font-weight: 600; color: var(--deep);
  padding: 2mm 0 2mm 5mm;
}
"""


def read_markdown(path: Path) -> tuple[str, str]:
    """Kapak için baş kısmı, gövde için kalanı ayırır (ilk `---` sınırı)."""
    text = path.read_text(encoding="utf-8")
    head, _, body = text.partition("\n---\n")
    return head, body


def cover_parts(head: str) -> tuple[str, str, str]:
    """Baş kısımdan başlık, alt başlık ve özet paragrafını çıkarır."""
    lines = head.strip().splitlines()
    title = lines[0].lstrip("# ").strip()
    rest = "\n".join(lines[1:]).strip()
    blocks = [b.strip() for b in rest.split("\n\n") if b.strip()]
    meta = blocks[0] if blocks else ""
    abstract = blocks[1] if len(blocks) > 1 else ""
    return title, meta, abstract


def rewrite_links(markdown_text: str, source: Path) -> str:
    """Depo içi göreli bağlantıları GitHub URL'lerine çevirir.

    PDF'te `../../gozcu/loop.py` ölü bir bağlantı; jüri dosyayı tarayıcıda
    açacak, o yüzden hedef depodaki kalıcı adres olmalı.
    """
    base = source.parent

    def fix(match: re.Match) -> str:
        label, target = match.group(1), match.group(2)
        if target.startswith(("http://", "https://", "#", "mailto:")):
            return match.group(0)
        anchor = ""
        if "#" in target:
            target, _, anchor = target.partition("#")
            anchor = "#" + anchor
        try:
            resolved = (base / target).resolve().relative_to(REPO)
        except ValueError:
            return match.group(0)
        return f"[{label}]({GITHUB}/{resolved.as_posix()}{anchor})"

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", fix, markdown_text)


def decorate(body_html: str) -> str:
    """Alıntılara sınıf verir: uyarı bandı amber, manşet cümlesi büyük punto."""
    def classify(match: re.Match) -> str:
        inner = match.group(1)
        if "⚠" in inner:
            return f'<blockquote class="warn">{inner}</blockquote>'
        if "<strong>" in inner and len(re.sub(r"<[^>]+>", "", inner)) < 160:
            return f'<blockquote class="thesis">{inner}</blockquote>'
        return match.group(0)

    return re.sub(r"<blockquote>(.*?)</blockquote>", classify, body_html,
                  flags=re.DOTALL)


def build_html(source: Path) -> str:
    import markdown

    head, body = read_markdown(source)
    title, meta, abstract = cover_parts(head)

    md = markdown.Markdown(extensions=["extra", "toc", "sane_lists"],
                           extension_configs={"toc": {"toc_depth": "2-3"}})
    body_html = decorate(md.convert(rewrite_links(body, source)))
    toc_html = md.toc

    # Kapaktaki künye satır satır dizilmeli: `nl2br` olmadan üç satır tek
    # paragrafa akıyor ve "Yarışması —" gibi yerlerden kırılıyor.
    meta_html = markdown.markdown(meta, extensions=["extra", "nl2br"])
    abstract_html = markdown.markdown(abstract, extensions=["extra"])

    stamp = date.today().strftime("%d.%m.%Y")
    commit = git_commit()

    return f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<title>{html_mod.escape(title)}</title><style>{CSS}</style></head><body>

<section class="cover">
  <div class="cover-rule"></div>
  <div class="cover-body">
    <div class="kicker">Proje Dokümantasyonu · Bölüm 1</div>
    <h1>{html_mod.escape(title)}</h1>
    <div class="sub">Gözcü — Video Analiz ve Karar Destek Sistemi</div>
    <div class="meta">{meta_html}</div>
    <div class="abstract">{abstract_html}</div>
  </div>
  <div class="cover-foot">{stamp}{commit} · Apache License 2.0</div>
</section>

<section class="toc-page"><h2>İçindekiler</h2>{toc_html}</section>

{body_html}
</body></html>"""


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=REPO, capture_output=True, text=True)
    except OSError:
        return ""
    return f" · commit {out.stdout.strip()}" if out.returncode == 0 else ""


def find_browser() -> Path:
    for candidate in BROWSERS:
        if candidate.exists():
            return candidate
    found = shutil.which("chrome") or shutil.which("msedge")
    if found:
        return Path(found)
    raise SystemExit("Chrome ya da Edge bulunamadı — PDF dizgisi tarayıcıya "
                     "dayanıyor (bkz. modül başı notu).")


def render(html_path: Path, pdf_path: Path) -> None:
    browser = find_browser()
    profile = Path(tempfile.mkdtemp(prefix="gozcu-pdf-"))
    done = subprocess.run([
        str(browser), "--headless=new", "--disable-gpu",
        f"--user-data-dir={profile}",
        "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=10000",
        f"--print-to-pdf={pdf_path}", html_path.as_uri(),
    ], capture_output=True, text=True)
    if not pdf_path.exists():
        raise SystemExit(f"tarayıcı PDF üretmedi:\n{done.stderr}")


def stamp_footer(pdf_path: Path) -> None:
    """Kapak dışındaki her sayfaya altbilgi ve sayfa numarası basar.

    Chrome CSS `@bottom-center` kenar kutusunu desteklemiyor; numara bu
    yüzden burada, ikinci geçişte konuyor.
    """
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    # Latin-1 Türkçe'yi taşımıyor (`ı`, `ş`, `ğ` yok) — gömülü TTF şart.
    pdfmetrics.registerFont(TTFont("UI", r"C:\Windows\Fonts\segoeui.ttf"))

    reader = PdfReader(str(pdf_path))
    total = len(reader.pages)
    writer = PdfWriter()

    for index, page in enumerate(reader.pages):
        if index:
            buffer = BytesIO()
            pen = canvas.Canvas(buffer, pagesize=A4)
            pen.setStrokeColor(HexColor("#d9e0e7"))
            pen.setLineWidth(0.5)
            pen.line(45, 40, A4[0] - 45, 40)
            pen.setFont("UI", 7.5)
            pen.setFillColor(HexColor("#5b6b7c"))
            pen.drawString(45, 30, FOOTER_LEFT)
            pen.drawRightString(A4[0] - 45, 30, f"{index + 1} / {total}")
            pen.save()
            buffer.seek(0)
            page.merge_page(PdfReader(buffer).pages[0])
        writer.add_page(page)

    with pdf_path.open("wb") as handle:
        writer.write(handle)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--keep-html", action="store_true")
    args = parser.parse_args()

    source = args.source.resolve()
    output = (args.output or source.with_suffix(".pdf")).resolve()

    html_path = (output.with_suffix(".html") if args.keep_html
                 else Path(tempfile.mkdtemp(prefix="gozcu-pdf-")) / "doc.html")
    html_path.write_text(build_html(source), encoding="utf-8")

    render(html_path, output)
    stamp_footer(output)
    size_kb = output.stat().st_size / 1024
    print(f"{output.relative_to(REPO)}  ({size_kb:.0f} KB)")


if __name__ == "__main__":
    sys.exit(main())
