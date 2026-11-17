/**
 * A photo's Panoramax outcome from the sequencer's last pass, as
 * GET /api/photos/{id}/panoramax-status returns it (owner and moderators).
 */
export type PanoramaxOutcome = 'member' | 'suppressed' | 'ineligible' | 'pending';

export interface PanoramaxStatus {
	outcome: PanoramaxOutcome;
	sequence_id: string | null;
	rank: number | null;
	winner_uid: string | null;
	failed_gates: string[];
	decided_at: string | null;
	last_pass_at: string | null;
}

// The level gates' limits: MAX_PITCH_DEG and MAX_ROLL_DEG in
// backend/panoramax/app/eligibility.py. The capture screen's level indicator says
// what the gates will decide, so it reads these too; capturePoseMath.test.ts pins
// them to backend/common/capture_pose_cases.json, which the backend pins to
// eligibility.py.
export const MAX_PITCH_DEG = 20;
export const MAX_ROLL_DEG = 10;

// One phrase per gate in GATES (backend/panoramax/app/eligibility.py).
export const PANORAMAX_GATE_TEXT: Record<string, string> = {
	grant: 'its upload grant is not offered to Panoramax',
	owner_share: 'Panoramax sharing is off',
	moderator_approval: 'a moderator has not approved it',
	contributor: 'the owner is not a Panoramax contributor',
	detections: 'it has no anonymization record',
	manual_anonymization: 'it was anonymized by hand',
	doodles: 'it has anonymization doodles',
	deleted: 'it is deleted',
	private: 'it is private',
	processing: 'its processing has not completed',
	location: 'it has no location',
	coordinates: 'its coordinates cannot be placed on the grid',
	capture_time: 'it has no capture time',
	renditions: 'it has no renditions',
	location_accuracy: 'its location fix is too inaccurate',
	blurry: 'it was judged blurry',
	bearing: 'it has no bearing',
	pitch: `its up/down tilt was not measured or is over ${MAX_PITCH_DEG}°`,
	roll: `its horizon tilt was not measured or is over ${MAX_ROLL_DEG}°`,
	analysis: 'it has not been analyzed',
	signage: 'its analysis found signage',
	owner_inactive: 'the owner’s account is inactive',
	thumbs_down: 'it has a thumbs-down rating',
	unresolved_flag: 'it has an unresolved flag',
};

/** Why an ineligible photo stayed out, in words. A photo whose grant is not
 * offered at all fails most other gates by consequence (sharing, approval),
 * so that reason stands alone. */
export function ineligibleReasons(gates: string[]): string[] {
	const shown = gates.includes('grant') ? ['grant'] : gates;
	return shown.map((gate) => PANORAMAX_GATE_TEXT[gate] ?? gate);
}
