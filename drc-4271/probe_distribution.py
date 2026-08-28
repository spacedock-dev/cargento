import os, sys, time, glob, statistics
sys.path.insert(0, os.getcwd())
from cargento_runtime import config as cfg, state as st_mod, turns

from pathlib import Path
config = cfg.build_runtime_config(environ=os.environ, platform_name=sys.platform, os_name=os.name, launcher_path=Path(os.getcwd())/"server.py")
roots = cfg.store_roots(config, "claude.projects")
print("claude store roots:", roots)

files = []
for r in roots:
    files += glob.glob(os.path.join(r, "*", "*.jsonl"))
files = sorted(set(files), key=lambda p: os.path.getmtime(p), reverse=True)
print("total transcripts found:", len(files))

now = time.time()
def probe(paths, label):
    state = st_mod.RuntimeState(config=config, server_started=now)
    durs, sessions_with = [], 0
    truncated = 0
    for p in paths:
        scan = turns.scan_turns(config, state, p, "claude.projects")
        if not scan: continue
        d = scan.get("durations") or []
        if scan.get("scanned_from_zero") is not True: truncated += 1
        if d:
            sessions_with += 1
            durs += list(d)
    if not durs:
        print(f"\n[{label}] no durations"); return
    durs.sort()
    def q(f):
        return durs[min(len(durs)-1, int(round(f*(len(durs)-1))))]
    def fm(s): return f"{int(s)//60}m{int(s)%60:02d}s"
    print(f"\n[{label}] files={len(paths)} sessions_with_turns={sessions_with} turns={len(durs)} tail-truncated_files={truncated}")
    print(f"  median {fm(statistics.median(durs))}  p75 {fm(q(.75))}  p90 {fm(q(.90))}  p95 {fm(q(.95))}  max {fm(durs[-1])}")
    print(f"  >=10m: {100*sum(1 for x in durs if x>=600)/len(durs):.0f}%   >=15m(long_turn): {100*sum(1 for x in durs if x>=900)/len(durs):.0f}%   >=20m: {100*sum(1 for x in durs if x>=1200)/len(durs):.0f}%")

# recency windows
for hrs in (24, 72, 24*7):
    sel = [p for p in files if now-os.path.getmtime(p) <= hrs*3600]
    probe(sel, f"modified within {hrs}h")
probe(files[:11], "11 most recent transcripts")
probe(files[:50], "50 most recent transcripts")
