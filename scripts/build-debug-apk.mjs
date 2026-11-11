import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const androidDir = path.join(root, 'android');
const windows = process.platform === 'win32';
const command = windows ? 'gradlew.bat' : './gradlew';
const result = spawnSync(command, ['assembleDebug'], {
  cwd: androidDir,
  stdio: 'inherit',
  shell: windows,
});

if (result.error) {
  console.error(`Could not start ${command}: ${result.error.message}`);
  process.exit(1);
}
process.exit(result.status ?? 1);
