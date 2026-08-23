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
`pytest` venv'de yok**, yani adım 2'nin kırmızısı ancak adım 1'den sonra
görülebilir.

## ⚠ PATH tuzağı — bu planı yürüten ajan önce bunu okusun

Bu makinede `/Users/uveyscengiz/.pyenv/shims/pytest` var. `uv run`, komutu
venv'de bulamazsa **PATH'e düşüyor** ve varsayılan sync *exact* değil. Sonuç:

```
uv run pytest --version   →  pytest 8.4.2, çıkış 0   (venv'de pytest YOKKEN)
```

Yani `pytest --version`'ın çalışması **hiçbir şey kanıtlamaz** — ne kırmızıyı
ne yeşili. Bu planda pytest'in varlığı **her zaman** lock ve venv üzerinden
ölçülür:

```bash
grep -c '^name = "pytest"' uv.lock     # 0 = yok, 1 = var
ls .venv/bin/pytest                     # yoksa "No such file"
```

Bu tutarsızlığı görüp "düzeltmeye" çalışma; shim başka projelerin.
(`litellm`'in shim'i yok, orada `uv run litellm --version` dürüst.)

## Genel kısıtlar

- **Algı katmanı donuk.** `gozcu/frames.py`, `detect.py`, `track.py`,
  `signals.py` bu planda **açılmıyor bile**.
- **Model kimlikleri sadece `gozcu/config.py`'da.** Bu plan `config.py`'a
  dokunmuyor. Yedi kademe adının `scripts/gen-litellm-config.py` içinde geçmesi
  bu kuralın bilinçli ve spec'te onaylanmış tek istisnası — script bir dağıtım
  artefaktı üretiyor, çalışma zamanı kodu değil.
- **`opencv-python`'a dokunulmuyor.** Gerekçe spec'te.
- **`uv.lock` commit edilir.**
- Mac'te günlük komut `uv sync --extra dev --extra mac`.
- `yaml` ayrı bir bağımlılık **değil** — `litellm[proxy]` üzerinden geliyor.
  Adım 3'te `import yaml` çalışıyorsa sebebi budur; `ImportError` alırsan
  çözüm `pyproject.toml`'a `pyyaml` eklemek değil, adım 1'i çalıştırmaktır.

## Spec'ten sapma — kabul edildi

Spec iki test tanımlıyordu. Bu plan **üçüncü bir test** ekliyor:
`test_ensure_server_running_explains_missing_mlx_vlm`. Gerekçe: adım 5'teki
koruma bu görevin **tek davranış değişikliği** ve spec'in kabul kriteri
"çalışma anında okunur hata veriyor" hiçbir testle bağlı değil.

Sapma inceleme sonucu **kabul edildi**, iki koşulla — ikisi de aşağıda
adımlaştırıldı:

1. Kırmızı adımda `subprocess.Popen` **ve** `time.sleep` de yamalanmalı
   (adım 5.1). Yoksa test gerçekten `uv run mlx_vlm.server` başlatır ve
   `60 × sleep(2)` = **iki dakika** bekler.
2. Spec üç yerde birden güncellenmeli (adım 6.3): test gövdesi python bloğuna,
   "Beklenen: 2 passed" → 3, ve kabul kriteri maddesindeki "2 test" → 3.
   `scripts/check-tasks.py` bu sayıyı mekanik denetliyor; biri eksik kalırsa
   planın kendi kapanış doğrulaması kırmızı olur.

---

## Görev 1: Paketleme — extra'lar ve kurulum

**Dosyalar:** `pyproject.toml` (düzenle), `uv.lock` (yeniden çözülür)

- [ ] **Adım 1.1 — kırmızıyı gör (PATH'e değil, lock'a bak).**
      `grep -c '^name = "pytest"' uv.lock` → `0`;
      `ls .venv/bin/pytest` → yok;
      `uv run --no-sync litellm --version` → "Failed to spawn".
- [ ] **Adım 1.2** — `[project.optional-dependencies]` ekle: `dev = ["pytest>=8.0",
      "pytest-cov>=5.0", "litellm[proxy]>=1.50"]`, `mac = ["mlx-vlm>=0.6.13"]`.
- [ ] **Adım 1.3** — `mlx-vlm`'i `[project].dependencies`'ten çıkar.
- [ ] **Adım 1.4** — `uv sync --extra dev --extra mac` (bu makine Mac).
- [ ] **Doğrula — yeşil de lock'tan okunur:**
      `grep -c '^name = "pytest"' uv.lock` → `1`;
      `ls .venv/bin/pytest` → var;
      `uv run litellm --version` → sürüm yazıyor.
- [ ] **Doğrula:** `uv run python -c "import mlx_vlm"` hâlâ çalışıyor
      (`mac` extra'sı sayesinde — bu, adım 1.3'ün demoyu kırmadığının kanıtı).
- [ ] **Doğrula:** `grep -c mlx-vlm pyproject.toml` → `1` (yalnız `mac`'te).

## Görev 2: Duman testleri

**Dosyalar:** `tests/__init__.py` (yeni, boş), `tests/test_smoke.py` (yeni)

**Arayüz:** `tests/__init__.py` `pytest`'in `sys.path`'e **repo kökünü**
eklemesini sağlıyor. `conftest.py` **yazılmıyor** — gerekçe spec'te.

- [ ] **Adım 2.1 — kırmızıyı gör.** `uv run pytest tests/ -v` → dizin yok hatası.
- [ ] **Adım 2.2** — `tests/__init__.py` boş oluştur.
      `uv run pytest tests/ -v; echo $?` → **5** (`NO_TESTS_COLLECTED`).
      Bu sayı, dizini boş bırakmamanın somut sebebi.
- [ ] **Adım 2.3** — `tests/test_smoke.py` yaz: `test_app_imports_without_mlx_vlm`
      ve `test_gozcu_config_is_importable` (gövdeler spec'te).
- [ ] **Doğrula:** `uv run pytest tests/ -v; echo $?` → 2 passed, `0`.
- [ ] **Doğrula — sahte yeşile dikkat.** `.venv`'de eski bir editable kurulum
      artefaktı var. Adım 1.4'ün `uv sync`'i (varsayılan *exact*) onu
      kaldırmış olmalı; kanıt **artefaktın yokluğu**:
      `ls .venv/lib/python3.12/site-packages | grep -i gozcu` → **boş**.
      (`import gozcu; print(gozcu.__file__)` bu işi görmez — editable finder de
      repo yolunu gösterir, iki durum ayırt edilemez.)

## Görev 3: Yerel gateway config üreticisi

**Dosyalar:** `scripts/gen-litellm-config.py` (yeni), `litellm-config.yaml`
(üretilir, commit **edilmez**)

- [ ] **Adım 3.1** — script'i spec'teki gövdeyle yaz.
- [ ] **Doğrula:** `uv run python scripts/gen-litellm-config.py && grep -c
      model_name litellm-config.yaml` → `7`.
- [ ] **Doğrula — yaml gerçekten ayrıştırılabiliyor** (`openai/qwen2.5:7b`
      içindeki iki nokta yaml'ı bozabilirdi):

```bash
uv run python -c "import yaml,pathlib; print(len(yaml.safe_load(pathlib.Path('litellm-config.yaml').read_text())['model_list']))"
```

Beklenen: `7`.

- [ ] **Doğrula — kademe adı kayması yok (gözle değil, komutla):**

```bash
uv run python - <<'EOF'
import pathlib, re, yaml

config = yaml.safe_load(pathlib.Path("litellm-config.yaml").read_text())
generated = {entry["model_name"] for entry in config["model_list"]}
task03 = pathlib.Path("docs/tasks/03-gateway.md").read_text()
declared = set(re.findall(r'GOZCU_MODEL_\w+",\s*"([^"]+)"', task03))
assert generated == declared, f"kayma: {generated ^ declared}"
print("yedi kademe adı Görev 03 ile aynı:", len(generated))
EOF
```

Beklenen: `yedi kademe adı Görev 03 ile aynı: 7`. Bir harf kayarsa gateway 400
döner ve sebebi görünmez — bu yüzden mekanik karşılaştırma.

- [ ] **Doğrula — kabul kriteri 4, proxy gerçekten yedi adı sunuyor mu.**
      Proxy terminali bloke eder; arka planda başlat, hazır olmasını bekle,
      sor, öldür:

```bash
uv run litellm --config litellm-config.yaml --port 4000 > /tmp/litellm-probe.log 2>&1 &
LITELLM_PID=$!
for _ in $(seq 40); do curl -sf http://localhost:4000/v1/models > /dev/null && break; sleep 1; done
curl -s http://localhost:4000/v1/models | grep -o Qwen3 | wc -l
kill $LITELLM_PID
```

Beklenen: `7`. Arka uç (Ollama) ayakta olmasa da `/v1/models` config'i
yansıtır. **Yansıtmıyorsa** — proxy ayağa kalkmıyor ya da uç boş dönüyorsa —
kriteri sessizce atlama: `/tmp/litellm-probe.log`'daki sebebi kapanış
listesine yaz ve kriteri "elle doğrulanacak" diye işaretle.

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
      yaz. **Dört şey birden yamalanmalı:**
      `app.OpenAI` (istemci `models.list()` fırlatsın ki erken dönüş olmasın),
      `importlib.util.find_spec` (`None` dönsün),
      **`app.subprocess.Popen`** ve **`app.time.sleep`**.
      Son ikisi olmadan test, korumadan önceki hâlde gerçekten
      `uv run mlx_vlm.server` başlatır ve `60 × sleep(2)` boyunca asılı kalır.
      Beklenen kırmızı: `RuntimeError` mesajında `mlx-vlm` **yok** (koruma
      yokken düşen mesaj `mlx_vlm.server` diyor — alt çizgili, tire değil).
- [ ] **Adım 5.2** — korumayı `_ensure_server_running()` içine, `hostname`
      kontrolünden **sonra** ve `Popen`'dan **önce** koy (gövde spec'te).
- [ ] **Doğrula:** `uv run pytest tests/ -v` → **3 passed**.
- [ ] **Doğrula — test hiçbir alt süreç açmıyor:** yamalanmış `Popen` için
      `assert_not_called()`. Testin süresi de kanıt: `uv run pytest tests/ -v
      --durations=3` → hiçbir test saniyeler sürmemeli.

## Görev 6: Belgeler

**Dosyalar:** `README.md` (yeni), `CLAUDE.md` (düzenle),
`docs/tasks/00-test-altyapisi.md` (sapma güncellemesi)

- [ ] **Adım 6.1** — `README.md`: sistem bir paragraf; `uv sync --extra dev`
      (Mac'te `--extra mac` de); **Linux sistem paketleri**
      (`sudo apt install ffmpeg libgl1 libglib2.0-0`, her birinin sebebiyle);
      `cp .env.example .env`; litellm'i **ayrı terminalde** çalıştırma;
      `uv run pytest tests/ -v`; `uv run --env-file .env python app.py`.
- [ ] **Adım 6.2** — `CLAUDE.md`'nin "Komutlar" bölümü README'ye işaret etsin ve
      `--env-file`'lı çalıştırma satırını göstersin.
- [ ] **Adım 6.3 — sapmayı spec'e işle, üçü birden:**
      (a) `test_ensure_server_running_explains_missing_mlx_vlm` gövdesini
      spec'teki python test bloğuna ekle;
      (b) "Beklenen: **2 passed**" → **3 passed**;
      (c) kabul kriteri maddesindeki "2 test, çıkış kodu 0" → "3 test".
      Üçü aynı commit'te olmalı — `check-tasks.py` #5 `def test_` sayısı ile
      "Beklenen: N passed" iddiasını karşılaştırıyor, biri eksik kalırsa
      "2 test var, [3] iddia ediliyor" der.
- [ ] **Doğrula:** `uv run python scripts/check-tasks.py` → "Hepsi temiz."
- [ ] **Doğrula — belge yalan söylemiyor:** README'deki komutlar sırayla
      çalıştırılsın; **`sudo apt` satırı hariç** (bu makine macOS) ve proxy
      satırı adım 3'teki arka plan reçetesiyle. `--env-file` satırı `.env`
      yokken hata verir — README `cp` satırını **önce** söylüyor mu?

## Kapanış doğrulaması

- [ ] `uv run pytest tests/ -v && uv run python -c "import app; print('ok')"`
      → **3 passed**, sonra `ok`. (pytest 5 dönerse `ok` hiç yazılmaz — bu
      komut aynı zamanda "boş tests/" regresyonunun kanıtı.)
- [ ] `uv run python scripts/check-tasks.py` → "Hepsi temiz."
- [ ] `git status --short` → `.env`, `litellm-config.yaml`, `*.pt` yok.
- [ ] **Kriter 1'i çıkarımla değil kanıtla işaretle.** Bu makinede her sync
      `--extra dev --extra mac` — yani jürinin yolu (yalnız `dev`) hiç
      çalıştırılmıyor. `grep -c mlx-vlm pyproject.toml` sadece *bildirimin*
      `mac`'te olduğunu gösterir, dev-only *çözümün* mlx'i dışladığını değil.
      Venv'e dokunmadan, lock'tan kanıt:

```bash
uv export --extra dev --no-extra mac | grep -ci mlx
```

Beklenen: `0`. Bu satır olmadan kriter 1'in ilk gerçek sınavı jürinin Ubuntu
makinesi olur.

- [ ] Spec'in sekiz kabul kriteri tek tek işaretlensin. İşaretlenemeyen varsa
      **neden** olduğu yazılsın — özellikle kriter 4 (proxy) elle bırakıldıysa.
