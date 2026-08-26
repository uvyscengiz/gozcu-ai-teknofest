"""Model-facing yedek notlarında iç katman adı sızmaz (Görev 20 devamı).

26 Ağustos canlı koşusunda "Sentez kademesi ... ÜRETEMEDİ" notu modele bir
bölge adı gibi göründü: `dispatch_medical(location="Sentez kademesi")`,
`site_alarm(zone="Sentez kademesi")`, `radio_call(message="Sentez
kademesinde ...")` çağrıldı ve teslim edilen `summary` de "Sentez
kademesinde forklift yan devrildi" dedi — "Sentez kademesi" delivered JSON'da
14 kez geçti, böyle bir bölge yok. Not arıza konusunda dürüsttü ama
"sentez"/"kademe"/"katman" gibi bir iç boru hattı ismi taşıyordu ve model onu
maddi bir yer sanıp uydurdu.

Bu test, modele giden BEŞ yedek notun hiçbirinde fabrika-plausible bir iç
katman isminin kalmadığını garanti eder. Operatöre/log'a giden mühendislik
dili (DEGRADED_SUMMARY, EMPTY_SUMMARY, UNREADABLE_SUMMARY,
DEGRADED_REASON/EMPTY_REASON/UNREADABLE_REASON) kasıtlı olarak kapsam DIŞI —
onlar zaten karantina sayesinde model prompt'una hiç girmiyor.
"""

import re

from gozcu.agents.reporter import _episode_line
from gozcu.agents.supervisor import FALLBACK_REMINDER, NO_DESCRIPTION_NOTE
from gozcu.agents.synthesizer import FALLBACK_CONTINUATION
from gozcu.models import Episode
from gozcu.report import FALLBACK_EVENT

#: Fabrikada gerçek bir bölge/hat/ekipman adı sanılabilecek iç katman
#: sözcükleri. Case-insensitive aranır.
_REIFIABLE_NOUNS = ("sentez", "kademe", "katman")


def _assert_clean(label: str, text: str) -> None:
    lowered = text.lower()
    for noun in _REIFIABLE_NOUNS:
        assert noun not in lowered, (
            f"{label} iç katman adı '{noun}' içeriyor ve modele fabrika "
            f"bölgesi/hattı gibi görünebilir: {text!r}")


def test_no_description_note_carries_no_internal_layer_noun():
    _assert_clean("NO_DESCRIPTION_NOTE", NO_DESCRIPTION_NOTE)


def test_no_description_note_tells_the_model_nothing_in_it_is_a_location():
    """Sadece iç katman adını silmek yetmez: model yine de notun içindeki
    herhangi bir kelimeyi bölge/hat/ekipman adı sanıp bir araç parametresi
    olarak kullanabilir. Not bunu açıkça yasaklamalı."""
    assert "parametre" in NO_DESCRIPTION_NOTE.lower()
    assert "bölge" in NO_DESCRIPTION_NOTE.lower()


def test_fallback_reminder_carries_no_internal_layer_noun():
    _assert_clean("FALLBACK_REMINDER", FALLBACK_REMINDER)


def test_fallback_continuation_carries_no_internal_layer_noun():
    _assert_clean("FALLBACK_CONTINUATION", FALLBACK_CONTINUATION)


def test_fallback_event_carries_no_internal_layer_noun():
    _assert_clean("FALLBACK_EVENT", FALLBACK_EVENT)


def test_episode_line_fallback_branch_carries_no_internal_layer_noun():
    fallback = Episode(start_ts=5.0, phase="development",
                       summary_tr="Sentez üretilemedi; ham gözlemler kayıtlı.",
                       preliminary_risk="Orta", summary_source="fallback")
    fallback.id = 1
    _assert_clean("_episode_line(fallback)", _episode_line(fallback))
