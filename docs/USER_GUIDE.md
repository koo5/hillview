# Hillview User Guide

*Identify what you're looking at from any hilltop*

---

## What is Hillview?

Ever stood on a hilltop wondering "What am I looking at?" Hillview answers that question. Open the app at a viewpoint and see labeled annotations pointing to distant landmarks, buildings, and peaks.

![Annotated panorama with labels](https://hillview.cz/docs/screenshots/desktop/hero-panorama-full.png)

**[Try it now — Prosecké skály viewpoint](https://hillview.cz/?lat=50.11691142317276&lon=14.488375782966616&zoom=20&bearing=139.06&photo=hillview-333e8851-c59b-4133-bce5-2d1ddc2ce335)**

Hillview is available as a **web app** at [hillview.cz](https://hillview.cz) and as a native **Android app**.

---

# I. Exploring Panoramas

The main screen shows a geotagged photo alongside an interactive map.

![Main view with photo and map](https://hillview.cz/docs/screenshots/desktop/hero-panorama.png)

When an annotated panorama is loaded, you'll see green boxes marking labeled features. **Tap the photo** to open the full-screen zoomable viewer, where every annotation becomes readable — building names, peaks, distances, and more.

You can:
- **Zoom and pan** to explore the panorama in detail
- **Tap any annotation** to see its label
- **Draw or Edit** to contribute your own annotations (after logging in)
- **Share** a direct link to the current view

### Browsing photos

Use the **left/right arrows** to step through nearby photos. The map updates to show each photo's location and the direction it faces.

The **Best of** page shows top-rated photos, including annotated panoramas — a good starting point for discovering content.

![Best of page](https://hillview.cz/docs/screenshots/desktop/07-best-of.png)

The **Activity** page shows recently uploaded photos from all users.

![Activity feed](https://hillview.cz/docs/screenshots/desktop/06-activity-feed.png)

### Rating photos

Use the **thumbs up / thumbs down** buttons to rate photos. Ratings feed into the Best of rankings.

---

# II. Hunting Down Points of Interest

Hillview provides tools for investigating and triangulating distant features you can see but can't identify.

### Bearing lines

![Bearing lines on the map](https://hillview.cz/docs/screenshots/desktop/12-bearing-lines.png)

Switch to **Lines** mode to cast bearing lines on the map. Each line extends from a point on the map in the direction you're facing. By placing lines from multiple vantage points, their intersection reveals the location of a distant feature.

- Tap **Add line** to create a line from the current map position along the current bearing
- **Drag** the endpoints or the line itself to adjust
- **Label** each line to keep track of what you're triangulating
- Lines are saved between sessions

### Photo filters

The **Filters** button lets you narrow down which photos appear on the map — useful for finding photos that show the feature you're investigating.

![Photo filters](https://hillview.cz/docs/screenshots/desktop/05-filters-modal.png)

Available filters include time of day, location type, view distance, scenic score, and visibility. You can also filter by AI-detected feature tags — nature, urban, structures, infrastructure, and even specific objects like cats.

### Photo sources

Hillview shows photos from two sources, toggled independently on the map:

- **H..** (Hillview) — photos uploaded by users
- **M..** (Mapillary) — street-level imagery from [Mapillary](https://mapillary.com), greatly expanding coverage

Combining both sources and using filters helps you find photos that show a specific area from different angles.

### Map navigation

The map shows photo markers — green circles with directional arrows. The current photo is highlighted.

- **+/−** to zoom
- **Location tracking** (crosshair icon) — center the map on your GPS position
- **Compass mode** (compass icon) — auto-rotate the map as you turn your phone

---

# III. Capturing Photos

### Phone camera

![Camera capture view](https://hillview.cz/docs/screenshots/desktop/10-camera-capture.png)

1. Tap the **camera button** (top toolbar)
2. Take a photo — the app captures GPS coordinates and compass bearing automatically
3. If auto-upload is enabled and you've agreed to the CC BY-SA 4.0 license, it uploads automatically

### External camera workflow

For higher-quality photos from a dedicated camera, Hillview provides tools to synchronize timestamps and location data.

**Time synchronization:**

![QR Timestamp page](https://hillview.cz/docs/screenshots/desktop/11-qr-timestamp.png)

1. Open **Settings → Advanced → QR Timestamp** on your phone
2. Point your external camera at the screen and take a photo — the QR code encodes the current time
3. After importing photos, use the time correction script to calculate and apply the clock offset between your camera and the phone

**Location & orientation export:**
- The Android app can export CSV files with GPS coordinates and compass bearings recorded during your session
- Find these under **Settings → Advanced → Export Location and Orientation Data**
- Auto-export on app start/exit is available for hands-free workflows
- Use this data to geotag your external camera's photos in post-processing

---

## Account & Authentication

![Login page](https://hillview.cz/docs/screenshots/desktop/03-login-page.png)

Sign in with **username & password** or **Google OAuth**. Once logged in, you can upload photos, rate and annotate, and flag inappropriate content.

<details>
<summary>Photo actions menu</summary>

The three-dot menu on any photo provides:

- **Share Photo** — shareable link with social media preview
- **Flag for Review** — report inappropriate content
- **Hide Photo** — remove a specific photo from your view
- **Hide User** — hide all photos from a user

Hidden content can be managed from Settings.

</details>

---

## Navigation Menu

![Navigation menu](https://hillview.cz/docs/screenshots/desktop/02-navigation-menu.png)

| Menu Item | Description |
|-----------|-------------|
| **Map** | Main map + photo view |
| **My Photos** | Your uploaded photos |
| **Activity** | Recent uploads from all users |
| **Best of** | Top-rated photos |
| **Users** | Browse user profiles |
| **Settings** | Camera, upload, compass, and advanced options |
| **Login / Register** | Sign in or create an account |
| **About** | App info and acknowledgments |
| **Report Bug** | Submit a bug report |
| **Download App** | Get the Android app |

---

## Settings

![Settings page](https://hillview.cz/docs/screenshots/desktop/08-settings.png)

<details>
<summary>Full settings reference</summary>

### Camera
- **Shutter sound** — toggle the camera click sound

### Auto-Upload
- **License agreement** — agree to CC BY-SA 4.0 before uploading
- **Upload mode**: Enabled (automatic), Disabled (prompt each time), or Disabled (never prompt)

### Advanced
- Developer tools, External camera synchronization

### Data Sources
- Define custom photo sources

### Push Notifications
- Activity updates

</details>

---

## Android App

Hillview is available as an Android app with the same full feature set as the web version. The Android app is currently looking for testers. Please leave your google email address at the [Contact]( https://hillview.cz/contact) page!
