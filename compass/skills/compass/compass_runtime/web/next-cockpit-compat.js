/* The semantic timeline and terminal are source-backed prototype mechanisms,
   shared byte-for-byte with the stable cockpit. This next-only compatibility
   seam supplies the small stable-page vocabulary they consume; it does not
   import the stable page's project navigation or render it. */
const sessKey = session => `${String(session && session.harness || "")}:` +
  `${String(session && (session.sid || session.session) || "")}`;
const fmtDur = seconds => nextFormatDuration(seconds) || "0s";
const NEXT_COCKPIT_SHARED = true;
let lastData = null;

function render(_data){
  renderNext();
}
