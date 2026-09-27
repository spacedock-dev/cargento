# Pi extension prompts, 0.85.1

[ui-prompts-0.85.1-macos.jsonl](ui-prompts-0.85.1-macos.jsonl) records real
`@earendil-works/pi-coding-agent@0.85.1` on macOS, driven through a Python PTY
with the shipped JavaScript adapter. A second contained install confirmed the same version
and automatic discovery of a copied adapter. Neither run changed the operator's Pi settings.

The prompt records retain native event spelling, field names, and the closed `kind` and
`reason` vocabularies. Those are Pi's names, not user text. Session numbers group equality
of observed IDs without retaining an ID. Identity evidence compares the complete context ID,
persisted header ID, and collected `sid`; no prefix or native path is committed.
Titles and answers are omitted even though four native kinds include a title field.

All five kinds were held and closed through the real CLI. A separate single-prompt pass
observed each appear in Attention and disappear after answering or cancellation.
Sessions initially omitted elapsed time; the corrected candidate displayed
“Waiting for input · 25s” in the same row. A close means the UI closed, not that approval succeeded.

The negative cases are part of the measurement: before persistence, a start had no collector
row to join; stock “Trust project folder?” emitted `project_trust`, no prompt pair and no
`session_start`. Missing adapter and disabled events left block state unreadable.
An enabled dashboard restart lost a standing custom wait and disclosed the missing reading.
After a resolved overlay expired, the row returned to unknown coverage.
The live custom UI also closed while its reporting HTTP request was still unanswered.

## Reproduce in a contained installation

Use a disposable directory, a spare dashboard port and an unused local model port.
The run used ports 48681 and 48682. Keep the normal dashboard separate.
Set `SKILL` to the directory containing the candidate's `server.py` and
`pi_extension.js`, and create a temporary `LAB` directory:

```bash
npm install --prefix "$LAB/pi" --no-audit --no-fund @earendil-works/pi-coding-agent@0.85.1
mkdir -p "$LAB/agent" "$LAB/project" "$LAB/dashboard"
export PI_CODING_AGENT_DIR="$LAB/agent" PI_OFFLINE=1 PI_TELEMETRY=0
export CARGENTO_HOME="$LAB/dashboard" CARGENTO_PORT=48681
```

Save this local model endpoint as `$LAB/model.py` and run it in a separate terminal.
It returns one controlled reply without a credential or vendor request.

```python
from http.server import HTTPServer, BaseHTTPRequestHandler
import json


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for delta, reason in [
            ({"role": "assistant", "content": "Controlled local capture."}, None),
            ({}, "stop"),
        ]:
            chunk = {
                "id": "capture",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "capture-model",
                "choices": [{"index": 0, "delta": delta, "finish_reason": reason}],
            }
            self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", 48682), Handler).serve_forever()
```

Write `$LAB/agent/models.json`:

```json
{"providers":{"capture":{"baseUrl":"http://127.0.0.1:48682/v1","api":"openai-completions","apiKey":"dummy","models":[{"id":"capture-model","reasoning":false}]}}}
```

Save this controlled prompt extension as `$LAB/probe.js`. It records shapes and
context/header equality under the isolated agent directory. Compare the native context ID
with `/api/data` locally; never commit the ID or the native session path.

```javascript
import {appendFileSync, existsSync, readFileSync} from "node:fs";
export default function(pi) {
  const write = record => appendFileSync(process.env.PI_CODING_AGENT_DIR + "/capture-shapes.jsonl", JSON.stringify(record) + "\n");
  const record = (event, ctx) => {
    const id = ctx.sessionManager.getSessionId(), file = ctx.sessionManager.getSessionFile();
    const persisted = typeof file === "string" && existsSync(file);
    const header = persisted ? JSON.parse(readFileSync(file, "utf8").split("\n")[0]) : null;
    write({event: event.type, keys: Object.keys(event).sort(), kind: event.kind, reason: event.reason,
      persisted, id_length: id.length, context_equals_header: persisted ? header.id === id : null});
  };
  for(const event of ["ui_prompt_start", "ui_prompt_end", "session_start"]) pi.on(event, record);
  pi.on("project_trust", () => write({event: "project_trust"}));
  pi.registerCommand("capture", {description: "Controlled prompt", handler: async(kind, ctx) => {
    if(kind === "select") await ctx.ui.select("Capture select", ["Continue"]);
    if(kind === "confirm") await ctx.ui.confirm("Capture confirm", "Continue capture?");
    if(kind === "input") await ctx.ui.input("Capture input");
    if(kind === "editor") await ctx.ui.editor("Capture editor", "");
    if(kind === "custom") await ctx.ui.custom((_tui, _theme, _keys, done) => ({
      render: () => ["Capture custom: press any key"], invalidate() {},
      handleInput() { done("done"); }
    }));
  }});
}
```

Start the dashboard from the candidate with the isolated environment above, `--port 48681`,
and `--no-usage --no-observer-model --no-git --no-focus --no-history --no-dismiss
--no-annotations --no-ask --no-irreversible --no-tripwires --no-spacedock`.
From `$LAB/project`, run:

```bash
node "$LAB/pi/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js" \
  --offline --no-extensions -e "$SKILL/pi_extension.js" -e "$LAB/probe.js" \
  --no-skills --no-prompt-templates --no-themes --no-context-files --no-tools \
  --provider capture --model capture-model --api-key capture-local-unused
```

Before any model turn, `/capture select` produces no new collected row. Close it, send
one controlled model prompt, and verify the resulting header ID equals the native context
ID and collected `sid`. Run `/capture` once per kind, taking native, API and browser
observations while held and after closing. Use Enter for select, Escape for confirm,
controlled text plus Enter for input, Escape for editor, and a key for custom.

For the absence controls, repeat with the adapter omitted, with `--no-events`, and with
an enabled dashboard restarted while a prompt stands. Reload the browser after every restart.
For automatic discovery, copy the adapter to `$LAB/agent/extensions/cargento.js`, omit
its explicit `-e` and `--no-extensions`, then resume the persisted session.
For stock trust, use a fresh project containing an empty `.pi/settings.json`; observe
`project_trust` passively without returning a trust decision. No prompt pair or new row should appear.
For the timeout control, replace only the isolated dashboard with a hanging loopback endpoint
and a disposable Pi capability; verify a key still closes the native prompt before the HTTP deadline.

Stop every Pi process, local model endpoint, substitute endpoint and dashboard you started.
Commit only sanitized shapes and equality verdicts. The exact version is a measurement;
other versions, nested prompt arrangements and other platforms need their own evidence.

## A validation run, 0.87.1

[validation-results-0.87.1-macos.jsonl](validation-results-0.87.1-macos.jsonl) records what
Pi's `isError` means on a bash call, for DRC-4690. It keeps key sets, the flag, which of Pi's
own status lines ended the result text and its exit code, which of DEC-23's closed summary
patterns matched, and timings. It keeps no output text, command, path or id.

The install was `npm install --prefix "$LAB/pi" @earendil-works/pi-coding-agent@0.87.1` into a
scratch directory, with `PI_CODING_AGENT_DIR="$LAB/agent" PI_OFFLINE=1 PI_TELEMETRY=0`. The
model was a loopback endpoint on an unused port, registered in `$LAB/agent/models.json` as above.
It differs from the prompt capture's endpoint in one way: when the last message is not a tool
result it streams one `tool_calls` delta naming `bash`, with the command read from a file, and
finishes with `tool_calls`; after the tool result it streams `done` and stops. Each run was one
print-mode session from a scratch project holding two tiny pytest files and two `node:test`
files:

```bash
node "$LAB/pi/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js" \
  --offline --no-extensions --no-skills --no-prompt-templates --no-themes --no-context-files \
  --tools bash --provider capture --model capture-model --api-key capture-local-unused \
  --session-dir "$LAB/cases/<case>" -p "run it" </dev/null
```

Redirect stdin. With it inherited, print mode waits on it and never reaches the model.

`isError` was set on exactly the runs whose text ended in a status line, and every nonzero exit
ended in `Command exited with code N`. `dist/core/tools/bash.js` says why: the tool throws on a
nonzero exit, a timeout, an abort and a missing exit code, and appends one status line after any
truncation notice. So the runtime reads a set flag with the exit line as a nonzero exit, a set
flag with a timeout or abort line as a run with no result, and a set flag with no status line as
a call that never ran. A clear flag is an exit of 0 for the whole call, which is why the run that
ended in `; true` reads clear beside its own failure summary.

The endpoint was stopped and the scratch install removed after the runs. Other versions need
their own evidence.
