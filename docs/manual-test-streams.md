# Manual test streams

Public HLS streams for trying RayoHX by hand (CLI, API, UI).

> **We do not own, host or control any of these streams.** They belong to their respective owners and are listed here only as references for manual testing. They may change or disappear at any time, and they are not used by the automated tests. Do not redistribute the content. Use the repository's own fixtures in `tests/fixtures` for automated tests.

| Scenario | URL | What to check |
| --- | --- | --- |
| Multiple audio and subtitle tracks (Apple bipbop advanced) | `https://devstreaming-cdn.apple.com/videos/streaming/examples/img_bipbop_adv_example_ts/master.m3u8` | Master playlist with several video bitrates, multiple audio languages, subtitle tracks and I-frame playlists. Use it to test variant, audio and subtitle selection. |
| Multi-bitrate video (Mux test stream) | `https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8` | Master playlist with several video renditions. Use it to test quality selection and a plain download. Audio and subtitle tracks have not been verified, so check with an inspect first. |
