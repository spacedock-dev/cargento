import os, sys, time, glob, json, random
sys.path.insert(0, os.getcwd())
from pathlib import Path
from cargento_runtime import config as cfg, records

config = cfg.build_runtime_config(environ=os.environ, platform_name=sys.platform,
                                  os_name=os.name, launcher_path=Path(os.getcwd())/"server.py")
root = cfg.store_roots(config, "claude.projects")[0]
now = time.time()
files = sorted(glob.glob(os.path.join(root, "*", "*.jsonl")), key=os.path.getmtime, reverse=True)
files = [p for p in files if now-os.path.getmtime(p) <= 7*24*3600]

# Rebuild absolute turn intervals with _apply_turn_record's boundary rules.
def intervals(path):
    out, ts_, prev = [], None, None
    try: raw = open(path,'rb').read()
    except OSError: return out
    for line in raw.split(b"\n"):
        if not line.startswith(b"{"): continue
        try: d = json.loads(line)
        except Exception: continue
        ep = records.parse_ts(d.get("timestamp") or "")
        if not ep: continue
        if ts_ and prev and ep - prev > config.turn_gap_reset_sec:
            if prev > ts_: out.append((ts_, prev))
            ts_ = ep
        sig = records._turn_signal(d, "claude")
        if sig:
            kind, override = sig
            if kind == "end":
                if ts_ and ep > ts_: out.append((ts_, ep))
                ts_ = None
            else:
                if kind == "prompt" and ts_ and prev and prev > ts_: out.append((ts_, prev))
                ts_ = records.norm_epoch(override) or ep
        prev = ep
    return out

sess = {}
for p in files:
    iv = intervals(p)
    if iv: sess[p] = sorted(iv)
print(f"sessions={len(sess)} turns={sum(len(v) for v in sess.values())}")

def eta_at(iv, i, t):
    """turn_progress' estimate for turn i of iv at wall-clock t, or None."""
    s,e = iv[i]; elapsed = t - s
    hist = [b-a for a,b in iv[:i]]
    c = sorted(d for d in hist if d >= elapsed)
    if not c: return None
    return s + c[len(c)//2]          # predicted completion (absolute)

# Sample instants; at each, compare published max-ETA vs the truth.
random.seed(7)
lo = min(a for v in sess.values() for a,_ in v); hi = max(b for v in sess.values() for _,b in v)
rows = []
for _ in range(200000):
    t = random.uniform(lo, hi)
    live = []
    for iv in sess.values():
        for i,(s,e) in enumerate(iv):
            if s <= t < e: live.append((iv,i,s,e)); break
    if len(live) < 2: continue
    ests = [eta_at(iv,i,t) for iv,i,_,_ in live]
    covered = [x for x in ests if x is not None]
    true_max = max(e for _,_,_,e in live)
    rows.append((len(live), len(covered), max(covered) if covered else None, true_max, t))
    if len(rows) >= 4000: break

print(f"sampled instants with >=2 working sessions: {len(rows)}")
fm = lambda s: ("-" if s is None else f"{int(abs(s))//60}m{int(abs(s))%60:02d}s")
for kmin,kmax,lab in ((2,2,"k=2"),(3,4,"k=3-4"),(5,99,"k>=5"),(2,99,"all k>=2")):
    sel=[r for r in rows if kmin<=r[0]<=kmax]
    if not sel: continue
    full=sum(1 for r in sel if r[1]==r[0]); none_=sum(1 for r in sel if r[1]==0)
    pub=[r for r in sel if r[2] is not None]
    errs=[r[3]-r[2] for r in pub]                      # +ve => published time is TOO EARLY
    under=[e for e in errs if e>0]
    print(f"\n{lab}: instants={len(sel)}  mean sessions={sum(r[0] for r in sel)/len(sel):.1f}")
    print(f"  full coverage (every working row has an ETA): {100*full/len(sel):.0f}%   zero coverage: {100*none_/len(sel):.0f}%")
    if errs:
        errs.sort()
        print(f"  published max is EARLIER than the truth: {100*len(under)/len(errs):.0f}% of instants")
        print(f"    understatement  median {fm(errs[len(errs)//2])}  p90 {fm(errs[int(.9*(len(errs)-1))])}  worst {fm(errs[-1])}")
