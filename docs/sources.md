# Discovery sources

Public evidence sources for the AI-powered discovery engine. These listings, searches, threads, and videos are the starting corpus for photo-retrieval problems in Google Photos.

Aligned with `docs/problemStatement.md`.

---

## Google Play Store

**Listing:** [Google Photos](https://play.google.com/store/apps/details?id=com.google.android.apps.photos)

| Field | Value |
| --- | --- |
| Package | `com.google.android.apps.photos` |
| Publisher | Google LLC |
| Rating (listing snapshot) | 4.4 stars, ~54M reviews |
| Why it is in the corpus | Android reviews and developer replies about search, missing photos, organization, and backup |

Use the listing’s **Ratings and reviews** surface as the Android review feed.

---

## Apple App Store

**Listing:** [Google Photos: Backup & Edit](https://apps.apple.com/us/app/google-photos-backup-edit/id962194608)

| Field | Value |
| --- | --- |
| App ID | `962194608` |
| Publisher | Google |
| Rating (listing snapshot) | 4.8 stars, ~1.6M ratings |
| Why it is in the corpus | iOS reviews about search, storage vs. retrieval, and finding people or memories |

Use the listing’s **Ratings & Reviews** surface as the iOS review feed.

---

## Reddit

Subreddit of record: [r/googlephotos](https://www.reddit.com/r/googlephotos/).

### Search queries

| Query | URL |
| --- | --- |
| find old photo (`r/googlephotos`) | https://www.reddit.com/r/googlephotos/search/?q=find+old+photo&cId=fa081445-8d3c-46d9-a3d1-8b7c1f250c3b&iId=d536d9ff-cee0-4793-b46f-f6eeef2cf740 |
| how to find old pictures in google photo | https://www.reddit.com/search/?q=how+to+find+old+pictures+in+google+photo&cId=525e57f1-07e9-4170-acd8-bb9bbf7b8e02&iId=cde0e95c-5a90-449f-822b-66e60f027d40&tl=en |
| google photos not showing photos after search with keyword | https://www.reddit.com/search/?q=google+photos+not+showing+photos+after+search+with+keyword&cId=41754428-d404-4926-80ef-8feb9114e533&iId=a14dcaae-1f5b-4eef-b41c-9f3111301225&tl=en |
| how to easily find specific photo in google photo, i only remember the occasion | https://www.reddit.com/search/?q=how+to+easily+find+specific+photo+in+google+photo+%2C+i+only+remeber+the+ocassion&cId=cf0e2868-94f2-48e9-9aa2-f430bb513b92&iId=bc5935e3-4b8f-4c12-8f1e-2160ec8b92fe&tl=en |
| search photos on google photos in more than 10000 pictures with face or place info | https://www.reddit.com/search/?q=search+photos+on+google+photos+in+more+than+10000+pictures+with+face+or+place+info+&cId=bf7f819f-a0c1-499c-84b1-be6c547096b9&iId=e9cc804f-64dc-4907-9725-ce78edd3b728&tl=en |
| google photos search | https://www.reddit.com/search/?q=google+photos+search&cId=69caf755-fc53-4384-92dd-7b58cfa016d6&iId=72406e1c-7a48-4902-9ec6-e7e5ea10bee6 |

### Threads

| Topic (from slug) | URL |
| --- | --- |
| Google Photos not showing photos | https://www.reddit.com/r/googlephotos/comments/1r6b2bf/google_photos_not_showing_photos/ |
| I can no longer search for photos by date | https://www.reddit.com/r/googlephotos/comments/1v3gsds/i_can_no_longer_search_for_photos_by_date/ |
| How can I easily find photos or videos that I… | https://www.reddit.com/r/googlephotos/comments/1ousytw/how_can_i_easily_find_photos_or_videos_that_i/ |
| Going through 14 years of photos looking for… | https://www.reddit.com/r/googlephotos/comments/1rrknab/going_through_14_years_of_photos_looking_for/ |
| Is there a way to search Google Photos using a… | https://www.reddit.com/r/googlephotos/comments/xl693t/is_there_a_way_to_search_google_photos_using_a/ |
| Finding specific photo in a large album | https://www.reddit.com/r/googlephotos/comments/1vcu3cs/finding_specific_photo_in_a_large_album/ |
| Google Photos date search completely changed | https://www.reddit.com/r/googlephotos/comments/1ob8og4/google_photos_date_search_completely_changed/ |
| Quickest way to go through old photos and delete | https://www.reddit.com/r/googlephotos/comments/1t5sam9/quickest_way_to_go_through_old_photos_and_delete/ |
| How can I find photos taken around a searched… | https://www.reddit.com/r/googlephotos/comments/1liwoxl/how_can_i_find_photos_taken_around_a_searched/ |

---

## YouTube

| Topic | URL |
| --- | --- |
| Fix: Google Photos not showing all photos (Android) | https://youtu.be/o44v9PZpH-I?si=QXQfllcbH9jh4D3c |
| How to see backup photos in Google Photos | https://youtu.be/uCniTUeIB6k?si=1jaCfA5PTd1LgVKN |
| How to search people’s pictures on Google Photos | https://youtu.be/XiphLATSINM?si=LB5KNxdNt1efhLTT |
| Google Photos walkthrough: search, organization, and large libraries | https://youtu.be/4DNQp3jgT8c?si=lHtRYbbJhH2kWuGq |

---

## How to use this file

Treat store listings as review streams. Treat Reddit searches as query scaffolds and threads as primary evidence. Treat YouTube as how-to and complaint context (missing photos, backup visibility, face search, large-library search).

Add new sources under the same headings. Do not mix store listings with discussion threads.

---

## Arctic Shift (Reddit archive)

Reddit data collected via the Arctic Shift community archive (not the official Reddit API), on 2026-10-02; subreddits and queries used; known gaps: archive may lag very recent days, comment scores may be backfilled later, no uptime guarantees.

- **API:** https://arctic-shift.photon-reddit.com (docs: https://github.com/ArthurHeitmann/arctic_shift/blob/master/api/README.md)
- **Fetcher:** `src/fetch_reddit_arctic.py` (`discover` then `collect`)
- **Subreddits:** googlephotos, GooglePixel, AndroidQuestions
- **Queries:** can't find photo; search old photo; find screenshot; can't remember; search not working; find picture; photos missing; how do I find
- **Outputs:** `data/raw/reddit_candidates.csv` (discover), `data/raw/reddit_arctic.csv` (collect)

