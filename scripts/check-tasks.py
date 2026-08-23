#!/usr/bin/env python3
"""Görev dosyalarının mekanik denetimi.

Bu script, elle yapıldığında atlanan kontrolleri yapar. Görev dosyalarına
dokunan herkes koştursun:

    uv run python scripts/check-tasks.py
"""
import ast, pathlib, re, sys, textwrap

TASKS = pathlib.Path("docs/tasks")
DOCS = pathlib.Path("docs")
fails: list[str] = []


def check(name: str, problems: list[str]) -> None:
    print(f"{'✓' if not problems else '✗'}  {name}")
    for p in problems:
        print(f"     {p}")
    fails.extend(problems)


def code_blocks(text: str):
    """(is_executable, block) — imza listeleri parse edilemez, o normal."""
    for blk in re.findall(r"```python\n(.*?)```", text, re.S):
        try:
            ast.parse(textwrap.dedent(blk))
            yield True, blk
        except SyntaxError:
            yield False, blk


def _keep_interpolations(m: re.Match) -> str:
    """String sabitinden insan metnini at, kimlikleri bırak.

    İçerideki düzyazı Türkçe olmak zorunda (CLAUDE.md). Ama boşluksuz bir
    string kimlik biçimindedir — JSON anahtarı, SQL adı — ve CLAUDE.md bunların
    İngilizce olmasını istiyor, o yüzden olduğu gibi taranır. f-string
    interpolasyonları da ('{ozet}') her hâlükârda görünür kalır. Aynı mantık
    hem tek satırlık hem üç tırnaklı ('''/\"\"\") gövdeler için geçerli — tırnak
    uzunluğu eşleşen metinden çıkarılır, geri kalanı aynı kurallarla süzülür.
    """
    text = m.group(0)
    qlen = 3 if text[:3] in ('"""', "'''") else 1
    govde = text[qlen:-qlen]
    if govde and not re.search(r"\s", govde):
        return text  # 'ozet' gibi kimlik biçimli string — taranmaya devam
    if re.search(r"(?i)\b(select|insert|update|delete|from|join|"
                 r"create table|alter table)\b", govde):
        return text  # gömülü SQL: tablo/kolon adları da kod, taranır
    return " ".join(re.findall(r"\{[^{}]*\}", govde))


def strip_prose(blk: str) -> str:
    """Türkçe *kimlik* ararken insan metnini ele: docstring, yorum, string.

    Operatöre görünen metin ve print çıktıları tanım gereği Türkçe; bunları
    kimlik sanmak yanlış alarm üretir. Üç tırnaklı gövdeler artık silinmiyor —
    tek satırlık stringlerle aynı carve-out'tan geçiyor, öyle ki içine gömülü
    SQL veya kimlik biçimli metin (Görev 02'nin SQLite sorguları gibi) taranmaya
    devam ediyor, düz Türkçe docstring ise yine elenip gidiyor.
    """
    blk = re.sub(r'"""(?:.|\n)*?"""', _keep_interpolations, blk)
    blk = re.sub(r"'''(?:.|\n)*?'''", _keep_interpolations, blk)
    blk = re.sub(r'"[^"\n]*"', _keep_interpolations, blk)
    blk = re.sub(r"'[^'\n]*'", _keep_interpolations, blk)
    return re.sub(r"(?m)#.*$", "", blk)


# 1 — karar bekleyen placeholder
allowed = {"adres", "anahtar", "klip", "model-adi"}
bad = []
for p in sorted(TASKS.glob("*.md")):
    for m in re.finditer(r"<([a-zçğıöşü][a-zçğıöşü-]*)>", p.read_text()):
        if m.group(1) not in allowed:
            bad.append(f"{p.name}: <{m.group(1)}>")
    for kw in ("TBD", "TODO", "sonra doldur"):
        if kw in p.read_text():
            bad.append(f"{p.name}: {kw}")
check("placeholder yok", bad)

# 2 — çalıştırılabilir kod blokları geçerli Python
bad = []
for p in sorted(TASKS.glob("*.md")):
    for i, blk in enumerate(re.findall(r"```python\n(.*?)```", p.read_text(), re.S), 1):
        d = textwrap.dedent(blk)
        if not re.search(r"(?m)^(def |class |import |from |@)", d):
            continue  # imza listesi
        try:
            ast.parse(d)
        except SyntaxError as e:
            bad.append(f"{p.name} blok#{i} satır {e.lineno}: {e.msg}")
check("kod blokları geçerli Python", bad)

# 3 — kod içinde Türkçe kimlik yok (string ve yorumlar hariç)
# Sınır `_` sayılır: Türkçe kökler snake_case'in *parçası* olarak da yakalanmalı.
# Eski desen `(?![\w])` kullanıyordu; `_` de `\w` olduğu için `epizot_embedding`
# ve `test_epizot_guncelle` elenmeden geçiyordu — Görev 02'de kırık bir SQL tablo
# adı bu yüzden temiz rapor aldı.
TR = re.compile(r"(?<![A-Za-z0-9])(ozet|kok|neden|yorum|gozlem|epizot|karar|"
                r"aksiyon|sinyal|kademe|mesajlar|sema|kritik|adaylar|sorgu|"
                r"gercek|kaydet|acik|kapali|hedef|devir|ac|kapat|guncelle)"
                r"(?![A-Za-z0-9])")
bad = []
for p in sorted(TASKS.glob("*.md")):
    for _, blk in code_blocks(p.read_text()):
        for m in sorted(set(TR.findall(strip_prose(blk)))):
            bad.append(f"{p.name}: '{m}'")
check("kod kimlikleri İngilizce", sorted(set(bad)))

# 4 — prompt enum değerleri şemadakiyle aynı
bad = []
TR_ENUM = ("yoksay", "gorsel_incele", "acil_yukselt", "epizot_ac",
           "epizot_kapat", "epizot_guncelle", "baslangic", "gelisim")
for p in sorted(TASKS.glob("*.md")):
    for blk in re.findall(r'"""(?:.|\n)*?"""', p.read_text()):
        for w in TR_ENUM:
            if re.search(rf"(?<![\wçğıöşü]){w}(?![\wçğıöşü])", blk):
                bad.append(f"{p.name}: prompt '{w}' diyor, şema İngilizce bekliyor")
check("prompt enum'ları şemayla uyumlu", bad)

# 5 — "Beklenen: N passed" gerçek test sayısıyla uyuşuyor.
# Parametrize edilmiş bir test tek `def`, ama pytest'e birden çok koşu olarak
# görünür; sayılan şey bu yüzden `def` adedi değil, genişletilmiş adet.
def _literals(tree: ast.Module) -> dict:
    """Modül seviyesindeki sabit liste/demetler — parametrize onlara ad verebilir."""
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                pass
    return out


def _runs(fn: ast.FunctionDef, consts: dict) -> int:
    """Bu testin kaç koşu ürettiği; parametrize yoksa 1."""
    total = 1
    for dec in fn.decorator_list:
        if not isinstance(dec, ast.Call) or len(dec.args) < 2:
            continue
        if not ast.unparse(dec.func).endswith("parametrize"):
            continue
        values = dec.args[1]
        try:
            seq = ast.literal_eval(values)
        except (ValueError, SyntaxError):
            seq = consts.get(values.id) if isinstance(values, ast.Name) else None
        if seq is not None:
            total *= len(seq)
    return total


bad = []
for p in sorted(TASKS.glob("*.md")):
    t = p.read_text()
    runs = {}
    for blk in re.findall(r"```python\n(.*?)```", t, re.S):
        try:
            tree = ast.parse(textwrap.dedent(blk))
        except SyntaxError:
            continue  # imza listesi
        consts = _literals(tree)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                runs[node.name] = _runs(node, consts)
    claimed = {int(m) for m in re.findall(r"Beklenen: \*{0,2}(\d+) passed", t)}
    total = sum(runs.values())
    if claimed and claimed != {total}:
        bad.append(f"{p.name}: {total} test var, {sorted(claimed)} iddia ediliyor")
check("test sayıları tutarlı", bad)

# 6 — ileri bağımlılık yok
bad = []
for p in sorted(TASKS.glob("[0-9]*.md")):
    n = int(p.name[:2])
    m = re.search(r"\*\*Bağımlılık:\*\*\s*(.+)", p.read_text())
    if m and "yok" not in m.group(1):
        for d in {int(x) for x in re.findall(r"\[(\d\d)\]", m.group(1))}:
            if d >= n:
                bad.append(f"{n:02d} -> {d:02d}")
check("ileri bağımlılık yok", bad)

# 7 — kırık link yok (docs geneli)
bad = [f"{md}: {m.group(1)}" for md in DOCS.rglob("*.md")
       for m in re.finditer(r"\]\((?!https?:)([^)#]+)", md.read_text())
       if not (md.parent / m.group(1)).resolve().exists()]
check("kırık link yok", bad)

print()
if fails:
    print(f"{len(fails)} sorun bulundu.")
    sys.exit(1)
print("Hepsi temiz.")
