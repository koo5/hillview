"""Upload CC-licensed test photos through the real upload path, shaped so the
sequencer has something interesting to split.

Used by e2e_federation.sh. Goes through the full authorize → worker → process
flow (SecureUploadClient), so the photos end up with real derivatives in
`sizes` — which is what the federation API serves as assets.

Photos are laid out as N sessions of M photos: within a session, captures are
minutes apart; between sessions, a gap wider than PANORAMAX_SESSION_GAP_HOURS.
So a successful run must produce exactly N sequences for the test user.
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(BACKEND, 'tests'))
sys.path.insert(0, BACKEND)

from utils.image_utils import create_test_image_full_gps  # noqa: E402
from utils.secure_upload_utils import SecureUploadClient  # noqa: E402
from utils.test_utils import wait_for_photo_processing  # noqa: E402

API_URL = os.getenv('API_URL', 'http://localhost:8055/api')
# The API hands clients the deployment's public WORKER_URL (e.g. a Caddy vhost
# that only resolves inside the VM). For a local e2e run we talk to the worker
# directly instead of routing through whatever the deployment advertises.
WORKER_URL = os.getenv('WORKER_URL_E2E', 'http://localhost:8056')

# Prague-ish, walked west→east so consecutive photos are ~40 m apart (under the
# catalog's 75 m line-drawing threshold, so harvested sequences render as lines)
BASE_LAT, BASE_LON = 50.0755, 14.4378
STEP_LON = 0.00055


async def seed(sessions: int, per_session: int, gap_hours: float) -> list[str]:
	client = SecureUploadClient(api_url=API_URL)
	setup = await client.setup_test_environment()
	token = await client.test_user_auth(setup)
	keys = client.generate_client_keys()
	await client.register_client_key(token, keys)

	start = datetime.now(timezone.utc) - timedelta(days=2)
	photo_ids: list[str] = []
	n = 0
	for s in range(sessions):
		session_start = start + timedelta(hours=s * (gap_hours + 1))
		for i in range(per_session):
			captured = session_start + timedelta(minutes=2 * i)
			lat = BASE_LAT
			lon = BASE_LON + STEP_LON * n
			bearing = (90 + 5 * i) % 360
			image = create_test_image_full_gps(240, 180, (40 * s % 255, 90, 160), lat, lon, bearing)
			filename = f"panoramax_e2e_s{s}_p{i}.jpg"
			auth = await client.authorize_upload_with_params(
				auth_token=token,
				filename=filename,
				file_size=len(image),
				latitude=lat,
				longitude=lon,
				description=f"panoramax e2e session {s} photo {i}",
				file_data=image,
				captured_at=captured.isoformat(),
				license='ccbysa4+osm',
				title=f"E2E session {s} #{i}",
			)
			auth['worker_url'] = WORKER_URL
			await client.upload_to_worker(image, auth, keys, filename=filename)
			photo_ids.append(auth['photo_id'])
			n += 1
			print(f"  uploaded {filename} -> {auth['photo_id']}")

	print(f"waiting for processing of {len(photo_ids)} photos…")
	failed = []
	for pid in photo_ids:
		photo = wait_for_photo_processing(pid, token, timeout=120)
		if photo.get('processing_status') != 'completed':
			failed.append((pid, photo.get('processing_status'), photo.get('error')))
	if failed:
		for pid, status, err in failed:
			print(f"  FAILED {pid}: {status} ({err})", file=sys.stderr)
		raise SystemExit(f"{len(failed)}/{len(photo_ids)} photos did not process")

	print(f"seeded {len(photo_ids)} photos in {sessions} sessions")
	return photo_ids


def main() -> None:
	p = argparse.ArgumentParser(description=__doc__)
	p.add_argument('--sessions', type=int, default=3)
	p.add_argument('--per-session', type=int, default=4)
	p.add_argument('--gap-hours', type=float,
		default=float(os.getenv('PANORAMAX_SESSION_GAP_HOURS', '3')))
	p.add_argument('--out', help="write the uploaded photo ids here, one per line")
	args = p.parse_args()

	ids = asyncio.run(seed(args.sessions, args.per_session, args.gap_hours))
	if args.out:
		with open(args.out, 'w') as f:
			f.write('\n'.join(ids) + '\n')


if __name__ == '__main__':
	main()
