"""Emsal alaka eşiklerini ölçer. Hiçbir şey YAZMAZ — sayıları basar.

Eşik iki tane çünkü iki tüketici arşivi FARKLI biçimde sorguluyor: risk
analisti bir CÜMLEYLE (`f"{summary_tr} {participants}"`), süpervizör
modelin yazdığı bir SORUYLA. Soru–cümle kosinüsü sistematik olarak
cümle–cümle kosinüsünden düşük; tek bir eşik ya analisti kör eder ya demo
senaryosunun 5. beat'ini keser.

**Bu script Aşama 6'dan SONRA koşar.** Eşik epizot özet metinleri üzerinden
kalibre ediliyor; Aşama 6.1 yorumlayıcının `description`'ını değiştiriyor →
sentezleyicinin `summary_tr`'si değişiyor → aynı arşive karşı skorlar
kayıyor. Önce koşulursa iki kez kalibre edilir.
"""

import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from gozcu.fixtures.loader import load_history     # noqa: E402
from gozcu.gateway import Gateway                  # noqa: E402
from gozcu.memory import search_timeline           # noqa: E402
from gozcu.store import Store                      # noqa: E402

#: (a) fikstür konusuna NEAR — eşik bunları KESMEMELİ.
NEAR = ["B-Hattı'nda istif aracının freni tutmadı",
        "forklift yükü hatalı istifledi",
        "kask takmayan personel görüldü"]

#: (b) kasten IRRELEVANT — eşik bunları KESMELİ. B4'ün ölçüm sorgusu.
IRRELEVANT = ["kantinde yemek kuyruğu uzadı",
              "muhasebe departmanı toplantı yapıyor",
              "otoparkta kar yağışı başladı"]

#: (c) **beat 5'in GERÇEK diyalog biçimi.** Bu aile ŞART: canlı sorgu,
#: süpervizör modelinin `params["query"]`'si — fikstür metnine benzeyen bir
#: cümle değil. (c)'yi ölçmeyen bir eşik, onarmak için var olduğumuz beat'i
#: keser. Soru–cümle kosinüsü sistematik olarak cümle–cümle kosinüsünden
#: düşük ve `QDRANT_SCORE_THRESHOLD_DIALOGUE` bu yüzden ayrı.
DIALOGUE = ["bu araçla daha önce sorun oldu mu?",
            "IST-04 ile ilgili geçmiş kayıt var mı?",
            "bu bölgede daha önce kaza oldu mu?"]

FAMILIES = {"yakın": NEAR, "alakasız": IRRELEVANT, "diyalog": DIALOGUE}


def _scores(gw, store, queries) -> list[float]:
    scores = []
    for query in queries:
        scores += [p.score for p in search_timeline(gw, store, query)]
    return sorted(scores, reverse=True)


def main() -> int:
    store = Store()
    gw = Gateway(store)
    embedded = load_history(gw, store)
    if not embedded:
        print("HATA: hiçbir fikstür gömülemedi — gömme kademesi bozuk.")
        return 1

    measured = {}
    for name, queries in FAMILIES.items():
        scores = _scores(gw, store, queries)
        measured[name] = scores
        if scores:
            print(f"{name:10s} n={len(scores):3d} "
                  f"min={min(scores):.3f} "
                  f"medyan={statistics.median(scores):.3f} "
                  f"max={max(scores):.3f}")
        else:
            print(f"{name:10s} n=0 — hiçbir sonuç dönmedi")

    # Eşik iki ailenin ARASINA konuyor: kesilmesi gerekenin en yükseğinin
    # üstü, korunması gerekenin en düşüğünün altı. Aralık negatifse
    # (kesilecek olan korunacak olandan yüksek skorluysa) eşik o aileyi
    # ayıramaz ve bu bir BULGU — susulmuyor.
    for name, keep_family in (("RISK", "yakın"), ("DIALOGUE", "diyalog")):
        cut_family = measured["alakasız"]
        if not measured[keep_family] or not cut_family:
            print(f"{name}: ölçülemedi")
            continue
        low, high = max(cut_family), min(measured[keep_family])
        if low >= high:
            print(f"{name}: AYIRAMAZ — alakasız {low:.3f} >= korunacak "
                  f"{high:.3f}. Eşik bu ikisini ayırt edemiyor; karar "
                  f"günlüğüne yazılır.")
        else:
            print(f"{name}: önerilen eşik {(low + high) / 2:.3f} "
                  f"(aralık {low:.3f}–{high:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
