# Test Video Korpusu — Katalog

32 kaynak video + 159 kesit (127 kullanilabilir, 32 elenip `clips/_elenen/` altina alindi). `catalog.py` uretir, elle duzenlenmez — etiketler `labels.tsv`'de.

## Kaynak videolar

| Kategori | Dosya | Süre | Çöz. | Boyut | Çekim tipi | Amaç |
|---|---|---|---|---|---|---|
| askeri | `military--MImbyEHJTkM.mp4` | 1:35 | 720p | 25.3 MB | montaj | Askeri operasyon |
| askeri | `military--hE14s_Z-1-Q.mp4` | 5:53 | 720p | 52.5 MB | derleme | Askeri operasyon |
| askeri-playlist | `pl1-01--B5xphv6lYkw.mp4` | 3:44 | 360p | 8.5 MB | derleme |  |
| askeri-playlist | `pl1-02--GCEhVKADlQ8.mp4` | 0:52 | 720p | 3.3 MB | montaj |  |
| askeri-playlist | `pl1-04--V7yXO_Nd5NI.mp4` | 3:35 | 720p | 16.1 MB | derleme |  |
| askeri-playlist | `pl1-05--6wLrSZyeha8.mp4` | 0:56 | 352p | 2.1 MB | derleme |  |
| askeri-playlist | `pl1-07--tv3aApzNPIw.mp4` | 1:37 | 352p | 2.9 MB | surekli |  |
| askeri-playlist | `pl1-08--3ycb4uUfu_E.mp4` | 0:31 | 360p | 0.5 MB | surekli |  |
| askeri-playlist | `pl1-09--IEsmSX019j4.mp4` | 3:37 | 360p | 10.1 MB | derleme |  |
| askeri-playlist | `pl1-10--FwJ9taZ3Ayo.mp4` | 0:46 | 702p | 3.9 MB | surekli |  |
| askeri-playlist | `pl2-02--O2A_KBTxB00.mp4` | 15:20 | 720p | 113.9 MB | derleme |  |
| askeri-playlist | `pl2-03--VwTt2FhYm4w.mp4` | 3:53 | 1080p | 42.6 MB | surekli |  |
| askeri-playlist | `pl2-07--opcF_sDwI1E.mp4` | 7:31 | 720p | 46.3 MB | surekli |  |
| askeri-playlist | `pl2-08--Rur_BrM8yXU.mp4` | 3:43 | 1080p | 48.6 MB | derleme |  |
| askeri-playlist | `pl2-09--Us192rQ_5Ec.mp4` | 5:09 | 1080p | 64.0 MB | surekli |  |
| fabrika | `factory-accidents--UuNsheZUgtE.mp4` | 0:17 | 1080p | 3.2 MB | surekli | Fabrika genel kaza anlari (muhtemelen derleme) |
| forklift | `forklift-accident--qOPnf-YRuk8.mp4` | 0:52 | 640p | 8.5 MB | surekli | Forklift kaza ani, kisa |
| forklift | `forklift-cause--6iCOp5MzXE4.mp4` | 0:59 | 1080p | 19.4 MB | surekli | Kaza ani + sebep algilama |
| forklift | `forklift-cause--7491923795838553366.mp4` | 0:23 | 1024p | 1.0 MB | surekli | Kaza ani + sebep algilama (TikTok) |
| forklift | `forklift-cause--P2X2Do5m0hY.mp4` | 2:01 | 1080p | 19.9 MB | surekli | Kaza ani + sebep algilama |
| forklift | `forklift-cause--Spig3ulTqxw.mp4` | 0:47 | 1080p | 24.7 MB | surekli | Kaza ani + sebep algilama |
| forklift | `forklift-cause--V8ZmOgMlyRE.mp4` | 1:38 | 348p | 3.0 MB | surekli | Kaza ani + sebep algilama |
| forklift | `forklift-compilation--N9bG-sOU6LE.mp4` | 5:52 | 620p | 32.9 MB | derleme | DERLEME - kisa forklift kazalari |
| forklift | `forklift-normal--2gL1vMvYQQQ.mp4` | 9:20 | 1080p | 240.3 MB | surekli | Fabrika calisma kaydi, kaza yok (surec takip) |
| forklift | `forklift-normal--BBcLqG3OYSA.mp4` | 5:42 | 1080p | 82.9 MB | surekli | Fabrika calisma kaydi, kaza yok (surec takip) |
| karisik | `multi-event--OlRDWS2E0EY.mp4` | 3:07 | 720p | 30.2 MB | surekli | Coklu algilama: her yerde farkli seyler, buyuk olay yok |
| sentetik | `synthetic-bodycam--KVkPToQGVAQ.mp4` | 3:32 | 1080p | 87.4 MB | derleme | Bodycam oyunu - sentetik uretim kaynagi |
| sentetik | `synthetic-bodycam--_NoifbuniNM.mp4` | 0:18 | 1080p | 1.9 MB | surekli | Bodycam oyunu - sentetik uretim kaynagi |
| sentetik | `synthetic-bodycam--nlXwNwilt8I.mp4` | 0:11 | 1080p | 0.9 MB | surekli | Bodycam oyunu - sentetik uretim kaynagi |
| sentetik | `synthetic-bodycam--wR-zo-dinUc.mp4` | 0:10 | 1080p | 1.2 MB | surekli | Bodycam oyunu - sentetik uretim kaynagi |
| trafik | `factory-accidents---8oYzSP5Vbw.mp4` | 9:17 | 1078p | 283.8 MB | derleme | Motosiklet kask-kamerasi trafik kazalari (dokumanda fabrika diye gecmis) |
| yangin | `fire-single--lleF2nmlkMY.mp4` | 1:01 | 1080p | 10.9 MB | derleme | Tekli algilama: videoda sadece yangin var |

## Kesitler — kullanilabilir

| Kategori | Kaynak | Kesit | Süre | Etiket |
|---|---|---|---|---|
| askeri-playlist | pl1-01--B5xphv6lYkw | `01` | 0:07 | daglik arazi operasyonu, kask kamerasi |
| askeri-playlist | pl1-01--B5xphv6lYkw | `02` | 0:12 | daglik arazi operasyonu, kask kamerasi |
| askeri-playlist | pl1-01--B5xphv6lYkw | `03` | 0:40 | daglik arazi operasyonu, kask kamerasi |
| askeri-playlist | pl1-01--B5xphv6lYkw | `04` | 1:06 | daglik arazi operasyonu, kask kamerasi |
| askeri-playlist | pl1-01--B5xphv6lYkw | `05` | 1:37 | daglik arazi operasyonu, kask kamerasi |
| askeri-playlist | pl1-04--V7yXO_Nd5NI | `02` | 0:06 | sinir otesi operasyon: zirhli arac, topcu, keskin nisanci |
| askeri-playlist | pl1-04--V7yXO_Nd5NI | `05` | 0:13 | sinir otesi operasyon: zirhli arac, topcu, keskin nisanci |
| askeri-playlist | pl1-04--V7yXO_Nd5NI | `06` | 0:06 | sinir otesi operasyon: zirhli arac, topcu, keskin nisanci |
| askeri-playlist | pl1-04--V7yXO_Nd5NI | `11` | 0:09 | sinir otesi operasyon: zirhli arac, topcu, keskin nisanci |
| askeri-playlist | pl1-04--V7yXO_Nd5NI | `12` | 0:09 | sinir otesi operasyon: zirhli arac, topcu, keskin nisanci |
| askeri-playlist | pl1-04--V7yXO_Nd5NI | `13` | 0:06 | sinir otesi operasyon: zirhli arac, topcu, keskin nisanci |
| askeri-playlist | pl1-04--V7yXO_Nd5NI | `17` | 0:07 | sinir otesi operasyon: zirhli arac, topcu, keskin nisanci |
| askeri-playlist | pl1-04--V7yXO_Nd5NI | `19` | 0:09 | sinir otesi operasyon: zirhli arac, topcu, keskin nisanci |
| askeri-playlist | pl1-04--V7yXO_Nd5NI | `21` | 0:16 | sinir otesi operasyon: zirhli arac, topcu, keskin nisanci |
| askeri-playlist | pl1-04--V7yXO_Nd5NI | `22` | 0:09 | sinir otesi operasyon: zirhli arac, topcu, keskin nisanci |
| askeri-playlist | pl1-04--V7yXO_Nd5NI | `38` | 0:07 | sinir otesi operasyon: zirhli arac, topcu, keskin nisanci |
| askeri-playlist | pl1-04--V7yXO_Nd5NI | `39` | 0:06 | sinir otesi operasyon: zirhli arac, topcu, keskin nisanci |
| askeri-playlist | pl1-04--V7yXO_Nd5NI | `42` | 0:11 | sinir otesi operasyon: zirhli arac, topcu, keskin nisanci |
| askeri-playlist | pl1-05--6wLrSZyeha8 | `01` | 0:06 | askeri operasyon |
| askeri-playlist | pl1-05--6wLrSZyeha8 | `03` | 0:22 | askeri operasyon |
| askeri-playlist | pl1-05--6wLrSZyeha8 | `04` | 0:23 | askeri operasyon |
| askeri-playlist | pl1-09--IEsmSX019j4 | `01` | 0:15 | arama-tarama operasyonu, malzeme ele gecirme |
| askeri-playlist | pl1-09--IEsmSX019j4 | `02` | 0:15 | arama-tarama operasyonu, malzeme ele gecirme |
| askeri-playlist | pl1-09--IEsmSX019j4 | `03` | 0:07 | arama-tarama operasyonu, malzeme ele gecirme |
| askeri-playlist | pl1-09--IEsmSX019j4 | `04` | 0:39 | arama-tarama operasyonu, malzeme ele gecirme |
| askeri-playlist | pl1-09--IEsmSX019j4 | `05` | 0:15 | arama-tarama operasyonu, malzeme ele gecirme |
| askeri-playlist | pl1-09--IEsmSX019j4 | `06` | 0:07 | arama-tarama operasyonu, malzeme ele gecirme |
| askeri-playlist | pl1-09--IEsmSX019j4 | `07` | 0:08 | arama-tarama operasyonu, malzeme ele gecirme |
| askeri-playlist | pl1-09--IEsmSX019j4 | `08` | 0:07 | arama-tarama operasyonu, malzeme ele gecirme |
| askeri-playlist | pl1-09--IEsmSX019j4 | `10` | 0:06 | arama-tarama operasyonu, malzeme ele gecirme |
| askeri-playlist | pl1-09--IEsmSX019j4 | `11` | 0:22 | arama-tarama operasyonu, malzeme ele gecirme |
| askeri-playlist | pl1-09--IEsmSX019j4 | `12` | 0:10 | arama-tarama operasyonu, malzeme ele gecirme |
| askeri-playlist | pl1-09--IEsmSX019j4 | `13` | 0:11 | arama-tarama operasyonu, malzeme ele gecirme |
| askeri-playlist | pl1-09--IEsmSX019j4 | `14` | 0:11 | arama-tarama operasyonu, malzeme ele gecirme |
| askeri-playlist | pl1-09--IEsmSX019j4 | `15` | 0:39 | arama-tarama operasyonu, malzeme ele gecirme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `04` | 0:08 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `05` | 0:36 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `06` | 0:12 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `07` | 0:05 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `09` | 0:07 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `10` | 0:27 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `17` | 0:19 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `18` | 0:28 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `19` | 0:46 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `20` | 0:25 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `21` | 0:11 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `22` | 0:22 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `23` | 0:26 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `24` | 0:17 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `25` | 0:18 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `27` | 0:05 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `30` | 0:25 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `31` | 0:15 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `32` | 0:11 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `33` | 0:30 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `34` | 0:05 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `35` | 0:33 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `36` | 0:07 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `37` | 0:11 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `38` | 0:37 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `41` | 0:09 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `43` | 0:08 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `44` | 0:10 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `45` | 0:06 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `47` | 0:06 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `48` | 0:24 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `52` | 0:24 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `56` | 0:05 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `57` | 0:07 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `58` | 0:47 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `59` | 0:16 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `61` | 0:06 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `63` | 0:08 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `67` | 0:06 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `68` | 0:24 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `69` | 0:05 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `70` | 0:17 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `71` | 0:07 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-02--O2A_KBTxB00 | `72` | 0:10 | sehir ici operasyon: devriye, zirhli arac, havadan hedefleme |
| askeri-playlist | pl2-08--Rur_BrM8yXU | `08` | 1:28 | sehir ici zirhli arac hareketi ve patlama |
| askeri-playlist | pl2-08--Rur_BrM8yXU | `10` | 1:54 | sehir ici zirhli arac hareketi ve patlama |
| askeri | military--hE14s_Z-1-Q | `01` | 0:05 | askeri operasyon |
| askeri | military--hE14s_Z-1-Q | `02` | 0:34 | askeri operasyon |
| askeri | military--hE14s_Z-1-Q | `03` | 1:16 | askeri operasyon |
| askeri | military--hE14s_Z-1-Q | `04` | 0:06 | askeri operasyon |
| forklift | forklift-compilation--N9bG-sOU6LE | `01` | 0:14 | atolyede patlama ve parca sacilmasi |
| forklift | forklift-compilation--N9bG-sOU6LE | `03` | 0:22 | depoda raf/yuk cokmesi |
| forklift | forklift-compilation--N9bG-sOU6LE | `04` | 1:38 | sokakta kamyon-forklift carpismasi |
| forklift | forklift-compilation--N9bG-sOU6LE | `05` | 1:17 | sokakta forklift devrilmesi |
| forklift | forklift-compilation--N9bG-sOU6LE | `06` | 0:28 | limanda konteyner istifleyici devrilmesi |
| forklift | forklift-compilation--N9bG-sOU6LE | `07` | 0:16 | limanda konteyner devrilmesi (devam) |
| forklift | forklift-compilation--N9bG-sOU6LE | `08` | 0:29 | dar koridorda forklift manevrasi |
| forklift | forklift-compilation--N9bG-sOU6LE | `09` | 0:12 | ic mekanda yuk dusmesi |
| forklift | forklift-compilation--N9bG-sOU6LE | `33` | 0:08 | depoda yuk/raf cokmesi |
| sentetik | synthetic-bodycam--KVkPToQGVAQ | `01` | 0:15 | Bodycam oyunu, birinci sahis ic/dis mekan |
| sentetik | synthetic-bodycam--KVkPToQGVAQ | `02` | 0:15 | Bodycam oyunu, birinci sahis ic/dis mekan |
| sentetik | synthetic-bodycam--KVkPToQGVAQ | `03` | 0:16 | Bodycam oyunu, birinci sahis ic/dis mekan |
| sentetik | synthetic-bodycam--KVkPToQGVAQ | `07` | 0:14 | Bodycam oyunu, birinci sahis ic/dis mekan |
| sentetik | synthetic-bodycam--KVkPToQGVAQ | `09` | 0:07 | Bodycam oyunu, birinci sahis ic/dis mekan |
| sentetik | synthetic-bodycam--KVkPToQGVAQ | `10` | 0:20 | Bodycam oyunu, birinci sahis ic/dis mekan |
| sentetik | synthetic-bodycam--KVkPToQGVAQ | `11` | 0:08 | Bodycam oyunu, birinci sahis ic/dis mekan |
| sentetik | synthetic-bodycam--KVkPToQGVAQ | `12` | 0:46 | Bodycam oyunu, birinci sahis ic/dis mekan |
| sentetik | synthetic-bodycam--KVkPToQGVAQ | `14` | 0:06 | Bodycam oyunu, birinci sahis ic/dis mekan |
| sentetik | synthetic-bodycam--KVkPToQGVAQ | `15` | 0:09 | Bodycam oyunu, birinci sahis ic/dis mekan |
| sentetik | synthetic-bodycam--KVkPToQGVAQ | `19` | 0:24 | Bodycam oyunu, birinci sahis ic/dis mekan |
| sentetik | synthetic-bodycam--KVkPToQGVAQ | `20` | 0:06 | Bodycam oyunu, birinci sahis ic/dis mekan |
| trafik | factory-accidents---8oYzSP5Vbw | `02` | 0:18 | motosiklet kask-kamerasi trafik kazasi |
| trafik | factory-accidents---8oYzSP5Vbw | `03` | 0:16 | motosiklet kask-kamerasi trafik kazasi |
| trafik | factory-accidents---8oYzSP5Vbw | `04` | 1:01 | motosiklet kask-kamerasi trafik kazasi |
| trafik | factory-accidents---8oYzSP5Vbw | `05` | 0:15 | motosiklet kask-kamerasi trafik kazasi |
| trafik | factory-accidents---8oYzSP5Vbw | `06` | 0:06 | motosiklet kask-kamerasi trafik kazasi |
| trafik | factory-accidents---8oYzSP5Vbw | `07` | 0:50 | motosiklet kask-kamerasi trafik kazasi |
| trafik | factory-accidents---8oYzSP5Vbw | `08` | 1:20 | motosiklet kask-kamerasi trafik kazasi |
| trafik | factory-accidents---8oYzSP5Vbw | `10` | 0:15 | motosiklet kask-kamerasi trafik kazasi |
| trafik | factory-accidents---8oYzSP5Vbw | `11` | 0:09 | motosiklet kask-kamerasi trafik kazasi |
| trafik | factory-accidents---8oYzSP5Vbw | `12` | 0:22 | motosiklet kask-kamerasi trafik kazasi |
| trafik | factory-accidents---8oYzSP5Vbw | `13` | 0:38 | motosiklet kask-kamerasi trafik kazasi |
| trafik | factory-accidents---8oYzSP5Vbw | `14` | 0:53 | motosiklet kask-kamerasi trafik kazasi |
| trafik | factory-accidents---8oYzSP5Vbw | `18` | 0:06 | motosiklet kask-kamerasi trafik kazasi |
| trafik | factory-accidents---8oYzSP5Vbw | `19` | 0:36 | motosiklet kask-kamerasi trafik kazasi |
| trafik | factory-accidents---8oYzSP5Vbw | `25` | 0:11 | motosiklet kask-kamerasi trafik kazasi |
| trafik | factory-accidents---8oYzSP5Vbw | `26` | 0:11 | motosiklet kask-kamerasi trafik kazasi |
| trafik | factory-accidents---8oYzSP5Vbw | `27` | 0:45 | motosiklet kask-kamerasi trafik kazasi |
| trafik | factory-accidents---8oYzSP5Vbw | `28` | 0:13 | motosiklet kask-kamerasi trafik kazasi |
| yangin | fire-single--lleF2nmlkMY | `01` | 0:25 | fabrika dis cephesinde yangin baslangici |
| yangin | fire-single--lleF2nmlkMY | `02` | 0:13 | yangin buyumesi, yogun duman |
| yangin | fire-single--lleF2nmlkMY | `03` | 0:12 | fabrika ici bos hat, yangin gorunmuyor |

## Kesitler — elendi

| Kaynak | Kesit | Sebep |
|---|---|---|
| pl1-04--V7yXO_Nd5NI | `25` | gece cekimi, neredeyse tamamen karanlik — tespit icin kullanissiz |
| pl1-04--V7yXO_Nd5NI | `27` | gece cekimi, neredeyse tamamen karanlik — tespit icin kullanissiz |
| pl1-04--V7yXO_Nd5NI | `28` | gece cekimi, neredeyse tamamen karanlik — tespit icin kullanissiz |
| pl1-04--V7yXO_Nd5NI | `29` | gece cekimi, neredeyse tamamen karanlik — tespit icin kullanissiz |
| pl2-02--O2A_KBTxB00 | `03` | haber spikeri/muhabir kamera karsisi — olay goruntusu degil |
| pl2-02--O2A_KBTxB00 | `15` | haber spikeri/muhabir kamera karsisi — olay goruntusu degil |
| pl2-02--O2A_KBTxB00 | `75` | haber spikeri/muhabir kamera karsisi — olay goruntusu degil |
| military--hE14s_Z-1-Q | `05` | yuzu bulanik roportaj — video analizi icin degersiz |
| military--hE14s_Z-1-Q | `06` | yuzu bulanik roportaj — video analizi icin degersiz |
| military--hE14s_Z-1-Q | `07` | yuzu bulanik roportaj — video analizi icin degersiz |
| military--hE14s_Z-1-Q | `08` | yuzu bulanik roportaj — video analizi icin degersiz |
| military--hE14s_Z-1-Q | `09` | yuzu bulanik roportaj — video analizi icin degersiz |
| military--hE14s_Z-1-Q | `10` | yuzu bulanik roportaj — video analizi icin degersiz |
| military--hE14s_Z-1-Q | `11` | yuzu bulanik roportaj — video analizi icin degersiz |
| military--hE14s_Z-1-Q | `12` | yuzu bulanik roportaj — video analizi icin degersiz |
| military--hE14s_Z-1-Q | `13` | yuzu bulanik roportaj — video analizi icin degersiz |
| military--hE14s_Z-1-Q | `14` | yuzu bulanik roportaj — video analizi icin degersiz |
| military--hE14s_Z-1-Q | `15` | yuzu bulanik roportaj — video analizi icin degersiz |
| military--hE14s_Z-1-Q | `16` | yuzu bulanik roportaj — video analizi icin degersiz |
| military--hE14s_Z-1-Q | `19` | yuzu bulanik roportaj — video analizi icin degersiz |
| military--hE14s_Z-1-Q | `20` | yuzu bulanik roportaj — video analizi icin degersiz |
| military--hE14s_Z-1-Q | `21` | yuzu bulanik roportaj — video analizi icin degersiz |
| forklift-cause--V8ZmOgMlyRE | `01` | tek olayin oncesi/sonrasi — yanlis bolme - neden-sonuc zinciri kopuyor |
| forklift-cause--V8ZmOgMlyRE | `03` | tek olayin oncesi/sonrasi — yanlis bolme - neden-sonuc zinciri kopuyor |
| multi-event--OlRDWS2E0EY | `01` | sabit IP kamera, gercek kesme yok — yanlis bolme - kaynak butun kullanilmali |
| multi-event--OlRDWS2E0EY | `02` | sabit IP kamera, gercek kesme yok — yanlis bolme - kaynak butun kullanilmali |
| multi-event--OlRDWS2E0EY | `03` | sabit IP kamera, gercek kesme yok — yanlis bolme - kaynak butun kullanilmali |
| multi-event--OlRDWS2E0EY | `04` | sabit IP kamera, gercek kesme yok — yanlis bolme - kaynak butun kullanilmali |
| multi-event--OlRDWS2E0EY | `05` | sabit IP kamera, gercek kesme yok — yanlis bolme - kaynak butun kullanilmali |
| multi-event--OlRDWS2E0EY | `06` | sabit IP kamera, gercek kesme yok — yanlis bolme - kaynak butun kullanilmali |
| factory-accidents---8oYzSP5Vbw | `24` | VHS "THE END" karti — icerik yok |
| fire-single--lleF2nmlkMY | `05` | kanal logosu — icerik yok |
