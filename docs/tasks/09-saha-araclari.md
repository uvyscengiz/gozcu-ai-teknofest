# Görev 09 — Yedi saha sistemi aracı (`gozcu/tools/`)

**Sahip:** `Xana-bit` · **Gün:** 25 Ağustos · **Süre:** ~3 saat
**Bağımlılık:** [01](01-sozlesme.md), [02](02-olay-deposu.md), [10](10-tesis-dunyasi.md)
**Etiket:** `cold-start` — bu kod tabanını ilk kez görüyorsan bu görev sana göre

## Bağlam

### Proje ne?

Gözcü, fabrika kamera kaydını izleyip olayları fark eden ve operatörle Türkçe
konuşan bir karar destek sistemi. TEKNOFEST Yapay Zekâ Dil Ajanları Yarışması,
3. senaryo. Teslim 26 Ağustos 23:59.

### Bu görev neden var?

Sistemin ajanı "sağlık ekibini çağırın" diye bir **cümle yazmıyor** — sağlık
ekibini gerçekten **arıyor.** Bu araçlar o çağrıların gittiği sahte saha
sistemleri: telsiz, alarm, İSG kaydı, vardiya listesi, ekipman geçmişi.

Şartname bunları iki ayrı yerde puanlıyor (*"mock fonksiyonların ajanın araçları
olarak başarıyla kullanılması"* ve *"mock sistem entegrasyonunun başarısı"*) ve
ayrıca teslim kalemi olarak sayıyor. Puanın %70'inin bulunduğu iki kalemden
ikisine birden dokunuyorsun.

**İyi haber:** bu görev hiçbir yapay zekâ modeli çağırmıyor. Saf Python
fonksiyonları, sözlük döndürüyor. Gateway erişimin olmasa da tamamen çalışır.

## Kurulum

```bash
git clone git@github.com:uvyscengiz/gozcu-ai-teknofest.git
cd gozcu-ai-teknofest
uv sync --extra dev
uv run pytest tests/ -v          # mevcut testler geçmeli
```

## Bağımlı olduğun imzalar

Bunların hepsi zaten yazılmış durumda, sen sadece kullanacaksın:

```python
# gozcu/models.py
AksiyonKaydi(id: int | None, ts: float, tool_adi: str, parametreler: dict,
             sonuc: dict, kim: "ajan" | "operator",
             onay_durumu: "gerekmiyor" | "bekliyor" | "onaylandi" | "reddedildi")

# gozcu/store.py
Store(db_path=":memory:")
Store.kaydet_aksiyon(a: AksiyonKaydi) -> int
Store.aksiyonlar() -> list[AksiyonKaydi]
```

Fixture dosyaları [Görev 10](10-tesis-dunyasi.md)'dan geliyor ve o da sende.
İkisini birlikte yap: önce 10, sonra 09.

## Ne yapacaksın

İki modül:

**`gozcu/tools/saha.py`** — yedi fonksiyon. İkisi **okuma** (ajanın muhakemesini
besliyor), beşi **aksiyon**.

| Araç | Tür | Döner |
|---|---|---|
| `vardiya_personel_sorgula(bolge, zaman)` | okuma | vardiyadaki personel, roller, **yetki belgeleri** |
| `ekipman_gecmisi_sorgula(ekipman_id)` | okuma | bakım geçmişi, arıza kayıtları |
| `saha_telsiz_cagrisi(birim, mesaj)` | aksiyon | `{cagri_id, durum, yanit_bekleniyor}` |
| `saglik_ekibi_cagir(konum, aciliyet, aciklama)` | aksiyon | `{talep_id, ekip, tahmini_varis_dk}` |
| `saha_alarmi(bolge, seviye)` | aksiyon | `{alarm_id, etkilenen_bolge, siren_durumu}` |
| `isg_olay_kaydi_ac(epizot_id, siniflandirma, aciklama)` | aksiyon | `{kayit_no, durum}` |
| `uretim_hatti_durdur(hat_id, gerekce)` | aksiyon | `{onay_bekliyor: True}` |

Okuma/aksiyon karışımı kasıtlı: ajan önce sorgulayıp sonra mı harekete geçecek,
yoksa doğrudan mı — bu gerçek bir karar ve şartnamenin *"dinamik araç seçimi"*
kalemi tam olarak burada görünür hale geliyor.

`uretim_hatti_durdur` **operatör onayı istiyor.** Ajan geri dönüşü zor bir
aksiyonu tek başına almıyor.

**`gozcu/tools/registry.py`** — araç şemaları, dağıtım, aksiyon defteri.

```python
ARACLAR: dict[str, Callable]
ARAC_SEMALARI: list[dict]          # OpenAI tool-schema formatı
ONAY_GEREKTIREN: set[str] = {"uretim_hatti_durdur"}
cagir(store, tool_adi, parametreler, kim="ajan", onay_durumu=None) -> dict
```

`onay_durumu` parametresi Görev 14'ün onay akışı için: operatör onayladığında
aynı araç `onay_durumu="onaylandi"` ile çağrılıyor, yoksa her onay yeni bir
bekleyen kayıt doğurur.

## Adımlar

### 1. Başarısız testi yaz — `tests/test_tools.py`

```python
import pytest

from gozcu.store import Store
from gozcu.tools.registry import ARAC_SEMALARI, ARACLAR, ONAY_GEREKTIREN, cagir


def test_every_call_lands_in_the_action_ledger():
    store = Store(":memory:")
    cagir(store, "saha_telsiz_cagrisi",
          {"birim": "vardiya amiri", "mesaj": "B-Hattı'na gel"})
    kayit = store.aksiyonlar()[0]
    assert kayit.tool_adi == "saha_telsiz_cagrisi" and kayit.kim == "ajan"
    assert kayit.onay_durumu == "gerekmiyor"


def test_line_stop_waits_for_operator_approval():
    store = Store(":memory:")
    sonuc = cagir(store, "uretim_hatti_durdur",
                  {"hat_id": "B", "gerekce": "devrilme"})
    assert sonuc["onay_bekliyor"] is True
    assert store.aksiyonlar()[0].onay_durumu == "bekliyor"
    assert "uretim_hatti_durdur" in ONAY_GEREKTIREN


def test_explicit_approval_state_overrides_the_default():
    store = Store(":memory:")
    cagir(store, "uretim_hatti_durdur", {"hat_id": "B", "gerekce": "x"},
          kim="operator", onay_durumu="onaylandi")
    assert store.aksiyonlar()[0].onay_durumu == "onaylandi"


def test_shift_query_returns_certifications_so_the_agent_can_reason():
    kisiler = cagir(Store(":memory:"), "vardiya_personel_sorgula",
                    {"bolge": "B-Hattı", "zaman": "03:12"})["personel"]
    assert kisiler and all("yetkiler" in k for k in kisiler)


def test_equipment_history_exposes_overdue_maintenance():
    gecmis = cagir(Store(":memory:"), "ekipman_gecmisi_sorgula",
                   {"ekipman_id": "IST-04"})
    assert gecmis["geciken_bakim_ay"] >= 4


def test_unknown_equipment_returns_a_flag_not_an_exception():
    g = cagir(Store(":memory:"), "ekipman_gecmisi_sorgula",
              {"ekipman_id": "YOK-99"})
    assert g["bulunamadi"] is True


def test_unknown_tool_raises_rather_than_silently_succeeding():
    with pytest.raises(KeyError):
        cagir(Store(":memory:"), "nukleer_firlat", {})


def test_schemas_cover_every_registered_tool():
    assert {s["function"]["name"] for s in ARAC_SEMALARI} == set(ARACLAR)


def test_every_schema_declares_its_required_parameters():
    for s in ARAC_SEMALARI:
        p = s["function"]["parameters"]
        assert p["required"] and set(p["required"]) <= set(p["properties"])
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_tools.py -v
```
Beklenen: `ModuleNotFoundError: No module named 'gozcu.tools'`

### 3. `gozcu/tools/saha.py` yaz

`gozcu/tools/__init__.py` (boş) de gerekiyor.

```python
import json
from pathlib import Path

FIXTURE = Path(__file__).parent.parent / "fixtures"
_sayac = {"cagri": 1000, "talep": 2000, "alarm": 3000, "kayit": 4000}


def _no(tur: str) -> str:
    _sayac[tur] += 1
    return f"2026-{_sayac[tur]}"


def _yukle(ad: str) -> dict:
    return json.loads((FIXTURE / f"{ad}.json").read_text(encoding="utf-8"))


def saha_telsiz_cagrisi(birim: str, mesaj: str) -> dict:
    return {"cagri_id": _no("cagri"), "birim": birim, "mesaj": mesaj,
            "durum": "iletildi", "yanit_bekleniyor": True}


def saglik_ekibi_cagir(konum: str, aciliyet: str, aciklama: str = "") -> dict:
    return {"talep_id": _no("talep"), "konum": konum, "ekip": "Revir-2",
            "tahmini_varis_dk": 2 if aciliyet == "kritik" else 8}


def saha_alarmi(bolge: str, seviye: str) -> dict:
    return {"alarm_id": _no("alarm"), "etkilenen_bolge": bolge,
            "siren_durumu": "aktif", "seviye": seviye}


def isg_olay_kaydi_ac(epizot_id: int, siniflandirma: str,
                      aciklama: str = "") -> dict:
    return {"kayit_no": _no("kayit"), "siniflandirma": siniflandirma,
            "durum": "acik", "epizot_id": epizot_id}


def uretim_hatti_durdur(hat_id: str, gerekce: str) -> dict:
    return {"hat_id": hat_id, "gerekce": gerekce, "onay_bekliyor": True}


def vardiya_personel_sorgula(bolge: str, zaman: str) -> dict:
    veri = _yukle("personel")
    return {"bolge": bolge, "zaman": zaman,
            "personel": [k for k in veri["personel"] if k["bolge"] == bolge]}


def ekipman_gecmisi_sorgula(ekipman_id: str) -> dict:
    kayit = _yukle("ekipman")["ekipman"].get(ekipman_id)
    if kayit is None:
        return {"ekipman_id": ekipman_id, "bulunamadi": True}
    return {"ekipman_id": ekipman_id, **kayit}
```

### 4. `gozcu/tools/registry.py` yaz

```python
from gozcu.models import AksiyonKaydi
from gozcu.tools import saha

ARACLAR = {
    "saha_telsiz_cagrisi": saha.saha_telsiz_cagrisi,
    "saglik_ekibi_cagir": saha.saglik_ekibi_cagir,
    "saha_alarmi": saha.saha_alarmi,
    "isg_olay_kaydi_ac": saha.isg_olay_kaydi_ac,
    "uretim_hatti_durdur": saha.uretim_hatti_durdur,
    "vardiya_personel_sorgula": saha.vardiya_personel_sorgula,
    "ekipman_gecmisi_sorgula": saha.ekipman_gecmisi_sorgula,
}

ONAY_GEREKTIREN = {"uretim_hatti_durdur"}

_ACIKLAMA = {
    "saha_telsiz_cagrisi": ("Bir saha birimini telsizle arar.",
                            {"birim": "string", "mesaj": "string"}),
    "saglik_ekibi_cagir": ("Revir sağlık ekibini olay yerine çağırır.",
                           {"konum": "string", "aciliyet": "string",
                            "aciklama": "string"}),
    "saha_alarmi": ("Bölgesel sesli alarmı çalıştırır.",
                    {"bolge": "string", "seviye": "string"}),
    "isg_olay_kaydi_ac": ("İş güvenliği olay kaydı açar.",
                          {"epizot_id": "integer", "siniflandirma": "string",
                           "aciklama": "string"}),
    "uretim_hatti_durdur": ("Üretim hattını durdurur. Operatör onayı gerekir.",
                            {"hat_id": "string", "gerekce": "string"}),
    "vardiya_personel_sorgula": ("Bir bölgede vardiyadaki personeli ve yetki "
                                 "belgelerini getirir.",
                                 {"bolge": "string", "zaman": "string"}),
    "ekipman_gecmisi_sorgula": ("Bir ekipmanın bakım ve arıza geçmişini "
                                "getirir.", {"ekipman_id": "string"}),
}

ARAC_SEMALARI = [{
    "type": "function",
    "function": {
        "name": ad,
        "description": aciklama,
        "parameters": {
            "type": "object",
            "properties": {p: {"type": t} for p, t in parametreler.items()},
            "required": list(parametreler),
        },
    },
} for ad, (aciklama, parametreler) in _ACIKLAMA.items()]


def cagir(store, tool_adi: str, parametreler: dict, kim: str = "ajan",
          onay_durumu: str | None = None) -> dict:
    fn = ARACLAR[tool_adi]          # bilinmeyen araçta KeyError — kasıtlı
    sonuc = fn(**parametreler)
    if onay_durumu is None:
        onay_durumu = ("bekliyor" if tool_adi in ONAY_GEREKTIREN
                       else "gerekmiyor")
    store.kaydet_aksiyon(AksiyonKaydi(
        ts=0.0, tool_adi=tool_adi, parametreler=parametreler, sonuc=sonuc,
        kim=kim, onay_durumu=onay_durumu))
    return sonuc
```

### 5. Yeşil olduğunu gör

```bash
uv run pytest tests/test_tools.py -v
```
Beklenen: 9 passed

3. ve 5. testler [Görev 10](10-tesis-dunyasi.md)'un fixture dosyalarına ihtiyaç
duyuyor. Görev 10'u önce yaptıysan geçerler.

### 6. Commit

```bash
git add gozcu/tools tests/test_tools.py
git commit -m "feat: seven mock field-system tools with an action ledger"
```

## Doğrulama

```bash
uv run pytest tests/test_tools.py -v
```
Beklenen: **9 passed**

## Takıldığında

Üveys'e yaz. **Bekleme** — bu sprintte bir saat, toplam kapasitenin yaklaşık %4'ü.
