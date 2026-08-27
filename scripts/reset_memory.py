"""team37 koleksiyonunu düşürür ve fikstürlerle yeniden tohumlar.

Bu depoda bir ilk: **veri silen** bir script. O yüzden çıplak çağrıldığında
hiçbir şey silmiyor — ne yapacağını yazıp çıkıyor. Silmesi için ortamda
`GOZCU_MEMORY_RESET=1` olmak zorunda.

Neden gerekli: 27 Ağustos'ta canlı koleksiyonda ölçüldü — üç nokta, üçü de
`prior_incidents.json` fikstürü, kimlikleri tamsayı (`1`/`2`/`3`) ve payload'da
`source` alanı YOK. Yeni kimlik `uuid5(source:id)` olduğu için o noktalar yeni
şemayla çakışmaz, ama silinmezlerse aynı üç fikstür arşivde İKİ KEZ durur ve
ne dışlama filtresi ne kaynak tekilleştirmesi onları tanır.

Kayıp geri alınabilir: silinen her nokta `prior_incidents.json`'dan bire bir
yeniden üretiliyor.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from gozcu.config import QDRANT_COLLECTION          # noqa: E402
from gozcu.fixtures.loader import load_history      # noqa: E402
from gozcu.gateway import Gateway                   # noqa: E402
from gozcu.memory import build_client, memory_backend  # noqa: E402
from gozcu.store import Store                       # noqa: E402

ONAY = "GOZCU_MEMORY_RESET"


def main() -> int:
    if memory_backend() != "qdrant":
        # Anahtarsız modda `build_client()` süreç içi bir Qdrant döndürüyor
        # (`memory.py:87`). O örneği "sıfırlamak" hiçbir şey yapmaz ama
        # ekrana "3 fikstür yeniden tohumlandı" yazar — yani script kalıcı
        # bir şey yaptığını SANDIRIR. Sessiz düşüş yasak.
        print("HATA: GOZCU_QDRANT_API_KEY tanımlı değil. Süreç içi bir "
              "Qdrant'ı sıfırlamanın anlamı yok; anahtarı ver.")
        return 1

    client = build_client()
    exists = client.collection_exists(QDRANT_COLLECTION)
    existing = client.get_collection(QDRANT_COLLECTION).points_count if exists else 0

    if exists and existing:
        # **Silinecekler silinmeden ÖNCE basılıyor.** "Üçü de fikstür"
        # ölçümü 27 Ağustos'a ait; uygulama gününde bir takım arkadaşının
        # noktası eklenmiş olabilir ve script buna körü körüne devam
        # etmemeli. Onay veren kişi neyi kaybettiğini GÖRSÜN.
        points, _ = client.scroll(QDRANT_COLLECTION, limit=100,
                                  with_payload=True, with_vectors=False)
        for point in points:
            payload = point.payload or {}
            print(f"  silinecek: id={point.id} "
                  f"kaynak={payload.get('source', '(yok)')} "
                  f"özet={str(payload.get('summary_tr'))[:60]}")

    if os.environ.get(ONAY) != "1":
        print(f"{QDRANT_COLLECTION}: {existing} nokta. Hiçbir şey silinmedi — "
              f"silmek için {ONAY}=1 ver.")
        return 0

    if exists:
        client.delete_collection(QDRANT_COLLECTION)

    store = Store()
    embedded = load_history(Gateway(store), store)
    print(f"{QDRANT_COLLECTION}: {existing} nokta silindi, "
          f"{embedded} fikstür yeniden tohumlandı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
