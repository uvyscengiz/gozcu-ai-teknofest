# Görev 22 — Mikro-ajan yeniden tasarımı (Karar & Aksiyon ajanı)

> ## ✅ TAMAMLANDI — 27 Ağustos 2026
>
> **Ajan kadrosu takım içi PDF önerisiyle hizalandı ve risk analistinden
> ayrılan yeni bir Karar & Aksiyon ajanı (`action_planner`) zincire girdi.**
> `router → orchestrator`, `synthesizer → anomaly_analyst` yeniden
> adlandırıldı (kodda; gateway kademesi `"router"` **hariç** — bkz. aşağı).
> `gozcu/agents/action_planner.py` (yeni), `gozcu/fixtures/protocols.json`
> (yeni, beş yazılı prosedür), `Episode.event_class`/`zone_id`,
> `fixtures.loader.match_protocols()`, altı çağrı noktasına dikiş. Risk
> analisti artık yalnız derecelendiriyor — `RiskAssessment.proposed_actions`
> kaldırıldı. Sekiz alt görev halinde (T1–T8), her biri kör inceleme
> turundan geçti; ledger:
> `.superpowers/sdd/2026-08-27-mikro-ajan-yeniden-tasarimi/progress.md`.
>
> Depo genelinde **1070 test** geçiyor (taban 1026, +44).
>
> **Sonraki göreve başlarken bilmen gerekenler**
> ([notlar](#tamamlanma-notları-gelecek-görevleri-bağlayan) bölümüne bak):
> **gateway kademesi hâlâ `"router"`** — ajan `orchestrator`, model kimliği
> `router`, bilerek ayrıştırılmış; **`action_planner` okuma araçlarını
> gerçekten çağırıyor**, yalnız sunmuyor; **yükseltme mesajının plan satırı
> update kipinde koşulsuz değil** — "fırtına" riskine karşı düzeltildi; ve
> **rapor promptu prosedür kimliği uydurmuyor** — eşleşme yoksa bunu açıkça
> söylüyor.

**Spec:** [2026-08-27-mikro-ajan-yeniden-tasarimi-design.md](../superpowers/specs/2026-08-27-mikro-ajan-yeniden-tasarimi-design.md)
(kaynak: takım içi `Feraset_Guncel_Ajan_Mimarisi.pdf`, §0b beş ürün sahibi
kararı) ·
**Plan:** [2026-08-27-mikro-ajan-yeniden-tasarimi.md](../superpowers/plans/2026-08-27-mikro-ajan-yeniden-tasarimi.md)
(8 görev) ·
**Karar günlüğü:** [decision-log.md](../05-decisions/decision-log.md#27-ağustos--mikro-ajan-yeniden-tasarımı-kadro-adları-ve-karar--aksiyon-ajanı)
(beş ürün sahibi kararı + uygulama sırasında planı bozan dokuz hüküm).

**Bağımlılık:** [17](17-cikti-sozlesmesi.md), [21](21-web-konsolu.md)

## Bağlam — PDF'in sekizi, kodun altısı

Takım içi mimari önerisi (`Feraset_Guncel_Ajan_Mimarisi.pdf`) sekiz
mikro-ajan sayıyordu. Altısı zaten koddaydı — farklı adlarla, aynı işi
yaparak. Gerçek fark üç yerdeydi:

1. **Karar & Aksiyon ajanı yoktu.** Risk analisti hem ciddiyeti biçiyor hem
   müdahale öneriyordu — tek model çağrısında iki iş.
2. **Adlar tutmuyordu.** PDF'in "Orkestratör"ü kodda `router`, "Anomali
   Analiz"i `synthesizer`. Mimari dokümanla trace panelinde aynı olay iki
   ayrı isimle görünüyordu.
3. **PDF üç bileşeni saymıyordu:** Yorumlayıcı (VLM), Raportör, Guard. Eksik
   sayımdı, silme talebi değildi — üçü de yerinde kaldı.

Ürün sahibi bu üçünü çözecek beş kararı spec §0b'de verdi; tam metin ve
gerekçeleri [karar günlüğünde](../05-decisions/decision-log.md). Özet:
"ajan" = model çalıştıran aktör (Mock/Benchmark alt sistem sayıldı),
"tamamen yerel" ifadesi düzeltildi, Karar & Aksiyon ajanı protokol seçici
(A2) olarak kapsandı, yeniden adlandırma kodda yapıldı, hız ölçümü sonraya
bırakıldı.

## Ne indi — sekiz alt görev

| T | İş | Sonuç |
|---|---|---|
| T1 | `router → orchestrator`, `synthesizer → anomaly_analyst` yeniden adlandırma | Gateway kademesi `"router"` hariç tutuldu (Ruling 1); `RouterDecision` tip adı da hariç (Ruling 5) |
| T2 | `Episode.event_class` (Türkçe enum) + `zone_id` | Anomali analisti ikisini de üretiyor |
| T3 | `gozcu/fixtures/protocols.json` — beş yazılı prosedür + `match_protocols()` | Olay sınıfı + bölge + asgari risk üzerinde deterministik süzgeç |
| T4 | `gozcu/agents/action_planner.py`, `ActionPlan`, `action_plan` depo tablosu | Aday prosedürler arasından seçiyor, asla uydurmuyor; model düşerse prosedürün adımları birebir yedeğe yazılıyor; okuma araçlarını gerçekten çağırıyor (Ruling 3) |
| T5 | Altı çağrı noktasına dikiş | Plan artık Nöbetçi'nin yükseltme mesajına giriyor; update kipinde koşulsuz değil (Ruling 8) |
| T6 | `RiskAssessment.proposed_actions` kaldırıldı | Risk analisti yalnız derecelendiriyor; `actions` çıktı anahtarı artık depolanmış `ActionPlan`lardan türüyor |
| T7 | Kök neden raporu uygulanan prosedürleri gösteriyor | Prompt, eşleşen prosedür yokken önlenebilirlik iddiası yapmayı ve kimlik uydurmayı yasaklıyor (Ruling 9) |
| T8 | Belgeleme (bu dosya) | Karar günlüğü, görev tablosu, eski spec'e üstyazı, `CLAUDE.md`, arayüz Türkçe kova etiketleri |

Ayrıntılı brief/report çiftleri ve inceleme diff'leri:
`.superpowers/sdd/2026-08-27-mikro-ajan-yeniden-tasarimi/`.

## Kabul

- [x] `AgentName` yeni hâli: `perception, orchestrator, interpreter, anomaly_analyst, risk_analyst, action_planner, supervisor, reporter`
- [x] `Episode.event_class`/`zone_id` anomali analistinden geliyor
- [x] `gozcu/fixtures/protocols.json` + `match_protocols()` — 8 test
- [x] `action_planner.plan_actions()` — asla prosedür uydurmuyor, model düşerse prosedür adımlarına düşüyor
- [x] Nöbetçi'nin yükseltme mesajı planı taşıyor; update kipi koşulsuz öneri/onay talimatı içermiyor
- [x] `RiskAssessment.proposed_actions` yok; `risk.py` yalnız derecelendiriyor
- [x] Kök neden raporu uygulanan prosedürleri gösteriyor, eşleşme yoksa uydurmuyor
- [x] `gozcu/ui/view.py::DECISION_BUCKET_LABELS` yeni rol adlarını kullanıyor — anahtarlar (`closed_at_router`, `to_synthesizer`) **değişmedi** (KPI taban ölçümü onlara kilitli)
- [x] `uv run pytest tests/ -v` → **1070 passed**

## Tamamlanma notları (gelecek görevleri bağlayan)

- **Gateway kademesi `"router"` KASITLI OLARAK yeniden adlandırılmadı.**
  `config.MODELS["router"]`, `gateway.Tier`, `gw.ask("router", …)`,
  `GOZCU_MODEL_ROUTER` — hepsi aynen kaldı. Ajan `orchestrator`, model
  kimliği `router`; bu bir tutarsızlık değil, kayıtlı bir karar
  (decision-log Ruling 1). Bir sonraki görev bu ikiliği "düzeltmeye"
  kalkışırsa önce CLAUDE.md'nin "model kimlikleri yalnız `config.py`'de"
  kuralına ve `.env`'de yaşayan `GOZCU_MODEL_ROUTER` değişkenine bakılmalı.
- **`action_planner` okuma araçlarını GERÇEKTEN çalıştırıyor,** `risk.py`
  ile aynı iki turlu şekilde (`_tool_calls`/`_run_tool_calls`/
  `_assistant_turn` ortak). `query_shift_personnel` ve
  `query_equipment_history` sunuluyor; ikinci tur araçsız.
- **Yükseltme mesajının plan satırı update kipinde `UPDATE_PLAN_LINE`'a
  düşüyor** — olgusal bir özet, öneri/onay talimatı yok. Tekrar eden bir
  yükseltmede aynı satırın "onay iste" demesi 26 Ağustos'ta düzeltilen
  yükseltme fırtınasını yeniden açardı; bkz. decision-log Ruling 8.
- **Kök neden raporu, prosedür eşleşmediğinde kimlik uydurmuyor.**
  `plan_source == "empty"` olduğunda rapor "bu olay sınıfını kapsayan
  tanımlı bir prosedür yok" diyor, önlenebilirlik iddiası yapmıyor —
  raportöre zaten prosedür kataloğu verilmiyor (yalnız `protocol_id`),
  yani iddia etmesi uydurma olurdu (decision-log Ruling 9).
- **Ertelenen minik bulgular** (test kusurları, ölü kod, eksik test
  kapsamı) kod kalitesini etkilemiyor ama bir sonraki dokunuşta akılda
  tutulmalı — tam liste
  `.superpowers/sdd/2026-08-27-mikro-ajan-yeniden-tasarimi/progress.md`'de.
  En görünürleri: `action_planner.py:249`'daki `candidates[0]` tek
  prosedürlü olay sınıflarında belirsiz değil ama dosya sırasına bağımlı;
  `supervisor.py:176-182`'deki `plan_line` yalnız `description_tr` taşıyor,
  `tool_name`/`params` düşürülüyor.
- **Kapsam dışı bırakılanlar** (planın kendisinde işaretli): Uzun Süreli
  Hafıza ajanı (`memory.py`, ayrı oturumda), Mock/Benchmark'ın
  ajanlaştırılması, A3 (düşük riskte özerk yürütme), `supervisor`
  yeniden adlandırması, gecikme optimizasyonu, PDF dosyasının kendisinin
  düzeltilmesi.
