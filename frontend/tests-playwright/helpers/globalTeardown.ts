import { releaseTestLock } from './testLock';

async function globalTeardown() {
  releaseTestLock();
}

export default globalTeardown;
