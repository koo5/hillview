// Photo interface that covers both UserPhoto and ActivityPhoto
export interface PhotoItemData {
	id: string;
	original_filename: string;
	uploaded_at: string;
	captured_at?: string;
	processing_status: string;
	latitude?: number;
	longitude?: number;
	bearing?: number;
	width?: number;
	height?: number;
	sizes?: Record<string, { path: string; url: string; width: number; height: number }>;
	description?: string;
	// Activity-specific fields
	owner_username?: string;
	owner_id?: string;
}