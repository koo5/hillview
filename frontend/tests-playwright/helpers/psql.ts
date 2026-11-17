/**
 * Read a value the API does not serve, straight from the dev database.
 *
 * The same route as backend/tests/integration/test_capture_pose_upload.py's
 * psql(): `docker exec` into hillview_postgres, unless PANORAMAX_TEST_PSQL names
 * another command (split on whitespace here). Read-only use only: the test
 * helpers own every write.
 */
import { execFileSync } from 'child_process';

export function psql(query: string): string {
	const override = process.env.PANORAMAX_TEST_PSQL?.trim();
	const command = override
		? override.split(/\s+/)
		: ['docker', 'exec', '-i', 'hillview_postgres', 'psql',
			'-U', process.env.POSTGRES_USER || 'hillview', '-d', process.env.POSTGRES_DB || 'hillview'];
	return execFileSync(command[0], [...command.slice(1), '-v', 'ON_ERROR_STOP=1', '-tA'], {
		input: query,
		encoding: 'utf8'
	}).trim();
}
