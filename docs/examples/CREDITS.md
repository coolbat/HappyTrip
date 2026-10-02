# HappyTrip showcase sources and credits

These photographs are licensed reference assets for HappyTrip demonstrations. They are not private user travel photographs and do not establish a user's travel dates or route.

## San Francisco photographs

Wikimedia-supplied 1280 px thumbnails were downloaded without local visual edits; poster use may resize and rotate them.

| Local asset | Landmark | Author and permission | Source page | Landmark coordinates |
|---|---|---|---|---|
| `golden_gate.jpg` | Golden Gate Bridge | Wattewyl, [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Golden_Gate_Bridge_from_Marin_Headlands_5.jpg) | 37.819722222222, -122.47861111111 · [Wikidata Q44440](https://www.wikidata.org/wiki/Q44440) |
| `pier39.jpg` | Pier 39 | Daderot, [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Pier_39_-_San_Francisco%2C_CA_-_DSC03485.jpg) | 37.809992, -122.410357 · [Wikidata Q1856083](https://www.wikidata.org/wiki/Q1856083) |
| `ferry_building.jpg` | San Francisco Ferry Building | DaveOinSF, author's worldwide public-domain dedication on file page | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:FerryBuildingEmbarcaderoBayBridge.JPG) | 37.79555555555555, -122.39361111111111 · [Wikidata Q1408117](https://www.wikidata.org/wiki/Q1408117) |

Coordinates identify the landmarks rather than camera positions. Sources were checked on 2026-10-02, Asia/Shanghai. Original download records remain in local development outputs. The repository also includes unchanged copies of the Golden Gate Bridge and Pier 39 input photographs as `golden-gate-source.jpg` and `pier39-source.jpg`, for before/after examples.

Suggested visible credit: **Photos: Wattewyl / Wikimedia Commons (CC BY 3.0); Daderot (CC0); DaveOinSF (public domain). Resized and arranged.** Keep a link to this credit record or the Commons file page and license with any shared derivative.

## Paris photograph

`louvre-source.jpg`: **Courtyard @ Louvre @ Paris**, by [Guilhem Vellut](https://www.flickr.com/people/22539273@N00), licensed [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/). [Wikimedia Commons file page](https://commons.wikimedia.org/wiki/File:Courtyard_@_Louvre_@_Paris_(28897294980).jpg) · [original Flickr page](https://www.flickr.com/photos/o_0/28897294980/).

The original 5472×3648 photograph was resized to 1600×1067 (JPEG quality 95), without cropping or semantic changes. The Commons license and original-source review were checked on 2026-10-02. Exact file hashes and the source revision are in [louvre-source.json](louvre-source.json).

Suggested visible credit: **Courtyard @ Louvre @ Paris — Guilhem Vellut / Wikimedia Commons, CC BY 2.0. Source resized; edited examples additionally remove tourists and reconstruct the underlying paving.** Retain the author, source and license with shared derivatives.

## Basemap

The poster uses the public [USGS The National Map / USGSTopo service](https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer). Map credit: USGS The National Map. The raster is georeferenced in Web Mercator. Dashed connections indicate landmark associations, not roads, navigation instructions, or an actual trip.

## README derivatives

- `a01-cleanup.png`: tourist removal and inferred ground reconstruction from Guilhem Vellut's Louvre photograph, [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/). A generated lower region was masked onto the resized original; source and upper architecture retained. This is a modified derivative, not an unedited record of an empty courtyard.
- `a02-natural-light.png`: AI light/color editing of Wattewyl's Golden Gate Bridge photograph, [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). Shadows and color were modified; fine texture may be reinterpreted. Not a pixel-preserving color correction.
- `b01-magnet-poster.png`: generated souvenir interpretation of Wattewyl's Golden Gate Bridge photograph, [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/), composited with a proportionally resized complete source photo and text. Imagined magnet, not an existing product.
- `a05-watercolor-postcard.png`: generated watercolor interpretation of Wattewyl's Golden Gate Bridge photograph, using the built-in image tool. Modified from the original; original photograph licensed [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/), source linked above. This is an intentionally text-free postcard.
- `b04-travel-globe.png`: generated glass-globe interpretation of Daderot's Pier 39 photograph (CC0). This is an imagined souvenir, not a photograph of an existing product.
- `b22-map-preview.png`: photographs resized and arranged over the USGS basemap; see map attribution above.

Generation prompts and the scope of each reviewed example are documented in [the showcase notes](README.md). These examples contain no private user photos.
