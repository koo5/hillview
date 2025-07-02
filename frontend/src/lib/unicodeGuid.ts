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

export function sanitizeFilename(filename: string): string {
	// Some filesystems might have issues with certain Unicode characters
	// This function can be expanded if needed to handle edge cases
	// For now, we'll just ensure no path separators
	return filename.replace(/[\/\\]/g, '_');
}