import os, sys, time, glob
sys.path.insert(0, os.getcwd())
from pathlib import Path
from cargento_runtime import config as cfg, state as st_mod, turns

config = cfg.build_runtime_config(environ=os.environ, platform_name=sys.platform,
                                  os_name=os.name, launcher_path=Path(os.getcwd())/"server.py")
root = cfg.store_roots(config, "claude.projects")[0]
now = time.time()
files = sorted(glob.glob(os.path.join(root, "*", "*.jsonl")), key=os.path.getmtime, reverse=True)

def run(paths, label):
    state = st_mod.RuntimeState(config=config, server_started=now)
    per_turn = []          # (duration, covered_at_end, covered_seconds)
    for p in paths:
        scan = turns.scan_turns(config, state, p, "claude")
        if not scan: continue
        hist = []
        for d in (scan.get("durations") or []):
            # replay turn_progress' rule: an ETA exists at elapsed e iff some
            # prior turn >= e. So the turn is covered on [0, max(hist)] only.
            cap = max(hist) if hist else 0.0
            per_turn.append((d, d <= cap, min(d, cap)))
            hist.append(d)
    if not per_turn: return
    n = len(per_turn)
    cov_end = sum(1 for d,c,_ in per_turn if c)
    tot = sum(d for d,_,_ in per_turn); cov_t = sum(c for _,_,c in per_turn)
    unc = [d for d,c,_ in per_turn if not c]; cvd = [d for d,c,_ in per_turn if c]
    med = lambda a: sorted(a)[len(a)//2] if a else 0
    fm = lambda s: f"{int(s)//60}m{int(s)%60:02d}s"
    print(f"\n[{label}] turns={n}")
    print(f"  turns with an ETA at the moment they ended: {cov_end}/{n} = {100*cov_end/n:.0f}%")
    print(f"  wall-clock covered by an ETA:               {100*cov_t/tot:.0f}%  ({fm(tot-cov_t)} of {fm(tot)} uncovered)")
    print(f"  median duration  covered turns {fm(med(cvd))}   UNCOVERED turns {fm(med(unc))}")
    print(f"  mean   duration  covered turns {fm(sum(cvd)/len(cvd)) if cvd else '-'}   UNCOVERED turns {fm(sum(unc)/len(unc)) if unc else '-'}")
    tail = sorted(per_turn, key=lambda t:-t[0])[:max(1,n//10)]
    print(f"  of the slowest 10% of turns, {sum(1 for _,c,_ in tail if c)}/{len(tail)} had an ETA at the end")

for hrs,l in ((24,"modified within 24h"),(72,"within 72h"),(168,"within 7d")):
    run([p for p in files if now-os.path.getmtime(p) <= hrs*3600], l)
run(files[:150], "150 most recent transcripts")
