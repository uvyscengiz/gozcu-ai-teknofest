"""Paylaşılan test ikizleri — `console.py` ve `server.py` testlerinin ortak
kütüphanesi.

`_StubLoop`/`_StubGateway` (eskiden `tests/test_console.py:341-357`) ve
`_FakeSupervisor` (eskiden `:43-58`) buraya taşındı: iki dosyanın kendi
kopyaları bir gün ayrışırdı ve `test_console.py` Görev 11'de silinirken bu
modül ayakta kalıyor — Görev 4'ün ağ geçidi testleri de aynı ikizlere
ihtiyaç duyuyor.
"""

from tests.test_run import _FakeGateway


class StubLoop:
    """`DecisionLoop` ikizi — yalnız `catch_up()`'ı sınamak için.

    `calls` telafi çağrısının kaç kez yapıldığını sayıyor:
    `/gateway/restore` iki kez basılırsa ikinci basış boş bir telafi
    yapmalı, hiç YAPMAMAK değil.
    """

    def __init__(self, events=()):
        self.events = list(events)
        self.calls = 0

    def catch_up(self):
        self.calls += 1
        yield from self.events


class StubGateway(_FakeGateway):
    """`/gateway/cut`|`/restore` uçlarının ihtiyaç duyduğu ağ geçidi ikizi.

    Taban sınıfta (`tests/test_run.py::_FakeGateway`) `inject_failure` YOK
    — o taban `ask()`/`router` senaryolarını oynuyor, kesinti enjeksiyonunu
    değil. `injections` çağrı sırasını kaydediyor: `/cut` sonra `/restore`
    doğru sırayla mı geldi, testler bunu doğruluyor.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.injections: list = []
        self._injected: set = set()

    def inject_failure(self, tiers) -> None:
        self.injections.append(set(tiers))
        self._injected = set(tiers)

    def is_degraded(self, tier=None) -> bool:
        injected = bool(self._injected) if tier is None else tier in self._injected
        return injected or super().is_degraded(tier)


class FakeSupervisor:
    """`approve()`'un dört durumunu senaryolayan Nöbetçi ikizi."""

    def __init__(self, result, pending_after=None):
        self.result = result
        self.pending_after = pending_after
        self.calls: list = []
        self.pending_reads = 0

    def approve(self, action_id, approved):
        self.calls.append((action_id, approved))
        return self.result

    def pending_approval(self):
        self.pending_reads += 1
        return self.pending_after
