import json, sys
from pathlib import Path
from gozcu.agents.supervisor import Supervisor
from gozcu.gateway import Gateway
from gozcu.run import run_pipeline
from gozcu.store import Store

label, clip = sys.argv[1], sys.argv[2]
out = Path("runs") / f"verify-{label}"; out.mkdir(parents=True, exist_ok=True)
store = Store(); gw = Gateway(store)
source = f"verify:{label}"
output, _ = run_pipeline(clip, store=store, gw=gw,
                         nobetci=Supervisor(gw, store, source=source),
                         output_dir=out, archive=False)
events = [e.model_dump() if hasattr(e, "model_dump") else e for e in output.events]
eps = store.episodes()
Path(f"runs/verify-{label}.json").write_text(json.dumps(
    {"label": label, "risk": output.risk, "events": events,
     "episodes": [{"start_ts": e.start_ts, "beats": len(e.beats)} for e in eps]},
    ensure_ascii=False), encoding="utf-8")
s = sorted(int(e["time"].split(":")[0])*60+int(e["time"].split(":")[1]) for e in events)
print(f"\n{label}: {len(events)} an, {s[0]}–{s[-1]}s, risk={output.risk!r}, "
      f"epizot açılışı={eps[0].start_ts}s")
