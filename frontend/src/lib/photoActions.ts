/**
 * Reusable photo action helpers (pure / side-effect only on the server API).
 *
 * These functions are extracted from PhotoActionsMenu.svelte so they can be
 * shared with /photo/[uid]/+page.svelte and any future photo UI. They never
 * reach into component-local state — callers pass the photo in and read the
 * returned result to update their own state.
 */

import { get } from 'svelte/store';
import { http, handleApiError } from '$lib/http';
import { simplePhotoWorker } from '$lib/simplePhotoWorker';
import { myGoto } from '$lib/navigation.svelte';
import { constructUserProfileUrl } from '$lib/urlUtilsServer';
import { openExternalUrl } from '$lib/urlUtils';
import { getPhotoSource, getUserId, getPhotoDetailUrl, getCanonicalPhotoUrl } from '$lib/photoUtils';
import type { PhotoData } from '$lib/sources';
import { track } from '$lib/analytics';

export type Rating = 'thumbs_up' | 'thumbs_down';

export interface RatingState {
    userRating: Rating | null;
    ratingCounts: { thumbs_up: number; thumbs_down: number };
}

export interface PhotoActionResult {
    success: boolean;
    message: string;
    error: boolean;
    alreadyFlagged?: boolean;
}

const EMPTY_RATING: RatingState = {
    userRating: null,
    ratingCounts: { thumbs_up: 0, thumbs_down: 0 }
};

/** Hide a photo from the current user's gallery. */
export async function hidePhotoRequest(photo: PhotoData): Promise<PhotoActionResult> {
    try {
        const photoSource = getPhotoSource(photo);
        const response = await http.post('/hidden/photos', {
            photo_source: photoSource,
            photo_id: photo.id,
            reason: 'Hidden from gallery'
        });

        if (!response.ok) {
            throw new Error(`Failed to hide photo: ${response.status}`);
        }

        if (photoSource) {
            simplePhotoWorker.removePhotoFromCache?.(photo.id, photoSource);
        }

        return { success: true, message: 'Photo hidden successfully', error: false };
    } catch (err) {
        console.error('🢄Error hiding photo:', err);
        return {
            success: false,
            message: `Error: ${handleApiError(err)}`,
            error: true
        };
    }
}

/**
 * Toggle a rating on a photo. If the user already has the same rating it is
 * removed, otherwise it is set. Returns the new RatingState.
 */
export async function togglePhotoRating(
    photo: PhotoData,
    rating: Rating,
    currentUserRating: Rating | null
): Promise<RatingState> {
    const photoSource = getPhotoSource(photo);

    const removing = currentUserRating === rating;
    const event = rating === 'thumbs_up'
        ? (removing ? 'likeUnset' : 'likeSet')
        : (removing ? 'dislikeUnset' : 'dislikeSet');
    track(event);
    if (removing) {
        // Remove rating
        const response = await http.delete(`/ratings/${photoSource}/${photo.id}`);
        if (!response.ok) {
            throw new Error(`Failed to update rating: ${response.status}`);
        }
        // Re-fetch counts after removal
        const getRatingResponse = await http.get(`/ratings/${photoSource}/${photo.id}`);
        if (getRatingResponse.ok) {
            const data = await getRatingResponse.json();
            return {
                userRating: null,
                ratingCounts: data.rating_counts ?? EMPTY_RATING.ratingCounts
            };
        }
        return { userRating: null, ratingCounts: EMPTY_RATING.ratingCounts };
    }

    // Set/change rating
    const response = await http.post(`/ratings/${photoSource}/${photo.id}`, { rating });
    if (!response.ok) {
        throw new Error(`Failed to update rating: ${response.status}`);
    }
    const data = await response.json();
    return {
        userRating: data.user_rating as Rating | null,
        ratingCounts: data.rating_counts ?? EMPTY_RATING.ratingCounts
    };
}

/** Fetch the current rating state for a photo. */
export async function fetchPhotoRating(photo: PhotoData): Promise<RatingState> {
    try {
        const photoSource = getPhotoSource(photo);
        const response = await http.get(`/ratings/${photoSource}/${photo.id}`);
        if (!response.ok) return { ...EMPTY_RATING };
        const data = await response.json();
        return {
            userRating: data.user_rating ?? null,
            ratingCounts: data.rating_counts ?? EMPTY_RATING.ratingCounts
        };
    } catch (err) {
        console.error('🢄Error loading rating:', err);
        return { ...EMPTY_RATING };
    }
}

/** Flag a photo for moderation. */
export async function flagPhotoRequest(photo: PhotoData): Promise<PhotoActionResult> {
    try {
        const photoSource = getPhotoSource(photo);
        const response = await http.post('/flagged/photos', {
            photo_source: photoSource,
            photo_id: photo.id,
            reason: 'Flagged for moderation'
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            if (errorData.already_flagged) {
                return {
                    success: true,
                    message: 'Photo already flagged',
                    error: false,
                    alreadyFlagged: true
                };
            }
            throw new Error(`Failed to flag photo: ${response.status}`);
        }

        const data = await response.json();
        return {
            success: true,
            message: data.already_flagged ? 'Photo already flagged' : 'Photo flagged for moderation',
            error: false,
            alreadyFlagged: !!data.already_flagged
        };
    } catch (err) {
        console.error('🢄Error flagging photo:', err);
        return {
            success: false,
            message: `Error: ${handleApiError(err)}`,
            error: true
        };
    }
}

/** Remove a flag on a photo. */
export async function unflagPhotoRequest(photo: PhotoData): Promise<PhotoActionResult> {
    try {
        const photoSource = getPhotoSource(photo);
        const response = await http.delete('/flagged/photos', {
            photo_source: photoSource,
            photo_id: photo.id
        });
        if (!response.ok) {
            throw new Error(`Failed to unflag photo: ${response.status}`);
        }
        return { success: true, message: 'Photo unflagged', error: false };
    } catch (err) {
        console.error('🢄Error unflagging photo:', err);
        return {
            success: false,
            message: `Error: ${handleApiError(err)}`,
            error: true
        };
    }
}

/**
 * Query whether the current user has flagged this photo.
 * Only meaningful for authenticated users; callers should guard.
 */
export async function fetchIsFlagged(photo: PhotoData): Promise<boolean> {
    try {
        const response = await http.get('/flagged/photos');
        if (!response.ok) return false;
        const flaggedPhotos = await response.json();
        const photoSource = getPhotoSource(photo);
        return flaggedPhotos.some(
            (fp: any) => fp.photo_source === photoSource && fp.photo_id === photo.id
        );
    } catch (err) {
        console.error('🢄Error checking flag status:', err);
        return false;
    }
}

/**
 * Navigate to the user profile associated with a photo (Hillview or Mapillary).
 * Returns true if navigation was initiated.
 */
export async function viewPhotoUserProfile(photo: PhotoData): Promise<boolean> {
    const photoSource = getPhotoSource(photo);
    const userId = getUserId(photo);

    if (photoSource === 'hillview' && userId) {
        myGoto(constructUserProfileUrl(userId));
        return true;
    }
    if (photoSource === 'mapillary' && (photo as any).creator?.username) {
        const username = (photo as any).creator.username;
        await openExternalUrl(`https://www.mapillary.com/app/user/${username}`);
        return true;
    }
    return false;
}

/**
 * Navigate to the photo's canonical detail page. For Mapillary photos this
 * opens mapillary.com externally; for Hillview photos it SPA-navigates to
 * /photo/[uid]. Returns true if navigation happened.
 */
export function openPhotoDetailPage(photo: PhotoData | null): boolean {
    const url = getCanonicalPhotoUrl(photo);
    if (!url) return false;
    if (/^https?:/i.test(url)) {
        void openExternalUrl(url);
    } else {
        myGoto(url);
    }
    return true;
}
