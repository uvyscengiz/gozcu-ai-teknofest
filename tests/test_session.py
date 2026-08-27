import threading
import time

import pytest

from gozcu.ui.session import RUN_STATES, Session


def test_every_state_change_bumps_the_version_and_wakes_waiters():
    """4. tur blocker'ı: bitiş geçişi bağlı istemciye ulaşmıyordu."""
    session = Session()
    seen = session.version
    woke = threading.Event()

    def watcher() -> None:
        if session.wait_for_version(seen, timeout=2.0):
            woke.set()

    thread = threading.Thread(target=watcher, daemon=True)
    thread.start()
    time.sleep(0.05)
    session.set_state("done")
    thread.join(timeout=2.0)
    assert woke.is_set(), "bitiş geçişi bekleyeni uyandırmadı"
    assert session.version > seen


def test_the_wire_states_are_the_only_states():
    assert set(RUN_STATES) == {"idle", "running", "paused", "intervened",
                               "done", "failed", "abandoned"}
    with pytest.raises(ValueError):
        Session().set_state("koşuyor")


def test_resume_is_refused_when_the_run_is_not_paused():
    """Bayat jeton: duraklamamışken yazılan bir jeton bir sonraki
    duraklamayı sessizce atlardı."""
    session = Session()
    session.set_state("running")
    assert session.request_resume() is False
    assert session.resume_requested is False


def test_no_blocking_when_step_mode_is_off():
    """Anahtar kapalıyken `wait_if_step_mode` HEMEN dönüyor.

    Görev 11'de `test_console.py:754`'ten yeniden kuruldu: mekanizma
    `Event` yerine `Condition`+yüklem oldu, kural değişmedi. Dönmezse bu
    test DONAR ve donması da doğru sonuçtur — 25 Ağustos'ta canlı koşuda
    olan tam buydu ve 115 saniyelik kayıt 4. pencerede durdu.
    """
    session = Session()
    assert session.step_mode is False
    session.wait_if_step_mode()
    assert session.run_state == "idle", "kapalıyken duraklamaya geçmemeli"


def test_the_waiter_consumes_the_token_and_leaves_paused_together():
    session = Session()
    session.set_step_mode(True)
    released = threading.Event()

    def worker() -> None:
        session.wait_if_step_mode()
        released.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    time.sleep(0.1)
    assert session.run_state == "paused"
    assert session.request_resume() is True
    thread.join(timeout=2.0)
    assert released.is_set()
    # Jeton tüketildi VE paused'dan çıkıldı — ikisi tek kritik bölümde.
    assert session.resume_requested is False
    assert session.run_state != "paused"


def test_step_mode_off_releases_a_waiting_loop():
    session = Session()
    session.set_step_mode(True)
    released = threading.Event()
    thread = threading.Thread(
        target=lambda: (session.wait_if_step_mode(), released.set()),
        daemon=True)
    thread.start()
    time.sleep(0.1)
    session.set_step_mode(False)
    thread.join(timeout=2.0)
    assert released.is_set()


def test_step_mode_cannot_be_re_armed_on_an_abandoned_run():
    """Terk edilmiş koşu bloklamadan sonuna kadar akmalı."""
    session = Session()
    session.abandon()
    assert session.set_step_mode(True) is False
    assert session.step_mode is False


def test_an_abandoned_run_does_not_finish_as_done():
    """Terk edilen koşunun çıktısı atılır (spec §4). Koşulsuz 'running'
    ve koşulsuz 'done' yazmak onu geçerli bir koşu gibi sunardı."""
    session = Session()
    session.set_step_mode(True)
    thread = threading.Thread(target=session.wait_if_step_mode, daemon=True)
    thread.start()
    time.sleep(0.1)
    session.abandon()
    thread.join(timeout=2.0)
    assert session.run_state == "abandoned"
    session.output = object()
    session.finish()
    assert session.run_state == "abandoned"
    assert session.output is None


def test_an_intervention_is_stamped_without_stopping_the_run():
    """`step_mode` kapalıyken müdahale anı kart olarak basılıyor ve koşu
    sürüyor — 25 Ağustos kararı. Önceki taslakta bu değerin yazarı yoktu."""
    session = Session()
    session.set_state("running")
    session.note_intervention()
    assert session.run_state == "intervened"


def test_abandon_releases_a_waiting_loop_without_a_lost_wakeup():
    """Event.clear()/wait() yarışı: set() bekleyenin kendi clear()'ı
    tarafından silinirse iş parçacığı sonsuza dek beklerdi."""
    session = Session()
    session.set_step_mode(True)
    released = threading.Event()
    thread = threading.Thread(
        target=lambda: (session.wait_if_step_mode(), released.set()),
        daemon=True)
    thread.start()
    time.sleep(0.1)
    session.abandon()
    thread.join(timeout=2.0)
    assert released.is_set()
