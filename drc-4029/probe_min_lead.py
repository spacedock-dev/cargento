"""D6 re-scope probe: can ANY honest statistic produce a walk-away time?

The ruling forbids a statistic whose plain reading is an all-clear. What remains
permitted is the settled narrow claim -- *the soonest expected completion among
turns we can estimate* -- i.e. the minimum, plus any rule layered on top of it
(most plausibly: publish nothing unless the window is worth leaving on).

Every statistic in that family is bounded above by the soonest completion, so the
family's ceiling is measurable in one pass. Two ceilings are reported:

  published  -- min over `turn_progress`-covered rows, i.e. what D6 could ship today
  oracle     -- min over the TRUE completion of every live turn, covered or not

The oracle is the point. It is what a perfect estimator with total coverage would
publish, so it bounds every possible improvement to estimation or coverage. If the
oracle lead time is short, no fourth statistic in this family can be built, and
the refusal is structural rather than a property of `turn_progress`.

Interval reconstruction is lifted verbatim from ../drc-4271/probe_max_error.py.
Read-only; reads the live ~/.claude/projects store, so the numbers are this
machine's and the method is portable.

    cd cargento/skills/cargento && python3 <path>/probe_min_lead.py
"""
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
    """turn_progress' predicted completion for turn i at wall-clock t, or None."""
    s, e = iv[i]; elapsed = t - s
    hist = [b-a for a,b in iv[:i]]
    c = sorted(d for d in hist if d >= elapsed)
    if not c: return None
    return s + c[len(c)//2]

random.seed(7)   # same seed as probe_max_error.py, so the instants are comparable
lo = min(a for v in sess.values() for a,_ in v); hi = max(b for v in sess.values() for _,b in v)
rows = []
for _ in range(200000):
    t = random.uniform(lo, hi)
    live = []
    for iv in sess.values():
        for i,(s,e) in enumerate(iv):
            if s <= t < e: live.append((iv,i,s,e)); break
    if len(live) < 1: continue
    ests = [eta_at(iv,i,t) for iv,i,_,_ in live]
    covered = [x for x in ests if x is not None]
    pub_min = min(covered) if covered else None          # what D6 would publish
    true_min = min(e for _,_,_,e in live)                # the oracle: soonest real completion
    rows.append((len(live), len(covered), pub_min, true_min, t))

# The full draw stream is exhausted rather than stopped at a row cap, so the k>=2
# sample matches probe_max_error.py's exactly: same seed, same reconstruction, same
# accept order. Stopping early would have truncated the decisive regime to a prefix.
print(f"sampled instants with >=1 working session: {len(rows)}")
fm = lambda s: "-" if s is None else f"{int(abs(s))//60}m{int(abs(s))%60:02d}s"
def pct(v, q):
    return v[int(q*(len(v)-1))] if v else None

for kmin,kmax,lab in ((1,1,"k=1"),(2,2,"k=2"),(3,4,"k=3-4"),(5,99,"k>=5"),(2,99,"all k>=2")):
    sel=[r for r in rows if kmin<=r[0]<=kmax]
    if not sel: continue
    print(f"\n{lab}: instants={len(sel)}  mean sessions={sum(r[0] for r in sel)/len(sel):.1f}")
    for name, idx in (("published min", 2), ("oracle min  ", 3)):
        leads = sorted(r[idx]-r[4] for r in sel if r[idx] is not None)
        if not leads: 
            print(f"  {name}: never publishable"); continue
        n = len(sel)
        ge = lambda m: 100*sum(1 for L in leads if L >= m*60)/n
        print(f"  {name}: renders {100*len(leads)/n:3.0f}% of instants | "
              f"median {fm(pct(leads,.5))}  p75 {fm(pct(leads,.75))}  p90 {fm(pct(leads,.9))}")
        print(f"                 lead >=5m {ge(5):4.1f}%   >=10m {ge(10):4.1f}%   >=20m {ge(20):4.1f}%")

# The suppression rule, measured: publish only when the window is worth leaving on.
print("\n--- suppression rule: publish the minimum ONLY when it is >= T minutes out ---")
print("    (k>=2 only; 'wrong' = something actually completed before the published time)")
sel = [r for r in rows if r[0] >= 2]
for T in (5, 10, 20):
    fires = [r for r in sel if r[2] is not None and r[2]-r[4] >= T*60]
    if not fires:
        print(f"  T={T:2d}m: renders 0.0% of instants ({0}/{len(sel)})"); continue
    wrong = [r for r in fires if r[3] < r[2]]
    early = sorted(r[2]-r[3] for r in wrong)
    print(f"  T={T:2d}m: renders {100*len(fires)/len(sel):4.1f}% of instants ({len(fires)}/{len(sel)})  "
          f"| wrong {100*len(wrong)/len(fires):3.0f}% of the times it renders"
          + (f", by a median of {fm(pct(early,.5))} (worst {fm(early[-1])})" if early else ""))
