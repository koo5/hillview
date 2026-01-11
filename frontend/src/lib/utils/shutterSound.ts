import { photoCaptureSettings } from '$lib/stores';
import { get } from 'svelte/store';

export function playShutterSound() {
	if (!get(photoCaptureSettings).shutterSoundEnabled) return;

	try {
		// Create a realistic camera shutter sound using Web Audio API
		const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();

		// Create multiple components for a realistic shutter sound
		const createShutterClick = (startTime: number, frequency: number, duration: number, volume: number) => {
			const oscillator = audioContext.createOscillator();
			const gainNode = audioContext.createGain();
			const filter = audioContext.createBiquadFilter();

			// Use square wave for sharper, more mechanical sound
			oscillator.type = 'square';
			oscillator.frequency.value = frequency;

			// High-pass filter to make it sound more crisp and mechanical
			filter.type = 'highpass';
			filter.frequency.value = 200;
			filter.Q.value = 1;

			oscillator.connect(filter);
			filter.connect(gainNode);
			gainNode.connect(audioContext.destination);

			// Sharp attack and quick decay for click sound
			gainNode.gain.setValueAtTime(0, startTime);
			gainNode.gain.linearRampToValueAtTime(volume, startTime + 0.002);
			gainNode.gain.exponentialRampToValueAtTime(0.001, startTime + duration);

			oscillator.start(startTime);
			oscillator.stop(startTime + duration);
		};

		const now = audioContext.currentTime;

		// Create the classic "ka-click" shutter sound with two distinct clicks
		// First click (shutter opening) - higher pitch, shorter
		createShutterClick(now, 1200, 0.05, 0.4);

		// Second click (shutter closing) - slightly lower pitch, a bit later
		createShutterClick(now + 0.08, 900, 0.06, 0.35);

		// Add a subtle mechanical noise burst for realism
		const noiseGain = audioContext.createGain();
		const filter2 = audioContext.createBiquadFilter();

		// Create white noise for mechanical sound
		const bufferSize = audioContext.sampleRate * 0.1;
		const noiseBuffer = audioContext.createBuffer(1, bufferSize, audioContext.sampleRate);
		const output = noiseBuffer.getChannelData(0);
		for (let i = 0; i < bufferSize; i++) {
			output[i] = Math.random() * 2 - 1;
		}

		const noiseSource = audioContext.createBufferSource();
		noiseSource.buffer = noiseBuffer;

		// Band-pass filter for the noise to sound more mechanical
		filter2.type = 'bandpass';
		filter2.frequency.value = 800;
		filter2.Q.value = 2;

		noiseSource.connect(filter2);
		filter2.connect(noiseGain);
		noiseGain.connect(audioContext.destination);

		// Very quiet noise burst between the clicks
		noiseGain.gain.setValueAtTime(0, now);
		noiseGain.gain.linearRampToValueAtTime(0.08, now + 0.04);
		noiseGain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);

		noiseSource.start(now + 0.03);
		noiseSource.stop(now + 0.13);

	} catch (error) {
		console.warn('Failed to play shutter sound:', error);
	}
}
