"""Canlı iz kaydı — bir şeyin SÜRDÜĞÜNÜ mü yoksa TAKILDIĞINI mı gösterir.

Boru hattı 20–40. saniyede sessizce duruyordu ve kayıtlarda hiçbir şey yoktu.
Sebep tahmin edilebilir bir yerdeydi: `GATEWAY_TIMEOUT_S` **1800 saniye** ve
`_attempt` bunu `GATEWAY_RETRIES` (3) kez deniyor, üstüne şemasız bir yedek
deneme daha yapıyor. Yani tek bir asılı çağrı **iki saate kadar** hiçbir çıktı
üretmeden bekleyebiliyor. Ekranda bu, "takıldı"dan ayırt edilemiyor.

## Neden başlangıç/bitiş kaydı YETMİYOR

"başladı … bitti" biçiminde bir kayıt, bitmeyen bir adım için hiçbir şey
söylemez: son satır "başladı" olarak kalır ve bakan kişi hâlâ çalışıyor mu,
ölmüş mü bilemez. Bu modülün asıl işi o yüzden **kalp atışı**: süren her adım
`HEARTBEAT_S` saniyede bir "hâlâ çalışıyor, 15,0 s" diye kendini bildiriyor.

    [21:34:12.345 +  12.3s]   → vlm.ask              model=vlm klip=1.2MB
    [21:34:17.350 +  17.3s]   ⋯ vlm.ask              hâlâ çalışıyor, 5,0 s
    [21:34:22.351 +  22.4s]   ⋯ vlm.ask              hâlâ çalışıyor, 10,0 s
    [21:34:25.120 +  25.1s]   ✓ vlm.ask              12775 ms tokens=843

İki zaman birden yazılıyor: **duvar saati** (kayıtla ekranı eşleştirmek için)
ve **koşu başından beri geçen süre** (+12.3s — hangi saniyede ne olduğunu
görmek için). Bitişte adımın kendi süresi de yazılıyor.

## Sözleşme

- **Hiçbir arıza koşuyu düşürmez.** Yazma hatası yutuluyor: bir tanı aracı
  ölçtüğü şeyi öldürmemeli.
- **İş parçacığı güvenli.** `run_pipeline` konsolda ayrı bir thread'de
  koşuyor; yazma tek bir kilit altında.
- **Kapatılabilir.** `GOZCU_TRACE=0` her şeyi susturuyor ve `step()` neredeyse
  bedava bir bağlam yöneticisine dönüyor.
"""

import os
import sys
import threading
import time
from contextlib import contextmanager

__all__ = ["HEARTBEAT_S", "enabled", "event", "reset_clock",
           "reset_depth", "step"]

#: Süren bir adımın kendini kaç saniyede bir bildireceği. 5 s: bakan kişiyi
#: boğmayacak kadar seyrek, "takıldı mı" sorusunu 5 saniyede cevaplayacak
#: kadar sık.
HEARTBEAT_S = float(os.environ.get("GOZCU_TRACE_HEARTBEAT", "5"))

_LOCK = threading.Lock()
_START = time.monotonic()
_DEPTH = threading.local()


def enabled() -> bool:
    """`GOZCU_TRACE=0` dışında her durumda açık.

    Varsayılan AÇIK: bu modül bir arızayı görünür kılmak için yazıldı ve
    varsayılan olarak kapalı bir tanı aracı, ihtiyaç duyulduğu anda kapalı
    olur.
    """
    return os.environ.get("GOZCU_TRACE", "1") not in ("0", "false", "no")


def reset_clock() -> None:
    """Koşu başlangıcını şimdiye alır — `+12.3s` sütununun sıfır noktası."""
    global _START
    _START = time.monotonic()


def _depth() -> int:
    """Girinti derinliği; asla negatif olmuyor.

    Savunma amaçlı: bir `step()` yarıda bırakılırsa (ör. tüketilmemiş bir
    generator çöp toplandığında) sayaç bozulabilir ve o andan sonraki BÜTÜN
    satırlar kayar. Kayan bir kayıt, okunamayan bir kayıttır.
    """
    return max(getattr(_DEPTH, "value", 0), 0)


def reset_depth() -> None:
    """Girinti sayacını sıfırlar — testlerin birbirini kirletmemesi için."""
    _DEPTH.value = 0


def _stream():
    path = os.environ.get("GOZCU_TRACE_FILE")
    if not path:
        return sys.stderr, False
    try:
        return open(path, "a", encoding="utf-8"), True   # noqa: SIM115
    except Exception:                    # noqa: BLE001 — tanı aracı patlamaz
        return sys.stderr, False


def _write(mark: str, name: str, detail: str = "", suffix: str = "") -> None:
    """Tek bir iz satırı. Hiçbir arıza yukarı kabarcıklanmaz.

    `detail` **burada** biçimleniyor, çağıranda değil: çağıranda bir f-string
    içinde biçimlenirse ve o nesnenin `__format__`'ı patlarsa istisna bu
    korumanın DIŞINDA doğar ve ölçtüğü koşuyu öldürür. Bir kez oldu, testle
    yakalandı.
    """
    if not enabled():
        return
    try:
        detail = f"{suffix} {detail}".strip() if suffix else f"{detail}"
        now = time.time()
        elapsed = time.monotonic() - _START
        stamp = time.strftime("%H:%M:%S", time.localtime(now))
        millis = int((now % 1) * 1000)
        indent = "  " * _depth()
        line = (f"[{stamp}.{millis:03d} {elapsed:+7.1f}s] {indent}{mark} "
                f"{name:<26} {detail}".rstrip())
        stream, should_close = _stream()
        with _LOCK:
            print(line, file=stream, flush=True)
            if should_close:
                stream.close()
    except Exception:                    # noqa: BLE001 — tanı aracı patlamaz
        pass


def event(name: str, detail: str = "") -> None:
    """Süresi olmayan tek seferlik olay."""
    _write("·", name, detail)


@contextmanager
def step(name: str, detail: str = ""):
    """Adımı başlangıç/kalp atışı/bitiş olarak kaydeder.

    Kalp atışı ayrı bir **daemon** thread'de: adım asılı kalırsa bile satırlar
    akmaya devam ediyor ve bakan kişi "sürüyor" ile "takıldı"yı ayırabiliyor.
    Daemon olması şart — asılı bir adım yüzünden süreç kapanamaz hâle gelmesin.

    İstisna yutulmuyor: adım patlarsa `✗` yazılıp istisna yukarı veriliyor.
    """
    if not enabled():
        yield
        return

    _write("→", name, detail)
    started = time.monotonic()
    done = threading.Event()

    def _heartbeat() -> None:
        while not done.wait(HEARTBEAT_S):
            alive = time.monotonic() - started
            _write("⋯", name, f"hâlâ çalışıyor, {alive:.1f} s")

    beat = threading.Thread(target=_heartbeat, daemon=True)
    beat.start()
    _DEPTH.value = _depth() + 1
    try:
        yield
    except Exception as error:           # noqa: BLE001 — kaydedip yukarı ver
        _DEPTH.value = _depth() - 1
        done.set()
        _write("✗", name,
               f"{(time.monotonic() - started) * 1000:.0f} ms sonra HATA: "
               f"{type(error).__name__}: {error}")
        raise
    else:
        _DEPTH.value = _depth() - 1
        done.set()
        _write("✓", name, detail,
               suffix=f"{(time.monotonic() - started) * 1000:.0f} ms")
