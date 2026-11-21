import { describe, it, expect } from 'vitest';
import { ineligibleReasons, PANORAMAX_GATE_TEXT } from './panoramaxStatus';

describe('ineligibleReasons', () => {
	it('words each failed gate', () => {
		expect(ineligibleReasons(['doodles', 'thumbs_down'])).toEqual([
			'it has anonymization doodles',
			'it has a thumbs-down rating',
		]);
	});

	it('lets a grant outside the scope stand alone', () => {
		expect(ineligibleReasons(['grant', 'owner_share', 'moderator_approval'])).toEqual([
			PANORAMAX_GATE_TEXT.grant,
		]);
	});

	it('words the level gates', () => {
		expect(ineligibleReasons(['bearing', 'pitch', 'roll'])).toEqual([
			'it has no bearing',
			'its up/down tilt was not measured or is over 20°',
			'its horizon tilt was not measured or is over 10°',
		]);
	});

	it('falls back to the gate name for one it does not know', () => {
		expect(ineligibleReasons(['some_new_gate'])).toEqual(['some_new_gate']);
	});
});
