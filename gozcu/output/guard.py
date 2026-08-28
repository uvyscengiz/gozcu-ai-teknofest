"""Çıktı denetimi — operatöre giden ve jüriye teslim edilen metnin önündeki
ucuz kontrol katmanı.

Şartnamenin etik maddesi sistemin "Türkçe konuşan tüm bireyler için adil,
kapsayıcı ve yanlılıktan arındırılmış" olmasını istiyor. Bu modül bunun somut
karşılığı. İki kural onu tanımlıyor ve ikisi de **engelleme** yönünde değil:

**Kritik uyarı asla engellenmez.** "Yerde hareketsiz kişi var" mesajını yutan
bir denetim katmanı, hiç denetim olmamasından kötüdür. Bir yaralanmayı
kaçırmak, ton ihlalinden ağır basar. `critical=True` işaretli metin modele hiç
gitmez.

**Denetim çökerse metin geçer (açık başarısızlık).** Kademe susarsa ya da
hüküm okunamazsa metin olduğu gibi ilerler. Bir denetim katmanının sistemin
tamamını susturabilmesi kabul edilebilir bir tasarım değil.

## Hüküm neden tek bir kelimeye bağlanamaz

`guard` kademesindeki model bir **güvenlik sınıflandırıcısı**, talimat takip
eden bir sohbet modeli değil — `Gateway.rerank`'ın docstring'indeki uyarının
aynısı burada da geçerli. Prompt Türkçe "uygun" / "uygunsuz" istiyor; gerçek
kademe gayet doğal olarak kendi etiket biçimini (`Safety: Unsafe` gibi)
basabilir. Tek bir `"uygunsuz" in content` kontrolü o cevabı **temiz** okur ve
denetim katmanı sahada kalıcı bir no-op'a döner — üstelik bütün testler yeşil
kalır, çünkü testlerdeki gateway bir `Mock`.

Bu yüzden `parse_verdict()` üç biçimi birden tanıyor (Türkçe hüküm,
sınıflandırıcı etiketi, Türkçe olumsuzlama) ve tanımadığı her cevabı
`"unknown"` sayıyor. `"unknown"` metni geçirir ama **temiz demez**: denetim
kaydı "denetlendi, temiz" ile "denetlenemedi" arasındaki farkı görebilmeli.

## Neden `try/except` yok

Görev 03'ten beri hiçbir kademe kesintide istisna atmıyor: `ask()` boş
içerikli, `degraded=True` bir yanıt döndürüyor. Kesinti kontrolü bu yüzden
bayrağa bakıyor. Geriye kalan tek istisna `GatewayError` ve o artık **kesinti
değil, yazım hatası** demek (kayıtlı olmayan kademe adı). Onu yutan bir
`except Exception` denetimi sessizce kapatırdı; bilerek yukarı bırakılıyor.

## Çağıranlar

- **Görev 14 (Nöbetçi):** operatöre giden her mesaj için `screen()` — ya da
  denetim kaydına hüküm yazacaksa `screen_text()`.
- **Görev 17 (boru hattı):** teslimden hemen önce
  `screen_delivery(gw, output)`. Ayrıntı için o fonksiyonun docstring'i.
"""

import re
from dataclasses import dataclass
from typing import Literal

from gozcu.core.models import PipelineOutput

__all__ = ["DELIVERY_FLAG_NOTICE", "DeliveryScreening", "NEUTRAL_NOTICE",
           "Screening", "Verdict", "parse_verdict", "screen",
           "screen_delivery", "screen_text"]

SYSTEM_PROMPT = """Aşağıdaki metin bir fabrika kontrol odasında operatöre gösterilecek.
Metin ayrımcı, aşağılayıcı, kişiyi hedef alan veya yanlı bir ifade içeriyor mu?
Kişi hakkında kimlik, etnik köken, cinsiyet veya yaş çıkarımı var mı?
Sadece "uygun" veya "uygunsuz" yaz."""

#: Uygunsuz bulunan operatör metninin yerine geçen bildirim. Olayın kendisi
#: kaybolmuyor — kayıt depoda, yalnız ifade gösterilmiyor.
NEUTRAL_NOTICE = ("[Bu ifade uygunsuz bulundu ve gösterilmedi. Olay kaydı "
                  "korunmuştur.]")

#: Teslim edilen yükün işaretlenme notu. Teslim tarafında metin SİLİNMİYOR;
#: gerekçe `screen_delivery()` docstring'inde.
DELIVERY_FLAG_NOTICE = ("[Denetim notu: bu raporun ifadeleri uygunsuz içerik "
                        "açısından işaretlendi. Kayıt bütünlüğü için metin "
                        "kaldırılmadı.]")

#: `unknown` bilerek `unsafe`'ten ayrı: "denetlendi ve uygunsuz" ile
#: "denetlenemedi" farklı olaylar. `skipped` ise denetimin bilerek
#: uygulanmadığı hâl (kritik uyarı, boş metin).
Verdict = Literal["safe", "unsafe", "unknown", "skipped"]

# Denetim kaydına düşen Türkçe notlar. Dördü bilerek farklı: aynı metni
# paylaşsalardı kaydı okuyan kişi "kademe sustu" ile "hüküm okunamadı"yı
# ayırt edemezdi ve `degraded` dalı sessizce ölü koda dönerdi.
CLEAN_NOTE = "Denetlendi, temiz."
FLAGGED_NOTE = "Denetlendi, uygunsuz bulundu."
DEGRADED_NOTE = "Denetim kademesi yanıt vermedi; metin denetlenmeden geçti."
UNREADABLE_NOTE = "Denetim hükmü okunamadı; metin denetlenmeden geçti."
CRITICAL_NOTE = "Can güvenliği uyarısı; denetim uygulanmadı."
NO_TEXT_NOTE = "Denetlenecek metin yok."

# Hüküm kalıpları. Sıra önemli: "uygunsuz" içinde "uygun", "unsafe" içinde
# "safe" geçiyor — kelime sınırları (`\b`) ikisini de ayırıyor, ama Türkçe
# olumsuzlama ("uygun değil") ancak ÖNCE aranarak yakalanabilir.
_UNSAFE = re.compile(
    r"\b(?:uygunsuz|unsafe|harmful|"
    r"uygun\s+(?:değil|degil|olmayan|bulunmad[ıi]|görülmed[ıi]|gorulmedi))\b",
    re.IGNORECASE)

# Sınıflandırıcının kararsız etiketi. `safe` saymak yanlış olurdu: model
# metnin bağlama göre sorunlu olabileceğini söylüyor. `unsafe` saymak da
# yanlış — modelin kendisi emin değil. Emin olmayan hüküm denetlenmemiş
# sayılır: metin geçer, kayıt "temiz" demez.
_UNDECIDED = re.compile(r"\b(?:controversial|tartışmalı|tartismali)\b",
                        re.IGNORECASE)

_SAFE = re.compile(r"\b(?:uygun|safe|güvenli|guvenli)\b", re.IGNORECASE)


def parse_verdict(content: str) -> Verdict:
    """Denetim kademesinin ham cevabını bir hükme çevirir.

    Üç biçim de kabul ediliyor — talimat edilen Türkçe hüküm (`uygun` /
    `uygunsuz`), sınıflandırıcı etiketi (`Safety: Unsafe`, `safe`, çevresinde
    başka metin olsa da) ve Türkçe olumsuzlama (`uygun değil`). Tanınmayan
    her cevap `"unknown"`: metin geçer ama temiz sayılmaz.
    """
    text = (content or "").strip()
    if not text:
        return "unknown"
    if _UNSAFE.search(text):
        return "unsafe"
    if _UNDECIDED.search(text):
        return "unknown"
    if _SAFE.search(text):
        return "safe"
    return "unknown"


@dataclass(frozen=True)
class Screening:
    """Bir metin denetiminin sonucu: gösterilecek metin, hüküm ve Türkçe not.

    `text` her zaman doludur — açık başarısızlık tasarımı gereği denetim
    hiçbir koşulda boş metin döndürmez.
    """

    text: str
    verdict: Verdict
    note: str

    @property
    def screened(self) -> bool:
        """Model gerçekten bir hüküm verdi mi.

        `"unknown"` ve `"skipped"` metni geçirir ama denetlenmiş saymaz —
        çağıran ve denetim kaydı "temiz" ile "denetlenemedi"yi ayırabilmeli.
        """
        return self.verdict in ("safe", "unsafe")


@dataclass(frozen=True)
class DeliveryScreening:
    """Teslim edilen yükün denetim sonucu. `output` her zaman teslim edilebilir."""

    output: PipelineOutput
    verdict: Verdict
    note: str

    @property
    def screened(self) -> bool:
        return self.verdict in ("safe", "unsafe")


def _ask_verdict(gw, text: str) -> Verdict:
    """Kademeye tek bir hüküm sorusu sorar; kesintide `"unknown"`.

    `temperature=0`: bu bir sınıflandırma kararı, yaratıcı yazı değil — aynı
    metin aynı hükmü almalı. Kademe adıyla anılıyor, model kimliği
    `gozcu.config` dışında hiçbir yerde yazılmaz (CLAUDE.md).
    """
    response = gw.ask("guard",
                      [{"role": "system", "content": SYSTEM_PROMPT},
                       {"role": "user", "content": text}],
                      temperature=0)
    if response.degraded:
        return "unknown"
    return parse_verdict(response.content)


def screen_text(gw, text: str, critical: bool = False) -> Screening:
    """Operatöre giden metni denetler ve hükmü de birlikte döndürür.

    Can güvenliği uyarısı asla tutulmaz ve denetim çökerse metin geçer;
    gerekçeler modül docstring'inde.
    """
    if critical:
        return Screening(text, "skipped", CRITICAL_NOTE)
    if not text.strip():
        return Screening(text, "skipped", NO_TEXT_NOTE)

    verdict = _ask_verdict(gw, text)
    if verdict == "unsafe":
        return Screening(NEUTRAL_NOTICE, "unsafe", FLAGGED_NOTE)
    if verdict == "safe":
        return Screening(text, "safe", CLEAN_NOTE)
    return Screening(text, "unknown", UNREADABLE_NOTE)


def screen(gw, text: str, critical: bool = False) -> str:
    """Gösterilecek metni döndürür — Görev 14'ün kısa yolu.

    Hükmü de kaydetmek isteyen çağıran `screen_text()` kullanır.
    """
    return screen_text(gw, text, critical).text


def _prose(output: PipelineOutput) -> list[str]:
    """Teslim edilen yükteki **düzyazı** alanları toplar.

    Yapısal kanıt bilerek dışarıda: `events[]` zaman damgaları, `risk`
    seviyesi, aksiyon defteri ve epizot kayıtları denetime girmez ve
    değiştirilmez. Denetim düzyazıyı işaretler, kayıt tutmaz.

    Kök neden raporu alan adlarıyla değil, **biçimiyle** taranıyor: rapor
    `detail.root_cause_report` altında düz bir `dict` (Görev 12) ve elle
    yazılmış bir alan listesi rapordan ayrışır — CLAUDE.md'nin adıyla
    uyardığı hata. Metin olan ve metin listesi olan her değer düzyazı sayılır.
    """
    parts: list[str] = [output.summary]
    parts += [a for a in output.actions if isinstance(a, str)]

    report = getattr(output.detail, "root_cause_report", None)
    if isinstance(report, dict):
        for value in report.values():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts += [v for v in value if isinstance(v, str)]

    return [p for p in parts if p.strip()]


def screen_delivery(gw, output: PipelineOutput) -> DeliveryScreening:
    """Teslim edilen yükü denetler — **Görev 17 teslimden hemen önce çağırır.**

    Şartnamenin dört anahtarının jüriye giden düzyazısı da model yazımı
    Türkçe: `summary`, `actions[]` ve `detail.root_cause_report`'un anlatı
    alanları. Bunlar Görev 14'ün diyaloğu kadar denetime muhtaç.

    **Yük hiçbir koşulda boşaltılmıyor.** Uygunsuz hükmünde bile metin
    kaldırılmıyor, `summary`'ye bir denetim notu ekleniyor. Gerekçe iki
    katmanlı: (1) CLAUDE.md'nin çıktı sözleşmesi dört anahtarın her hâlükârda
    üretilmesini istiyor; (2) `guard` bir güvenlik sınıflandırıcısı ve bir
    endüstriyel kaza anlatısını ("yerde hareketsiz kişi", "yük düştü") şiddet
    içeriği sayıp işaretlemesi beklenen bir yanlış pozitif. Böyle bir hükümle
    jürinin okuduğu raporu silmek, denetimin engellemediği tek şeyi —
    teslimatı — engellemek olurdu. İşaret görünür, kanıt yerinde kalır.

    Kesinti ve okunamayan hüküm de açık başarısız oluyor: yük olduğu gibi,
    işaretsiz teslim edilir ve `screened` `False` döner.

    Tek bir kademe çağrısı yapılır; alan başına dağıtılmaz.
    """
    prose = _prose(output)
    if not prose:
        return DeliveryScreening(output, "skipped", NO_TEXT_NOTE)

    verdict = _ask_verdict(gw, "\n".join(prose))
    if verdict == "safe":
        return DeliveryScreening(output, "safe", CLEAN_NOTE)
    if verdict != "unsafe":
        return DeliveryScreening(output, "unknown", UNREADABLE_NOTE)

    # Çağıranın nesnesi değişmiyor: teslim edilen kopya işaretleniyor.
    flagged = output.model_copy(deep=True)
    flagged.summary = f"{output.summary}\n\n{DELIVERY_FLAG_NOTICE}".strip()
    return DeliveryScreening(flagged, "unsafe", FLAGGED_NOTE)
