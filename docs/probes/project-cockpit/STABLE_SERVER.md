# Stable operator cockpit server

This server keeps `http://127.0.0.1:8766/` available while the Cargento backend changes.
It starts two backend ports in sequence and publishes only a healthy backend.

The server owns a clean checkout of `clkao/proto/operator-cockpit`.
It fetches this branch and accepts only a fast-forward update.
The imported branch in `spacedock-dev/cargento` has the same name. To follow it, pass
`--remote-url https://github.com/spacedock-dev/cargento.git --branch proto/operator-cockpit`
to the commands below; the default remote remains the original fork.
The server does not write to `spacedock-dev/cargento`.

## Start a review checkpoint

Run this command from the review worktree:

```bash
.venv/bin/python scripts/serve_operator_cockpit.py \
  --public-port 8766 \
  --backend-port-a 18766 \
  --backend-port-b 18767 \
  --checkout /Users/clkao/git/spacedock-research/cargento/.spacedock/runtime/operator-cockpit/checkout \
  --state-dir /Users/clkao/git/spacedock-research/cargento/.spacedock/runtime/operator-cockpit/state \
  --review-root /Users/clkao/git/spacedock-research/cargento/.worktrees/spacedock-ensign-project-cockpit \
  --review-commit <review-sha> \
  --python /Users/clkao/git/spacedock-research/cargento/.worktrees/spacedock-ensign-project-cockpit/.venv/bin/python
```

The review worktree must be clean. Its `HEAD` must equal `<review-sha>`.
The server watches this worktree and accepts only fast-forward commits.

Open `http://127.0.0.1:8766/__proto/checkpoint` to see the published checkpoint and backend port.
The HTML page requests this endpoint every 1.5 seconds.
The browser reloads when the published checkpoint changes.

## Follow an accepted remote checkpoint

After the accepted push, record the exact remote checkpoint:

```bash
.venv/bin/python scripts/serve_operator_cockpit.py \
  --checkout /Users/clkao/git/spacedock-research/cargento/.spacedock/runtime/operator-cockpit/checkout \
  --state-dir /Users/clkao/git/spacedock-research/cargento/.spacedock/runtime/operator-cockpit/state \
  --accept-remote <pushed-sha>
```

The watcher fetches the remote branch.
It changes the source only after the branch contains `<pushed-sha>`.
This explicit step supports an accepted change that has a new SHA after a rebase.

## Stop the server

```bash
.venv/bin/python scripts/serve_operator_cockpit.py \
  --public-port 8766 \
  --checkout /Users/clkao/git/spacedock-research/cargento/.spacedock/runtime/operator-cockpit/checkout \
  --state-dir /Users/clkao/git/spacedock-research/cargento/.spacedock/runtime/operator-cockpit/state \
  --stop
```

The stop command reads the recorded PID.
It also makes sure that this PID owns the stable URL before it sends `SIGTERM`.

## Recover the server

If the process stops, run the start command again.
After integration, use the last accepted checkout without `--review-root` and `--review-commit`:

```bash
.venv/bin/python scripts/serve_operator_cockpit.py \
  --public-port 8766 \
  --backend-port-a 18766 \
  --backend-port-b 18767 \
  --checkout /Users/clkao/git/spacedock-research/cargento/.spacedock/runtime/operator-cockpit/checkout \
  --state-dir /Users/clkao/git/spacedock-research/cargento/.spacedock/runtime/operator-cockpit/state \
  --python /Users/clkao/git/spacedock-research/cargento/.worktrees/spacedock-ensign-project-cockpit/.venv/bin/python
```

If the checkout is dirty or the remote branch diverges, read the server error.
Do not repair the checkout with `git reset --hard`.
Move the checkout aside.
Then let the server make a new dedicated clone.

Backend logs are in `/Users/clkao/git/spacedock-research/cargento/.spacedock/runtime/operator-cockpit/state/`.
The proxy keeps the public port during a backend replacement.
The API and SSE paths use the same proxy as the HTML page.

## Exercise record

The exercise started at review checkpoint `938e4f83056792d26a1d961feb2e5a8e4df5062e`.
The stable proxy used backend port 18766 and process 3035.
The `/api/data` response had 13 active sessions, seven project labels, and zero real asks.
The `/api/stream` response had revision event `1787634817.4`.

This record commit is the review-checkout update for the exercise.
Its exact checkpoint is `f664aea21c3cb78daa92ede3a817cafb63b780e4`.

The watcher changed the backend port from 18766 to 18767.
The stable proxy process stayed at process 3035.
The API measurements stayed at 13 active sessions, seven project labels, and zero real asks.
No collector reported an error before or after the update.
The new SSE connection received revision events `1787634869.2` and `1787634869.3`.

These commands supplied the measurements:

```bash
curl -fsS http://127.0.0.1:8766/__proto/checkpoint | jq .
curl -fsS http://127.0.0.1:8766/api/data | jq \
  '{sessions:(.sessions|length),active:([.sessions[]|select(.active)]|length),projects:([.sessions[].project]|unique|length),ask:.ask,asks:(.asks|length)}'
curl -sSN --max-time 6 http://127.0.0.1:8766/api/stream
```
