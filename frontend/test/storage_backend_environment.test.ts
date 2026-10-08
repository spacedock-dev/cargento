// @vitest-environment node
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const root = fileURLToPath(new URL('../../', import.meta.url));
const python =
  process.env['CARGENTO_TEST_PYTHON'] || (process.platform === 'win32' ? 'python' : 'python3');

// The conformance backend must isolate the environment the way the installed smoke backend
// does; Winsock and side-by-side loading need the OS directory on Windows and nothing else.
function isolate(osName: string, environ: Record<string, string>): Record<string, string> {
  const program = [
    'import json, sys',
    'from pathlib import Path',
    "sys.path.insert(0, 'frontend/test')",
    'import storage_backend',
    'environ = json.loads(sys.argv[2])',
    'print(json.dumps(storage_backend.isolated_environment(Path(sys.argv[1]), environ, os_name=sys.argv[3])))',
  ].join('\n');
  const out = execFileSync(
    python,
    ['-I', '-c', program, '/scratch', JSON.stringify(environ), osName],
    {
      cwd: root,
      encoding: 'utf8',
      timeout: 15_000,
      env: { ...process.env, PYTHONPATH: '' },
    },
  );
  return JSON.parse(out) as Record<string, string>;
}

describe('the storage conformance backend environment', () => {
  const host = {
    HOME: '/home/real',
    PATH: '/usr/bin',
    SystemRoot: 'C:\\Windows',
    windir: 'C:\\Windows',
    APPDATA: 'C:\\x',
    HARNESS_STORE_ROOT: '/home/real/.store',
  };

  // Python prints a path with the separators of the machine running the test, so locations are compared
  // with forward slashes.
  const slashes = (value: string | undefined): string => (value ?? '').replaceAll('\\', '/');
  const owned = (environ: Record<string, string>): Record<string, string> =>
    Object.fromEntries(
      Object.entries(environ).map(([key, value]) => [
        key,
        ['SYSTEMROOT', 'WINDIR'].includes(key) ? value : slashes(value),
      ]),
    );

  it('keeps only the owned locations on POSIX', () => {
    expect(owned(isolate('posix', host))).toEqual({
      HOME: '/scratch',
      USERPROFILE: '/scratch',
      CARGENTO_HOME: expect.stringMatching(/state$/) as string,
      PATH: expect.stringMatching(/no-executables$/) as string,
    });
  });

  it('keeps the normalized Windows loader directories on nt and nothing else of the host', () => {
    const result = isolate('nt', host);
    expect(result['SYSTEMROOT']).toBe('C:\\Windows');
    expect(result['WINDIR']).toBe('C:\\Windows');
    expect(Object.keys(result).sort()).toEqual([
      'CARGENTO_HOME',
      'HOME',
      'PATH',
      'SYSTEMROOT',
      'USERPROFILE',
      'WINDIR',
    ]);
    expect(slashes(result['HOME'])).toBe('/scratch');
    expect(slashes(result['PATH'])).toMatch(/no-executables$/);
  });
});
