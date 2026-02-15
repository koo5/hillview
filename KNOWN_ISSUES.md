## KNOWN ISSUES (as of version 1.27)

### clicking on activity notification should ensure view mode properly
* leaves capture mode on

### landscape mode compass is wrong when pointed at horizon, on some devices
* arrow jumps randomly. Workaround: point slightly above or below horizon

### landscape mode compass is completely wrong, on some devices
* Workaround: enable Landscape mode workaround in Settings


### when moving map, photo markers hide/show randomly
* this happens when there are too many photos on the map, when zoomed out, because the total number of photo markers shown at any one time is limited
- #49
* workaround: zoom in
* todo: stable picks

### battery drain, when app is in foreground
* should be ok when app is hidden or screen is off

### UI is laggy, especially during photo capture:
* #25 

### capture progress/total count indicator (camera screen bottom right) is confusing
* 
 
### mapillary source is flaky: 
* #18 
* #8
 
### lack of photo filtering/sorting throughout the app
*

### issue:
* #48  

### issue:
* #19

### need to distinguish permanent and temporary upload failures
* should only say "retrying" for now


## PLANNED FEATURES

### webp
* switch to webp for photo storage

### annotations
* support for tiled large photos/panoramas - research OpenSeadragon etc
* ability to add/edit/view annotations on photos

### toggle/reupload without anonymization
* need solid data model for synchronization of photo state

### UI overhaul + better map library
* CMP...
* better camera screen UI / focus / exposure controls / video support

### better photo organization
* (automatic) tagging
* filtering/sorting

### sources
#### support Panoramix as source / share some code?
* research Panoramix codebase

#### better mapillary integration
* research mapillary dumps

### external camera support
* camera flash hack to get sub-second photo timestamps
* finish GeoTrackingDumps script


### multiple photo licensing options (CC, NC, NC+CLA, ...?)
*

### web based photo capture
*



