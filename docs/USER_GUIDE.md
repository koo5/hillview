# Hillview User Guide

*Identify what you're looking at from any hilltop*

---

## What is Hillview?

Ever stood on a hilltop wondering "What am I looking at?" Hillview is a photo mapping application that answers that question. It uses geotagged photos with compass bearing data to help you identify distant landmarks, mountain peaks, and other features from any viewpoint.

By combining GPS coordinates with compass direction, Hillview creates a directional photo database that turns your device into a smart viewfinder for the landscape around you. Whether you're hiking, exploring a new city, or just curious about your surroundings, Hillview shows you photos taken from nearby positions pointing in the same direction -- helping you understand what's in front of you.

Hillview is available as a **web app** at [hillview.cz](https://hillview.cz) and as a native **Android app**.

---

## The Main View

![Main map view](screenshots/01-main-map-view.png)

The main screen is split into two halves:

### Photo Viewer (top half)

The upper portion shows a photo taken from the current map location, facing the current compass bearing. Key elements:

- **Compass strip** along the top edge -- shows the current bearing (e.g. "244 SW") with tick marks for surrounding directions
- **Coordinate & altitude overlay** -- displays GPS coordinates, accuracy, and elevation (e.g. `50.114378, 14.523546 +/-1m, 331m`)
- **Timestamp** -- capture date and time shown in the bottom-right corner of the photo
- **Crosshair** -- the green crosshair and tilt indicators help you orient the photo relative to the horizon
- **Previous / Next arrows** -- swipe or tap the left/right arrows to browse through nearby photos
- **Thumbs up / Thumbs down** -- rate the photo (visible in the bottom-right corner)
- **More actions menu** (three dots) -- additional options for the current photo

### Map (bottom half)

The lower portion is an interactive Leaflet map showing:

- **Photo markers** -- green circular markers with directional arrows indicate where photos were taken and which direction they face. The currently viewed photo's marker is highlighted with a dashed circle.
- **Zoom controls** (+/-) and scale bar
- **Navigation buttons** (bottom bar) -- rotate left/right, move forward/backward along the current bearing direction
- **Location tracking** button -- centers the map on your GPS position
- **Compass mode** button -- auto-updates the map bearing based on your device's compass sensor
- **Source toggles** (bottom-right corner) -- checkboxes labeled "H.." (Hillview photos) and "M.." (Mapillary photos) to toggle which photo sources are shown on the map

---

## Navigation Menu

![Navigation menu](screenshots/02-navigation-menu.png)

Tap the hamburger menu (top-left) to access all sections:

| Menu Item | Description |
|-----------|-------------|
| **Map** | Return to the main map + photo view |
| **My Photos** | View and manage your own uploaded photos |
| **Activity** | See a feed of recently uploaded photos from all users |
| **Best of** | Browse top-rated photos ranked by community score |
| **Users** | Discover other Hillview users and view their profiles |
| **Settings** | Camera, upload, compass, and advanced configuration |
| **Login / Register** | Sign in or create an account |
| **About** | Information about the app, version, and acknowledgments |
| **Report Bug** | Submit a bug report |
| **Download App** | Get the Android app |

The menu footer shows the current version number, build commit hash, build timestamp, and API server address.

---

## Account & Authentication

![Login page](screenshots/03-login-page.png)

Hillview supports multiple ways to sign in:

- **Username & password** -- register with a username, email, and password, then log in directly
- **Google OAuth** -- sign in with your Google account via the "Continue with Google" button

Once logged in, you can:
- Upload and manage your own photos
- Rate other users' photos (thumbs up/down)
- Add annotations (comments) to photos
- Flag inappropriate content for review
- Configure push notifications
- Delete your account (with all associated data)

---

## Browsing & Discovering Photos

### Activity Feed

![Activity feed](screenshots/06-activity-feed.png)

The **Activity** page shows recently uploaded photos in a chronological grid, grouped by day and user. Each entry shows:

- A thumbnail of the photo
- The filename or description
- The capture date and time
- The uploader's username (clickable to view their profile)

Tapping a photo opens it on the map view, centered on its GPS location and oriented to its compass bearing. You can load more photos by scrolling down and tapping "Load More Photos."

### Best Of

![Best of page](screenshots/07-best-of.png)

The **Best of** page ranks photos by a composite score that considers:

- **Thumbs-up votes** from the community
- **Number of annotations** the photo has received
- **Image resolution** (higher resolution gets a bonus)

Each photo card shows its score, description (if provided), capture date, and a thumbnail. Tapping a photo opens it on the map. Photos with descriptions show their title prominently (e.g. "Vyhlídka Prosecké skály - východ", "Klokočské skály").

### User Profiles

The **Users** page lets you browse all registered users. Clicking a username anywhere in the app takes you to that user's profile, where you can see all their publicly shared photos.

---

## Photo Interactions

![Photo actions menu](screenshots/04-photo-actions-menu.png)

When viewing any photo, the **three-dot menu** reveals:

- **Username & source** -- shows who uploaded the photo and from which source (Hillview or Mapillary)
- **Share Photo** -- generate a shareable link with social media preview metadata (OpenGraph)
- **Flag for Review** -- report inappropriate content with a reason (reviewed by admins)
- **Hide Photo** -- remove this specific photo from your view (reversible)
- **Hide User** -- hide all photos from this user (reversible)

### Rating Photos

The thumbs-up and thumbs-down buttons let you rate any photo. Your ratings contribute to the photo's community score visible on the Best Of page. You can remove your rating at any time.

### Annotations

You can add text annotations (comments) to photos. Annotations support:

- Free-form text comments on any photo
- Spatial markup (mark a specific region of the photo)
- Version history -- edits create new versions, nothing is permanently lost
- Community participation -- anyone can annotate any photo

---

## Photo Filters

![Photo filters](screenshots/05-filters-modal.png)

The **Filters** button on the map opens a comprehensive filtering modal. Hillview uses AI-based scene analysis to categorize photos, enabling powerful filtering:

### Available Filters

| Filter | Options |
|--------|---------|
| **Max Photos in Area** | Limit how many photos load on the map (default: 100) |
| **Time of Day** | Day, Night, Dawn/Dusk |
| **Location Type** | Outdoors, Indoors |
| **Minimum View Distance** | 100m+, 500m+, 1km+, 5km+ |
| **Maximum Close Object Distance** | <5m, <20m, <50m, <100m, <500m |
| **Scenic Score** | 2+ Good, 3+ Nice, 4+ Great, 5 Exceptional |
| **Visibility Distance** | Near, Medium, Far, Panoramic |
| **Tallest Building** | None, Low-rise, Mid-rise, High-rise, Skyscraper |

### Feature Tags

Filter by specific features detected in photos, organized into categories:

- **Nature**: hill, mountain, river, stream, water body, landscape, rock outcrop, tree-lined path, path, nature
- **Urban**: street, building, cityscape, high-rise building, church, playground, bench
- **Structures**: bridge, tower, observation tower, water tower, cooling tower, crane, curved structure, mast
- **Infrastructure**: lamp post, powerline pole, utility pole, high-mast lighting, row of streetlights, EV charger
- **Activity**: construction, roadworks, ski slope, accident
- **Animals**: cat, dog
- **Other**: art, signage

Active filter count is shown on the Filters button (e.g. "Filters (3)"). A "Clear all filters" button resets everything.

---

## Photo Sources

Hillview displays photos from multiple sources:

### Hillview Photos (user-uploaded)

Photos uploaded by Hillview users through the app's camera or manual upload. These include full EXIF metadata: GPS location, compass bearing, altitude, capture time, and image dimensions. Source toggle: **H..** on the map.

### Mapillary Integration

Hillview integrates with [Mapillary](https://mapillary.com), a collaborative street-level imagery platform. Mapillary photos appear as an additional layer on the map, greatly expanding coverage. The app uses intelligent spatial caching to minimize API calls and provide fast responses. Source toggle: **M..** on the map.

Both sources can be independently toggled on/off, and you can rate or annotate photos from either source.

---

## Uploading Photos

### From the App Camera

1. Tap the **camera button** in the top toolbar
2. Take a photo -- the app automatically captures GPS coordinates and compass bearing from your device sensors
3. The photo enters the upload queue
4. If auto-upload is enabled and you've agreed to the CC BY-SA 4.0 license, it uploads automatically
5. Otherwise, you're prompted whether to upload each photo

### Upload Process

Photo uploads use a secure three-phase process:

1. **Authorization** -- the app requests permission from the server, sending photo metadata
2. **Signed upload** -- the photo is uploaded with a cryptographic (ECDSA) signature to prevent tampering
3. **Server processing** -- the backend extracts EXIF data, generates thumbnails at multiple sizes, and stores the photo with its geospatial data

### Photo Metadata

Each uploaded photo stores:
- GPS coordinates (latitude/longitude)
- Compass bearing (0-360 degrees)
- Altitude
- Capture date and time
- Image dimensions
- File hash (for duplicate detection)
- Optional text description

---

## Map Controls

### Tile Providers

Tap the map layers icon (bottom-right of the map) to switch between different map tile providers. Options include Hillview's own tile server, OpenStreetMap, and others.

### Directional Navigation

The bottom bar provides four directional buttons:

- **Rotate left/right** -- rotates the view by 15 degrees
- **Move forward** -- advances in the current viewing direction
- **Move backward** -- retreats opposite the viewing direction

These let you "walk through" a location by stepping between photos along a path.

### Location & Compass Tracking

- **Location tracking** (crosshair icon) -- centers the map on your device's GPS position
- **Compass mode** (compass icon) -- automatically updates the map bearing based on your device's compass sensor, so the map rotates as you turn your phone

The compass supports multiple sensor modes for accuracy on different devices:
- GAME_ROTATION_VECTOR (default)
- MADGWICK_AHRS (advanced fusion)
- ROTATION_VECTOR (standard)
- COMPLEMENTARY_FILTER (simple)

---

## Settings

![Settings page](screenshots/08-settings.png)

### Camera
- **Shutter sound** -- toggle the camera click sound

### Auto-Upload
- **License agreement** -- you must agree to share photos under CC BY-SA 4.0 before uploading
- **Upload mode**:
  - *Enabled* -- photos upload automatically after capture
  - *Disabled* -- prompts each time
  - *Disabled (Never prompt)* -- no uploads, no prompts

### Compass
- **Landscape mode workaround** -- fixes inverted compass readings when holding the phone sideways

### Advanced Settings
- Developer tools, debug logging, and QR timestamp verification

### Data Sources
- Define custom sources for photos.

### Push Notifications
- Enable/disable push notifications for activity updates (e.g. when someone interacts with your photos)

---

## Content Moderation

### Hiding Content
If you don't want to see certain content:
- **Hide Photo** -- removes a specific photo from your view
- **Hide User** -- hides all photos from a specific user

Hidden content can be managed and unhidden from the **Hidden Content** page (accessible via Settings or menu).

### Flagging Content
If you see inappropriate content:
- **Flag for Review** -- reports the photo to administrators with a reason
- Admins review flagged content and can resolve or take action

---

## Account Management

From the **Account** page (accessible when logged in via the menu):
- View your username, email, and authentication provider
- **Delete Account** -- permanently removes your account and all associated data (photos, ratings, annotations, hidden content records, push registrations). This action requires typing "DELETE" to confirm and cannot be undone.

---

## Android App

Hillview is available as a native Android app built with Tauri, providing:

- **Camera** for taking geotagged photos
- **Device compass & GPS** sensors for accurate bearing and location data
- **Push notifications** for activity updates
- **Offline-ready** design with upload queuing when connectivity is poor

The Android app provides the same full feature set as the web version.

Download: Available from the [Download page](https://hillview.cz/download).

---

## About Hillview

![About page](screenshots/09-about-page.png)

Hillview is an early-access, source-available project. The source code is available on [GitHub](https://github.com/koo5/hillview).

**Built with**: SvelteKit, TypeScript, Tauri, Leaflet, FastAPI, PostgreSQL + PostGIS

**Map data**: OpenStreetMap contributors, TracesTrack

**Photo services**: Mapillary

**Contact**: Use the in-app contact form or file issues on the [GitHub issue tracker](https://github.com/koo5/hillview/issues).

---

*Version 1.29.0 -- Made with love for photographers and explorers.*
