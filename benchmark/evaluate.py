"""Özet kalitesi değerlendirmesi — LLM-as-judge.

`kpi.py` saf fonksiyonlarla çalışır; bu modül gateway çağrısı yapıyor.
Ayrı dosyada durmasının sebebi bu. Sonuç `kpi.json`'un `summary_quality`
anahtarına yazılır.
"""

from pydantic import BaseModel, Field, ValidationError


class SummaryScore(BaseModel):
    """Dört boyutlu özet puanı."""
    completeness: int = Field(ge=1, le=5)
    grounding: int = Field(ge=1, le=5)
    turkish_quality: int = Field(ge=1, le=5)
    conciseness: int = Field(ge=1, le=5)


RUBRIC_PROMPT = """\
Sen bir ölçüm aracısısın. Aşağıda bir video analiz sisteminin ürettiği rapor var.
Raporu dört boyutta 1 (çok kötü) ile 5 (mükemmel) arasında puanla.

**Bütünlük (completeness):** Rapor, algılanan olayların tümünü kapsıyor mu?
**Doğruluk (grounding):** Rapordaki iddialar aşağıdaki epizot kayıtlarıyla tutarlı mı?
**Türkçe kalitesi (turkish_quality):** Metin doğal Türkçe mi, yoksa makine çevirisi ya da İngilizce karışım mı?
**Özlülük (conciseness):** Fazlalık olmadan, operatörün hızla okuması için yeterince kısa mı?

### Epizot kayıtları (depodaki gerçek tespit)
{episodes}

### Risk değerlendirmeleri
{risks}

### Değerlendirilecek rapor
{report}

Yalnız puanları döndür, açıklama ekleme.
"""


def evaluate_summary(store, gw) -> dict | None:
    """Depodaki özeti gateway üzerinden değerlendirir.

    Gateway kesintiyse veya yeterli veri yoksa `None`.
    """
    episodes = store.episodes()
    if not episodes:
        return None

    summaries = [ep.summary_tr for ep in episodes if ep.summary_tr]
    if not summaries:
        return None

    risks = store.risks()
    episode_text = "\n".join(
        f"- [{ep.phase}] {ep.summary_tr} (risk: {ep.preliminary_risk})"
        for ep in episodes
    )
    risk_text = "\n".join(
        f"- {r.level}: {r.rationale_tr}" for r in risks
    ) or "(risk değerlendirmesi yok)"

    report_text = "\n\n".join(summaries)

    prompt = RUBRIC_PROMPT.format(
        episodes=episode_text,
        risks=risk_text,
        report=report_text,
    )

    try:
        response = gw.ask(
            "main",
            [{"role": "user", "content": prompt}],
            schema=SummaryScore,
            temperature=0.0,
        )
        # `Gateway.ask` şemalı çağrıda bile ham JSON metnini `content`'te
        # döndürür; ayrıştırmayı çağıran yapar (bkz. agents/risk.py).
        if response.degraded or not (response.content or "").strip():
            return None
        try:
            score = SummaryScore.model_validate_json(response.content)
        except (ValueError, ValidationError):
            return None
        mean = (score.completeness + score.grounding
                + score.turkish_quality + score.conciseness) / 4.0
        return {
            "completeness": score.completeness,
            "grounding": score.grounding,
            "turkish_quality": score.turkish_quality,
            "conciseness": score.conciseness,
            "mean": round(mean, 2),
        }
    except Exception:
        return None
