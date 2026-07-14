# In-app explainer: how casual photos feed annotation + commons

## Context

Hillview currently presents itself as a photo-mapping app. Users uploading
casual photos don't see how their contribution fits into anything larger.
There's no in-app articulation of:

- That photos are **evidence substrate** — a photo with reliable bearing is
  what makes Hunt-mode triangulation and panorama annotation possible later.
- That the CC-vs-`full1` choice has real downstream consequences for two
  distinct ecosystems (OSM commons vs Hillview's curated knowledge layer).
- That contribution to OSM matters and why anyone should care about it.

Without this articulation, casual contributors treat Hillview as a personal
photo-stash with a map view. They don't know they're producing useful data.
They have no model for why one license choice differs from another. They
have no reason to take the next step toward annotating themselves.

## The narrative chain to communicate

The story, in plain language:

1. **You take photos with bearing.** Casually, at viewpoints, from car
   windows, on walks. Hillview makes this low-friction.
2. **Those photos become evidence.** Each photo records "from this point,
   looking in this direction, these features are visible." This is rare
   data — most photo platforms don't capture or care about bearing.
3. **Evidence enables annotation.** Multiple bearings on the same feature
   triangulate where it is (Hunt mode). A high-quality panorama becomes
   annotatable because the bearing makes feature identification possible.
4. **Annotation creates a knowledge graph.** "The tower visible from
   Prosecké skály at bearing 142° is also visible from Mělník at bearing
   223° and is called X." Hillview's curated layer.
5. **All photos also feed OSM.** Bearing-tagged photos are valuable to OSM
   mappers verifying features (does that church still stand? what does
   that tower actually look like?). Hillview's commons contribution.
6. **OSM matters because** it's the open data layer underneath countless
   hiking apps, navigation tools, map renderers, research projects, and
   open-data efforts. When OSM is good, a lot of tools are good. Hillview
   makes a small contribution to that.

The story is layered: not every surface should tell the whole arc. A casual
user upload prompt only needs steps 1-2. A license selector needs 4-5. A
"why we exist" page can tell the whole thing.

## Candidate surfaces in the app

Ranked roughly by ROI and ease:

- **License selector (highest ROI).** This is the moment a user is making a
  conscious choice between CC and `full1`. Embedding 1-2 sentences explaining
  what each choice *enables* downstream is much more actionable than legal
  text alone. ("CC photos feed the open commons.
  `full1` photos support Hillview and may be
  included in paid tiers later.")
- **After first photo upload.** A brief one-time message acknowledging the
  contribution and showing what becomes possible. Not intrusive — small
  toast or single-step modal with "learn more" link.
- **Dedicated "How this works / Why" page** linked from About / menu.
  Carries the full arc with maybe one diagram. Doesn't interrupt anyone but
  is available for the curious.
- **Annotation editor** could mention that the annotation depends on
  bearing-tagged photos like the one being annotated. Reinforces the loop
  for users who reach this surface - this can be more obvious when annotations
  consistently link to closeup photos.
- **My Photos page** could surface aggregate stats: "You've contributed N
  photos which help open mapping; M `full1` photos which build Hillview's
  curated corpus." Makes contribution feel visible.

Start with the license selector and the dedicated "Why" page. Those two
surfaces cover the most cases without requiring big UX changes. Other
surfaces follow if/when they earn their place.

## What to avoid

- **Lecturing.** The story should feel like context, not a sermon. Two
  sentences in the license selector, not five paragraphs.
- **Hiding it.** A "Why we exist" page nobody links to is wasted effort.
  Surface the story where users naturally encounter relevant decisions.
- **Burying the bearing point.** The "your photos have *bearing*, which
  is rare and useful" angle is the genuinely distinctive contribution.
  Most users won't realize this without being told.

## Out of scope / future iterations

- Localization (Czech translation eventually mandatory given audience).
- Visual diagram of the evidence → annotation → commons flow. Worth
  doing but later.
- Per-user contribution dashboard showing downstream impact ("your
  photos have been used in N annotations / N OSM edits"). Aspirational
  and probably impossible to implement honestly until those events are
  trackable.
- Different framings for different user archetypes (casual phone
  contributor vs annotation-focused contributor vs OSM-aligned
  contributor). Useful eventually; one general story is fine for v1.

## Connection to other work

- The license-selector copy here overlaps with `content-license-model-draft.md`'s
  "user-facing communication" section. The narrative-chain version is the
  *positive framing* (what your choice enables); the model spec carries
  the *legal-mechanic framing* (what each choice means contractually).
  Both should exist and reference each other.
- The Panoramax corpus release moment (private memory: `panoramax-release-plan.md`)
  is a natural trigger to update / refresh this content — the "we contributed
  15k photos to the commons" story is the contribution narrative made
  concrete.
- The annotation-funnel ambition from the release plan depends on this
  narrative existing somewhere. A user who arrives via the Panoramax
  release won't convert to annotator without understanding the loop.

## Definition of done (rough)

- [ ] License-selector copy revised to surface 1-2 sentences on what each
      choice enables.
- [x] The "how it fits together" narrative lives on **/about** (section
      `id="how-it-works"`, replacing the old marketing-voice About blurb) —
      decided against a dedicated page to avoid duplicating /about and
      splitting SEO signals across two near-identical texts. Deep-link
      target for future license-selector / first-upload links:
      `/about#how-it-works`. License mechanics (CC vs full1) deliberately
      absent until the license model ships; Panoramax gets one sentence in
      "Part of the commons" once federation is live.
- [ ] After-first-upload acknowledgement implemented (low priority).
- [ ] Czech translation of the surfaces above.

Not Stage-1 critical. Worth doing before the Panoramax release moment, ideally.
