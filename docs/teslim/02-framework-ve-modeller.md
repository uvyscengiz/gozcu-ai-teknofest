# ② Kullanılan agentic framework ve LLM'ler

**Gözcü** · Takım **FERASET** (`team37`) · Muğla Sıtkı Koçman Üniversitesi

Bu bölüm şartname §6'nın *"kullanılan agentic framework ve LLM'ler"* kalemidir.

> **TODO — koddan yazılacak.** Kaynaklar: `gozcu/core/config.py` (model
> kimlikleri), `gozcu/core/gateway.py` (OpenAI-uyumlu gateway), agent
> modülleri (`gozcu/agents/`), ve tasarım spec'i.

## Kapatılması gereken başlıklar

- Agentic framework: neden kendi orkestrasyon (LangGraph/CrewAI değil)?
- LLM seçimi: hangi modeller, neden, Türkçe performans karşılaştırması
- Model servisleme: EVREN gateway, OpenAI-uyumlu API, yerel çalışma garantisi
- Prompt mühendisliği: yapılandırılmış çıktı, Türkçe enum'lar, şema uyumu
