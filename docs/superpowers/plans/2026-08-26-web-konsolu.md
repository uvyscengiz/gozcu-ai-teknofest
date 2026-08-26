# Web konsolu — uygulama planı

> **Ajan işçiler için:** ZORUNLU ALT BECERİ —
> `superpowers:subagent-driven-development` ile görev görev uygulayın.
> Adımlar `- [ ]` kutucuklarıyla izleniyor.

**Amaç:** Gradio operatör konsolunu (`gozcu/ui/console.py`), aynı boru
hattını FastAPI + SSE + statik HTML üzerinden sunan özel bir web konsoluyla
değiştirmek.

**Mimari:** `console.py` zaten ikiye bölünmüş — saf fonksiyonlar üstte,
Gradio bağlantısı altta. Bu plan yalnız alt yarıyı değiştiriyor. Boru
hattı (`run_pipeline`, `DecisionLoop`, ajanlar, `Store`, `Gateway`,
`Supervisor`) **tek satır değişmiyor**. Durum tarayıcıya SSE ile tam
durum olarak akıyor; komutlar sıradan `POST`.

**Teknoloji:** FastAPI · `sse-starlette` · uvicorn · bağımlılıksız
HTML/CSS/JS (harici CDN, font, kütüphane **yok**).

**Spec:** [2026-08-26-web-konsolu-design.md](../specs/2026-08-26-web-konsolu-design.md)
— beş kör inceleme turundan geçti. Plan spec'ten argüman kuruyor; ikisi
birlikte okunuyor.

## Küresel kısıtlar

Her görevin gereksinimleri bu bölümü kapsıyor.

- **Kod İngilizce.** Sınıf, fonksiyon, alan, JSON anahtarı, HTML `id`/sınıf
  adı, SQL tablo adı — hepsi İngilizce.
- **İnsana görünen metin Türkçe.** Promptlar, operatör mesajları, ekrandaki
  her kelime, yorumlar ve docstring'ler.
- **Risk seviyeleri Türkçe ve tam dört:** `"Düşük" | "Orta" | "Yüksek" |
  "Kritik"` (`gozcu/models.py:11`).
- **`run_status` üç değer:** `measured` · `degraded` · `unmeasured`
  (`benchmark/kpi.py:124`). Telde bu değerler birebir.
- **Bir enum iki yerde yazılmaz.** Prompt/şema ayrışması bu depoyu bir kez
  sessizce öldürdü; tel de bir şema.
- **Model kimlikleri yalnız `gozcu/config.py`'da.**
- **Dört anahtar her koşuda:** `summary` · `events` · `risk` · `actions`.
- **Harici ağ bağımlılığı yok** — CDN, font, analytics hiçbiri.
- **TDD:** önce test, kırmızı olduğunu gör, sonra minimum kod.
- **Worktree yok** — `gorev-21-web-konsolu` dalında, ana çalışma ağacında.
- **Kapı:** `.venv/bin/pytest tests/ -q` bütünüyle yeşil **ve**
  `uv run python scripts/check-tasks.py` temiz.

## Dosya yapısı

| Dosya | Sorumluluk |
|---|---|
| `gozcu/ui/session.py` (yeni) | `Session`, `RunState`, `Condition`+`version` durum makinesi |
| `gozcu/ui/view.py` (yeni) | Depodan **veri** derleyicileri (eski Markdown'ın yerine) |
| `gozcu/ui/server.py` (yeni) | FastAPI: statik servis, JSON uçları, SSE, koşu yaşam döngüsü |
| `gozcu/ui/web/index.html` (yeni) | Üç görünümün iskeleti |
| `gozcu/ui/web/css/styles.css` (yeni) | Tema ve düzen |
| `gozcu/ui/web/js/sse.js` (yeni) | SSE bağlantısı, `seq` artımlı çizim |
| `gozcu/ui/web/js/feed.js` (yeni) | `FeedEntry` çizimi |
| `gozcu/ui/web/js/player.js` (yeni) | Oynatıcı, zaman çizelgesi, kutu katmanı |
| `gozcu/ui/web/js/trace.js` (yeni) | Şeffaflık görünümü |
| `gozcu/ui/web/js/bench.js` (yeni) | Performans görünümü |
| `gozcu/ui/feed.py` | `build_feed`/`FeedEntry` **değişmiyor**; `feed_html` Görev 11'de siliniyor (spec §2b) |
| `gozcu/ui/console.py` | **SİLİNİYOR** (Görev 11) |
| `app.py` | `gozcu.ui.server:baslat()` çağırıyor |
| `pyproject.toml` | `gradio` düşüyor; dört doğrudan bağımlılık + `stt` ekstrası |

## `Session` durum tablosu

Spec §2.1'in bağladığı tablo. Beş turun bulgularının kökü bu tablonun
boş satırlarıydı — özellikle son sütun.

| Alan | Yazan | Sıfırlayan / sonlandıran | Kilit | `notify_all()`? |
|---|---|---|---|---|
| `run_state` | **yalnız `_set_state_locked()`** | `_work` bitişte | `cond` | **EVET, her geçişte** |
| `resume_requested` | `POST /resume`, `abandon()` | **bekleyen**, `wait_for` döner dönmez, aynı kritik bölümde | `cond` | EVET |
| `version` | `bump()` — durumu değiştiren her yazım | — (monoton) | `cond` | EVET |
| `step_mode` | `POST /step-mode`, `abandon()` | — | `cond` | EVET |
| `abandoned` | `abandon()` | — | `cond` | EVET |
| `thread` | `POST /api/run` | `is_alive()` yanlışa döner | `cond` | HAYIR |
| `output`, `error`, `finished` | boru hattı (`_work`) | — | `cond` | EVET |
| `events` | `on_event` (boru hattı), `restore` (sunucu) | — | **`loop_lock`** | EVET |
| `loop` | `on_loop_ready` (boru hattı) | — | **`loop_lock`** | HAYIR |
| `output_dir`, `video_path` | `POST /api/run`, koşudan **önce** | koşu başına yeni dizin | — (yazma-bir-kez) | HAYIR |
| `frame_size` | ilk `GET /detections` (önbellek) | — | — (idempotent) | HAYIR |
| `archived`, `started_at` | `__init__` | — | — (yazma-bir-kez) | HAYIR |

**`_set_state_locked()` gerçekten tek giriş.** Önceki taslak "`set_state()`
tek giriş" diyordu ama **kendi kodu bunu yalanlıyordu**:
`wait_if_step_mode` `paused`/`running`'i, `abandon` `abandoned`'ı doğrudan
yazıyordu. Yani reklam edilen yapısal garanti yoktu — tam da 4. tur
blocker'ının sınıfı. Şimdi kilidi TUTAN her yol `_set_state_locked()`'tan
geçiyor; `set_state()` yalnız onun kilit alan sarmalayıcısı.

**`loop_lock` düşmüştü ve gerekli.** Bugünkü `Session.lock`
(`console.py:549`) telafi ile canlı döngünün aynı `deferred` listesini
aynı anda boşaltmasını engelliyor (`console.py:767-772`). Yeni `Session`'da
karşılığı yoktu; `POST /gateway/restore` ve §7.3'ün `pending_deferred_ts`'i
ikisi de `loop.deferred`'a iş parçacıkları arasından dokunuyor.

**`intervened`'ı kim yazıyor.** Bugün `_analyse`, `step_mode` KAPALIYKEN
gelen bir olay sinyalinde (`console.py:722`). Yeni yerde `on_event`:
`step_mode` kapalıysa `intervened`, açıksa `wait_if_step_mode` `paused`
yazıyor. Önceki taslakta bu değerin hiçbir yazarı yoktu — telde ölü bir
enum değeri ve kaybolmuş bir yükseltme anı.

## Enum eşleme tablosu

| Teldeki değer | Koddaki kaynak |
|---|---|
| `run_state`: `idle` `running` `paused` `intervened` `done` `failed` `abandoned` | `gozcu/ui/session.py::RunState` — **tek kaynak** |
| `badges.run`: `measured` `degraded` `unmeasured` | `benchmark/kpi.py::run_status` (`MEASURED`/`DEGRADED`/`UNMEASURED` sabitleri) |
| `risk`: `Düşük` `Orta` `Yüksek` `Kritik` | `gozcu/models.py::RiskLevel` |
| `WindowRecord.outcome`: `routed` `forced` `skipped` `deferred` | `gozcu/models.py::WindowRecord` |
| `ActionRecord.approval`: `not_required` `pending` `approved` `rejected` | `gozcu/models.py::ActionRecord` |

Her biri için Görev 3'te bir test var: teldeki değer kümesi koddaki
kaynakla **birebir** eşit.

## Test triyajı — 140 fonksiyon

Sayım birimi **test fonksiyonu**. 140 = konsol 100 + besleme 40.
`pytest --collect-only` 143 topluyor; fark `test_console.py:225`'teki
4'lü `parametrize` (triyajda tek satır).

| Karar | Sayı | Anlamı |
|---|---|---|
| taşı | **64** | İddia aynen geçerli; yalnız import yeni eve dönüyor |
| göç ettir | **39** | Kural aynı, iddia Markdown/satır yerine **veriye** bakıyor |
| yeniden kur | **27** | Değişmez korunuyor, yeni taşıyıcıda kuruluyor |
| **sil** | **10** | Kaybolan şey **Gradio'nun protokolü** |
| | **140** | |

Silinen 10'un hepsi `SCREEN_SLOTS`/`SLOT`/`gr.skip()`/`gr.Tabs`
protokolünü test ediyor — hiçbiri bir alan kuralı taşımıyor. Bu ölçüt
iki testi silme listesinden geri aldı: `test_console.py:370` ("SSE her
zaman tam durum taşır" olarak) ve `:1028` (`LoopEvent → escalated_ids →
kart` zinciri).

#### `tests/test_console.py` — 100

| Satır | Test | Karar | Not |
|---|---|---|---|
| 75 | `audit_rows_are_hidden_from_the_chat_pane` | taşı | visible_dialogue saf; feed.py'de kalıyor |
| 84 | `the_degraded_reply_stays_on_screen` | taşı | visible_dialogue |
| 94 | `the_catch_up_notice_stays_on_screen` | taşı | visible_dialogue |
| 101 | `the_pending_gate_notice_stays_on_screen` | taşı | visible_dialogue |
| 107 | `only_a_leading_audit_prefix_hides_a_row` | taşı | visible_dialogue |
| 117 | `the_status_badge_asks_the_bare_degradation_flag` | göç ettir | status_badges → badges sözlüğü |
| 128 | `a_healthy_run_shows_all_three_badges` | göç ettir | status_badges |
| 137 | `the_memory_badge_reports_the_real_backend` | göç ettir | status_badges |
| 146 | `the_run_status_badge_comes_from_the_kpi_module` | göç ettir | status_badges → badges.run |
| 153 | `an_approved_halt_says_the_line_actually_stopped` | taşı | apply_approval alan mantığı |
| 167 | `an_approved_action_that_did_not_halt_is_not_reported_as_halted` | taşı | apply_approval |
| 176 | `a_rejected_action_says_nothing_was_called` | taşı | apply_approval |
| 183 | `an_unknown_action_is_reported_not_raised` | taşı | apply_approval |
| 190 | `an_already_decided_action_is_reported_not_raised` | taşı | apply_approval |
| 197 | `an_unexpected_state_is_still_shown_to_the_operator` | taşı | apply_approval |
| 204 | `the_bar_is_refreshed_from_the_supervisor_after_every_decision` | taşı | apply_approval |
| 214 | `the_approval_text_names_the_tool_and_disappears_when_empty` | göç ettir | approval_text → pending nesnesi |
| 229 | `every_risk_level_has_its_own_colour` | taşı | risk_color |
| 233 | `the_four_risk_colours_are_distinct` | taşı | RISK_COLORS |
| 239 | `an_unknown_risk_level_does_not_borrow_a_real_colour` | taşı | RISK_COLORS |
| 258 | `the_four_keys_are_rendered_as_json` | göç ettir | payload_json → GET /payload |
| 264 | `no_run_yet_is_said_in_turkish_not_shown_as_empty_json` | göç ettir | payload_json + root_cause |
| 269 | `a_crashed_run_does_not_fabricate_an_empty_root_cause_report` | göç ettir | root_cause_markdown → veri |
| 282 | `a_run_without_a_report_says_so_rather_than_printing_blanks` | göç ettir | root_cause_markdown |
| 289 | `a_real_report_renders_all_five_sections` | göç ettir | root_cause_markdown |
| 303 | `the_handoff_ledger_stamps_video_time` | göç ettir | handoff_rows → GET /handoffs |
| 314 | `the_console_module_imports_cleanly` | yeniden kur | modül temiz import — hedef server.py |
| 318 | `ensure_server_running_explains_missing_mlx_vlm` | taşı | _ensure_server_running server.py'ye taşınıyor |
| 370 | `no_handler_refreshes_only_part_of_the_screen` | yeniden kur | değişmez: SSE HER ZAMAN tam durum taşır |
| 397 | `the_perception_drawing_stays_outside_the_screen_slots` | **sil** | SCREEN_SLOTS protokolü — kavram yok oluyor |
| 409 | `the_refresh_and_blank_screens_have_the_same_shape` | **sil** | _refresh/_blank demet şekli |
| 415 | `cutting_the_link_injects_a_vision_tier_outage` | yeniden kur | POST /gateway/cut |
| 423 | `restoring_the_link_clears_the_outage_and_catches_up` | yeniden kur | POST /gateway/restore |
| 445 | `restoring_without_a_running_loop_says_so` | yeniden kur | POST /gateway/restore, döngü yok |
| 451 | `resume_releases_the_paused_loop` | yeniden kur | POST /resume |
| 460 | `starting_without_a_video_says_so_instead_of_crashing` | yeniden kur | POST /api/run dosyasız |
| 465 | `every_button_handler_survives_a_missing_session` | yeniden kur | her uç oturumsuz çökmüyor |
| 473 | `the_approval_bar_opens_only_while_an_action_is_pending` | yeniden kur | pending yalnız bekleyen aksiyonda dolu |
| 492 | `the_screen_streams_and_the_loop_really_pauses` | yeniden kur | KRİTİK: duraklama gerçekten blokluyor (SSE) |
| 537 | `the_decision_note_reaches_the_screen` | yeniden kur | POST /approve notu |
| 545 | `deciding_with_nothing_pending_does_not_call_the_supervisor` | yeniden kur | POST /approve, bekleyen yok |
| 562 | `empty_ledger_says_so` | göç ettir | tool_rows → GET /actions |
| 565 | `timestamp_is_video_time` | göç ettir | tool_rows |
| 569 | `tool_name_is_shown_verbatim` | göç ettir | tool_rows |
| 574 | `params_are_rendered_readably` | göç ettir | tool_rows |
| 579 | `empty_params_are_a_dash_not_blank` | göç ettir | tool_rows |
| 582 | `result_is_rendered` | göç ettir | tool_rows |
| 586 | `approval_states_are_turkish_and_distinct` | göç ettir | tool_rows |
| 592 | `operator_actor_is_distinguishable_from_agent` | göç ettir | tool_rows |
| 599 | `rows_are_sorted_by_time` | göç ettir | tool_rows |
| 603 | `row_width_matches_headers` | göç ettir | tool_rows başlık genişliği |
| 608 | `no_calls_is_not_an_empty_string` | göç ettir | tool_summary |
| 612 | `counts_distinct_tools_against_the_catalogue` | göç ettir | tool_summary |
| 618 | `counts_total_calls` | göç ettir | tool_summary |
| 622 | `counts_approval_gated_calls` | göç ettir | tool_summary |
| 628 | `catalogue_size_comes_from_the_registry` | göç ettir | tool_summary katalog boyu |
| 634 | `screen_slot_names_match_the_slot_count` | **sil** | SLOT adları/sayısı |
| 640 | `refresh_returns_exactly_the_declared_slots` | **sil** | _refresh yuva sayısı |
| 679 | `card_is_stamped_with_the_event_moment_not_the_window_edge` | taşı | intervention_card |
| 692 | `card_falls_back_to_start_when_there_are_no_beats` | taşı | intervention_card |
| 696 | `card_states_the_realtime_framing` | taşı | intervention_card |
| 701 | `card_shows_what_was_seen` | taşı | intervention_card |
| 705 | `card_shows_what_the_agent_said` | taşı | intervention_card |
| 710 | `card_separates_automatic_calls_from_gated_ones` | taşı | intervention_card |
| 723 | `card_omits_the_gated_row_when_nothing_is_gated` | taşı | intervention_card |
| 728 | `card_shows_the_risk_rationale` | taşı | intervention_card |
| 732 | `card_survives_a_missing_risk_assessment` | taşı | intervention_card |
| 738 | `card_escapes_model_text` | taşı | intervention_card kaçırma — sunucuda kalıyor |
| 744 | `empty_rows_are_a_dash_not_blank` | taşı | intervention_card |
| 750 | `step_mode_is_off_by_default` | taşı | STEP_MODE_DEFAULT sabiti |
| 754 | `no_blocking_when_step_mode_is_off` | yeniden kur | §4.1 Condition+yüklem mekanizmayı yeniden yazıyor |
| 762 | `step_mode_blocks_until_resume` | yeniden kur | §4.1 mekanizma değişti |
| 787 | `the_run_never_blocks_by_default` | yeniden kur | varsayılanda bloklamıyor — SSE üzerinden |
| 816 | `unmeasured_is_never_rendered_as_zero` | göç ettir | kpi_markdown ölçülemedi kuralı |
| 823 | `perception_block_reads_the_bench_file` | göç ettir | perception_markdown |
| 833 | `perception_block_says_so_when_the_file_is_missing` | göç ettir | perception_markdown |
| 838 | `perception_block_survives_a_corrupt_file` | göç ettir | perception_markdown |
| 843 | `kpi_markdown_names_its_three_blocks` | göç ettir | kpi_markdown üç blok |
| 860 | `every_prompt_has_text_and_a_label` | taşı | STRESS_PROMPTS |
| 865 | `context_change_prompt_is_off_topic` | taşı | STRESS_PROMPTS |
| 871 | `false_information_prompt_contradicts_the_observation` | taşı | STRESS_PROMPTS |
| 875 | `pressing_a_button_without_a_session_does_not_crash` | yeniden kur | POST /stress oturumsuz |
| 879 | `an_unknown_key_is_refused_not_sent` | yeniden kur | POST /stress bilinmeyen anahtar |
| 888 | `pressing_a_button_sends_the_canned_text` | yeniden kur | POST /stress metni gönderiyor |
| 897 | `perception_kpis_are_visible_before_any_run` | yeniden kur | GET /kpi koşudan ÖNCE algı bloğunu veriyor |
| 907 | `kpi_numbers_use_turkish_decimal_commas` | göç ettir | Türkçe ondalık virgül — sunucuda biçimleniyor |
| 919 | `hidden_when_step_mode_is_off` | yeniden kur | POST /step-mode |
| 923 | `shown_when_step_mode_is_on` | yeniden kur | POST /step-mode |
| 927 | `turning_it_off_releases_a_waiting_loop` | yeniden kur | POST /step-mode kapatmak bekleyeni serbest bırakıyor |
| 942 | `the_console_has_exactly_two_tabs` | **sil** | gr.Tabs sayısı |
| 954 | `every_slot_has_a_name_and_the_count_matches` | **sil** | SLOT adı/sayı eşleşmesi |
| 963 | `the_blank_screen_fills_every_slot` | **sil** | _blank her yuvayı dolduruyor |
| 969 | `the_refresh_fills_every_slot_and_draws_the_feed` | **sil** | _refresh her yuvayı dolduruyor |
| 978 | `the_feed_slot_is_skipped_when_nothing_changed` | **sil** | gr.skip() numarası |
| 999 | `the_feed_skips_episodes_that_were_in_the_store_before_the_run` | yeniden kur | arşiv epizotları beslemeye girmiyor — Session.archived |
| 1017 | `the_audit_rule_has_exactly_one_home` | taşı | denetim kuralının tek evi — yeni modüle işaret edecek |
| 1028 | `the_streaming_generator_survives_a_skipped_feed_slot` | yeniden kur | KRİTİK: LoopEvent→escalated_ids→kart zinciri |
| 1064 | `the_drawing_button_says_what_is_missing_instead_of_failing` | yeniden kur | POST /annotate koşu yok |
| 1076 | `a_drawing_failure_reaches_the_screen_instead_of_killing_the_run` | yeniden kur | POST /annotate hata |
| 1092 | `a_successful_drawing_returns_a_path_the_player_can_use` | yeniden kur | POST /annotate başarı |

#### `tests/test_feed.py` — 40

| Satır | Test | Karar | Not |
|---|---|---|---|
| 20 | `an_empty_store_says_so_instead_of_drawing_a_box` | göç ettir | `feed_html` iddiası veri/`card` iddiasına dönüyor |
| 25 | `the_feed_follows_write_order_not_timestamp` | taşı | `build_feed` saf veri — dokunulmuyor |
| 36 | `every_entry_names_the_agent_that_produced_it` | taşı | `build_feed` saf veri — dokunulmuyor |
| 63 | `a_handoff_carries_both_ends_so_the_arrow_can_be_drawn` | göç ettir | `feed_html` iddiası veri/`card` iddiasına dönüyor |
| 77 | `the_perception_line_says_what_was_seen_and_what_happened_to_it` | taşı | `build_feed` saf veri — dokunulmuyor |
| 93 | `an_operator_action_is_not_credited_to_an_agent` | taşı | `build_feed` saf veri — dokunulmuyor |
| 100 | `the_approval_decision_appears_where_it_was_decided` | taşı | `build_feed` saf veri — dokunulmuyor |
| 112 | `the_call_line_keeps_the_state_it_had_when_it_was_called` | taşı | `build_feed` saf veri — dokunulmuyor |
| 124 | `a_gated_call_does_not_print_the_same_tool_three_times` | taşı | `build_feed` saf veri — dokunulmuyor |
| 138 | `an_updated_episode_shows_the_summary_it_had_at_the_time` | taşı | `build_feed` saf veri — dokunulmuyor |
| 149 | `an_operator_correction_is_not_dressed_up_as_model_output` | taşı | `build_feed` saf veri — dokunulmuyor |
| 163 | `the_escalated_episode_is_marked_and_the_others_are_not` | taşı | `build_feed` saf veri — dokunulmuyor |
| 180 | `an_escalation_that_merged_into_an_open_episode_is_still_marked` | taşı | `build_feed` saf veri — dokunulmuyor |
| 197 | `the_proactive_mark_comes_from_the_record_not_from_adjacency` | göç ettir | `feed_html` iddiası veri/`card` iddiasına dönüyor |
| 219 | `audit_rows_stay_out_of_the_feed` | taşı | `build_feed` saf veri — dokunulmuyor |
| 231 | `archived_episodes_never_enter_the_feed` | taşı | `build_feed` saf veri — dokunulmuyor |
| 244 | `the_risk_line_carries_its_level_and_proposed_tools` | taşı | `build_feed` saf veri — dokunulmuyor |
| 261 | `the_risk_row_carries_the_assessment_moment_not_the_episode_start` | taşı | `build_feed` saf veri — dokunulmuyor |
| 277 | `the_interpreter_line_carries_its_beats` | taşı | `build_feed` saf veri — dokunulmuyor |
| 289 | `a_journal_row_pointing_at_a_missing_record_is_skipped_not_raised` | taşı | `build_feed` saf veri — dokunulmuyor |
| 302 | `the_html_puts_the_newest_entry_first_in_the_dom` | göç ettir | `feed_html` iddiası veri/`card` iddiasına dönüyor |
| 314 | `the_html_is_deterministic_so_the_skip_can_work` | **sil** | `gr.skip()` determinizm protokolü |
| 323 | `the_operator_is_visually_apart_from_the_supervisor` | taşı | `build_feed` saf veri — dokunulmuyor |
| 335 | `model_text_is_escaped_so_it_cannot_break_the_page` | göç ettir | `feed_html` iddiası veri/`card` iddiasına dönüyor |
| 344 | `an_unknown_risk_level_does_not_borrow_a_real_colour` | taşı | `build_feed` saf veri — dokunulmuyor |
| 352 | `the_intervention_card_is_drawn_inside_the_feed_at_that_moment` | göç ettir | `feed_html` iddiası veri/`card` iddiasına dönüyor |
| 379 | `the_intervention_card_is_stamped_with_the_first_assessment` | taşı | `build_feed` saf veri — dokunulmuyor |
| 399 | `an_episode_nobody_escalated_gets_no_card` | göç ettir | `feed_html` iddiası veri/`card` iddiasına dönüyor |
| 411 | `an_episode_shows_its_own_beats_not_just_the_summary` | taşı | `build_feed` saf veri — dokunulmuyor |
| 428 | `an_episode_entry_does_not_show_beats_learned_later` | taşı | `build_feed` saf veri — dokunulmuyor |
| 445 | `an_episode_with_no_beats_falls_back_to_the_window_edge` | taşı | `build_feed` saf veri — dokunulmuyor |
| 452 | `the_operator_indent_is_not_eaten_by_the_margin_shorthand` | taşı | `build_feed` saf veri — dokunulmuyor |
| 467 | `the_risk_analysts_tool_calls_are_not_credited_to_the_supervisor` | taşı | `build_feed` saf veri — dokunulmuyor |
| 480 | `an_operator_triggered_call_stays_the_operators_whatever_the_caller` | taşı | `build_feed` saf veri — dokunulmuyor |
| 489 | `the_card_quotes_what_was_said_after_the_escalation_not_before` | taşı | `build_feed` saf veri — dokunulmuyor |
| 514 | `the_feed_shows_a_deferred_window_as_its_own_line` | taşı | `build_feed` saf veri — dokunulmuyor |
| 532 | `a_call_lines_detail_shows_the_state_it_was_recorded_with` | taşı | `build_feed` saf veri — dokunulmuyor |
| 549 | `a_successful_call_still_reads_naturally` | taşı | `build_feed` saf veri — dokunulmuyor |
| 559 | `a_merge_is_stamped_when_it_merged_not_when_the_event_began` | taşı | `build_feed` saf veri — dokunulmuyor |
| 579 | `an_episode_with_no_end_still_stamps_something_sensible` | taşı | `build_feed` saf veri — dokunulmuyor |

---

## Görev 1 — `gozcu/ui/session.py`: durum makinesi

**Dosyalar:**
- Oluştur: `gozcu/ui/session.py`
- Oluştur: `tests/test_session.py`

**Arayüzler:**
- Tüketir: `gozcu.store.Store`, `gozcu.gateway.Gateway`,
  `gozcu.agents.supervisor.Supervisor`, `gozcu.run.run_pipeline`
- Üretir:
  - `RunState` — `Literal["idle","running","paused","intervened","done","failed","abandoned"]`
  - `RUN_STATES: tuple[str, ...]` — tel/kod tek kaynağı
  - `Session` — alanlar tablodaki gibi; metotlar:
    - `set_state(state: str) -> None`
    - `bump() -> None` (`version += 1; notify_all()`)
    - `wait_for_version(seen: int, timeout: float) -> bool`
    - `request_resume() -> bool` (yalnız `paused` iken `True`)
    - `wait_if_step_mode() -> None`
    - `set_step_mode(enabled: bool) -> bool`
    - `abandon() -> None`, `finish(error=None) -> None`
    - `note_intervention() -> None`, `pending_deferred_ts() -> set`
    - `elapsed_s() -> float`, `escalated_ids() -> set`

- [ ] **Adım 1: Başarısız testleri yaz**

```python
# tests/test_session.py
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
```

- [ ] **Adım 2: Kırmızı olduğunu gör**

Çalıştır: `.venv/bin/pytest tests/test_session.py -q`
Beklenen: `ModuleNotFoundError: No module named 'gozcu.ui.session'`

- [ ] **Adım 3: `gozcu/ui/session.py`'yi yaz**

```python
"""Bir analiz koşusunun bütün tutamakları ve durum makinesi.

## Neden `Event` değil `Condition`

`threading.Event` ile bekleme deseni şuydu: `step_mode` kontrolü →
`clear()` → `wait()`. Serbest bırakan taraf (terk etme, anahtarı kapatma)
kontrol ile `clear()` arasına düşerse, `set()` bekleyenin KENDİ
`clear()`'ı tarafından siliniyor ve iş parçacığı sonsuza dek bekliyor.
Yüklemli bekleme (`wait_for`) yüklemi yeniden kontrol ettiği için kayıp
uyandırma imkânsız.

## Neden `set_state` tek giriş

`run_state`'i yazan her yol `version`'u artırıp `notify_all()` çağırmak
ZORUNDA. Yükümlülük yazıyla bırakıldığında bir kez unutuldu: koşunun
bitişi hiçbir bekleyeni uyandırmıyordu ve bağlı istemci sonsuza dek
"koşuyor" gösteriyordu. Tek giriş noktası bunu yapısal olarak garanti
ediyor.
"""

import threading
import time
from typing import Literal

from gozcu.agents.supervisor import Supervisor
from gozcu.gateway import Gateway
from gozcu.store import Store

RunState = Literal["idle", "running", "paused", "intervened",
                   "done", "failed", "abandoned"]

#: Teldeki değerlerin TEK kaynağı. Sunucu ve testler buradan okuyor;
#: ikinci bir liste bir gün ayrışır ve arayüz olmayan bir durumu bekler.
RUN_STATES: tuple[str, ...] = ("idle", "running", "paused", "intervened",
                               "done", "failed", "abandoned")

#: Kalp atışı aralığı — SSE bağlantısının kendi zaman aşımı.
HEARTBEAT_S = 1.0


class Session:
    """Tek koşunun durumu. Bütün mutasyon `cond` altında."""

    def __init__(self) -> None:
        self.store = Store()
        self.gw = Gateway(self.store)
        self.nobetci = Supervisor(self.gw, self.store)

        self.cond = threading.Condition()
        #: Telafi ile canlı döngü aynı `deferred` listesine dokunuyor
        #: (bugün `console.py:549`). `cond` DEĞİL: `catch_up()` uzun sürüyor
        #: ve `cond`'u o süre boyunca tutmak bütün SSE bekleyenlerini
        #: kilitlerdi.
        self.loop_lock = threading.Lock()
        self.version = 0
        self.run_state: str = "idle"
        self.resume_requested = False
        self.step_mode = False
        self.abandoned = False

        self.loop = None
        self.thread: threading.Thread | None = None
        self.output = None
        self.error: Exception | None = None
        self.finished = False
        self.events: list = []

        self.output_dir = None
        self.frame_size: tuple[int, int] | None = None
        self.video_path = None

        self.started_at = time.monotonic()
        self.archived = {episode.id for episode in self.store.episodes()}

    # --- bildirim ---------------------------------------------------------

    def bump(self) -> None:
        """Sürümü artırır, bekleyenleri uyandırır. Çağıran `cond`'u TUTUYOR."""
        self.version += 1
        self.cond.notify_all()

    def _set_state_locked(self, state: str) -> None:
        """`run_state`'in TEK yazma yolu. Çağıran `cond`'u TUTUYOR.

        Kilidi tutan her yol buradan geçiyor — `wait_if_step_mode` ve
        `abandon` dahil. Doğrudan atama yapan bir yol kalırsa
        "her geçiş bildirilir" garantisi reklamdan ibaret olur.
        """
        if state not in RUN_STATES:
            raise ValueError(f"bilinmeyen koşu durumu: {state!r}")
        if self.run_state == state:
            return
        self.run_state = state
        self.bump()

    def set_state(self, state: str) -> None:
        """`_set_state_locked`'ın kilit alan sarmalayıcısı."""
        with self.cond:
            self._set_state_locked(state)

    def wait_for_version(self, seen: int, timeout: float = HEARTBEAT_S) -> bool:
        """`version > seen` olana kadar bekler. Zaman aşımında `False`."""
        with self.cond:
            return self.cond.wait_for(lambda: self.version > seen, timeout)

    # --- duraklama --------------------------------------------------------

    def note_intervention(self) -> None:
        """`step_mode` KAPALIYKEN müdahale anı — koşu durmuyor, damgalanıyor."""
        with self.cond:
            if not self.abandoned:
                self._set_state_locked("intervened")

    def wait_if_step_mode(self) -> None:
        """`step_mode` açıkken operatörü bekler.

        Kapalıyken hemen dönüyor ve videonun zaman çizelgesi akmaya devam
        ediyor — bloklama kaldırılmadı, KOŞULA bağlandı.
        """
        with self.cond:
            if not self.step_mode:
                return
            self._set_state_locked("paused")
            self.cond.wait_for(
                lambda: not self.step_mode or self.resume_requested)
            # Jeton tüketimi ile paused'dan çıkış TEK kritik bölüm: ayrılırsa
            # aradan geçen ikinci bir "Devam et" 409'dan geçip jetonu bankaya
            # yatırır ve bir sonraki duraklamayı sessizce atlar.
            self.resume_requested = False
            # `abandoned` KORUNUYOR. Koşulsuz "running" yazmak terk edilmiş
            # bir koşuyu canlı gibi gösterirdi ve `_work` onu `done`'a
            # çevirip çıktısını geçerliymiş gibi sunardı.
            if not self.abandoned:
                self._set_state_locked("running")

    def request_resume(self) -> bool:
        """**Devam et.** Yalnız gerçekten duraklamışken jeton yazıyor."""
        with self.cond:
            if self.run_state != "paused":
                return False
            self.resume_requested = True
            self.bump()
            return True

    def set_step_mode(self, enabled: bool) -> bool:
        """Anahtar koşu SIRASINDA da değişebilir.

        Kapatan kişi o an bekleyen döngüyü serbest bırakmak zorunda, yoksa
        anahtarı kapatmak koşuyu kilitli bırakırdı.
        """
        with self.cond:
            if enabled and self.abandoned:
                return False        # Terk edilmiş koşu bloklamadan akmalı.
            self.step_mode = bool(enabled)
            self.bump()
            return True

    def abandon(self) -> None:
        """Duraklamayı çözer; koşuyu BİTİRMEZ."""
        with self.cond:
            self.abandoned = True
            self.step_mode = False
            self.resume_requested = True
            self._set_state_locked("abandoned")

    def finish(self, error: Exception | None = None) -> None:
        """Boru hattı bitti. Terk edilmiş koşu `done` OLMUYOR."""
        with self.cond:
            self.error = error
            self.finished = True
            if self.abandoned:
                self.output = None      # Çıktısı atılıyor (spec §4).
            else:
                self._set_state_locked("failed" if error else "done")
            self.bump()

    # --- okuma ------------------------------------------------------------

    def is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def elapsed_s(self) -> float:
        return time.monotonic() - self.started_at

    def escalated_ids(self) -> set:
        with self.loop_lock:
            return {event.episode.id for event in self.events
                    if getattr(event, "episode", None) is not None}

    def pending_deferred_ts(self) -> set:
        """Telafi kuyruğunda HÂLÂ bekleyen pencerelerin başlangıçları.

        `catch_up()` telafi ettiği pencerenin kaydına hiçbir şey yazmıyor
        (`loop.py:834`), yani `WindowRecord` "ertelendi" diyebiliyor ama
        "telafi edildi" diyemiyor. Belirsizliği çözen şey bu yüzden kayıt
        değil, canlı döngü.
        """
        with self.loop_lock:
            if self.loop is None:
                return set()
            return {window[0].ts for window in self.loop.deferred if window}
- [ ] **Adım 4: Yeşil olduğunu gör**

Çalıştır: `.venv/bin/pytest tests/test_session.py -q`
Beklenen: 9 passed

- [ ] **Adım 5: Bütün depoyu koştur**

Çalıştır: `.venv/bin/pytest tests/ -q`
Beklenen: mevcut testlerin hepsi hâlâ yeşil (`console.py` daha durmuyor).

- [ ] **Adım 6: Commit**

```bash
git add gozcu/ui/session.py tests/test_session.py
git commit -m "feat(konsol): Session durum makinesi — Condition, tek girişli set_state"
```

---

## Görev 2 — `gozcu/ui/view.py`: veri derleyicileri

Triyaj tablosundaki **39 "göç ettir"** testinin indiği yer. Kural aynı,
çıktı Markdown/satır listesi yerine veri.

**Dosyalar:**
- Oluştur: `gozcu/ui/view.py`
- Oluştur: `tests/test_view.py`
- Değiştir: `tests/test_console.py` — göç eden testler `view`'a taşınıyor

**Arayüzler:**
- Tüketir: `Store`, `Gateway`, `benchmark.kpi`, `gozcu.memory.memory_backend`
- Üretir:
  - `badges(gw, store) -> dict` — `{"gateway": "healthy"|"degraded", "memory": str, "run": str}`
  - `pending_payload(pending) -> dict | None` — `{"action_id", "tool", "params"}`
  - `tool_rows(actions) -> list[dict]`
  - `tool_summary(actions) -> dict`
  - `handoff_rows(handoffs) -> list[dict]`
  - `kpi_payload(store, elapsed_s) -> dict`
  - `perception_payload(path=None) -> dict`
  - `root_cause_payload(output) -> dict | None`
  - `payload_dict(output) -> dict | None`
  - `pct(value) -> str` — `None` ise `KPI_UNMEASURED` **yazar**
  - `apply_approval(nobetci, action_id, approved) -> tuple[str, object]`
    — `console.py:280`'den **kopyalanıyor** (triyajda `taşı`, 6 test)
  - `STRESS_PROMPTS` — `console.py:167`'den kopyalanıyor (3 test)
  - `STEP_MODE_DEFAULT = False` — `console.py:141`'den kopyalanıyor (1 test)

- [ ] **Adım 1: Başarısız testleri yaz**

```python
# tests/test_view.py
from benchmark.kpi import DEGRADED, MEASURED, UNMEASURED
from gozcu.models import RiskLevel
from gozcu.ui import view


def test_unmeasured_is_written_not_hidden():
    """Deponun kuralı: 0 'ölçtük, sıfır çıktı' demek. Ölçülemeyeni
    gizlemek okuyanına o metriğin var olmadığını düşündürür."""
    assert view.pct(None) == view.KPI_UNMEASURED
    assert view.pct(0.0) == "%0,0"


def test_kpi_numbers_use_turkish_decimal_commas():
    """Biçimleme SUNUCUDA — tarayıcıda olsaydı test kapsamı dışına
    düşerdi ve panel iki belgeyi ayrı dillere bölerdi."""
    assert view.pct(0.724) == "%72,4"
    assert "." not in view.pct(0.724)


def test_the_run_badge_uses_only_the_kpi_modules_values():
    assert view.RUN_BADGE_VALUES == (MEASURED, DEGRADED, UNMEASURED)


def test_perception_kpis_are_available_before_any_run():
    """Algı ölçümü koşudan bağımsız — çevrimdışı ölçüldü (şartname §4)."""
    payload = view.perception_payload()
    assert payload is not None
    assert "blocks" in payload


def test_a_crashed_run_does_not_fabricate_an_empty_root_cause_report():
    class _Output:
        detail = None
    assert view.root_cause_payload(_Output()) is None


def test_tool_rows_put_the_outcome_first():
    """Bir aracın çalışmadığını gizleyen şerit, çalıştığını iddia eder."""
    from gozcu.models import ActionRecord
    action = ActionRecord(id=1, ts=12.0, tool_name="site_alarm",
                          params={"zone": "A"},
                          result={"alarm_id": "x", "siren_state": "zone_unresolved"},
                          actor="agent", approval="not_required")
    row = view.tool_rows([action])[0]
    assert list(row["result"])[0] == "siren_state"


def test_the_wire_risk_levels_match_the_schema_exactly():
    """Prompt/şema ayrışması bu depoyu bir kez sessizce öldürdü."""
    import typing
    assert set(view.RISK_LEVELS) == set(typing.get_args(RiskLevel))
```

- [ ] **Adım 2: Kırmızı olduğunu gör**

Çalıştır: `.venv/bin/pytest tests/test_view.py -q`
Beklenen: `ModuleNotFoundError: No module named 'gozcu.ui.view'`

- [ ] **Adım 3: `gozcu/ui/view.py`'yi yaz**

> **KOPYALA, TAŞIMA.** `console.py` Görev 11'e kadar yaşıyor ve
> `_refresh`/`_blank` (`console.py:619-650`) bu fonksiyonların HEPSİNİ
> çağırıyor; ~20 konsol testi de onları Görev 11'e kadar sınıyor. Gövdeyi
> gerçekten taşımak ara görevlerde süiti kırar ve "hepsi yeşil" kapısı
> imkânsız olur. Bu görev `view.py`'ye **yeni, veri döndüren** kardeşler
> yazıyor; `console.py`'deki Markdown sürümleri Görev 11'de,
> `console.py` silinirken ölüyor. Geçici ikizlik bilinçli ve süresi bir
> görev değil, bir plan.

`console.py`'nin `_pct`, `status_badges`, `tool_rows`, `tool_summary`,
`handoff_rows`, `kpi_markdown`, `perception_markdown`,
`root_cause_markdown`, `approval_text`, `payload_json` mantığını
`view.py`'ye kopyala; her birinin **dönüş tipini** dizeden sözlüğe/listeye
çevir. Metin sabitleri
(`KPI_UNMEASURED`, `NO_TOOLS_YET`, `NO_RUN_YET`, `CRASHED_RUN`,
`NO_ROOT_CAUSE`, `HALTED_NOTE` …) **aynen** taşınıyor — Türkçe metin
kuralı ve testleri onlara bakıyor.

`RISK_LEVELS` ve `RUN_BADGE_VALUES` şemadan türetiliyor:

```python
import typing

from benchmark.kpi import DEGRADED, MEASURED, UNMEASURED
from gozcu.models import RiskLevel

#: Şemadan TÜRETİLİYOR, elle yazılmıyor — ikinci bir liste bir gün ayrışır.
RISK_LEVELS: tuple[str, ...] = typing.get_args(RiskLevel)
RUN_BADGE_VALUES: tuple[str, ...] = (MEASURED, DEGRADED, UNMEASURED)


def pct(value) -> str:
    """Oranı yüzdeye çevirir; `None` ise ölçülemediğini YAZAR."""
    if value is None:
        return KPI_UNMEASURED
    return f"%{value * 100:.1f}".replace(".", ",")
```

- [ ] **Adım 4: Yeşil olduğunu gör**

Çalıştır: `.venv/bin/pytest tests/test_view.py -q`

- [ ] **Adım 5: 32 konsol testini göç ettir**

`göç ettir` yazan 39 satırın **32'si `test_console.py`'de, 7'si
`test_feed.py`'de** (satır 20, 63, 197, 302, 335, 352, 399 — hepsi
`feed_html` çağırıyor). Bu adım yalnız konsoldaki 32'yi taşıyor;
`test_feed.py`'nin 7'si Görev 11'de, `feed_html` ölürken dönüşüyor.

Çalıştır: `.venv/bin/pytest tests/test_view.py tests/test_console.py -q`
Beklenen: hepsi yeşil, `test_view.py` = 32 göç + 7 yeni = **39 test**.

- [ ] **Adım 6: Commit**

```bash
git add gozcu/ui/view.py tests/test_view.py tests/test_console.py
git commit -m "feat(konsol): view.py veri derleyicileri; 39 test Markdown'dan veriye göç etti"
```

---

## Görev 3 — `gozcu/ui/server.py`: iskelet ve salt-okunur uçlar

**Dosyalar:**
- Oluştur: `gozcu/ui/server.py`
- Oluştur: `tests/test_server.py`
- Oluştur: `tests/doubles.py` — `StubGateway`, `StubLoop`, `FakeSupervisor`
  (bugün `test_console.py:341-360`'ta; o dosyayla ölmesinler)

**Arayüzler:**
- Tüketir: Görev 1'in `Session`/`RUN_STATES`, Görev 2'nin `view.*`
- Üretir: `app: FastAPI`, `baslat(**launch) -> None`,
  `current_session() -> Session | None`, `_ensure_server_running()`
  (`console.py`'den taşındı)

- [ ] **Adım 1: Başarısız testleri yaz**

```python
# tests/test_server.py
import pytest
from fastapi.testclient import TestClient

from gozcu.ui import server
from gozcu.ui.session import RUN_STATES


@pytest.fixture
def client(monkeypatch):
    """Bu görevin fikstürü — boru hattı sahteleri Görev 4'te EKLENİYOR.

    Modül düzeyinde `client = TestClient(app)` yazılamaz: Görev 4 aynı
    dosyaya bir `client` fikstürü ekliyor ve tanım adı ezer, bu beş test
    sessizce kırılırdı. Tek bir `client` var ve büyüyen o.
    """
    monkeypatch.setattr(server, "_SESSION", None)
    monkeypatch.setattr(server, "_RUN_ID", None)
    with TestClient(server.app) as test_client:
        yield test_client


def test_every_endpoint_survives_a_missing_session(client):
    """`every_button_handler_survives_a_missing_session`'ın HTTP karşılığı:
    oturum yokken hiçbir uç 500 vermiyor."""
    for path in ("/api/status", "/api/run/none/payload", "/api/run/none/kpi",
                 "/api/run/none/handoffs", "/api/run/none/actions",
                 "/api/run/none/windows"):
        response = client.get(path)
        assert response.status_code in (200, 404), path


def test_status_answers_before_any_run(client):
    """`Gateway` oturumla doğuyor; oturum yokken uç modül düzeyi bilgiyi
    döndürüyor — boş bir 500 yerine eksik ama dürüst bir cevap."""
    body = client.get("/api/status").json()
    assert body["model"]
    assert body["gateway"] is None


def test_perception_kpis_are_visible_before_any_run(client):
    body = client.get("/api/run/none/kpi").json()
    assert body["perception"]["blocks"]


def test_the_wire_run_states_come_from_one_source(client):
    body = client.get("/api/meta").json()
    assert tuple(body["run_states"]) == RUN_STATES


def test_the_wire_enums_match_the_schema(client):
    """Enum eşleme tablosunun testi — teldeki küme koddakiyle birebir."""
    import typing

    from gozcu.models import ActionRecord, RiskLevel, WindowRecord
    body = client.get("/api/meta").json()
    assert set(body["risk_levels"]) == set(typing.get_args(RiskLevel))
    assert set(body["window_outcomes"]) == set(
        typing.get_args(WindowRecord.model_fields["outcome"].annotation))
    assert set(body["approval_states"]) == set(
        typing.get_args(ActionRecord.model_fields["approval"].annotation))
```

- [ ] **Adım 2: Kırmızı olduğunu gör**

Çalıştır: `.venv/bin/pytest tests/test_server.py -q`
Beklenen: `ModuleNotFoundError: No module named 'gozcu.ui.server'`
(fikstürün `from gozcu.ui import server` satırı toplama sırasında patlar).

- [ ] **Adım 3: İskeleti yaz**

`app = FastAPI()`; `GET /api/meta` enum kümelerini şemadan türetip
döndürüyor; salt-okunur uçlar `view.*`'i çağırıyor; oturum yoksa
`view.perception_payload()` gibi koşudan bağımsız olanlar yine cevap
veriyor, koşuya bağlı olanlar `404`. `_ensure_server_running`
`console.py`'den **aynen** taşınıyor (silinmiyor — yerel mlx-vlm
sunucusunu o kaldırıyor). Statik dosyalar `gozcu/ui/web/` altından `StaticFiles` ile servis
ediliyor — **dizin bu görevde `.gitkeep` ile oluşturuluyor** (içerik
Görev 6'da gelir). Starlette eksik bir dizine `mount` edilirken **açılışta
hata atıyor**; dizin olmadan Görev 3-5'in hiçbir testi koşmaz.

- [ ] **Adım 4: Yeşil olduğunu gör**

Çalıştır: `.venv/bin/pytest tests/test_server.py -q`

- [ ] **Adım 5: `tests/doubles.py`'yi oluştur**

`test_console.py:341-357`'deki `_StubLoop`/`_StubGateway` ile `:43-58`'deki
`_FakeSupervisor` buraya taşınıyor ve `StubLoop`/`StubGateway`/
`FakeSupervisor` diye dışa veriliyor. **`StubGateway`, `_FakeGateway`'i
genişletiyor:** taban sınıfta `inject_failure` YOK
(`tests/test_run.py:65-115`) ve `/gateway/cut|restore` testleri onu
istiyor; `injections` listesi çağrıları kaydediyor.

`test_console.py` **kendi yerel kopyalarını silip buradan import ediyor**
— iki kopya bir gün ayrışır ve iki dosya aynı ikizi farklı davrandırır.
Görev 11'de o dosya ölürken `doubles.py` ayakta kalıyor.

- [ ] **Adım 6: `_ensure_server_running` testini taşı**

`test_console.py:318` (`ensure_server_running_explains_missing_mlx_vlm`)
`tests/test_server.py`'ye taşınıyor — triyajda `taşı`.

- [ ] **Adım 7: Commit**

```bash
git add gozcu/ui/server.py tests/test_server.py tests/doubles.py tests/test_console.py
git commit -m "feat(konsol): FastAPI iskeleti, salt-okunur uçlar, test ikizleri ve enum eşleme testi"
```

---

## Görev 4 — Koşu yaşam döngüsü ve SSE

Planın kalbi. **27 "yeniden kur" testinin çoğu burada iniyor**, iki
kritik olanı dahil.

**Dosyalar:**
- Değiştir: `gozcu/ui/server.py`
- Değiştir: `tests/test_server.py`

**Arayüzler:**
- Tüketir: `Session`, `run_pipeline`, `apply_approval` (`view`'dan)
- Üretir: `POST /api/run`, `/abandon`, `/resume`, `/approve`, `/say`,
  `/stress/{key}`, `/gateway/cut`, `/gateway/restore`, `/step-mode`,
  `GET /api/run/{id}/events` (SSE)

### Koşu kimliği ve tek oturum

`run_id` **koşu başına `uuid4().hex`**. Sunucu modülünde tek bir
`_SESSION: Session | None` ve onun `run_id`'si duruyor; bir yol
parametresi eşleşmiyorsa `404`. Çok kullanıcılı bir sunucu değil — jüri
önünde tek operatör var ve oturum havuzu uydurma bir gereksinim olurdu.
`current_session(run_id)` eşleşmede oturumu, eşleşmezse `None` döndürüyor.

- [ ] **Adım 0: Görev 3'ün `client` fikstürünü GENİŞLET**

Yeni bir fikstür yazılmıyor — Görev 3'ünkine boru hattı sahteleri, dizin
yaması ve teardown ekleniyor. İkinci bir tanım Görev 3'ün beş testini
sessizce kırardı. Bu blok olmadan aşağıdaki testlerin hiçbiri koşmaz. Gerçek modeller ve
gerçek ffmpeg çağrılmıyor: depoda zaten kullanılan sahteler
(`tests/test_run.py:65` `_FakeGateway`, `:135` `_perception`, `:160`
`_fake_clip`) buraya da alınıyor — `test_console.py:492` bugün tam
olarak böyle koşuyor.

```python
# tests/test_server.py — Görev 3'ün `client` fikstürü GENİŞLETİLMİŞ hâli
import json
import time

import pytest
from fastapi.testclient import TestClient

from gozcu.ui import server, session as session_module
from tests.doubles import StubGateway
from tests.test_run import _fake_clip, _perception


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Ağa çıkmayan, ffmpeg/YOLO koşmayan bir sunucu.

    `_perception` ve `_fake_clip` YEDEK DEĞİL, **yama kurucu**: kendileri
    `monkeypatch.setattr` çağırıyor (`tests/test_run.py:135, 160`) ve
    `run_module`'ün `extract_frames`/`track_video`/`compute_signals`/
    `_clip_for` adlarını değiştiriyorlar. Onları bir şeyin YERİNE koymak
    ilk çağrıda `AttributeError` verir.

    `Gateway` **import yerinde** yamalanıyor (`gozcu.ui.session`), tanım
    yerinde değil: `session.py` `from gozcu.gateway import Gateway`
    yapıyor ve tanım yerini yamalamak onu etkilemez. Uyarlayıcı lambda
    şart — `StubGateway(store)` imzası `_FakeGateway(router=...)`'a
    düşerdi. Bugünkü `test_console.py:503-508` tam olarak bu desen.
    """
    _perception(monkeypatch, tmp_path)
    _fake_clip(monkeypatch, tmp_path)
    # İki ayrı sorun, tek çözüm. (a) `_perception` yalnız `Frame` NESNESİ
    # üretiyor, diske hiçbir şey yazmıyor; `frame_size` ilk kareyi
    # `cv2.imread` ile okuyor (Görev 5). (b) Sunucu `output_dir`'i kendisi
    # seçiyor ve oraya YALNIZ gerçek `extract_frames` yazıyor
    # (`gozcu/frames.py:30`) — sahtelenince o dizin boş kalır ve glob
    # hiçbir şey bulamaz. Bu yüzden sunucunun dizin seçicisi `tmp_path`'e
    # yamalanıyor (yukarıda) ve kareler oraya yazılıyor: `_perception`'ın
    # `Frame.path`'leri de `tmp_path/frame_XXXX.jpg` (`test_run.py:148`).
    _write_frames(tmp_path)
    monkeypatch.setattr(session_module, "Gateway", lambda store: StubGateway())
    # `Supervisor` YAMALANMIYOR — gerçek Nöbetçi sahte ağ geçidi üzerinde
    # koşuyor. `FakeSupervisor`'ın yalnız `approve`/`pending_approval`'ı var
    # (`test_console.py:43-58`); `run_pipeline` her yükseltmede
    # `nobetci.escalate()` çağırıyor (`run.py:230`) ve o çağrı `on_event`'ten
    # ÖNCE geliyor. Eksik metot `run.py:467`'nin geniş `except`'ine düşer,
    # koşu sessizce bozulmuş çıktıya iner, `session.events` boş kalır ve
    # duraklama HİÇ olmaz — yani planın kritik dediği iki test ölür.
    # Bugünkü çalışan desen (`test_console.py:503-508`) de yalnız `Gateway`
    # yamalıyor. `FakeSupervisor` onay testlerinde kullanılıyor, burada değil.
    monkeypatch.setattr(server, "_output_dir_for", lambda run_id: tmp_path)
    monkeypatch.setattr(server, "_SESSION", None)
    monkeypatch.setattr(server, "_RUN_ID", None)
    with TestClient(server.app) as test_client:
        yield test_client
    # Teardown ŞART: duraklamış bir koşu bırakan test, sonraki her
    # `_start_run`'ı 409'a düşürür (§4: iş parçacığı ölene kadar 409).
    live = server._SESSION
    if live is not None and live.is_running():
        live.abandon()
        if live.thread is not None:
            live.thread.join(timeout=5.0)


def _write_frames(tmp_path) -> None:
    import numpy
    import cv2
    for index in range(4):
        cv2.imwrite(str(tmp_path / f"frame_{index:04d}.jpg"),
                    numpy.zeros((360, 640, 3), dtype=numpy.uint8))


def _post_run(client, step_mode=False):
    return client.post("/api/run",
                       files={"video": ("k.mp4", b"\x00" * 32, "video/mp4")},
                       data={"step_mode": str(step_mode).lower()})


def _start_run(client, step_mode=False) -> str:
    response = _post_run(client, step_mode)
    assert response.status_code == 200, response.text
    return response.json()["run_id"]


def _frames(client, run_id, limit=2000):
    """SSE akışındaki `state` çerçevelerini sözlük olarak veriyor.

    Ayrıştırma BURADA — ayrı bir `_parse_sse` yok; kalp atışı satırları
    (`:keepalive`) `data:` ile başlamadığı için kendiliğinden eleniyor.
    """
    with client.stream("GET", f"/api/run/{run_id}/events") as stream:
        for line in stream.iter_lines():
            if not line.startswith("data:"):
                continue
            yield json.loads(line[5:].strip())
            limit -= 1
            if limit <= 0:
                return


def _first_frame(client, run_id) -> dict:
    return next(_frames(client, run_id))


def _wait_for_state(client, run_id, wanted, timeout=20.0) -> dict:
    deadline = time.monotonic() + timeout
    for frame in _frames(client, run_id):
        if frame["run_state"] == wanted:
            return frame
        if time.monotonic() > deadline:
            break
    raise AssertionError(f"{wanted!r} durumuna hiç ulaşılmadı")


def _drain_until_done(client, run_id) -> list:
    last = []
    for frame in _frames(client, run_id):
        last = frame["feed"]
        if frame["run_state"] in ("done", "failed"):
            break
    return last


def _finished_run(client) -> str:
    run_id = _start_run(client, step_mode=False)
    _drain_until_done(client, run_id)
    return run_id


def _raise(error):
    def boom(*args, **kwargs):
        raise error
    return boom
```

> **`tests/doubles.py` Görev 3'te oluşturuluyor.** `StubGateway`
> (`_FakeGateway` + `inject_failure`/`injections` — `_FakeGateway`'de
> `inject_failure` YOK ve `/gateway/cut|restore` testleri onu ister),
> `StubLoop`, `FakeSupervisor`. İlk ikisi bugün
> `test_console.py:341-357`'de, `FakeSupervisor` `:43-58`'de
> yaşıyor ve o dosyayla birlikte ölecekler; ortak eve taşınmazlarsa
> Görev 4'ün yeniden kurduğu 415/423/445 testleri yazılamaz.



- [ ] **Adım 1: Kritik testleri yaz**

```python
def test_the_stream_carries_full_state_and_the_loop_really_pauses(client):
    """KRİTİK — duraklamanın gerçek olduğunun tek kanıtı.
    (`test_console.py:492`'nin yeniden kurulmuş hâli.)"""
    run_id = _start_run(client, step_mode=True)
    states = []
    for frame in _frames(client, run_id):
        states.append(frame["run_state"])
        # Her çerçeve TAM durum taşıyor — kısmi güncelleme yok.
        assert {"feed", "run_state", "badges", "version"} <= set(frame)
        if frame["run_state"] == "paused":
            break
    assert "paused" in states
    # Video gerçekten durdu: bekleyen bir döngü var.
    assert client.get(f"/api/run/{run_id}/payload").status_code == 404
    assert client.post(f"/api/run/{run_id}/resume").status_code == 200


def test_the_finished_run_reaches_a_connected_client(client):
    """4. tur blocker'ı: bitiş geçişi hiçbir bekleyeni uyandırmıyordu ve
    bağlı istemci sonsuza dek 'running' gösteriyordu."""
    run_id = _start_run(client, step_mode=False)
    for frame in _frames(client, run_id):
        if frame["run_state"] in ("done", "failed"):
            return
    raise AssertionError("bitiş durumu akışa hiç düşmedi")


def test_the_escalation_card_reaches_the_stream(client):
    """`LoopEvent → escalated_ids → kart` zincirinin tek uçtan uca kanıtı
    (`test_console.py:1028`'in yeniden kurulmuş hâli). Bu zincir
    bozulursa hiçbir birim testi kırmızıya dönmez."""
    run_id = _start_run(client, step_mode=False)
    cards = _drain_until_done(client, run_id)
    assert any(entry.get("card") for entry in cards)


def test_two_connections_see_the_same_state(client):
    """`queue.Queue` tek tüketiciliydi; iki SSE üreteci onu yarıştırırdı
    ve `done` bir kez tüketilirdi."""
    run_id = _start_run(client, step_mode=False)
    first = _first_frame(client, run_id)
    second = _first_frame(client, run_id)
    assert first["version"] and second["version"]
    assert first["run_state"] == second["run_state"]


def test_a_second_run_is_refused_while_the_thread_is_alive(client):
    """İptal mekanizması yok; iki eşzamanlı koşu gateway kotasında
    yarışır ve ölçümü sessizce bozar."""
    _start_run(client, step_mode=True)
    assert _post_run(client).status_code == 409


def test_resume_is_refused_when_the_run_is_not_paused(client):
    run_id = _start_run(client, step_mode=False)
    assert client.post(f"/api/run/{run_id}/resume").status_code == 409


def test_step_mode_cannot_be_re_armed_on_an_abandoned_run(client):
    run_id = _start_run(client, step_mode=True)
    client.post(f"/api/run/{run_id}/abandon")
    response = client.post(f"/api/run/{run_id}/step-mode",
                           json={"enabled": True})
    assert response.status_code == 409
```

- [ ] **Adım 2: Kırmızı olduğunu gör**

Çalıştır: `.venv/bin/pytest tests/test_server.py -q`
Beklenen: 404/405 — uçlar yok.

- [ ] **Adım 3: Koşu başlatmayı, geri çağrıları ve SSE'yi yaz**

`POST /api/run`: `_SESSION` varsa ve `is_running()` ise **`409`**. Yeni
oturum kuruluyor, `run_id = uuid4().hex`, iş parçacığı başlatılmadan
**önce `session.set_state("running")`** — `idle`'da bırakılırsa ilk SSE
çerçevesi `version = 0` taşır ve
`test_two_connections_see_the_same_state`'in `assert first["version"]`
iddiası falsy değere düşer. Yüklenen dosya kaydediliyor; **`output_dir` koşudan ÖNCE, `_output_dir_for(run_id)`
adlı ayrı bir fonksiyonla seçiliyor** (adı olması şart: testler dizini
kendi `tmp_path`'lerine yamalıyor) (koşu başına
yeni dizin — `extract_frames` eskinin karelerini siliyor) ki kare boyutu
koşu sürerken okunabilsin.

```python
def _on_loop_ready(session: Session):
    def handler(loop) -> None:
        with session.loop_lock:
            session.loop = loop
    return handler


def _on_event(session: Session):
    """Boru hattı iş parçacığında, olayın TAM ANINDA çağrılıyor."""
    def handler(event) -> None:
        with session.loop_lock:
            session.events.append(event)
        if session.step_mode:
            # Burada bloklanıyor: videonun zaman çizelgesi gerçekten duruyor.
            session.wait_if_step_mode()
        else:
            # Kapalıyken koşu sürüyor, an damgalanıyor (25 Ağustos kararı).
            session.note_intervention()
    return handler


def _work(session: Session, video_path) -> None:
    try:
        session.output, _ = run_pipeline(
            video_path, store=session.store, gw=session.gw,
            nobetci=session.nobetci, output_dir=session.output_dir,
            on_event=_on_event(session), on_loop_ready=_on_loop_ready(session))
    except Exception as error:      # noqa: BLE001 — ekranda görünmeli
        session.finish(error)
    else:
        session.finish()            # Terk edilmişse `done` YAZMIYOR.
```

`_snapshot` telin tamamı — SSE'nin gövdesi bu:

```python
def _snapshot(session: Session) -> dict:
    """Tam durum. Delta yok: yeniden bağlanma bedavaya çözülüyor."""
    pending = session.nobetci.pending_approval()
    return {
        "version": session.version,
        "run_state": session.run_state,
        "feed": [entry.model_dump() for entry in build_feed(
            session.store, session.escalated_ids(), session.archived)],
        "pending": view.pending_payload(pending),
        "badges": view.badges(session.gw, session.store),
        "processed_until_s": _processed_until_s(session),
        "pending_deferred_ts": sorted(session.pending_deferred_ts()),
        "elapsed_s": session.elapsed_s(),
    }


def _processed_until_s(session: Session) -> float:
    """EN YENİ kayıt hariç en büyük `end_ts`; koşu bitince hepsi.

    Kayıt pencere İŞLENMEDEN yazılıyor (`loop.py:781`), yani en yeni kayıt
    işlenmekte olan penceredir. Onu dışlamak doğru bir ALT sınır veriyor —
    sınırı abartmak, henüz karar verilmemiş bir saniyeyi "karar verildi,
    olay yok" diye göstermek olurdu.

    `set_window_outcome`'a bağlanamaz: iki çağrı yeri de `"deferred"`
    yazıyor (`loop.py:797, 813`), sağlıklı pencere akıbetini `save_window`
    anında alıyor ve bir daha güncellenmiyor — o mekanizmayla sınır
    sağlıklı koşuda sonsuza dek 0'da kalırdı.
    """
    records = session.store.window_records()
    if not records:
        return 0.0
    if session.run_state in ("done", "failed"):
        return max(record.end_ts for record in records)
    if len(records) == 1:
        return 0.0
    return max(record.end_ts for record in records[:-1])
```

SSE üreteci:

```python
async def _stream(session: Session):
    # Bağlanır bağlanmaz tam durum: koşusu bitmiş bir oturumda `version`
    # bir daha hiç artmaz ve istemci sonsuza dek boş beklerdi.
    yield {"event": "state", "data": json.dumps(_snapshot(session))}
    seen = session.version
    while True:
        changed = await anyio.to_thread.run_sync(
            session.wait_for_version, seen, HEARTBEAT_S)
        if changed:
            seen = session.version
            yield {"event": "state", "data": json.dumps(_snapshot(session))}
        else:
            # Kalp atışı DURUM TAŞIMIYOR — yalnız bağlantıyı canlı tutuyor.
            yield {"comment": "keepalive"}
```

Komut uçları `Session` metotlarına ince sarmalayıcılar:
`/resume` → `request_resume()`, `False` ise `409`.
`/step-mode` → `set_step_mode()`, `False` ise `409`.
`/abandon` → `abandon()`. `/approve` → `view.apply_approval()`.
`/say` → `nobetci.talk()`. `/stress/{key}` → `view.STRESS_PROMPTS`,
bilinmeyen anahtar `400`. `/gateway/cut` → `gw.inject_failure({"vision"})`.
`/gateway/restore` → `inject_failure(set())` + `loop_lock` altında
`catch_up()` (bugünkü `console.py:767-772` ile aynı korumada).

- [ ] **Adım 4: Yeşil olduğunu gör**

Çalıştır: `.venv/bin/pytest tests/test_server.py -q`

- [ ] **Adım 5: Kalan "yeniden kur" testlerini kur**

Triyaj tablosunda `yeniden kur` yazan satırlardan Görev 4'e ait olanlar:
`370, 415, 423, 445, 451, 460, 465, 473, 492, 537, 545, 754, 762, 787,
875, 879, 888, 919, 923, 927, 999, 1028` — **22 satır**. Kalan 5'i:
`314` Görev 3'te (modül temiz import), `897` Görev 3'te (koşudan önce
KPI), `1064/1076/1092` Görev 5'te (`/annotate`). 22 + 2 + 3 = 27.

- [ ] **Adım 6: Commit**

```bash
git add gozcu/ui/server.py tests/test_server.py tests/test_console.py
git commit -m "feat(konsol): koşu yaşam döngüsü ve SSE — duraklama gerçek, bitiş bildiriliyor"
```

---

## Görev 5 — Video servisi, tespitler, kare boyutu ve açıklamalı kayıt

**Dosyalar:** `gozcu/ui/server.py`, `tests/test_server.py`

**Arayüzler:** `GET /api/run/{id}/video` (`Range` destekli),
`GET /api/run/{id}/detections?from=&to=` → `{"frame_size": [w, h], "items": [...]}`,
`POST /api/run/{id}/annotate` → `{"path": str}` | `409` | `404`

- [ ] **Adım 1: Testleri yaz**

```python
def test_detections_report_the_inference_frame_size(client):
    """Kutular 0-1 normalize DEĞİL: tam sayı piksel ve uzay orijinal
    video değil, FRAME_WIDTH'e (896) ölçeklenmiş çıkarım karesi.
    Tarayıcı ölçeği tahmin etmemeli."""
    run_id = _finished_run(client)
    body = client.get(f"/api/run/{run_id}/detections?from=0&to=10").json()
    width, height = body["frame_size"]
    assert width > 0 and height > 0
    for item in body["items"]:
        x1, y1, x2, y2 = item["box"]
        assert 0 <= x1 <= width and 0 <= x2 <= width
        assert 0 <= y1 <= height and 0 <= y2 <= height


def test_the_frame_size_is_available_while_the_run_is_still_going(client):
    """`Session.frames_dir` koşu boyunca None'dı — demet açması
    `run_pipeline` BİTTİKTEN sonra çalışıyor. Sunucu `output_dir`'i
    kendisi seçtiği için yol ilk saniyeden itibaren biliniyor."""
    run_id = _start_run(client, step_mode=True)
    _wait_for_state(client, run_id, "paused")
    body = client.get(f"/api/run/{run_id}/detections?from=0&to=5").json()
    assert body["frame_size"][0] > 0


def test_the_video_is_served_with_range_support(client):
    run_id = _finished_run(client)
    response = client.get(f"/api/run/{run_id}/video",
                          headers={"Range": "bytes=0-1023"})
    assert response.status_code == 206
    assert response.headers["accept-ranges"] == "bytes"
```

- [ ] **Adım 2: Kırmızı olduğunu gör** — `.venv/bin/pytest tests/test_server.py -k detections -q`

- [ ] **Adım 3: Uçları yaz**

`frame_size` `session.output_dir`'deki ilk `frame_*.jpg`'den bir kez
okunup `session.frame_size`'a önbellekleniyor.

`Range` desteği `FileResponse`'a bırakılmıyor — sürüme göre değişiyor.
Uç `Range` başlığını kendisi ayrıştırıp `206` ile
`content-range`/`accept-ranges` yazıyor; başlık yoksa `200` ve tam gövde.
Aranabilirlik buna bağlı: operatör geri saramazsa zaman çizelgesine
tıklamak çalışmaz.

- [ ] **Adım 4: Yeşil olduğunu gör** — `.venv/bin/pytest tests/test_server.py -q`

- [ ] **Adım 5: `POST /annotate`'i yaz — triyajın üç testi buraya iniyor**

`test_console.py:1064, 1076, 1092` (`yeniden kur`). Açıklamalı kayıt
**istek üzerine** üretiliyor, koşuyla birlikte değil — `annotate_run`
(`gozcu/annotate.py:129`) bütün kareleri yeniden çiziyor ve bir kalp
atışına sığmaz. (`test_console.py:397`'nin silinmesi tam da bu yüzden
savunulabilir: kaybolan şey "çizim yuvaların dışında" protokolüydü,
"çizim istek üzerine" kuralı değil — ve o kural burada yaşıyor.)

```python
# Dosyanın başına: `from gozcu.annotate import AnnotateError`
# (`gozcu/annotate.py:62`; `annotate_run` `:129`). `_raise` koşum bloğunda.
def test_annotate_says_what_is_missing_instead_of_failing(client):
    """Koşu yokken uydurma bir yol dönmüyor."""
    assert client.post("/api/run/none/annotate").status_code == 404


def test_an_annotate_failure_reaches_the_screen_instead_of_killing_the_run(
        client, monkeypatch):
    run_id = _finished_run(client)
    monkeypatch.setattr("gozcu.ui.server.annotate_run",
                        _raise(AnnotateError("ffmpeg yok")))
    response = client.post(f"/api/run/{run_id}/annotate")
    assert response.status_code == 409
    assert "ffmpeg" in response.json()["detail"]


def test_a_successful_annotate_returns_a_path_the_player_can_use(client):
    run_id = _finished_run(client)
    body = client.post(f"/api/run/{run_id}/annotate").json()
    assert body["path"].endswith(".mp4")
    assert client.get(body["path"]).status_code == 200
```

Uç `session.output_dir`'i `annotate_run`'a veriyor (Görev 4'te sunucu onu
kendisi seçtiği için koşu bitmiş olmasa da biliniyor) ve üretilen dosyayı
`GET /api/run/{id}/annotated` üzerinden servis ediyor.

- [ ] **Adım 6: Yeşil olduğunu gör** — `.venv/bin/pytest tests/test_server.py -q`

- [ ] **Adım 7: Commit**

```bash
git add gozcu/ui/server.py tests/test_server.py tests/test_console.py
git commit -m "feat(konsol): video servisi, tespit ucu, kare boyutu ve istek üzerine açıklamalı kayıt"
```

---

## Görev 6 — Statik kabuk ve Operasyon görünümü

**Dosyalar:** `gozcu/ui/web/index.html`, `css/styles.css`,
`js/sse.js`, `js/feed.js`

Tarayıcı tarafında otomatik test **yok** — bu bilinçli bir kapsam boşluğu.
O yüzden **karar veren hiçbir şey tarayıcıya inmiyor:** renk sunucudan
(`view` `risk_color`'ı veriyle gönderiyor), ondalık biçimi sunucudan
(`view.pct`), risk seviyesi sunucudan. Tarayıcıda kalan yalnız çizim,
`fetch` ve ölçek aritmetiği.

- [ ] **Adım 1: `index.html` — üç görünümün iskeleti**

Üst bar (marka, modül anahtarı `1`/`2`/`3`, durum rozetleri, JSON düğmesi),
`#viewOps` / `#viewBench` / `#viewTrace`. Video DOM'da kalıyor; sekme
değişince oynatma kesilmiyor.

- [ ] **Adım 2: `styles.css` — tema**

Koyu tema, `--radius`, `--panel`, `--border` gibi belirteçler. **Risk
rengi CSS'te sabit DEĞİL** — sunucudan gelen değer satır içi uygulanıyor.
Harici font yok; sistem yığını.

- [ ] **Adım 3: `sse.js` — bağlantı ve artımlı çizim**

```js
// Tel tam durum taşıyor, çizim artımlı: gördüğümüz en yüksek `seq`'i
// tutup yalnız yenileri DOM'a ekliyoruz. Kaydırma konumu korunuyor.
let lastSeq = -1;
const source = new EventSource(`/api/run/${runId}/events`);
source.addEventListener("state", (message) => {
  const state = JSON.parse(message.data);
  for (const entry of state.feed) {
    if (entry.seq > lastSeq) { appendEntry(entry); lastSeq = entry.seq; }
  }
  renderState(state);   // DURAKLADI bandı, rozetler, bekleyen onay
});
```

- [ ] **Adım 4: DURAKLADI bandı**

`run_state === "paused"` iken ekranın üstünde bant + **Devam et**, ve
oynatıcı duraklıyor — duraklama iddiası ekranda görünmezse yoktur.
PoC'de böyle bir durum yok.

- [ ] **Adım 5: Karar destek paneli — risk göstergesi DÖRT kademeli**

`RiskLevel` dört değerli (`models.py:11`); PoC'nin göstergesi üç kademeli
ve `Kritik`'in yeri yok. Gösterge dörde genişliyor ve **rengi sunucudan
gelen değerden** alıyor (`view` `risk_color`'ı veriyle gönderiyor);
CSS'te risk rengi sabiti yok. İkinci bir renk tablosu bir gün ayrışır ve
iki ekran aynı riski iki renkle gösterir.

- [ ] **Adım 6: Olay günlüğü — filtre, arama ve zamana atlama**

`Tümü` / `Önemli` / `Kritik` çipleri, serbest metin araması, ve olaya
tıklayınca videonun o saniyeye atlaması (spec §8.1). Gradio'da hiçbiri
yoktu.

- [ ] **Adım 7: Devre dışı RTSP kartı**

`Canlı Sisteme Bağlan` kartı ekranda ama **devre dışı**, üzerinde
*"kapsam dışı — bu sürüm dosyadan çalışır"*. `run_pipeline` dosya yolu
alıyor. Not "final sürümde" **DEMİYOR**: tutulacağı belli olmayan bir
vaat, deponun dürüstlük kuralının ihlali olurdu (spec §10).

- [ ] **Adım 8: Elle doğrula**

Çalıştır: `uv run --env-file .env python app.py`, bir kayıt yükle,
`Adım adım` açık koştur. Duraklamayı gör, **Devam et**'e bas, akışın
sürdüğünü gör.

- [ ] **Adım 9: Commit**

```bash
git add gozcu/ui/web
git commit -m "feat(konsol): statik kabuk, SSE istemcisi ve Operasyon görünümü"
```

---

## Görev 7 — Kutu katmanı, zaman çizelgesi ve belirsizlik

**Dosyalar:** `gozcu/ui/web/js/player.js`

- [ ] **Adım 1: İki ölçekli kutu çevirisi**

```js
// Kutular çıkarım karesi uzayında PİKSEL (896 genişlik), 0-1 değil.
// object-fit: contain yüzünden videonun gerçekten kapladığı alan
// hesaplanıp ölçekleniyor — yoksa her en-boy oranında kayar.
function place(box, frameSize, video) {
  const [fw, fh] = frameSize;
  const scale = Math.min(video.clientWidth / video.videoWidth,
                         video.clientHeight / video.videoHeight);
  const shownW = video.videoWidth * scale;
  const shownH = video.videoHeight * scale;
  const offsetX = (video.clientWidth - shownW) / 2;
  const offsetY = (video.clientHeight - shownH) / 2;
  return {
    left: offsetX + (box[0] / fw) * shownW,
    top: offsetY + (box[1] / fh) * shownH,
    width: ((box[2] - box[0]) / fw) * shownW,
    height: ((box[3] - box[1]) / fh) * shownH,
  };
}
```

- [ ] **Adım 2: Zaman çizelgesi işaretçileri**

`Episode.start_ts` ve `EventBeat.ts`'ten; tıklayınca video o saniyeye
atlıyor.

- [ ] **Adım 3: Belirsizlik çizimi**

İki ayrı kural, spec §7.3:

1. **Sınırın ötesi** (`t > processed_until_s`): kutular **görünür**
   (algı bütün videoyu koşu başlamadan tarıyor), ama olay/risk
   göstergeleri "henüz karar verilmedi" — boş değil, belirsiz.
2. **Sınırın içindeki `deferred` pencereler:** kayıt "ertelendi" diyebiliyor
   ama `catch_up` kayda hiçbir şey yazmadığı için "telafi edildi"
   diyemiyor (`loop.py:834`). Bu yüzden belirsizlik **canlı döngüden**
   çözülüyor: kayıt ancak `loop.deferred`'da HÂLÂ bekliyorsa belirsiz
   çiziliyor. Küme SSE durumunda `pending_deferred_ts` olarak **Görev
   4'te zaten gönderiliyor** (`Session.pending_deferred_ts`,
   `_snapshot`); bu görev yalnız onu çiziyor — sunucuda iş yok.

- [ ] **Adım 4: Elle doğrula**

Koştur, **Bağlantıyı kes** → ertelenen saniyelerin belirsiz çizildiğini
gör → **Bağlantıyı geri ver** → telafi sonrası belirsizliğin
**kalktığını** gör. Bu demo beat 6.

- [ ] **Adım 5: Commit**

```bash
git add gozcu/ui/web/js/player.js
git commit -m "feat(konsol): kutu katmanı, zaman çizelgesi ve belirsiz bölge çizimi"
```

---

## Görev 8 — Şeffaflık görünümü

**Dosyalar:** `gozcu/ui/web/js/trace.js`

En yüksek sadakatli sayfa; verisi zaten var.

- [ ] **Adım 1: Devir defteri** — `Handoff{source_agent, target_agent, reason, confidence}`; `perception → router → interpreter → synthesizer → risk_analyst → supervisor` akış diyagramı.
- [ ] **Adım 2: Araç çağrı günlüğü** — `caller` (hangi ajan) ile `actor` (insan mı makine mi) **ayrı sütun**; `OUTCOME_KEYS` sırası korunuyor.
- [ ] **Adım 3: Pencere defteri** — `WindowRecord.outcome`'un dört dalı ayrı ayrı; "bakılmadı" ile "bakıldı, bir şey yoktu" ayrı kelimeler.
- [ ] **Adım 4: Elle doğrula** — bir koşu sonrası üç panelin de dolduğunu gör.
- [ ] **Adım 5: Commit**

```bash
git add gozcu/ui/web/js/trace.js
git commit -m "feat(konsol): Şeffaflık görünümü — devir zinciri, araç günlüğü, pencere defteri"
```

---

## Görev 9 — Performans görünümü

**Dosyalar:** `gozcu/ui/web/js/bench.js`

- [ ] **Adım 1: Altı KPI** — `collect`'ten (`decision_distribution`, `vlm_trigger_rate`, `vision_tokens`, `correction_propagation`, `timestamp_drift_s`, `turkish_output_rate`). PoC'nin kare/sn, VRAM, GPU kartları **yok**; bu sistem onları ölçmüyor.
- [ ] **Adım 2: Ölçülemeyen KPI "ölçülemedi" YAZIYOR**, gizlenmiyor — `view.pct` zaten `KPI_UNMEASURED` döndürüyor.
- [ ] **Adım 3: Algı bloğu koşudan önce de görünüyor.**
- [ ] **Adım 4: Bozulmuş koşu ayrı kovada** — `badges.run` `degraded` iken KPI'lar gizlenmiyor, damgalanıyor. Gizlemek kesinti hikâyesini saklardı, ki o hikâye demo beat 6.
- [ ] **Adım 5: Commit**

```bash
git add gozcu/ui/web/js/bench.js
git commit -m "feat(konsol): Performans görünümü — gerçek KPI'lar, ölçülemeyen gizlenmiyor"
```

---

## Görev 10 — Bas-konuş (STT)

**Dosyalar:** `gozcu/ui/server.py`, `gozcu/ui/web/js/app.js`, `tests/test_server.py`

- [ ] **Adım 1: Testi yaz**

```python
def test_stt_returns_501_when_faster_whisper_is_absent(client, monkeypatch):
    """Örnek transkript DÖNMÜYOR. Bu depo uydurulmuş çıktıyı ölçülmüş
    gibi göstermeme kuralını başka her katmanda uyguluyor."""
    monkeypatch.setattr("gozcu.ui.server._whisper", None)
    response = client.post("/api/stt", files={"audio": ("a.webm", b"", "audio/webm")})
    assert response.status_code == 501
    assert "demo" not in response.text
```

- [ ] **Adım 2: Kırmızı olduğunu gör** — `.venv/bin/pytest tests/test_server.py -k stt -q`
- [ ] **Adım 3: Ucu yaz** — `faster-whisper` **yerel**; yoksa `501`.
- [ ] **Adım 4: Yeşil olduğunu gör**
- [ ] **Adım 5: Tarayıcı tarafı** — mikrofon basılı tutuluyor, bırakılınca gönderiliyor, dönen metin sohbet kutusuna **yazılıyor, gönderilmiyor**: operatör göndermeden önce görüyor. Yanlış duyulmuş bir komut geri alınamaz. `501` ise düğme devre dışı çiziliyor.
- [ ] **Adım 6: Commit**

```bash
git add gozcu/ui/server.py gozcu/ui/web/js/app.js tests/test_server.py
git commit -m "feat(konsol): yerel bas-konuş; kurulu değilse 501, uydurma transkript yok"
```

---

## Görev 11 — Gradio'yu emekliye ayır

**Dosyalar:** `gozcu/ui/console.py` (sil), `app.py`, `pyproject.toml`,
`tests/test_console.py` (sil), `tests/test_feed.py`, `README.md`,
`.claude/launch.json`, `docs/tasks/21-web-konsolu.md` (yeni)

- [ ] **Adım 1: Kalan "taşı" testlerini yeni eve bağla**

Triyajda `taşı` olan 64 testin import'u `gozcu.ui.console`'dan
`gozcu.ui.feed` / `gozcu.ui.view` / `gozcu.ui.session`'a dönüyor.
`test_console.py`'de kalan içerik `test_view.py`, `test_session.py`,
`test_server.py`, `test_feed.py` arasında dağıtılıyor.

- [ ] **Adım 2: 10 testi sil**

`test_console.py:397, 409, 634, 640, 942, 954, 963, 969, 978` ve
`test_feed.py:314`. Her biri `SCREEN_SLOTS`/`SLOT`/`gr.skip()`/`gr.Tabs`
protokolünü test ediyor; hiçbiri bir alan kuralı taşımıyor.

- [ ] **Adım 3: `console.py`'yi ve `test_console.py`'yi sil**

```bash
git rm gozcu/ui/console.py tests/test_console.py
```

- [ ] **Adım 4: `app.py` ve `pyproject.toml`**

`app.py` → `from gozcu.ui.server import baslat`.
`pyproject.toml`: `gradio>=6.0` **düşüyor**; `fastapi`, `uvicorn`,
`sse-starlette`, `python-multipart` ana bağımlılığa **giriyor**
(bugün gradio/mlx-vlm üzerinden transitif geliyorlar ve `sse-starlette`
üretimde hiç yok — `litellm[proxy] → mcp` zinciriyle dev ekstrasından
düşmüş). `[project.optional-dependencies]` altına
`stt = ["faster-whisper"]`. `psutil` **eklenmiyor** — depoda sıfır çağrı
yeri var.

- [ ] **Adım 5: Temiz makinede doğrula**

```bash
uv sync --extra dev && .venv/bin/python -c "import gozcu.ui.server"
```

- [ ] **Adım 6: Bütün kapıyı koştur**

```bash
.venv/bin/pytest tests/ -q && uv run python scripts/check-tasks.py
```

Beklenen: hepsi yeşil, `check-tasks` temiz. Toplam test sayısı 130
(140 − 10 silinen) + yeni sunucu/oturum testleri.

- [ ] **Adım 7: Görev dosyasını ve karar günlüğünü yaz**

`docs/tasks/21-web-konsolu.md` — tamamlanma bandı, kabul kutuları,
"Tamamlanma notları (gelecek görevleri bağlayan)".
`docs/tasks/README.md` — `Durum` hücresi.
`docs/05-decisions/decision-log.md` — Gradio'nun neden kalktığı, beş kör
inceleme turunun ne bulduğu, `Session` durum tablosunun neden var olduğu.
`README.md` — çalıştırma adımları ve bağımlılık listesi.
`.claude/launch.json` — port ve komut.

- [ ] **Adım 8: Commit**

```bash
git add -A -- gozcu app.py pyproject.toml tests docs README.md .claude/launch.json
git commit -m "feat(konsol)!: Gradio konsolu emekliye ayrıldı, web konsolu devraldı"
```

---

## Öz-inceleme kaydı

- **Spec kapsaması:** §2 → Görev 1-2, §4/§4.1 → Görev 1+4, §5 → Görev 3-5,
  §6 → Görev 4, §7 → Görev 5+7, §8.1 → Görev 6-7, §8.2 → Görev 8,
  §8.3 → Görev 9, §9 → Görev 10, §10 → Görev 6 (devre dışı RTSP kartı),
  §11 → Görev 11, §12 → her görevin test adımları.
- **Yer tutucu taraması:** yok.
- **Tip tutarlılığı:** `Session.set_state` / `request_resume` /
  `set_step_mode` / `wait_for_version` imzaları Görev 1'de tanımlanıp
  Görev 4'te aynen çağrılıyor. `view.*` dönüş tipleri Görev 2'de
  tanımlanıp Görev 3-5'te tüketiliyor. `frame_size` Görev 5'te üretilip
  Görev 7'de tüketiliyor.
- **Bağlanan üç tablo:** test triyajı (140 satır, yukarıda),
  `Session` durum tablosu, enum eşlemesi — üçü de bu belgede **var**,
  plana ertelenmiş bir sayım yok.
