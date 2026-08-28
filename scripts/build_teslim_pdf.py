#!/usr/bin/env python3
"""docs/teslim/01..08 dosyalarını tek bir jüri PDF'ine birleştirir.

Kaynak .md dosyalarına hiç dokunmaz — yalnız render sırasında başlık
kimlikleri atar, bölümler-arası linkleri PDF-içi çapalara çevirir ve
kapak/İçindekiler ekler. Şema/başlık numaraları değişirse (şartname §7)
CHAPTERS listesini güncelle.

Kullanım:
    uv run --extra docs python scripts/build_teslim_pdf.py
    uv run --extra docs python scripts/build_teslim_pdf.py --output /tmp/gozcu.pdf
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Homebrew'in libgobject/libpango/libcairo'sunu weasyprint import edilmeden
# ÖNCE bulmasını sağlar (macOS'ta DYLD_LIBRARY_PATH set değilse dlopen çöker).
if sys.platform == "darwin":
    _brew_lib = "/opt/homebrew/lib" if Path("/opt/homebrew/lib").is_dir() else "/usr/local/lib"
    os.environ["DYLD_LIBRARY_PATH"] = _brew_lib + ":" + os.environ.get("DYLD_LIBRARY_PATH", "")

import markdown  # noqa: E402
from markdown.extensions.toc import TocExtension  # noqa: E402
from weasyprint import HTML  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
TESLIM_DIR = REPO_ROOT / "docs" / "teslim"

# Şartname §6/§7'nin sekiz zorunlu bölümü, sırayla (bkz. docs/teslim/README.md).
CHAPTERS = [
    "01-mimari-ozeti-ve-diyagramlar.md",
    "02-framework-ve-modeller.md",
    "03-senaryolar-ve-mock.md",
    "04-kurulum-calistirma.md",
    "05-zorluklar-ve-cozumler.md",
    "06-ek-ozellikler.md",
    "07-olcumleme.md",
    "08-olcekleme.md",
]

COVER_TITLE = "Gözcü"
COVER_SUBTITLE = "Video Analiz ve Karar Destek Sistemi — Proje Dokümantasyonu"
COVER_MATCH = "TEKNOFEST 2026 Yapay Zekâ Dil Ajanları Yarışması · 3. Senaryo"
COVER_TEAM = "Takım FERASET  ·  team37  ·  Muğla Sıtkı Koçman Üniversitesi"
COVER_MEMBERS = "uvyscengiz · Xana-bit · beyzaalive · rumeysaoru"

MD_EXTENSIONS = [
    "tables",
    "fenced_code",
    "sane_lists",
    "attr_list",
    "toc",
]


def gh_slugify(value: str, separator: str) -> str:
    """docs/teslim içindeki elle yazılmış #çapa linkleriyle eşleşen basit
    GitHub-tarzı slug (kelime karakteri + boşluk dışındakileri at, boşluğu
    ayırıcıyla değiştir)."""
    value = value.strip().lower()
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    return re.sub(r"\s+", separator, value)


def first_h1_text(md_text: str) -> str:
    for line in md_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    raise ValueError("H1 bulunamadı")


def chapter_anchor(index: int, filename: str) -> str:
    """O bölümün H1'inin id'si — bölüm-üstü linklerin hedefi."""
    text = first_h1_text((TESLIM_DIR / filename).read_text(encoding="utf-8"))
    return f"ch{index}-{gh_slugify(text, '-')}"


def rewrite_internal_links(md_text: str, index: int, name_to_index: dict[str, int]) -> str:
    """`0X-....md[#çapa]` ve bare `#çapa` linklerini PDF-içi `#chN-...`
    çapalarına çevirir. docs/teslim dışına giden linklere dokunmaz."""

    def repl_file_link(m: re.Match) -> str:
        target_file, frag = m.group(1), m.group(2)
        target_index = name_to_index.get(target_file)
        if target_index is None:
            return m.group(0)
        if frag:
            return f"](#ch{target_index}-{frag})"
        return f"](#{chapter_anchor(target_index, target_file)})"

    md_text = re.sub(r"\]\((0[1-8]-[\w-]+\.md)(?:#([^)]+))?\)", repl_file_link, md_text)

    def repl_bare_anchor(m: re.Match) -> str:
        return f"](#ch{index}-{m.group(1)})"

    # Aynı dosya içi `(#çapa)` linkleri — dosya adı olmadan.
    md_text = re.sub(r"\]\(#([^)]+)\)", repl_bare_anchor, md_text)
    return md_text


def render_chapter(index: int, filename: str, name_to_index: dict[str, int]) -> str:
    raw = (TESLIM_DIR / filename).read_text(encoding="utf-8")
    raw = rewrite_internal_links(raw, index, name_to_index)
    html = markdown.markdown(
        raw,
        extensions=MD_EXTENSIONS,
        extension_configs={"toc": {"slugify": gh_slugify, "anchorlink": False}},
    )
    # toc uzantısının verdiği id="slug" -> id="chN-slug" (bölümler arası çakışmayı önler).
    html = re.sub(r'id="([^"]+)"', lambda m: f'id="ch{index}-{m.group(1)}"', html)
    return f'<article class="chapter">{html}</article>'


def build_toc(chapters_html_titles: list[tuple[str, str]]) -> str:
    items = "\n".join(
        f'<div class="toc-entry"><a href="#{anchor}">{title}</a></div>'
        for anchor, title in chapters_html_titles
    )
    return f'<section class="toc"><h2>İçindekiler</h2>{items}</section>'


CSS = """
@page {
  size: A4;
  margin: 2.4cm 1.9cm 2.2cm 1.9cm;
  @top-center {
    content: "Gözcü — Takım FERASET (team37)";
    font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
    font-size: 7.5pt;
    color: #9a9a9a;
    letter-spacing: 0.03em;
  }
  @bottom-center {
    content: counter(page);
    font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
    font-size: 8.5pt;
    color: #6b6b6b;
  }
}
@page cover {
  margin: 0;
  @top-center { content: none; }
  @bottom-center { content: none; }
}

* { box-sizing: border-box; }

body {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 10.3pt;
  line-height: 1.5;
  color: #1b1b1b;
}

h1, h2, h3, h4 {
  font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
  color: #0f2438;
  line-height: 1.25;
  break-after: avoid;
}

.chapter { page-break-before: always; }
.chapter > h1 {
  font-size: 20pt;
  border-bottom: 2.2pt solid #0f2438;
  padding-bottom: 0.28em;
  margin: 0 0 0.9em 0;
}
.chapter h2 {
  font-size: 14pt;
  margin: 1.7em 0 0.6em 0;
  border-bottom: 0.7pt solid #c8ccd0;
  padding-bottom: 0.15em;
}
.chapter h3 {
  font-size: 11.5pt;
  margin: 1.3em 0 0.4em 0;
  color: #26415c;
}

p { margin: 0.55em 0; text-align: left; }
ul, ol { margin: 0.4em 0 0.7em 0; padding-left: 1.4em; }
li { margin: 0.18em 0; }

hr {
  border: none;
  border-top: 0.6pt solid #d3d7db;
  margin: 1.6em 0;
}

a { color: #0e5a8a; text-decoration: none; }

strong { color: #10151a; }

blockquote {
  margin: 0.9em 0;
  padding: 0.55em 0.9em;
  border-left: 3pt solid #0e5a8a;
  background: #f4f7f9;
  color: #24333f;
  font-size: 9.8pt;
}
blockquote p { margin: 0.25em 0; }

code {
  font-family: Menlo, "SF Mono", "DejaVu Sans Mono", "Courier New", monospace;
  background: #eef1f3;
  padding: 0.05em 0.3em;
  border-radius: 2pt;
  font-size: 0.88em;
}

pre {
  font-family: Menlo, "SF Mono", "DejaVu Sans Mono", "Courier New", monospace;
  font-size: 7pt;
  line-height: 1.35;
  background: #f6f7f8;
  border: 0.6pt solid #dde1e4;
  border-radius: 3pt;
  padding: 0.6em 0.7em;
  margin: 0.7em -0.5cm;
  white-space: pre;
  overflow: hidden;
}
pre code { background: none; padding: 0; font-size: 1em; }

table {
  border-collapse: collapse;
  width: 100%;
  margin: 0.8em 0;
  font-size: 9pt;
}
th, td {
  border: 0.6pt solid #ccd1d5;
  padding: 0.35em 0.5em;
  text-align: left;
  vertical-align: top;
}
th {
  background: #eef1f3;
  font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
  font-weight: 600;
}
tr:nth-child(even) td { background: #fafbfc; }

/* Kapak */
.cover {
  page: cover;
  height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  padding: 0 2cm;
}
.cover .kicker {
  font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
  font-size: 10.5pt;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #6b7680;
  margin-bottom: 1.4em;
}
.cover h1 {
  font-family: Georgia, serif;
  font-size: 44pt;
  margin: 0;
  color: #0f2438;
}
.cover .subtitle {
  font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
  font-size: 13pt;
  color: #2c3e4d;
  margin-top: 0.6em;
}
.cover .rule {
  width: 5.5cm;
  border-top: 1.2pt solid #0e5a8a;
  margin: 1.8em 0;
}
.cover .team {
  font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
  font-size: 11pt;
  color: #1b1b1b;
}
.cover .members {
  font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
  font-size: 9.5pt;
  color: #6b7680;
  margin-top: 0.35em;
}

/* İçindekiler */
.toc { page-break-before: always; page-break-after: always; }
.toc h2 {
  font-size: 18pt;
  border-bottom: 2.2pt solid #0f2438;
  padding-bottom: 0.28em;
  margin-bottom: 1em;
}
.toc-entry {
  font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
  font-size: 11.5pt;
  margin: 0.9em 0;
}
.toc-entry a {
  color: #10151a;
}
.toc-entry a::after {
  content: leader(dotted) " " target-counter(attr(href), page);
  color: #6b7680;
}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=TESLIM_DIR / "gozcu-teslim-dokumani.pdf",
        help="Çıktı PDF yolu (varsayılan: docs/teslim/gozcu-teslim-dokumani.pdf)",
    )
    args = parser.parse_args()

    name_to_index = {name: i + 1 for i, name in enumerate(CHAPTERS)}

    toc_entries = []
    chapters_html = []
    for i, name in enumerate(CHAPTERS, start=1):
        anchor = chapter_anchor(i, name)
        title = first_h1_text((TESLIM_DIR / name).read_text(encoding="utf-8"))
        toc_entries.append((anchor, title))
        chapters_html.append(render_chapter(i, name, name_to_index))
        print(f"  [{i}/{len(CHAPTERS)}] {name} -> #{anchor}")

    cover = f"""
    <section class="cover">
      <div class="kicker">{COVER_MATCH}</div>
      <h1>{COVER_TITLE}</h1>
      <div class="subtitle">{COVER_SUBTITLE}</div>
      <div class="rule"></div>
      <div class="team">{COVER_TEAM}</div>
      <div class="members">{COVER_MEMBERS}</div>
    </section>
    """

    full_html = f"""<!doctype html>
<html lang="tr">
<head><meta charset="utf-8"><style>{CSS}</style></head>
<body>
{cover}
{build_toc(toc_entries)}
{"".join(chapters_html)}
</body>
</html>"""

    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(f"PDF yazılıyor: {args.output}")
    HTML(string=full_html, base_url=str(TESLIM_DIR)).write_pdf(str(args.output))
    print("Bitti.")


if __name__ == "__main__":
    main()
