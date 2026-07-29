# Design: daemon mode, and stopping Cargento from its own UI

The durable rationale behind `--daemon`, `--status`, `--stop`, and the two HTTP routes that back
them. It records the decisions and the alternatives that were tried and rejected. The rejected ones
are the expensive part, because without them they get re-attempted.

Behavioral detail lives in [`COMPATIBILITY.md`](../COMPATIBILITY.md) (the per-OS matrix), the written
paths and the `/api/shutdown` exposure are owned by [`SECURITY.md`](../SECURITY.md), and the
user-facing contract is the skill body. This file explains *why*, not *what*.

Each decision keeps a stable `D-N` anchor, and code comments cite them by name. Grep the identifier
across `*.py` and `*.md` before renumbering anything.

---

## The problem these decisions answer

Cargento is started by an agent, in that agent's session, as a background child of the session's
shell. Two consequences, and they pull against each other.

The dashboard dies with the session that opened it. That is wrong on its own terms (a board
watching eight harnesses is not an artifact of whichever session happened to open it), and it is
worse for the notification path, whose whole point is to fire with no browser tab open. Detaching
fixes it.

But a process nothing supervises and nothing reaps is worse than one that dies too early, unless
there is an obvious way to end it. Before this work, "stop it" meant the three platform-specific
`lsof`/`netstat`/`taskkill` blocks in the skill's Stop section, and the `cmd` form matches any port
whose digits contain the string you asked for. That is not an off-switch a person reaches for. So
detaching and a reliable off-switch shipped together, in one change, because neither is worth
shipping alone.

## D-1: `--daemon` detaches, and the socket is bound before it does

On POSIX: bind the listener, then double-fork (`fork`, `setsid`, `fork`), with both parents leaving
through `os._exit(0)` to avoid flushing inherited buffers twice.

Binding first is the load-bearing part. `bind_error_message()` exists so that a busy port produces an
explanation instead of a traceback, and the skill tells the agent to check for an already-running
dashboard when it sees one. A daemon that forks before it binds sends that message to a log file
nobody has been told about yet, and reports success instead. Binding first is what keeps a busy-port
message on the terminal that asked, instead of in a log nobody reads. That is the whole value of
the ordering, and it is easy to get backwards because forking first *looks* more conventional.

`stdin` comes from `os.devnull`; `stdout` and `stderr` are `os.dup2`'d onto the log file so that
writes from C and uncaught tracebacks land there too, not just Python-level prints.

No `chdir("/")`. It is conventional, it buys nothing for a loopback dashboard that resolves every
store path from `HOME`, and it would silently change how any relative path in the process resolves.

## D-2: Windows re-spawns instead of forking, and waits to be sure

There is no `fork`, so the parent starts a fresh copy of itself with
`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`, `stdin` from `DEVNULL`, `stdout`/`stderr` to the log
file, then waits for the child to become reachable, bounded by a named constant,
`DAEMON_READY_TIMEOUT_SEC = 10`, polled against `/api/health`. If the child exits first, or the wait
runs out, the parent prints the tail of its log and exits 1.

That wait is how Windows keeps D-1's promise. The parent cannot observe the child's `bind()`
directly, so it observes the consequence, and a port conflict remains a message on the terminal
rather than a silent failure.

The child needs no private flag: it is an ordinary foreground run that happens to own no console. One
fewer argument, and one fewer way for the two paths to diverge.

The Windows branch has to be checked, and the re-spawn dispatched, *before* the POSIX bind-then-fork
path runs. Reversing that order means the parent holds the listening socket it is supposed to be
handing to the child.

## D-3: One state file per port, written by every instance that binds

`~/.cargento/cargento-<port>.json` holds `pid`, `port`, `started`, `log` and `python`;
`~/.cargento/cargento-<port>.log` is the log. The directory is created `0o700`. `CARGENTO_HOME`
relocates it, which is how this project already treats store locations: when the variable is set it
is authoritative.

One layout on every platform. `XDG_RUNTIME_DIR` on Linux, `%LOCALAPPDATA%` on Windows and a
`~/.cargento` fallback would be three code paths, three sets of documentation and three ways for
`--status` to look in the wrong place, to place a file more correctly than anyone needs.

Foreground runs write it too. A user who started the server without `--daemon` still benefits from
`--status` and `--stop`, and a state file that exists only sometimes is a state file whose absence
means nothing.

This adds the only paths Cargento writes. `CONTRIBUTING.md`'s read-only constraint is about harness
stores and still holds exactly as written, but `SECURITY.md` has to say what is written and where:
including that nothing ever deletes or rotates the log, so `~/.cargento` accumulates one log per port
indefinitely.

## D-4: Liveness is an HTTP probe. Never a signal, and never `os.kill`

`os.kill(pid, 0)` is the usual liveness check, and it must not be used here. On Windows, CPython
implements `os.kill` for ordinary signal numbers through `TerminateProcess`, the call that is
supposed to inspect a process kills it instead. This is not a hypothetical: it is the kind of thing
that looks correct in a POSIX-only test run and only shows up once someone runs `--status` on
Windows and kills the very process they asked about. A cross-platform `--status` built on `os.kill`
would terminate the dashboard it was asked to describe.

So `--status` reads the state file, requests `/api/health`, and compares the pid it gets back:

| Observation | Report |
|---|---|
| pid matches | running, with uptime and URL |
| connection refused, state file present | stale; `--stop` deletes the file and says so |
| connection refused, no state file | absent: nothing recorded and nothing listening |
| answered, different pid | the port belongs to another process, so touch nothing |

The last row is why the pid is in the health response at all. Without it, "something is listening"
reads as "Cargento is running", and the next step is a kill aimed at an innocent process.

`--stop` is idempotent by design: it exits 0 whether it stopped a running instance, cleaned up a
stale state file, or found nothing at all, and exits 1 only in the foreign-process case, the one
case where it deliberately did nothing. A script can call `--stop` unconditionally before starting a
fresh instance.

## D-5: Stopping is one code path, over HTTP, shared by the button and the CLI

`--stop` POSTs `/api/shutdown`, which is exactly what the UI button does. Two ways to ask for a stop,
one implementation of stopping, no signal-handling differences between platforms to reconcile.

A wedged server that has stopped serving cannot be stopped this way. The existing per-platform kill
blocks therefore stay in the skill body, demoted from the documented way to stop Cargento to the last
resort for a server that has stopped answering. A `--force` flag that reimplements them in Python is
not worth its own cross-platform surface.

`--daemon` combined with `--diagnose`, `--stop` or `--status` is an argparse error. Each of those
three exits without serving, so `--daemon` cannot mean anything alongside them, and accepting it
silently would teach that it had been honored.

## D-6: The two new routes, and why stopping happens on its own thread

`GET /api/health` returns `{"ok": true, "pid": …, "port": …, "started": …}` and touches no
filesystem. The skill previously sent the agent to `/api/data` to ask whether a dashboard is up,
which runs a full scan across every harness store to answer a yes-or-no question.

`POST /api/shutdown` returns `{"ok": true, "stopping": true}` and is gated by the existing
`_local_ok()`: the `Host`, `Origin` and `Sec-Fetch-Site` checks that already protect `/api/notify`.
It responds *before* stopping, and calls `server.shutdown()` on a thread it spawns.
`main()` removes the state file in a `finally` and exits 0.

An earlier revision of this design justified that thread as deadlock avoidance, on the theory that a
handler cannot call `server.shutdown()` from inside itself without the accept loop hanging. That
reasoning does not hold here, and it is worth being precise about why: the listener is a
`ThreadingHTTPServer`, so `ThreadingMixIn.process_request` gives every request its own thread, and
the accept loop is never the thread that dispatched the handler. `BaseServer.shutdown`'s deadlock
warning describes a server whose handler runs on the same thread as `serve_forever`, the case a
threading listener is already clear of. Calling `shutdown()` inline here would not deadlock.

The thread earns its place for two duller reasons instead. First, `shutdown()` blocks until the
accept loop notices the request, which can take up to one poll interval (0.5s by default); running it
inline would hold the client open for that long just to deliver "stopping". Second, it keeps the code
correct if the listener class ever stops being a threading one. At that point the handler *would*
run on the serve loop's own thread, and an inline call really would deadlock exactly as the docstring
warns. The thread costs nothing today and removes a footgun for whoever touches this later.

The exposure is worth stating plainly rather than leaving implicit. Any local process that can reach
the port could already read every session on the machine through `/api/data`. It can now also stop
the server, a smaller capability than the one already granted, gated by the same trust boundary and
the same `_local_ok()` checks. `SECURITY.md` says so rather than leaving a reader to work it out.

## D-7: The button arms before it fires, and the stopped page is not the stalled page

A `stop` button sits beside the display toggle, in both display modes. The first click arms it in
place, asking for confirmation; the second POSTs. `esc` or a click elsewhere disarms.

`stopArmed` lives in a module variable and is reapplied after each render, which is the rule
`CONTRIBUTING.md` already states for anything a reader set: `#app` is rebuilt from scratch every five
seconds, so state that is not reapplied is state the refresh eats. Here that rule has teeth: a
button that disarmed itself on the next poll would arm and disarm under the reader's cursor.

No keystroke is bound to stopping. Calm mode gives single keys to moving, expanding and filtering,
all of which are free to get wrong.

On success the page enters a terminal stopped panel and stops polling. Falling through to the
existing "stalled · retrying every 5s" banner would be actively misleading: nothing is retrying,
nothing is coming back, and the reader is the one who ended it. A failed POST shows the error inline
and disarms, because the server is still running and the page should not pretend otherwise.

## Verified: the macOS notification path survives detaching

The one thing this design refused to assume rather than reason about: whether `osascript display
notification`, fired from a fully double-forked session leader with no controlling terminal, still
reaches the user's Aqua session. It does. A `--daemon` server, started under a temporary
`CARGENTO_HOME`, received a `permission_request` POST and answered `{"ok":true}`; its log file stayed
at 0 bytes, and `notify_mac()` logs any non-zero `osascript` exit through `diag()`, which in a
daemon, goes to that same log file, so a silent log is itself the evidence that `osascript`
reported success. A control `osascript` invocation in the same shell exited 0 for comparison.

The double-fork keeps the daemon in the user's login session rather than moving it to a new one,
which is why this works, and it is the main reason daemon mode is worth having: delivering the popup
with no browser tab open at all.

One caveat worth keeping attached to this result: it proves `osascript` reported success, not that a
banner was visibly displayed. Focus modes and Do Not Disturb can still suppress on-screen display
independently of whether the process is attached to a session. That is a macOS notification-center
setting, not something detaching affects one way or the other.

The equivalent question for Linux and Windows is not this design's to close; it is
[`plans/native-notifications.md`](plans/native-notifications.md), which daemon mode makes more
valuable and does not otherwise touch.

## Rejected

- **Documenting `nohup` and `Start-Process` instead of writing code.** Cheapest, and it leaves the
  agent choosing between per-shell incantations that cannot be tested. The old Start section was
  already three code blocks for one idea.
- **Signals for stopping.** D-4: unusable on Windows, and D-5 gets one code path without them.
- **`psutil` for process liveness.** Stdlib only, permanently.
- **An idle timeout that exits on its own.** The request was a way to turn Cargento off, and there is
  now a button and a flag. A dashboard that vanishes because nobody looked at it is a new surprise,
  not a fix for the old one.
- **Platform-correct runtime directories.** D-3.
