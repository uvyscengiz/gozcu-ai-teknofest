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
dev = ["pytest>=8.0", "pytest-cov>=5.0"]
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

**3. Yerel gateway takma adları — `litellm-config.yaml`.**

Yedi kademe adının hepsi çözülebilmeli, yoksa 24 Ağustos çıkış kriteri test
edilemez. Organizasyonun gateway'i geldiğinde bu dosya kullanılmaz, sadece
yerel geliştirme içindir.

```yaml
model_list:
  - model_name: Qwen3-8B
    litellm_params: {model: openai/<yerelde-ne-varsa>, api_base: http://localhost:8080/v1, api_key: none}
  - model_name: Qwen3.6-35B-A3B
    litellm_params: {model: openai/<yerelde-ne-varsa>, api_base: http://localhost:8080/v1, api_key: none}
  - model_name: Qwen3.5-122B-A10B
    litellm_params: {model: openai/<yerelde-ne-varsa>, api_base: http://localhost:8080/v1, api_key: none}
  - model_name: Qwen3-VL-30B-A3B
    litellm_params: {model: openai/<yerel-vlm>, api_base: http://localhost:8081/v1, api_key: none}
  - model_name: Qwen3Guard-Gen-4B
    litellm_params: {model: openai/<yerelde-ne-varsa>, api_base: http://localhost:8080/v1, api_key: none}
  - model_name: Qwen3-Embedding-4B
    litellm_params: {model: openai/<yerel-embed>, api_base: http://localhost:8080/v1, api_key: none}
  - model_name: Qwen3-Reranker-4B
    litellm_params: {model: openai/<yerelde-ne-varsa>, api_base: http://localhost:8080/v1, api_key: none}
```

`README.md`'ye çalıştırma satırını ekle: `litellm --config litellm-config.yaml --port 4000`.

**4. Mevcut testleri taşı.** Repoda test yoksa bu adım boş geçilir.

## Kabul kriterleri

- [ ] `uv sync --extra dev` temiz bir Linux makinesinde çalışıyor (mlx-vlm çekilmiyor)
- [ ] `uv run pytest tests/ -v` hata vermeden koşuyor (0 test olabilir, çökmemeli)
- [ ] `litellm-config.yaml` yedi kademe adını da içeriyor
- [ ] `app.py` `mlx_vlm` yokken import hatası vermiyor

## Doğrulama

```bash
uv run pytest tests/ -v && uv run python -c "import app; print('ok')"
```

Beklenen: pytest hatasız çıkıyor, `ok` yazıyor.

## Bittiğinde

```bash
git add pyproject.toml tests/ litellm-config.yaml app.py README.md
git commit -m "chore: test harness, optional mlx extra, local gateway aliases"
```
