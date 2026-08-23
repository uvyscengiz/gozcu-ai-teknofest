# Uygulama planı — Görev 00: test altyapısı ve yerel gateway

> **Bu dosya yürütme artefaktıdır, spec değil.** Spec:
> [docs/tasks/00-test-altyapisi.md](../../tasks/00-test-altyapisi.md) — *ne* ve
> *neden* orada. Burada olan tek şey *hangi sırayla, hangi doğrulamayla*: alt
> ajanlara verilebilecek boyutta adımlar. Çift kayıt olmasın diye gerekçeler
> tekrar edilmiyor, spec'e link veriliyor.

> **Ajanlar için:** `superpowers:subagent-driven-development` ile görev görev
> yürütülür. Adımlar `- [ ]` kutucuklu.

**Hedef:** Diğer 18 görevin "testi yaz, koştur" adımını çalışır hâle getirmek;
`uv sync`'i Apple Silicon'a bağımlı olmaktan çıkarmak; yedi model kademesinin
hepsini çözen bir yerel gateway config'i üretmek.

**Mimari:** Yeni kod yok denecek kadar az. Bir üretici script
(`scripts/gen-litellm-config.py`), bir duman testi dosyası, `app.py`'de tek bir
koruma bloğu. Geri kalanı paketleme ve belge.

**Kritik sıra:** Adım 1 `dev` extra'sını tanımlayıp kuruyor. **Ondan önce
`pytest` diye bir şey yok**, yani adım 2'nin kırmızısı ancak adım 1'den sonra
görülebilir. Adım 1 atlanırsa sonraki her komut "Failed to spawn" der.

## Genel kısıtlar

- **Algı katmanı donuk.** `gozcu/frames.py`, `detect.py`, `track.py`,
  `signals.py` bu planda **açılmıyor bile**.
- **Model kimlikleri sadece `gozcu/config.py`'da.** Bu plan `config.py`'a
  dokunmuyor; yedi kademe adı `scripts/gen-litellm-config.py` içinde geçiyor ve
  oradaki liste Görev 03'ün `MODELS` bloğuyla **birebir aynı** olmalı.
- **`opencv-python`'a dokunulmuyor.** Gerekçe spec'te (headless takası
  `ultralytics` yüzünden işe yaramıyor).
- **`uv.lock` commit edilir.** Bağımlılık taşıması yapıyoruz; lock'suz commit
  jürinin makinesinde farklı sürüm çözer.
- Mac'te günlük komut `uv sync --extra dev --extra mac`. Yalnız `--extra dev`
  `mlx-vlm`'i siler ve 24 Ağustos demosunu kırar.

## Spec'ten bir sapma — onay bekliyor

Spec "2 passed" diyor. Bu plan **üçüncü bir test** ekliyor:
`test_ensure_server_running_explains_missing_mlx_vlm`. Gerekçe: adım 5'teki
koruma bu görevin **tek davranış değişikliği** ve spec'in kabul kriterlerinden
biri ("çalışma anında okunur hata veriyor") şu an hiçbir testle bağlanmamış
durumda — yani kimse bozduğunda haber vermez. Test ucuz: `app.OpenAI` ve
`importlib.util.find_spec` yamalanır, `RuntimeError` ve mesaj içeriği aranır.

Kabul edilirse spec'teki "Beklenen: **2 passed**" → **3 passed** güncellenir
(`scripts/check-tasks.py` bu sayıyı denetliyor, ikisi birlikte değişmeli).

---

## Görev 1: Paketleme — extra'lar ve kurulum

**Dosyalar:** `pyproject.toml` (düzenle), `uv.lock` (yeniden çözülür)

**Arayüz:** Sonraki her görev `uv run pytest` / `uv run litellm`'in var
olmasına dayanıyor.

- [ ] **Adım 1.1 — kırmızıyı gör.** `uv run pytest --version` → "Failed to
      spawn" beklenir. Bu, altyapının gerçekten yok olduğunun kanıtı.
- [ ] **Adım 1.2** — `[project.optional-dependencies]` ekle: `dev = ["pytest>=8.0",
      "pytest-cov>=5.0", "litellm[proxy]>=1.50"]`, `mac = ["mlx-vlm>=0.6.13"]`.
- [ ] **Adım 1.3** — `mlx-vlm`'i `[project].dependencies`'ten çıkar.
- [ ] **Adım 1.4** — `uv sync --extra dev --extra mac` (bu makine Mac).
- [ ] **Doğrula:** `uv run pytest --version` sürüm yazıyor; `uv run litellm
      --version` çalışıyor; `uv run python -c "import mlx_vlm"` hâlâ çalışıyor
      (mac extra'sı sayesinde).
- [ ] **Doğrula:** `grep -c mlx-vlm pyproject.toml` → `1` (sadece `mac`'te).

## Görev 2: Duman testleri

**Dosyalar:** `tests/__init__.py` (yeni, boş), `tests/test_smoke.py` (yeni)

**Arayüz:** `tests/__init__.py` `pytest`'in `sys.path`'e **repo kökünü**
eklemesini sağlıyor; `[tool.uv] package = false` olduğu için `import gozcu` ve
`import app` buna bağlı. `conftest.py` **yazılmıyor** — gerekçe spec'te.

- [ ] **Adım 2.1 — kırmızıyı gör.** `uv run pytest tests/ -v` → dizin yok.
- [ ] **Adım 2.2** — `tests/__init__.py` boş oluştur. `uv run pytest tests/ -v`
      → **çıkış kodu 5** (`NO_TESTS_COLLECTED`). Kodu `echo $?` ile gör; bu,
      dizini boş bırakmamanın somut sebebi.
- [ ] **Adım 2.3** — `tests/test_smoke.py` yaz: `test_app_imports_without_mlx_vlm`
      (`import app`, `process_video` var mı) ve `test_gozcu_config_is_importable`
      (`config.FRAME_FPS > 0`).
- [ ] **Doğrula:** `uv run pytest tests/ -v` → 2 passed, `echo $?` → `0`.
- [ ] **Doğrula — sahte yeşile dikkat:** `.venv` içinde eski bir editable kurulum
      (`__editable__.gozcu-0.1.0.pth`) var; `import gozcu` bu yüzden temiz bir
      klonda olmayan bir sebeple çalışıyor olabilir. Kanıt için:
      `uv run python -c "import gozcu; print(gozcu.__file__)"` → repo içindeki
      `gozcu/__init__.py`'ı göstermeli, `site-packages`'i değil.

## Görev 3: Yerel gateway config üreticisi

**Dosyalar:** `scripts/gen-litellm-config.py` (yeni), `litellm-config.yaml`
(üretilir, commit **edilmez**)

**Arayüz:** Yedi kademe adı Görev 03'ün `config.py`'daki `MODELS` bloğunun
değerleriyle aynı. `GOZCU_LOCAL_BASE` / `_MODEL` / `_VLM` ile yönlendirilebilir.

- [ ] **Adım 3.1** — script'i spec'teki gövdeyle yaz.
- [ ] **Doğrula:** `uv run python scripts/gen-litellm-config.py && grep -c
      model_name litellm-config.yaml` → `7`.
- [ ] **Doğrula — kayma yok:** üretilen yaml'daki yedi ad ile
      `docs/tasks/03-gateway.md`'deki `MODELS` değerleri programatik olarak
      karşılaştırılsın (gözle değil). Bir harf kayarsa gateway 400 döner ve
      sebebi görünmez.
- [ ] **Doğrula:** yaml gerçekten ayrıştırılabiliyor —
      `uv run python -c "import yaml,pathlib;
      d=yaml.safe_load(pathlib.Path('litellm-config.yaml').read_text());
      print(len(d['model_list']))"` → `7`. (`openai/qwen2.5:7b` içindeki iki
      nokta üst üste yaml'ı bozabilirdi; bozmadığı ölçülsün.)

## Görev 4: Ortam dosyaları

**Dosyalar:** `.env.example` (yeni), `.gitignore` (düzenle)

- [ ] **Adım 4.1** — `.env.example`: `GOZCU_GATEWAY_BASE_URL=http://localhost:4000/v1`,
      `GOZCU_GATEWAY_API_KEY=not-needed`.
- [ ] **Adım 4.2** — `.gitignore`'a `.env` ve `litellm-config.yaml` ekle.
- [ ] **Doğrula:** `cp .env.example .env && uv run --env-file .env python -c
      "import os; print(os.environ['GOZCU_GATEWAY_BASE_URL'])"` → adresi yazıyor.
- [ ] **Doğrula:** `git status --short` çıktısında `.env` ve
      `litellm-config.yaml` **görünmüyor**.

## Görev 5: `app.py` — `mlx_vlm` koruması

**Dosyalar:** `app.py` (düzenle), `tests/test_smoke.py` (test ekle)

**Arayüz:** `_ensure_server_running()`, alt süreci açmadan önce paketin
varlığına bakar. `app.py`'nin geri kalanı ve `gozcu/` **değişmiyor**.

- [ ] **Adım 5.1 — kırmızıyı gör.** `test_ensure_server_running_explains_missing_mlx_vlm`
      yaz: `app.OpenAI` yamalanır (`models.list()` fırlatsın), `importlib.util
      .find_spec` `None` döndürsün; `RuntimeError` beklenir ve mesajında
      `mlx-vlm` geçmeli. Koruma yokken test, `Popen`'ın gerçekten `uv run`
      çağırmasıyla ya da farklı bir hatayla düşer.
- [ ] **Adım 5.2** — korumayı `_ensure_server_running()` içine, `hostname`
      kontrolünden **sonra** ve `Popen`'dan **önce** koy. Mesaj Türkçe ve
      `uv sync --extra dev --extra mac` demeli.
- [ ] **Doğrula:** `uv run pytest tests/ -v` → 3 passed (sapma onaylandıysa).
- [ ] **Doğrula:** testin gerçekten hiçbir alt süreç açmadığını gör —
      `Popen` da yamalanmış olsun, yamanın çağrılmadığı `assert_not_called()`
      ile kanıtlansın. Aksi hâlde test yavaş yavaş bir `uv run` başlatır.

## Görev 6: Belgeler

**Dosyalar:** `README.md` (yeni), `CLAUDE.md` (düzenle),
`docs/tasks/00-test-altyapisi.md` (test sayısı, sapma onaylandıysa)

- [ ] **Adım 6.1** — `README.md`: sistem bir paragraf; `uv sync --extra dev`
      (Mac'te `--extra mac` de); **Linux sistem paketleri**
      (`sudo apt install ffmpeg libgl1 libglib2.0-0`, her birinin sebebiyle);
      `cp .env.example .env`; litellm'i **ayrı terminalde** çalıştırma;
      `uv run pytest tests/ -v`; `uv run --env-file .env python app.py`.
- [ ] **Adım 6.2** — `CLAUDE.md`'nin "Komutlar" bölümü README'ye işaret etsin ve
      `--env-file`'lı çalıştırma satırını göstersin.
- [ ] **Adım 6.3** — sapma onaylandıysa spec'teki "Beklenen: **2 passed**" →
      **3 passed**.
- [ ] **Doğrula:** `uv run python scripts/check-tasks.py` temiz (kırık link ve
      test sayısı denetimleri README/spec değişikliklerini yakalar).
- [ ] **Doğrula — belge yalan söylemiyor:** README'deki her komut sırayla
      kopyala-yapıştır çalıştırılsın. `--env-file` satırı `.env` yokken hata
      verir; README `cp` satırını **önce** söylüyor mu?

## Kapanış doğrulaması

- [ ] `uv run pytest tests/ -v && uv run python -c "import app; print('ok')"`
      → 3 passed, sonra `ok`. (Çıkış kodu zinciri: pytest 5 dönerse `ok`
      hiç yazılmaz — bu komut aynı zamanda "boş tests/" regresyonunun kanıtı.)
- [ ] `uv run python scripts/check-tasks.py` → "Hepsi temiz."
- [ ] `git status --short` → `.env`, `litellm-config.yaml`, `*.pt` yok.
- [ ] Spec'in sekiz kabul kriteri tek tek işaretlensin; işaretlenemeyen varsa
      **neden** olduğu yazılsın, sessizce bırakılmasın.
