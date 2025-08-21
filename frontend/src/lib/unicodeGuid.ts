export function generateUnicodeGuid(): string {
	// Arrays of interesting Unicode characters grouped by theme
	const symbols = [
		// Celestial
		'✨', '⭐', '🌟', '💫', '☄️', '🌙', '🌞', '🪐', '🌌', '🌠',
		// Nature
		'🌸', '🌺', '🌻', '🌷', '🌹', '🌿', '🍀', '🌳', '🌲', '🌴',
		// Gems & Shapes
		'💎', '💠', '🔷', '🔶', '🔸', '🔹', '▪️', '▫️', '◾', '◽',
		// Animals
		'🦋', '🐉', '🦄', '🐬', '🦜', '🦚', '🦢', '🐙', '🦑', '🐠',
		// Elements
		'🔥', '💧', '🌊', '⚡', '❄️', '🌪️', '☁️', '🌈', '☀️', '🌤️',
		// Mystical
		'🔮', '🗿', '🛸', '👁️', '🌀', '♾️', '☯️', '🕉️', '☮️', '🔯',
		// Mathematical & Technical
		'∞', '∑', '∏', '√', '∫', '∂', '∇', '∆', 'Ω', 'Φ',
		// Arrows & Directions
		'➤', '⟹', '⟸', '⟷', '⟶', '↻', '↺', '⤴️', '⤵️', '↗️',
		// Musical
		'♪', '♫', '♬', '♭', '♮', '♯', '𝄞', '𝄢', '🎵', '🎶',
		// Chess & Games
		'♔', '♕', '♖', '♗', '♘', '♙', '♚', '♛', '♜', '♝'
	];

	// Generate a 6-character GUID using random Unicode symbols
	const guidLength = 6;
	let guid = '';
	
	for (let i = 0; i < guidLength; i++) {
		const randomIndex = Math.floor(Math.random() * symbols.length);
		guid += symbols[randomIndex];
	}
	
	return guid;
}

