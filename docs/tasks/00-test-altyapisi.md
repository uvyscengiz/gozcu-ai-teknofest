# Görev 00 — Test altyapısı ve yerel gateway

**Sahip:** `uvyscengiz` · **Gün:** 23 Ağustos · **Süre:** ~1 saat
**Bağımlılık:** yok · **Diğer 18 görevin hepsi buna dayanıyor**

## Bağlam

Bugün repoda `pytest` bağımlılık listesinde yok ve `tests/` dizini hiç yok. Yani
diğer görevlerin "testi yaz, koştur" adımı ilk komutta patlıyor. Ayrıca bütün
ajan görevleri bir model gateway'ine konuşuyor ve varsayılan adres
`localhost:4000` — orada hiçbir şey çalışmıyor.

Üçüncü konu `mlx-vlm`. **Yaygın inanışın aksine `uv sync` bunun yüzünden
Linux'ta kırılmıyor:** `uv.lock`'a göre `mlx 0.32.0` `manylinux_2_35` x86_64 ve
aarch64 wheel'leri yayınlıyor, `mlx_vlm 0.6.14` saf `py3-none-any`, ve
darwin'e özel `mlx-metal` zaten `sys_platform == 'darwin'` işaretiyle korumalı.
Modern bir Ubuntu'da bugün de kuruluyor. Yine de opsiyonel yapıyoruz, çünkü:
glibc 2.35'ten eski dağıtımlar ve musl tabanlılar wheel bulamaz; ve Apple
Silicon dışında bu ~1 GB'lık çıkarım yığını **pratikte işe yaramaz** —
hızlandırılmış çalışma yolu Metal istiyor. Jürinin makinesinde boşuna indirme
ve boşuna risk istemiyoruz.

### Repoyu okurken düzeltilen varsayımlar

Bu görev yazıldığında doğru sanılan ama repoda öyle olmayan şeyler:

1. **`litellm` paketi proxy'yi getirmiyor.** Düz `litellm` CLI'ı kuruyor ama
   `litellm --config ...` "proxy bağımlılıkları kurulu değil" diye ölüyor.
   Doğrusu **`litellm[proxy]`**. (Proxy'nin varsayılan portu zaten 4000.)
2. **Boş `tests/` doğrulama komutunu kırıyor.** `pytest` hiç test toplayamazsa
   **5** ile çıkıyor (`NO_TESTS_COLLECTED`), yani `pytest && python -c "import
   app"` zincirinin ikinci yarısı hiç çalışmıyor. Ölçüldü: boş `tests/` → 5,
   tek testle → 0. Bu yüzden `tests/` boş bırakılmıyor.
3. **`app.py` `mlx_vlm`'i zaten import etmiyor.** `_ensure_server_running()`
   içinde `subprocess.Popen(["uv", "run", "mlx_vlm.server", ...])` ile alt süreç
   açıyor. Sarılacak bir import yok. Gerçek Linux arızası **çalışma anında**:
   `uv run` `mlx_vlm`'i çözmeye çalışıp anlaşılmaz bir hatayla ölüyor. Doğru
   düzeltme `importlib.util.find_spec` ile bakıp okunur bir hata vermek.
4. **`.env` kendi kendine yüklenmiyor.** Repoda `python-dotenv` yok ve
   `gozcu/config.py` doğrudan `os.environ` okuyor. Yani bir `.env` dosyası
   yazmak tek başına **hiçbir şey yapmaz** — sessizce yok sayılır. Kod
   eklemeden çözümü `uv run --env-file .env ...` (uv'de var, ölçüldü). Dosya
   yoksa `uv` hata verip duruyor, o yüzden `--env-file` sadece gerçekten
   gateway'e konuşan komutlarda kullanılıyor; testler mock'lu, onlarda yok.
5. **Üretici script repoda yaşamalı.** `litellm-config.yaml` `.gitignore`'a
   girdiği için onu üreten kodun tek kopyası bir markdown heredoc'u olamaz.
   `scripts/gen-litellm-config.py` olarak repoya giriyor.

### Karar — 23 Ağustos

Organizasyonun gateway'i **henüz hazır değil**. Adım 3'te **(b) yolu**
uygulanır: yedi kademe adı yerel bir uca yönlendirilir. Varsayılan arka uç
**Ollama, `http://localhost:11434/v1`**. Adres geldiğinde değişecek tek yer
`.env` — kod değişmez.

## Kurulum

```bash
git clone git@github.com:uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest
```

**Burada `uv sync --extra dev` çalıştırma** — `dev` extra'sı henüz yok, uv
`Extra 'dev' is not defined` der. Onu adım 1 oluşturuyor; sync adım 1'in
sonunda. (Diğer görevlerde extra hazır olduğu için kurulum bloğunda.)

## Ne yapacaksın

**1. `pyproject.toml`'a dev bağımlılıkları ekle.**

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=5.0", "litellm[proxy]>=1.50"]
mac = ["mlx-vlm>=0.6.13"]
```

Ve `mlx-vlm`'i `[project].dependencies` listesinden **çıkar** — artık opsiyonel.

Extra tanımlandı, şimdi kur:

```bash
uv sync --extra dev
```

`uv run` **extra'ları kendiliğinden açmaz** — bu atlanırsa `pytest` ve
`litellm` kurulmaz, aşağıdaki her komut "Failed to spawn" der.

> **Apple Silicon'daysan senin günlük komutun `uv sync --extra dev --extra mac`.**
> `uv sync` varsayılan olarak *tam* eşitler: yalnız `--extra dev` dersen
> `mlx-vlm` **silinir** ve 24 Ağustos'ta `app.py` ile yapacağın demo kırılır.
> Yalnız `--extra mac` dersen bu sefer `pytest` silinir. İkisini birden ver.

`opencv-python`'a dokunma. `opencv-python-headless`'a çevirmek Linux'taki
`libGL` ihtiyacını **çözmez**: `ultralytics` kendi bağımlılığı olarak
`opencv-python`'ı zaten çekiyor (`uv.lock`), ikisi birden kurulur ve hiçbir şey
kazanılmaz. Doğru çözüm sistem paketlerini README'de yazmak (adım 6).

**2. `tests/` dizinini oluştur.**

`tests/__init__.py` (boş). Bu dosya `pytest`'in `sys.path`'e **repo kökünü**
eklemesini sağlıyor (`tests/` dizinini değil) — `[tool.uv] package = false`
olduğu için `import gozcu` ve `import app` buna bağlı.

`conftest.py` **yazma.** Hiçbir görev dosyası `store` fixture'ı kullanmıyor;
02 ve 05 dahil hepsi testin içinde `Store(":memory:")` kuruyor. Her koşuda
yüklenen dosyada ölü fixture istemiyoruz — ihtiyaç doğduğunda o görev ekler.

`tests/test_smoke.py` — dizin boş kalmamalı, yoksa `pytest` 5 ile çıkar:

```python
def test_app_imports_without_mlx_vlm():
    """mlx-vlm opsiyonel oldu; app.py onsuz da import edilebilmeli."""
    import app

    assert hasattr(app, "process_video")


def test_gozcu_config_is_importable():
    from gozcu import config

    assert config.FRAME_FPS > 0
```

**3. Yerel gateway (karar: (b) yolu).**

`scripts/gen-litellm-config.py` yaz — yedi kademe adının hepsi çözülebilmeli,
yoksa 24 Ağustos çıkış kriteri test edilemez:

```python
import os
import pathlib

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
print("litellm-config.yaml yazıldı:", len(tiers), "adet")
```

Kademe adları **Görev 03'ün `config.py` bloğuyla birebir aynı olmalı.** Prompt
enum kuralının model adlarına uygulanmış hâli: bir harf kayarsa gateway 400
döner ve sebebi görünmez.

Üret, sonra **ayrı bir terminalde** çalıştır — proxy terminali bloke eder:

```bash
uv run python scripts/gen-litellm-config.py
uv run litellm --config litellm-config.yaml --port 4000
```

Başka bir yerel sunucu kullanıyorsan üç değişkeni ver:

```bash
GOZCU_LOCAL_BASE=http://localhost:8080/v1 GOZCU_LOCAL_MODEL=<model-adi> \
  uv run python scripts/gen-litellm-config.py
```

`litellm-config.yaml` **sadece yerel geliştirme içindir** — organizasyonun
gateway'i geldiğinde kullanılmaz, `.gitignore`'a girer. Üreten script kalır.

**4. `.env.example` ve `.gitignore`.**

```bash
GOZCU_GATEWAY_BASE_URL=http://localhost:4000/v1
GOZCU_GATEWAY_API_KEY=not-needed
```

`.gitignore`'a `.env` ve `litellm-config.yaml` eklenir. Kullanımı:

```bash
cp .env.example .env
uv run --env-file .env python app.py
```

Organizasyonun gateway'i gelince `.env`'deki iki satır değişir, kod değişmez.
`--env-file` olmadan `.env` **okunmaz**; testlerde gerek yok (mock'lular).

**5. `app.py` — `mlx_vlm` koruması.**

`_ensure_server_running()` içinde, alt süreci açmadan **önce** paket var mı diye
bak; yoksa `uv run`'ın anlaşılmaz hatası yerine ne yapılacağını söyleyen bir
hata ver:

```python
import importlib.util

if importlib.util.find_spec("mlx_vlm") is None:
    raise RuntimeError(
        f"{VLM_BASE_URL} adresinde sunucu yok ve mlx-vlm kurulu değil. "
        "Apple Silicon'daysan: uv sync --extra dev --extra mac. "
        "Değilsen GOZCU_VLM_BASE_URL'i çalışan bir gateway'e çevir."
    )
```

**6. `README.md` oluştur.** Repoda yok — giriş noktası şu an `CLAUDE.md` ve o
ajan talimatı. Şartname `git clone` + tek komut istiyor, jüri `README`'ye bakar.

İçerik: sistem bir paragraf; `uv sync --extra dev` (Mac'te `--extra mac` de);
`cp .env.example .env`; litellm'i ayrı terminalde çalıştırma; `pytest`;
`uv run --env-file .env python app.py`. **Linux bölümü sistem paketlerini
saysın** — bunlar wheel'lerle gelmiyor ve ikisi de zorunlu:

```bash
sudo apt install ffmpeg libgl1 libglib2.0-0
```

`ffmpeg` `gozcu/frames.py`'nin kare çıkarması için bir *binary* olarak gerekli;
`libgl1`/`libglib2.0-0` `opencv-python`'ın import edilebilmesi için.

`CLAUDE.md`'nin "Komutlar" bölümü README'ye işaret eder ve `--env-file`'lı
çalıştırma satırını gösterir.

## Kabul kriterleri

- [ ] `uv sync --extra dev` mlx-vlm çekmeden tamamlanıyor
- [ ] `uv run pytest tests/ -v` yeşil — 2 test, çıkış kodu 0 (5 değil)
- [ ] `scripts/gen-litellm-config.py` yedi kademeyi de çözen bir yaml üretiyor
- [ ] Proxy ayakta iken `curl localhost:4000/v1/models` yedi adı da listeliyor
- [ ] `.env.example` repoda, `.env` ve `litellm-config.yaml` `.gitignore`'da
- [ ] `app.py` `mlx_vlm` yokken import hatası vermiyor, çalışma anında okunur hata veriyor
- [ ] `README.md` var, Linux sistem paketlerini sayıyor, baştan sona takip edilebiliyor
- [ ] `uv run python scripts/check-tasks.py` temiz

## Doğrulama

```bash
uv run pytest tests/ -v && uv run python -c "import app; print('ok')"
```

Beklenen: **2 passed**, sonra `ok` yazıyor.

```bash
uv run python scripts/gen-litellm-config.py && grep -c model_name litellm-config.yaml
```

Beklenen: `7`.

Proxy'yi ayrı terminalde başlattıysan:

```bash
curl -s http://localhost:4000/v1/models | grep -o Qwen3 | wc -l
```

Beklenen: `7`.

## Bittiğinde

```bash
git add pyproject.toml uv.lock tests/ scripts/ .env.example .gitignore \
        app.py README.md CLAUDE.md docs/tasks/00-test-altyapisi.md
git commit -m "chore: test harness, optional mlx extra, local gateway aliases"
```
