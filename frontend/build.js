import { execSync } from 'child_process';
import path from 'path';

const clientPath = path.resolve('.');

execSync('bun install && bun run build', {
    cwd: clientPath,
    env: { ...process.env, TAURI: 'true' },
    stdio: 'inherit',
    shell: true,
});

