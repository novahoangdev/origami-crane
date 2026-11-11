# Recording versions

All recordings: sim "Origami Crane Rec 17 Pro Max" (`notes/udid_rec.txt`, Release app from `render/dd-release` +
`tools/embed.sh` DEMO=1 TS=0.5), `tools/rec.sh` → `render/promo/vN/screen.mp4` (1320×2868, 60 fps CFR, demo time).
"60/60" = distinct frames per second in the recording (`vN/check.txt`). Film start = app t = 0 in screen.mp4
(`vN/filmstart.txt`, from the end of the sync marker).

| Version | What changed | Notes |
|---|---|---|
| v0 | first take with the anime-house build (bundled 00:42, 04/11), promo pipeline test | 60/60 from second 2; film start 1.4 (marker 23 frames: first drawn frame = app 0.117 → app_start 0.12); event times = coordinator timeline, checked on the motion curve (fold swipes) and the vanish flash at ~24.8; an earlier take (bundle 00:34, mid-edit app: no rewind, crane gone at ~7 s) was dropped. App glitch seen: a blue band with yellow blobs along the bottom edge for ~0.3 s at ~23.4 s (sky shot). Half-res test clip `render/promo/origami-crane-demo-v0-test.mp4` |
| v1 | build bundled ~01:04 (same storyboard as v0) | 60/60 from second 2; film start 1.2667 (marker 26 frames, first drawn frame app 0.067); events = v0, vanish flash measured at 24.85 (`v1/evcheck.jpg`); full clip `render/promo/origami-crane-demo-v1.mp4` |
| v2 | 01:45 build: establishing shot on frame 1 (dolly in during the rewind), 24-frame warm-up hold, 292-facet bake, crane glows red outside, vanish starburst, expo-audio Release binary | 60/60 from second 2; film start 1.6 (marker 38 frames incl. the warm-up hold; first drawn frame = complete t = 0); rewind motion starts exactly at 2.30 on the picture; folds = coordinator EVT times (picture: fold5 ~0.1 s early, fold9 on time, awaken ring at 15.02); vanish flash onset on the picture 24.98 (EVT 24.84) → beat sheet uses 24.98; app_end 27.445 (96.2 BPM). Full clip `render/promo/origami-crane-demo-v2.mp4` |
| v3 | final take 04/11 07:16 (tools/final.sh): current app | rawcheck clean; film start 2.4833; clip render/promo/origami-crane-demo-v3.mp4 |
| v4 | final take 05/11 00:45 (tools/final.sh): current app | rawcheck clean; film start 2.6167; clip render/promo/origami-crane-demo-v4.mp4 |
| v5 | final take 05/11 12:29 (tools/final.sh): current app | rawcheck clean; film start 2.15; clip render/promo/origami-crane-demo-v5.mp4 |
| v6 | final take 05/11 13:13 (tools/final.sh): current app | rawcheck clean; film start 2.0667; clip render/promo/origami-crane-demo-v6.mp4 |
| v8 | final take 05/11 15:13 (tools/final.sh): current app | rawcheck clean; film start 2.1833; clip render/promo/origami-crane-demo-v8.mp4 |
| v9 | final take 05/11 17:10 (tools/final.sh): current app | rawcheck clean; film start 1.7667; clip render/promo/origami-crane-demo-v9.mp4 |
| user_v9 | real-use recording 05/11 (tools/rec_user.sh v9 on the v9 app): home screen, icon tap, scripted user folds all 14 steps, flight, next sheet | render/promo/origami-crane-user-9x19-v9.mp4, 68.8 s |
