import { acquireTestLock } from './testLock';

/** Contribution tests create and remove only their own account and photos. */
export default async function setup() {
	await acquireTestLock();
}
