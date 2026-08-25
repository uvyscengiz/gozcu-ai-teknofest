"""Testlerin ortak yardımcıları."""

import pytest


@pytest.fixture
def gated(monkeypatch):
    """Onay kapısını AÇAR — `halt_production_line` yeniden kapılanır.

    Kapı 26 Ağustos'ta varsayılan olarak boşaltıldı (araçlar mock; olmayan
    bir eylemi kapılamak ajanı araç çağırmaktan alıkoyuyordu). Makine
    silinmedi ve gerçek saha sistemlerine bağlanan bir kurulumda geri
    gelmeli — bu fixture onu sınayan testleri ayakta tutuyor.

    İki modülde birden yamalanıyor: `supervisor` adı içeri **import ederek**
    bağlıyor, yani yalnız `registry`'yi yamalamak onu etkilemez.
    """
    from gozcu.agents import supervisor
    from gozcu.tools import registry

    gate = frozenset({"halt_production_line"})
    monkeypatch.setattr(registry, "NEEDS_APPROVAL", gate)
    monkeypatch.setattr(supervisor, "NEEDS_APPROVAL", gate)
    return gate
