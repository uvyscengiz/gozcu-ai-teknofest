"""Koşu içi kısa süreli hafıza — Aşama 6.

Görü katmanı her pencereye SIFIRDAN bakıyor: 2. dakikadaki dengesizlik,
5. dakikadaki devrilmenin bağlamı olamıyor. `RunMemory` o bağlamı taşıyor.
"""

from gozcu.models import SEVERITY_LEVELS
from gozcu.recall import RunMemory


def _fill(memory, n, severity="rutin"):
    for index in range(n):
        memory.note(ts=float(index * 10), moment=f"pencere {index}",
                    participants=["forklift"], decision="ignore",
                    severity=severity)


def test_routine_windows_scroll_out_of_the_recent_view():
    memory = RunMemory(limit=3)
    _fill(memory, 6)
    assert [n.moment for n in memory.recent()] == [
        "pencere 3", "pencere 4", "pencere 5"]


def test_an_incident_window_is_never_dropped():
    """Sınır HİYERARŞİK: son N pencere tam detay + `severity == "olay"` olan
    HER pencere kalıcı. Olay asla düşmez, rutin pencereler kayar."""
    memory = RunMemory(limit=2)
    memory.note(ts=0.0, moment="istif aracı dengesini kaybetti",
                participants=["forklift"], decision="open_episode",
                severity="olay")
    _fill(memory, 5)
    moments = [n.moment for n in memory.recent()]
    assert "istif aracı dengesini kaybetti" in moments
    assert moments[-1] == "pencere 4", "rutin pencereler yine de kayar"


def test_kept_incidents_stay_in_chronological_order():
    memory = RunMemory(limit=2)
    memory.note(ts=5.0, moment="ilk olay", participants=[],
                decision="open_episode", severity="olay")
    _fill(memory, 4)
    memory.note(ts=90.0, moment="ikinci olay", participants=[],
                decision="escalate", severity="olay")
    stamps = [n.ts for n in memory.recent()]
    assert stamps == sorted(stamps)


def test_the_rendered_block_leaks_no_severity_grading():
    """`severity` epizot açılışının TEK kapısı (`DecisionLoop._may_open`).
    Geçmiş derecelendirmeleri gören model kendini doğrulayan bir döngüye
    girer ("olay, olay → olay"). Blok NE GÖRÜLDÜĞÜNÜ taşır, NASIL
    DERECELENDİRİLDİĞİNİ değil.

    Kayıt metinleri o üç kelimeyi içermeyecek şekilde seçildi — yoksa test
    kendi verisini yakalar.
    """
    memory = RunMemory(limit=4)
    memory.note(ts=0.0, moment="istif aracı yükü yüksek konuma kaldırıyor",
                participants=["forklift"], decision="open_episode",
                severity="olay")
    memory.note(ts=10.0, moment="arka tekerlekler yerden kesildi",
                participants=["forklift"], decision="update_episode",
                severity="dikkat")
    block = memory.render()
    for level in SEVERITY_LEVELS:
        assert level not in block, f"derecelendirme sızdı: {level}"
    assert "istif aracı yükü yüksek konuma kaldırıyor" in block


def test_an_empty_memory_renders_nothing():
    """İlk pencerede block HİÇ basılmamalı — boş bir başlık modele
    olmayan bir geçmiş vaat eder."""
    assert RunMemory().render() == ""


def test_the_block_says_it_is_context_and_not_evidence():
    memory = RunMemory()
    memory.note(ts=0.0, moment="forklift geçti", participants=[],
                decision="ignore", severity="rutin")
    assert "kanıt" in memory.render().lower()
