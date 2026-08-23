# Görev 14 — Nöbetçi süpervizör (`gozcu/agents/nobetci.py`)

**Sahip:** `uvyscengiz` · **Gün:** 25 Ağustos · **Süre:** ~4 saat
**Bağımlılık:** [08](08-hafiza.md), [09](09-saha-araclari.md), [11](11-risk-analisti.md), [12](12-raportor.md), [13](13-guard.md)
**Puanın %20'si burada yaşıyor — projedeki en yüksek getirili tek dosya**

## Bağlam

Operatörün konuştuğu ajan. Şartnamenin "Otonomi ve Zeka" kalemi (%20) kelimesi
kelimesine şunları istiyor ve dördü de bu dosyada karşılanıyor:

| Şartname kriteri | Bu dosyada nerede |
|---|---|
| *"diyalog sırasında inisiyatif alma"* | `yukselt()` — kimse sormadan operatöre seslenir |
| *"doğru soruları sorma"* | Belirsizlik notu — kameradan göremediğini sorar |
| *"beklenmedik durumlara (bağlam değişimi) tepki"* | `konus()` açık olayı isteme ekler |
| *"doğal ve insansı akış"* | Sistem promptu + Türkçe üslup |

Süpervizörün kendi araçları (`zaman_cizelgesi_ara`, `gozlem_duzelt`,
`risk_analizi_iste`, `kok_neden_raporu_uret`) yedi saha aracının **yanına**
ekleniyor — böylece iki tür arasında seçim yapmak model için tek bir karar
oluyor ve *"dinamik araç seçimi"* gerçekten gözlenebiliyor.

### Üç ince nokta

**Düzeltme kaskadı.** Operatör bir şeyi düzelttiğinde `duzeltme` tablosuna
yazmak yetmiyor — epizot özeti de güncellenmeli ve risk analizi yeniden
koşmalı. Aksi halde "düzeltme her yere yayılır" iddiası prompt umuduna kalır ve
`duzeltme_yayilimi` KPI'ı %0 okur.

**Onay akışı.** Operatör bir aksiyonu onayladığında aracı yeniden `cagir` ile
çağırırsan **yeni bir bekleyen kayıt** doğar ve onay çubuğu hiç kapanmaz.
`onay_durumu="onaylandi"` geçirmek ve orijinal satırı `aksiyon_durumu` ile
güncellemek zorunlu.

**Belirsizlik notu.** Beat 2 — *"yerdeki kişi hareket ediyor mu, göremiyorum"* —
promptta bir cümleye bırakılırsa güvenilir tetiklenmez. Sinyallerden gerçek bir
belirsizlik notu üretip yükseltme mesajına koyuyoruz: kadraj dışına çıkan track
varsa ajan neyi göremediğini biliyor ve sorusu kendiliğinden geliyor.

## Kurulum

```bash
uv sync --extra dev
uv run pytest tests/ -v      # 08, 09, 11, 12, 13 yeşil olmalı
```

## Bağımlı olduğun imzalar

```python
# gozcu/tools/registry.py
ARAC_SEMALARI: list[dict]
ONAY_GEREKTIREN: set[str] = {"uretim_hatti_durdur"}
cagir(store, tool_adi, parametreler, kim="ajan", onay_durumu=None) -> dict

# gozcu/memory.py
zaman_cizelgesi_ara(gw, store, sorgu, ust_k=5) -> list[Epizot]

# gozcu/agents/risk.py
risk_analiz_et(gw, store, epizot: Epizot) -> RiskDegerlendirme

# gozcu/agents/raportor.py
kok_neden_raporu_uret(gw, store) -> KokNedenRaporu

# gozcu/guard.py
denetle(gw, metin: str, kritik: bool = False) -> str

# gozcu/store.py
Store.kaydet_diyalog, Store.kaydet_duzeltme, Store.epizot_guncelle,
Store.acik_epizot, Store.epizotlar, Store.aksiyonlar, Store.aksiyon_durumu

# gozcu/agents/router.py
mmss(ts: float) -> str
```

## Ne yapacaksın

```python
Nobetci(gw, store)
  .yukselt(epizot: Epizot) -> str        # proaktif açılış — beat 1
  .konus(operator_metni: str) -> str     # bir diyalog turu
  .bekleyen_onay() -> AksiyonKaydi | None
  .onayla(aksiyon_id: int, onay: bool) -> dict
```

## Adımlar

### 1. Başarısız testi yaz — `tests/test_nobetci.py`

```python
import json
from unittest.mock import Mock, patch

from gozcu.agents.nobetci import Nobetci, belirsizlik_notu
from gozcu.gateway import Yanit
from gozcu.models import (AksiyonKaydi, Epizot, RiskDegerlendirme, Sinyaller)
from gozcu.store import Store


def _arac(ad, params):
    return Yanit(arac_cagrilari=[{"id": "c1", "type": "function",
                                  "function": {"name": ad,
                                               "arguments": json.dumps(params)}}])


def _kurulum(yanitlar):
    gw = Mock(); gw.sor.side_effect = yanitlar
    store = Store(":memory:")
    e = Epizot(baslangic_ts=192.0, faz="gelisim",
               ozet_tr="istif aracı devrildi, yerde hareketsiz kişi",
               on_risk="Kritik")
    e.id = store.epizot_ac(e)
    return gw, store, e


def _risk(e):
    return RiskDegerlendirme(epizot_id=e.id, seviye="Kritik",
                             gerekce_tr="g", onlenebilir=True)


def test_uncertainty_note_names_what_the_camera_cannot_see():
    n = belirsizlik_notu(Sinyaller(kaybolan_trackler=[3], kisi_sayisi=1))
    assert n and "göremiyor" in n.lower()
    assert belirsizlik_notu(Sinyaller(kisi_sayisi=1)) == ""


def test_escalation_queries_the_shift_before_speaking():
    gw, store, e = _kurulum([
        _arac("vardiya_personel_sorgula",
              {"bolge": "B-Hattı", "zaman": "03:12"}),
        Yanit(icerik="03:12 — B-Hattı'nda istif aracı devrildi. Risk: Kritik."),
        Yanit(icerik="uygun"),
    ])
    with patch("gozcu.agents.nobetci.risk_analiz_et", return_value=_risk(e)):
        mesaj = Nobetci(gw, store).yukselt(e)
    assert "vardiya_personel_sorgula" in [a.tool_adi for a in store.aksiyonlar()]
    assert "03:12" in mesaj


def test_critical_escalation_is_not_filtered_by_the_guard():
    gw, store, e = _kurulum([
        Yanit(icerik="KRİTİK: yerde hareketsiz kişi var."),
    ])
    with patch("gozcu.agents.nobetci.risk_analiz_et", return_value=_risk(e)), \
         patch("gozcu.agents.nobetci.denetle") as g:
        Nobetci(gw, store).yukselt(e)
    assert g.call_args.kwargs["kritik"] is True


def test_line_stop_is_held_for_approval_and_not_executed():
    gw, store, _ = _kurulum([
        _arac("uretim_hatti_durdur", {"hat_id": "B", "gerekce": "devrilme"}),
        Yanit(icerik="B-Hattı'nı durdurmamı ister misiniz?"),
        Yanit(icerik="uygun"),
    ])
    n = Nobetci(gw, store)
    n.konus("durumu özetle")
    bekleyen = n.bekleyen_onay()
    assert bekleyen is not None and bekleyen.tool_adi == "uretim_hatti_durdur"


def test_approving_does_not_create_a_second_pending_approval():
    gw, store, _ = _kurulum([
        _arac("uretim_hatti_durdur", {"hat_id": "B", "gerekce": "x"}),
        Yanit(icerik="onay?"), Yanit(icerik="uygun"),
    ])
    n = Nobetci(gw, store)
    n.konus("dur")
    n.onayla(n.bekleyen_onay().id, True)
    assert n.bekleyen_onay() is None
    assert [a.onay_durumu for a in store.aksiyonlar()].count("bekliyor") == 0


def test_refusing_marks_the_action_rejected_and_does_not_run_it():
    gw, store, _ = _kurulum([
        _arac("uretim_hatti_durdur", {"hat_id": "B", "gerekce": "x"}),
        Yanit(icerik="onay?"), Yanit(icerik="uygun"),
    ])
    n = Nobetci(gw, store)
    n.konus("dur")
    onceki = len(store.aksiyonlar())
    n.onayla(n.bekleyen_onay().id, False)
    assert len(store.aksiyonlar()) == onceki
    assert store.aksiyonlar()[-1].onay_durumu == "reddedildi"


def test_correction_is_recorded_and_cascades_to_the_episode_summary():
    gw, store, e = _kurulum([
        _arac("gozlem_duzelt",
              {"epizot_id": 1, "alan": "olay_turu", "eski": "araç devrildi",
               "yeni": "yük düştü", "gerekce": "operatör gözlemi"}),
        Yanit(icerik="Anlaşıldı, kaydı güncelledim."),
        Yanit(icerik="uygun"),
    ])
    with patch("gozcu.agents.nobetci.risk_analiz_et", return_value=_risk(e)):
        Nobetci(gw, store).konus("araç devrilmedi, yük düştü")
    assert store.duzeltmeler(1)[0].yeni == "yük düştü"
    assert "yük düştü" in store.epizotlar()[0].ozet_tr


def test_correction_re_runs_the_risk_assessment():
    gw, store, e = _kurulum([
        _arac("gozlem_duzelt",
              {"epizot_id": 1, "alan": "olay_turu", "eski": "a", "yeni": "b",
               "gerekce": "g"}),
        Yanit(icerik="tamam"), Yanit(icerik="uygun"),
    ])
    with patch("gozcu.agents.nobetci.risk_analiz_et",
               return_value=_risk(e)) as r:
        Nobetci(gw, store).konus("düzeltme")
    r.assert_called_once()


def test_open_incident_is_appended_to_every_operator_turn():
    gw, store, _ = _kurulum([Yanit(icerik="cevap"), Yanit(icerik="uygun")])
    Nobetci(gw, store).konus("dur, başka bir şey soracağım")
    istem = gw.sor.call_args_list[0].args[1][-1]["content"]
    assert "Açık olay" in istem


def test_dialogue_turns_are_recorded_both_sides():
    gw, store, _ = _kurulum([Yanit(icerik="Anlaşıldı."), Yanit(icerik="uygun")])
    Nobetci(gw, store).konus("durum nedir?")
    assert [s.rol for s in store.diyalog()] == ["operator", "nobetci"]


def test_tool_loop_terminates_instead_of_spinning_forever():
    gw, store, _ = _kurulum([_arac("saha_alarmi", {"bolge": "B",
                                                   "seviye": "yuksek"})] * 12)
    cevap = Nobetci(gw, store).konus("alarm çal")
    assert cevap and gw.sor.call_count <= 6
```

### 2. Kırmızı olduğunu gör

```bash
uv run pytest tests/test_nobetci.py -v
```
Beklenen: `ModuleNotFoundError`

### 3. `gozcu/agents/nobetci.py` yaz

```python
import json

from gozcu.agents.router import mmss
from gozcu.agents.risk import risk_analiz_et
from gozcu.memory import zaman_cizelgesi_ara
from gozcu.models import DiyalogSatiri, Duzeltme, Epizot, Sinyaller
from gozcu.tools.registry import ARAC_SEMALARI, cagir

MAKS_TUR = 4

SISTEM = """Sen bir savunma sanayi üretim tesisinin kontrol odasında görevli
vardiya amirisin. Operatörle Türkçe konuşuyorsun.

Nasıl davranırsın:
- Kritik bir olay gördüğünde SORULMADAN önce sen haber verirsin
- Konuşmadan önce gerekli sorguları yaparsın (vardiya, ekipman geçmişi)
- Kameradan göremediğin bir şeyi UYDURMAZSIN, operatöre sorarsın
- Operatör seni düzeltirse gozlem_duzelt aracını çağırırsın
- Operatör konuyu değiştirirse cevaplarsın ama AÇIK OLAYI HATIRLATIRSIN
- Geri dönüşü zor aksiyonlarda (hat durdurma) İZİN İSTERSİN
- Kısa cümleler kurarsın. Saha terminolojisi kullanırsın.

Zaman damgalarını MM:SS biçiminde yazarsın."""

EK_ARACLAR = [
    {"type": "function", "function": {
        "name": "zaman_cizelgesi_ara",
        "description": "Geçmiş olay arşivinde anlamsal arama yapar.",
        "parameters": {"type": "object",
                       "properties": {"sorgu": {"type": "string"}},
                       "required": ["sorgu"]}}},
    {"type": "function", "function": {
        "name": "gozlem_duzelt",
        "description": "Operatörün düzeltmesini kalıcı olarak kaydeder.",
        "parameters": {"type": "object", "properties": {
            "epizot_id": {"type": "integer"}, "alan": {"type": "string"},
            "eski": {"type": "string"}, "yeni": {"type": "string"},
            "gerekce": {"type": "string"}},
            "required": ["epizot_id", "alan", "eski", "yeni", "gerekce"]}}},
    {"type": "function", "function": {
        "name": "risk_analizi_iste",
        "description": "Bir olay için iş güvenliği risk analizi ister.",
        "parameters": {"type": "object",
                       "properties": {"epizot_id": {"type": "integer"}},
                       "required": ["epizot_id"]}}},
    {"type": "function", "function": {
        "name": "kok_neden_raporu_uret",
        "description": "Kapanan olay için kök neden raporu üretir.",
        "parameters": {"type": "object", "properties": {}, "required": []}}},
]


def belirsizlik_notu(sinyaller: Sinyaller) -> str:
    """Kameranın göremediğini açıkça adlandırır.

    Beat 2 buna dayanıyor: 'yerdeki kişi hareket ediyor mu, göremiyorum'
    sorusunu prompt umuduna bırakmak yerine, sinyallerden türetilmiş gerçek
    bir belirsizlik notuyla güvenilir şekilde tetikliyoruz.
    """
    notlar = []
    if sinyaller.kaybolan_trackler:
        notlar.append("bazı nesneler kadraj dışına çıktı, durumlarını "
                      "göremiyorum")
    if sinyaller.kisi_sayisi and not sinyaller.hizlar:
        notlar.append("yerdeki kişinin hareket edip etmediğini bu açıdan "
                      "göremiyorum")
    return ("BELİRSİZLİK: " + "; ".join(notlar)) if notlar else ""


class Nobetci:
    def __init__(self, gw, store) -> None:
        self.gw, self.store = gw, store
        self.gecmis: list[dict] = [{"role": "system", "content": SISTEM}]

    # -- iç araçlar ---------------------------------------------------------

    def _duzelt(self, p: dict) -> dict:
        """Düzeltmeyi kaydeder VE yayar: epizot özeti güncellenir, risk
        yeniden koşar. Sadece tabloya yazmak, hiçbir şey yapmamaktır."""
        self.store.kaydet_duzeltme(Duzeltme(ts=0.0, **p))
        epizot = next((e for e in self.store.epizotlar()
                       if e.id == p["epizot_id"]), None)
        if epizot is None:
            return {"durum": "kaydedildi", "uyari": "epizot bulunamadı"}

        yeni_ozet = epizot.ozet_tr.replace(p["eski"], p["yeni"])
        if yeni_ozet == epizot.ozet_tr:
            yeni_ozet = f"{epizot.ozet_tr} (operatör düzeltmesi: {p['yeni']})"
        self.store.epizot_guncelle(epizot.id, ozet_tr=yeni_ozet[:600])

        guncel = next(e for e in self.store.epizotlar() if e.id == epizot.id)
        risk = risk_analiz_et(self.gw, self.store, guncel)
        return {"durum": "kaydedildi", "yeni_ozet": yeni_ozet,
                "yeni_risk": risk.seviye}

    def _ic_arac(self, ad: str, p: dict):
        if ad == "zaman_cizelgesi_ara":
            return {"sonuclar": [e.model_dump() for e in
                                 zaman_cizelgesi_ara(self.gw, self.store,
                                                     p["sorgu"])]}
        if ad == "gozlem_duzelt":
            return self._duzelt(p)
        if ad == "risk_analizi_iste":
            epizot = next((e for e in self.store.epizotlar()
                           if e.id == p["epizot_id"]), None)
            if epizot is None:
                return {"hata": "epizot bulunamadı"}
            return risk_analiz_et(self.gw, self.store, epizot).model_dump()
        if ad == "kok_neden_raporu_uret":
            # Geç import: Görev 12 aynı gün başka biri tarafından yazılıyor,
            # modül seviyesinde import etmek bu görevi ona bağlardı.
            from gozcu.agents.raportor import kok_neden_raporu_uret
            return kok_neden_raporu_uret(self.gw, self.store).model_dump()
        return None

    def _arac_calistir(self, cagri: dict) -> dict:
        ad = cagri["function"]["name"]
        try:
            p = json.loads(cagri["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            return {"hata": "parametreler okunamadı"}
        ic = self._ic_arac(ad, p)
        if ic is not None:
            return ic
        try:
            return cagir(self.store, ad, p, kim="ajan")
        except KeyError:
            return {"hata": f"bilinmeyen araç: {ad}"}

    # -- diyalog ------------------------------------------------------------

    def _dongu(self, kritik: bool) -> str:
        from gozcu.guard import denetle  # geç import — Görev 13 aynı gün

        araclar = ARAC_SEMALARI + EK_ARACLAR
        for _ in range(MAKS_TUR):
            yanit = self.gw.sor("ana", self.gecmis, araclar=araclar)
            if not yanit.arac_cagrilari:
                metin = denetle(self.gw, yanit.icerik, kritik=kritik)
                self.gecmis.append({"role": "assistant", "content": metin})
                self.store.kaydet_diyalog(
                    DiyalogSatiri(ts=0.0, rol="nobetci", metin=metin))
                return metin

            self.gecmis.append({"role": "assistant",
                                "tool_calls": yanit.arac_cagrilari})
            for cagri in yanit.arac_cagrilari:
                sonuc = self._arac_calistir(cagri)
                self.gecmis.append({
                    "role": "tool", "tool_call_id": cagri.get("id", "c"),
                    "content": json.dumps(sonuc, ensure_ascii=False,
                                          default=str)})

        mesaj = "Yanıt üretilemedi; olay kaydı korunuyor."
        self.store.kaydet_diyalog(
            DiyalogSatiri(ts=0.0, rol="sistem", metin=mesaj))
        return mesaj

    def yukselt(self, epizot: Epizot) -> str:
        risk = risk_analiz_et(self.gw, self.store, epizot)
        gozlemler = [g for g in self.store.gozlemler()
                     if epizot.baslangic_ts <= g.ts <= (epizot.bitis_ts
                                                        or epizot.baslangic_ts)]
        sinyaller = gozlemler[-1].sinyaller if gozlemler else Sinyaller()
        not_ = belirsizlik_notu(sinyaller)

        self.gecmis.append({
            "role": "user",
            "content": f"[SİSTEM] {mmss(epizot.baslangic_ts)} — kritik olay: "
                       f"{epizot.ozet_tr}. Risk: {risk.seviye}. "
                       f"Gerekçe: {risk.gerekce_tr}\n{not_}\n"
                       f"Operatöre kendin haber ver. Belirsizlik varsa sor."})
        return self._dongu(kritik=risk.seviye in ("Yüksek", "Kritik"))

    def konus(self, operator_metni: str) -> str:
        self.store.kaydet_diyalog(
            DiyalogSatiri(ts=0.0, rol="operator", metin=operator_metni))
        acik = self.store.acik_epizot()
        ek = (f"\n[SİSTEM] Açık olay: epizot {acik.id} — {acik.ozet_tr}"
              if acik else "")
        self.gecmis.append({"role": "user", "content": operator_metni + ek})
        return self._dongu(kritik=False)

    # -- onaylar ------------------------------------------------------------

    def bekleyen_onay(self):
        bekleyen = [a for a in self.store.aksiyonlar()
                    if a.onay_durumu == "bekliyor"]
        return bekleyen[-1] if bekleyen else None

    def onayla(self, aksiyon_id: int, onay: bool) -> dict:
        kayit = next(a for a in self.store.aksiyonlar() if a.id == aksiyon_id)
        if not onay:
            self.store.aksiyon_durumu(aksiyon_id, "reddedildi")
            return {"durum": "reddedildi"}
        # onay_durumu geçilmezse cagir yeni bir "bekliyor" satırı doğurur ve
        # onay çubuğu hiç kapanmaz.
        sonuc = cagir(self.store, kayit.tool_adi, kayit.parametreler,
                      kim="operator", onay_durumu="onaylandi")
        self.store.aksiyon_durumu(aksiyon_id, "onaylandi")
        return {"durum": "onaylandi", **sonuc}
```

### 4. Yeşil olduğunu gör

```bash
uv run pytest tests/test_nobetci.py -v
```
Beklenen: 11 passed

### 5. Commit

```bash
git add gozcu/agents/nobetci.py tests/test_nobetci.py
git commit -m "feat: Nöbetçi supervisor with tool loop, correction cascade and approvals"
```

## Doğrulama

```bash
uv run pytest tests/test_nobetci.py -v
```
Beklenen: **11 passed**

## 25 Ağustos akşamı: canlı prova — 2 saat, atlanamaz

Yukarıdaki testlerin hepsi mock. **Puanın %20'sini taşıyan katmanın gerçek
modelle hiç konuşmamış olması kabul edilemez.** Testler yeşile döndükten sonra
gerçek gateway ile en az iki tur prova yap ve promptu düzelt:

1. Yükseltme mesajı gerçekten kısa ve Türkçe mi, yoksa çeviri mi kokuyor?
2. Belirsizlik notu varken ajan **gerçekten soruyor mu**, yoksa uyduruyor mu?
3. Operatör konuyu değiştirdiğinde açık olaya **kendiliğinden dönüyor mu**?
4. Hat durdurma için **izin istiyor mu**, yoksa doğrudan çağırıyor mu?

Bunların dördü de demo videosunda görünecek. Prompt iterasyonu için bu iki saat
plandaki en yüksek getirili zaman.
