"""Bir analiz koşusunun bütün tutamakları ve durum makinesi.

## Neden `Event` değil `Condition`

`threading.Event` ile bekleme deseni şuydu: `step_mode` kontrolü →
`clear()` → `wait()`. Serbest bırakan taraf (terk etme, anahtarı kapatma)
kontrol ile `clear()` arasına düşerse, `set()` bekleyenin KENDİ
`clear()`'ı tarafından siliniyor ve iş parçacığı sonsuza dek bekliyor.
Yüklemli bekleme (`wait_for`) yüklemi yeniden kontrol ettiği için kayıp
uyandırma imkânsız.

## Neden `set_state` tek giriş

`run_state`'i yazan her yol `version`'u artırıp `notify_all()` çağırmak
ZORUNDA. Yükümlülük yazıyla bırakıldığında bir kez unutuldu: koşunun
bitişi hiçbir bekleyeni uyandırmıyordu ve bağlı istemci sonsuza dek
"koşuyor" gösteriyordu. Tek giriş noktası bunu yapısal olarak garanti
ediyor.
"""

import threading
import time
from typing import Literal

from gozcu.agents.supervisor import Supervisor
from gozcu.gateway import Gateway
from gozcu.store import Store

RunState = Literal["idle", "running", "paused", "intervened",
                   "done", "failed", "abandoned"]

#: Teldeki değerlerin TEK kaynağı. Sunucu ve testler buradan okuyor;
#: ikinci bir liste bir gün ayrışır ve arayüz olmayan bir durumu bekler.
RUN_STATES: tuple[str, ...] = ("idle", "running", "paused", "intervened",
                               "done", "failed", "abandoned")

#: Kalp atışı aralığı — SSE bağlantısının kendi zaman aşımı.
HEARTBEAT_S = 1.0


class Session:
    """Tek koşunun durumu. Bütün mutasyon `cond` altında."""

    def __init__(self) -> None:
        self.store = Store()
        self.gw = Gateway(self.store)
        self.nobetci = Supervisor(self.gw, self.store)

        self.cond = threading.Condition()
        #: Telafi ile canlı döngü aynı `deferred` listesine dokunuyor
        #: (bugün `console.py:549`). `cond` DEĞİL: `catch_up()` uzun sürüyor
        #: ve `cond`'u o süre boyunca tutmak bütün SSE bekleyenlerini
        #: kilitlerdi.
        self.loop_lock = threading.Lock()
        self.version = 0
        self.run_state: str = "idle"
        self.resume_requested = False
        self.step_mode = False
        self.abandoned = False

        self.loop = None
        self.thread: threading.Thread | None = None
        self.output = None
        self.error: Exception | None = None
        self.finished = False
        self.events: list = []

        self.output_dir = None
        self.frame_size: tuple[int, int] | None = None
        self.video_path = None

        self.started_at = time.monotonic()
        self.archived = {episode.id for episode in self.store.episodes()}

    # --- bildirim ---------------------------------------------------------

    def bump(self) -> None:
        """Sürümü artırır, bekleyenleri uyandırır. Çağıran `cond`'u TUTUYOR."""
        self.version += 1
        self.cond.notify_all()

    def _set_state_locked(self, state: str) -> None:
        """`run_state`'in TEK yazma yolu. Çağıran `cond`'u TUTUYOR.

        Kilidi tutan her yol buradan geçiyor — `wait_if_step_mode` ve
        `abandon` dahil. Doğrudan atama yapan bir yol kalırsa
        "her geçiş bildirilir" garantisi reklamdan ibaret olur.
        """
        if state not in RUN_STATES:
            raise ValueError(f"bilinmeyen koşu durumu: {state!r}")
        if self.run_state == state:
            return
        self.run_state = state
        self.bump()

    def set_state(self, state: str) -> None:
        """`_set_state_locked`'ın kilit alan sarmalayıcısı."""
        with self.cond:
            self._set_state_locked(state)

    def wait_for_version(self, seen: int, timeout: float = HEARTBEAT_S) -> bool:
        """`version > seen` olana kadar bekler. Zaman aşımında `False`."""
        with self.cond:
            return self.cond.wait_for(lambda: self.version > seen, timeout)

    # --- duraklama --------------------------------------------------------

    def note_intervention(self) -> None:
        """`step_mode` KAPALIYKEN müdahale anı — koşu durmuyor, damgalanıyor."""
        with self.cond:
            if not self.abandoned:
                self._set_state_locked("intervened")

    def wait_if_step_mode(self) -> None:
        """`step_mode` açıkken operatörü bekler.

        Kapalıyken hemen dönüyor ve videonun zaman çizelgesi akmaya devam
        ediyor — bloklama kaldırılmadı, KOŞULA bağlandı.
        """
        with self.cond:
            if not self.step_mode:
                return
            self._set_state_locked("paused")
            self.cond.wait_for(
                lambda: not self.step_mode or self.resume_requested)
            # Jeton tüketimi ile paused'dan çıkış TEK kritik bölüm: ayrılırsa
            # aradan geçen ikinci bir "Devam et" 409'dan geçip jetonu bankaya
            # yatırır ve bir sonraki duraklamayı sessizce atlar.
            self.resume_requested = False
            # `abandoned` KORUNUYOR. Koşulsuz "running" yazmak terk edilmiş
            # bir koşuyu canlı gibi gösterirdi ve `_work` onu `done`'a
            # çevirip çıktısını geçerliymiş gibi sunardı.
            if not self.abandoned:
                self._set_state_locked("running")

    def request_resume(self) -> bool:
        """**Devam et.** Yalnız gerçekten duraklamışken jeton yazıyor."""
        with self.cond:
            if self.run_state != "paused":
                return False
            self.resume_requested = True
            self.bump()
            return True

    def set_step_mode(self, enabled: bool) -> bool:
        """Anahtar koşu SIRASINDA da değişebilir.

        Kapatan kişi o an bekleyen döngüyü serbest bırakmak zorunda, yoksa
        anahtarı kapatmak koşuyu kilitli bırakırdı.
        """
        with self.cond:
            if enabled and self.abandoned:
                return False        # Terk edilmiş koşu bloklamadan akmalı.
            self.step_mode = bool(enabled)
            self.bump()
            return True

    def abandon(self) -> None:
        """Duraklamayı çözer; koşuyu BİTİRMEZ."""
        with self.cond:
            self.abandoned = True
            self.step_mode = False
            self.resume_requested = True
            self._set_state_locked("abandoned")

    def finish(self, error: Exception | None = None) -> None:
        """Boru hattı bitti. Terk edilmiş koşu `done` OLMUYOR."""
        with self.cond:
            self.error = error
            self.finished = True
            if self.abandoned:
                self.output = None      # Çıktısı atılıyor (spec §4).
            else:
                self._set_state_locked("failed" if error else "done")
            self.bump()

    # --- okuma ------------------------------------------------------------

    def is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def elapsed_s(self) -> float:
        return time.monotonic() - self.started_at

    def escalated_ids(self) -> set:
        with self.loop_lock:
            return {event.episode.id for event in self.events
                    if getattr(event, "episode", None) is not None}

    def pending_deferred_ts(self) -> set:
        """Telafi kuyruğunda HÂLÂ bekleyen pencerelerin başlangıçları.

        `catch_up()` telafi ettiği pencerenin kaydına hiçbir şey yazmıyor
        (`loop.py:834`), yani `WindowRecord` "ertelendi" diyebiliyor ama
        "telafi edildi" diyemiyor. Belirsizliği çözen şey bu yüzden kayıt
        değil, canlı döngü.
        """
        with self.loop_lock:
            if self.loop is None:
                return set()
            return {window[0].ts for window in self.loop.deferred if window}
