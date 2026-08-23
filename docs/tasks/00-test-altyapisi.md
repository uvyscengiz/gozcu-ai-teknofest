# Görev 00 — Test altyapısı ve yerel gateway

**Sahip:** `uvyscengiz` · **Gün:** 23 Ağustos · **Süre:** ~1 saat
**Bağımlılık:** yok · **Bu görev diğer 17'sinin hepsini bloke ediyor**

## Bağlam

Bugün repoda `pytest` bağımlılık listesinde yok ve `tests/` dizini hiç yok. Yani
diğer görevlerin "testi yaz, koştur" adımı ilk komutta patlıyor. Ayrıca bütün
ajan görevleri bir model gateway'ine konuşuyor ve varsayılan adres
`localhost:4000` — orada hiçbir şey çalışmıyor.

Üçüncü bir sorun: `mlx-vlm` sert bağımlılık ve Apple Silicon dışında wheel'i yok.
Yani `uv sync` bir Linux makinesinde kırılıyor — jürinin çalıştıracağı makine
dahil. Şartname `git clone` + tek komutla çalışmayı istiyor.

## Kurulum

```bash
git clone git@github.com:uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest
```

## Ne yapacaksın

**1. `pyproject.toml`'a dev bağımlılıkları ekle.**

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=5.0", "litellm>=1.50"]
mac = ["mlx-vlm>=0.6.13"]
```

Ve `mlx-vlm`'i `[project].dependencies` listesinden **çıkar** — artık opsiyonel.
`app.py`'daki yerel sunucu spawn'ı `mlx_vlm` import'unu try/except içine al;
yoksa sadece gateway kullanılır.

**2. `tests/` dizinini oluştur.**

`tests/__init__.py` (boş) ve `tests/conftest.py`:

```python
import pytest


@pytest.fixture
def store():
    from gozcu.store import Store
    return Store(":memory:")
```

**3. Gateway erişimi.**

İki durum var, hangisindeysen onu yap.

**a) Organizasyonun gateway'i hazırsa** — tek yapılacak, adresi bir yere yazmak.
`.env.example` oluştur:

```bash
GOZCU_GATEWAY_BASE_URL=http://ORGANIZASYON_ADRESI:4000/v1
GOZCU_GATEWAY_API_KEY=ANAHTAR
```

`README.md`'ye "bu değerleri `.env` olarak kopyala ve doldur" satırını ekle.
`.env` `.gitignore`'a girer. **Yerel litellm'e gerek yok, bu adımı burada bitir.**

**b) Gateway henüz yoksa** — yedi kademe adının hepsi çözülebilmeli, yoksa
24 Ağustos çıkış kriteri test edilemez. Hepsini tek bir yerel uca yönlendiren
config'i üret:

```bash
uv run python - <<'EOF'
import os, pathlib
text = os.environ.get("GOZCU_LOCAL_MODEL", "qwen2.5:7b")
vision = os.environ.get("GOZCU_LOCAL_VLM", text)
base = os.environ.get("GOZCU_LOCAL_BASE", "http://localhost:11434/v1")
tiers = {"Qwen3-8B": text, "Qwen3.6-35B-A3B": text, "Qwen3.5-122B-A10B": text,
         "Qwen3-VL-30B-A3B": vision, "Qwen3Guard-Gen-4B": text,
         "Qwen3-Embedding-4B": text, "Qwen3-Reranker-4B": text}
lines = ["model_list:"]
for alias, target in tiers.items():
    lines.append(f"  - model_name: {alias}")
    lines.append(f"    litellm_params: {{model: openai/{target}, "
                 f"api_base: {base}, api_key: none}}")
pathlib.Path("litellm-config.yaml").write_text("\n".join(lines) + "\n")
print("litellm-config.yaml yazıldı:", len(tiers), "kademe")
EOF
```

Varsayılanlar Ollama'ya göre. Başka bir şey kullanıyorsan üç değişkeni ver:

```bash
GOZCU_LOCAL_BASE=http://localhost:8080/v1 GOZCU_LOCAL_MODEL=<model-adi> uv run python - <<'EOF'
...yukarıdaki script...
EOF
```

Sonra çalıştır ve `README.md`'ye ekle:

```bash
uv run litellm --config litellm-config.yaml --port 4000
```

`litellm`'i `dev` extra'sına ekle. **Bu dosya sadece yerel geliştirme içindir** —
organizasyonun gateway'i geldiğinde kullanılmaz, `.gitignore`'a girer.

**4. Mevcut testleri taşı.** Repoda test yoksa bu adım boş geçilir.

## Kabul kriterleri

- [ ] `uv sync --extra dev` temiz bir Linux makinesinde çalışıyor (mlx-vlm çekilmiyor)
- [ ] `uv run pytest tests/ -v` hata vermeden koşuyor (0 test olabilir, çökmemeli)
- [ ] Gateway adresi `.env.example`'da **veya** `litellm-config.yaml` yedi kademeyi de çözüyor
- [ ] `app.py` `mlx_vlm` yokken import hatası vermiyor

## Doğrulama

```bash
uv run pytest tests/ -v && uv run python -c "import app; print('ok')"
```

Beklenen: pytest hatasız çıkıyor, `ok` yazıyor.

## Bittiğinde

```bash
git add pyproject.toml tests/ .env.example .gitignore app.py README.md
git commit -m "chore: test harness, optional mlx extra, local gateway aliases"
```
