"""Etiketli klip listesi — benchmark'ın tek doğruluk kaynağı.

Dosya `benchmark/ground_truth.csv`. Etiketleme **el işi**: olay penceresini
videoyu izleyen bir insan işaretler. Bu yüzden burada üç durum var ve üçü
birbirine karıştırılmıyor:

- **olaylı ve penceresi işaretli** — `timestamp_drift` yalnız bunları kullanır
- **olaylı ama penceresi henüz işaretlenmemiş** — ölçüme girmez, koşucu
  bunları adıyla sayar; sessizce sıfır saymak sahte bir doğruluk üretirdi
- **olaysız (negatif örnek)** — `start_s` alanı boş; `float("")` istisna atar,
  bu yüzden satır sapma hesabına hiç sokulmaz
"""

import csv
from dataclasses import dataclass
from pathlib import Path

#: `kind` sözlüğü. Serbest metin kabul edilmiyor: yazım farkları etiketli
#: kümeyi sessizce ikiye böler.
KINDS = frozenset({"vehicle_tipover", "load_drop", "fire", "ppe_violation",
                   "fall", "yok"})

NO_INCIDENT_KIND = "yok"

DEFAULT_PATH = Path(__file__).resolve().parent / "ground_truth.csv"

COLUMNS = ("video", "has_incident", "start_s", "end_s", "kind")


class GroundTruthError(ValueError):
    """Etiket dosyası okunamadı — ölçüm başlatılmadan durdurulur."""


@dataclass(frozen=True)
class Clip:
    """Tek bir etiketli klip.

    `window` yalnız olay penceresi işaretlenmişse dolu; `None` ise ya klip
    negatif örnek ya da pencere henüz işaretlenmemiş (`labelled` ikisini
    ayırır).
    """

    video: str
    has_incident: bool
    window: tuple[float, float] | None
    kind: str

    @property
    def labelled(self) -> bool:
        return self.has_incident and self.window is not None

    @property
    def unlabelled(self) -> bool:
        return self.has_incident and self.window is None


def _seconds(value: str, field: str, line: int) -> float | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError as error:
        raise GroundTruthError(
            f"{line}. satır: {field} sayı değil ({value!r})") from error


def load_ground_truth(path: str | Path = DEFAULT_PATH) -> list[Clip]:
    """Etiket dosyasını okur; bozuk satırda `GroundTruthError` atar.

    `#` ile başlayan satırlar yorum (`data/labels.tsv` ile aynı gelenek).
    Sessizce atlanan tek şey yorumlar ve boş satırlar; geri kalan her tutarsız
    satır yüksek sesle durdurur — ölçüm dosyası yarı okunmuş hâlde işe
    yaramaz.
    """
    path = Path(path)
    if not path.is_file():
        raise GroundTruthError(f"etiket dosyası yok: {path}")

    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        raise GroundTruthError(f"etiket dosyası boş: {path}")

    reader = csv.DictReader(lines)
    if tuple(reader.fieldnames or ()) != COLUMNS:
        raise GroundTruthError(
            f"başlık satırı {COLUMNS} olmalı, {tuple(reader.fieldnames or ())} var")

    clips: list[Clip] = []
    for number, row in enumerate(reader, start=2):
        video = (row["video"] or "").strip()
        if not video:
            raise GroundTruthError(f"{number}. satır: video yolu boş")

        flag = (row["has_incident"] or "").strip()
        if flag not in ("0", "1"):
            raise GroundTruthError(
                f"{number}. satır: has_incident 0 ya da 1 olmalı ({flag!r})")
        has_incident = flag == "1"

        kind = (row["kind"] or "").strip()
        if kind not in KINDS:
            raise GroundTruthError(
                f"{number}. satır: bilinmeyen kind {kind!r}; "
                f"sözlük: {sorted(KINDS)}")
        if has_incident and kind == NO_INCIDENT_KIND:
            raise GroundTruthError(
                f"{number}. satır: has_incident=1 ama kind={NO_INCIDENT_KIND}")
        if not has_incident and kind != NO_INCIDENT_KIND:
            raise GroundTruthError(
                f"{number}. satır: has_incident=0 ama kind={kind}")

        start = _seconds(row["start_s"], "start_s", number)
        end = _seconds(row["end_s"], "end_s", number)
        window = None
        if has_incident and start is not None:
            if end is None:
                raise GroundTruthError(
                    f"{number}. satır: start_s var ama end_s yok")
            if end <= start:
                raise GroundTruthError(
                    f"{number}. satır: end_s ({end}) start_s'ten ({start}) büyük olmalı")
            window = (start, end)
        clips.append(Clip(video=video, has_incident=has_incident,
                          window=window, kind=kind))
    return clips


def windows(clips: list[Clip]) -> list[tuple[float, float]]:
    """`timestamp_drift`'in beklediği pencere listesi — yalnız işaretliler."""
    return [clip.window for clip in clips if clip.labelled]
