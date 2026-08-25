"""İz kaydının testleri — tanı aracı ölçtüğü şeyi öldürmemeli."""

import time

import pytest

from gozcu import trace


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("GOZCU_TRACE", "1")
    monkeypatch.delenv("GOZCU_TRACE_FILE", raising=False)
    # Girinti sayacı thread-local ve testler arasında taşınıyor; sıfırlanmazsa
    # önceki testten kalan derinlik bu testin girinti iddiasını bozar.
    trace.reset_depth()


def _lines(capsys):
    return [line for line in capsys.readouterr().err.splitlines() if line.strip()]


class TestStep:
    def test_start_and_end_are_both_recorded(self, capsys):
        with trace.step("kademe"):
            pass
        lines = _lines(capsys)
        assert any("→ kademe" in line for line in lines)
        assert any("✓ kademe" in line for line in lines)

    def test_duration_is_reported(self, capsys):
        with trace.step("kademe"):
            time.sleep(0.02)
        end = [line for line in _lines(capsys) if "✓" in line][0]
        assert "ms" in end

    def test_failure_is_marked_and_reraised(self, capsys):
        with pytest.raises(ValueError):
            with trace.step("kademe"):
                raise ValueError("patladı")
        end = [line for line in _lines(capsys) if "✗" in line][0]
        assert "ValueError" in end and "patladı" in end

    def test_both_clocks_appear(self, capsys):
        """Duvar saati ekranla eşleştirmek, geçen süre hangi saniyede
        olduğunu görmek için. İkisi birden gerekli."""
        with trace.step("kademe"):
            pass
        first = _lines(capsys)[0]
        assert ":" in first.split("]")[0]      # duvar saati
        assert "s]" in first                    # koşudan beri geçen

    def test_nested_steps_indent(self, capsys):
        with trace.step("dış"):
            with trace.step("iç"):
                pass
        # `capsys.readouterr()` tamponu BOŞALTIR — iki kez çağırmak ikinci
        # seferde boş liste verir. Bir kez okunuyor.
        lines = _lines(capsys)
        inner = [line for line in lines if "→ iç" in line][0]
        outer = [line for line in lines if "→ dış" in line][0]
        assert inner.index("→") > outer.index("→")

    def test_depth_is_restored_after_a_failure(self, capsys):
        """Patlayan bir adım girintiyi bozarsa sonraki her satır kayar."""
        with pytest.raises(ValueError):
            with trace.step("patlayan"):
                raise ValueError("x")
        capsys.readouterr()
        with trace.step("sonraki"):
            pass
        line = [line for line in _lines(capsys) if "→ sonraki" in line][0]
        assert line.index("→") == line.index("]") + 2


class TestHeartbeat:
    def test_a_long_step_reports_while_running(self, capsys, monkeypatch):
        """Asıl mesele bu: bitmeyen bir adım kendini bildirmeli.

        Başlangıç/bitiş kaydı bitmeyen bir adım için hiçbir şey söylemez —
        son satır 'başladı' olarak kalır ve bakan kişi sürüyor mu, ölmüş mü
        bilemez.
        """
        monkeypatch.setattr(trace, "HEARTBEAT_S", 0.05)
        with trace.step("uzun"):
            time.sleep(0.22)
        beats = [line for line in _lines(capsys) if "⋯ uzun" in line]
        assert len(beats) >= 2
        assert "hâlâ çalışıyor" in beats[0]

    def test_a_short_step_does_not_beat(self, capsys, monkeypatch):
        monkeypatch.setattr(trace, "HEARTBEAT_S", 5.0)
        with trace.step("kısa"):
            pass
        assert not [line for line in _lines(capsys) if "⋯" in line]

    def test_heartbeat_stops_after_the_step(self, capsys, monkeypatch):
        monkeypatch.setattr(trace, "HEARTBEAT_S", 0.05)
        with trace.step("bitti"):
            pass
        capsys.readouterr()
        time.sleep(0.16)
        assert not [line for line in _lines(capsys) if "⋯ bitti" in line]


class TestDisabled:
    def test_nothing_is_written_when_off(self, capsys, monkeypatch):
        monkeypatch.setenv("GOZCU_TRACE", "0")
        with trace.step("kademe"):
            pass
        trace.event("olay")
        assert not _lines(capsys)

    def test_the_body_still_runs_when_off(self, monkeypatch):
        monkeypatch.setenv("GOZCU_TRACE", "0")
        ran = []
        with trace.step("kademe"):
            ran.append(True)
        assert ran == [True]

    def test_exceptions_still_propagate_when_off(self, monkeypatch):
        monkeypatch.setenv("GOZCU_TRACE", "0")
        with pytest.raises(ValueError):
            with trace.step("kademe"):
                raise ValueError("x")


class TestNeverBreaksTheRun:
    def test_a_broken_stream_does_not_kill_the_step(self, monkeypatch):
        """Tanı aracı ölçtüğü şeyi öldürmemeli."""
        def explode(*args, **kwargs):
            raise OSError("disk dolu")

        monkeypatch.setattr(trace, "_stream", explode)
        ran = []
        with trace.step("kademe"):
            ran.append(True)
        assert ran == [True]

    def test_an_unprintable_detail_does_not_kill_the_step(self, monkeypatch):
        class Nasty:
            def __format__(self, spec):
                raise RuntimeError("biçimlenemiyor")

        ran = []
        with trace.step("kademe", Nasty()):     # type: ignore[arg-type]
            ran.append(True)
        assert ran == [True]


class TestEvent:
    def test_event_is_written(self, capsys):
        trace.event("pencere", "3/12")
        line = _lines(capsys)[0]
        assert "pencere" in line and "3/12" in line


class TestFileSink:
    def test_writes_to_a_file_when_asked(self, tmp_path, monkeypatch, capsys):
        path = tmp_path / "iz.log"
        monkeypatch.setenv("GOZCU_TRACE_FILE", str(path))
        with trace.step("kademe"):
            pass
        assert "→ kademe" in path.read_text(encoding="utf-8")
        assert not _lines(capsys)          # dosyaya giderken stderr'e gitmiyor
