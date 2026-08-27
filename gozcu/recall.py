"""Koşu içi kısa süreli hafıza — bir koşunun kendi geçmişi.

Görü katmanı her pencereye **sıfırdan** bakıyor: 10 saniyelik bir klip
gidiyor, bir açıklama dönüyor, sonraki pencere öncekini hiç bilmiyor. 2.
dakikadaki dengesizlik 5. dakikadaki devrilmenin bağlamı olamıyor.

Uzun-video literatüründeki "hafıza bankası" deseninin **text** karşılığı:
özellik seviyesinde yapılamıyor çünkü ağ geçidine base64 mp4 gidip text
dönüyor. Elimizdeki tek temsil text, o yüzden hafıza da text.

**Ajansız ve modelsiz.** Saf veri yapısı: model çağırmıyor, ağa çıkmıyor,
`DecisionLoop`'a bağımlı değil. Beslemesi `run.py`'deki kapanışlardan
geliyor — döngünün kendisi DEĞİŞMİYOR.
"""

from dataclasses import dataclass, field

from gozcu.config import RECALL_WINDOW_N
from gozcu.models import SEVERITY_LEVELS

#: Bloğun başlığı. "kanıt DEĞİL" kısmı süs değil: block görü çağrısına
#: giriyor ve modelin oradan üreteceği anlar epizoda, oradan da teslim
#: edilen `events[]`'e akıyor. Model geçmiş bir pencereyi bu klipte
#: gördüğü bir şey sanarsa uydurma üretir.
RECALL_HEADER = "ÖNCEKİ PENCERELER (bağlam — bu klibin kanıtı DEĞİL)"

#: Kalıcı tutulan derecelendirme. **Kopyalanmıyor, İTHAL EDİLİYOR:** bu
#: depoda bir enum bir kez ikinci bir yere elle yazıldı ve iki liste
#: ayrışınca sistem sessizce ölü hâle geldi (CLAUDE.md). Yorumla önlenen
#: ayrışma, önlenmemiş ayrışmadır.
INCIDENT = SEVERITY_LEVELS[-1]


@dataclass
class WindowNote:
    """Tek pencerenin satırı."""

    ts: float
    moment: str
    participants: list[str] = field(default_factory=list)
    decision: str = "ignore"
    #: **Tutuluyor ama RENDER EDİLMİYOR** — bkz. `render()`.
    severity: str = "rutin"


class RunMemory:
    """Koşunun pencere geçmişi, hiyerarşik sınırla.

    Sınır iki katmanlı: **son N pencere** tam detay + `severity == "olay"`
    olan **her** pencere kalıcı. Olay asla düşmez, rutin pencereler kayar.
    Düz bir kayan pencere, uzun bir videoda olayın kendisini düşürürdü ve
    tam da hatırlanması gereken şey odur.
    """

    def __init__(self, limit: int | None = None) -> None:
        self.limit = RECALL_WINDOW_N if limit is None else limit
        self._notes: list[WindowNote] = []

    def note(self, ts: float, moment: str, participants=(),
             decision: str = "ignore", severity: str = "rutin") -> None:
        self._notes.append(WindowNote(ts=ts, moment=moment,
                                      participants=list(participants),
                                      decision=decision, severity=severity))

    def recent(self, n: int | None = None) -> list[WindowNote]:
        """Kalıcı olaylar + son N pencere, zaman sırasında ve tekrarsız."""
        limit = self.limit if n is None else n
        pinned_notes = [note for note in self._notes if note.severity == INCIDENT]
        latest_notes = self._notes[-limit:] if limit else []
        selected = {id(note): note for note in (*pinned_notes, *latest_notes)}
        return sorted(selected.values(), key=lambda note: note.ts)

    def render(self, n: int | None = None) -> str:
        """Prompt'a girecek block. Boşsa **boş dize** — başlık bile yok.

        **`severity` YAZILMIYOR ve bu bir tercih değil, bir kısıt.**
        `severity` epizot açılışının tek kapısı (`DecisionLoop._may_open`).
        Geçmiş derecelendirmeleri gören model kendini doğrulayan bir döngüye
        girer: "olay, olay → olay". Blok NE GÖRÜLDÜĞÜNÜ taşır, NASIL
        DERECELENDİRİLDİĞİNİ değil.
        """
        notes = self.recent(n)
        if not notes:
            return ""
        if all(note.severity == "rutin" for note in notes):
            return ""
        lines = [RECALL_HEADER]
        for note in notes:
            who = f" [{', '.join(note.participants)}]" if note.participants else ""
            lines.append(f"- {int(note.ts // 60):02d}:"
                         f"{int(note.ts % 60):02d}{who} {note.moment}")
        return "\n".join(lines)
