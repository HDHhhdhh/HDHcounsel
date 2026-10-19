# UI Baseline

Accepted layout: 2026-09-05, after moving `정리본 생성·복사` below the recording
uploader. `DESIGN.md` is the layout contract; `OPERATIONS.md` defines behavior.
No new theme, labels, success criteria or live data changes are part of this baseline.

## Reproduce Safely

From the canonical application root:

```powershell
.\.venv\Scripts\python.exe -m streamlit run scripts/ui_contract_fixture.py --server.address 127.0.0.1 --server.port 8502 --server.headless true --server.fileWatcherType none --browser.gatherUsageStats false
```

Use a free test port, never replace the user's 8501 server. Launch background
helpers hidden. Close only the verified fixture process and tab after checking.

The fixture uses the real overview/history rendering helpers and CSV preview
logic with TEST-only data. Buttons render normally but cannot dispatch a save.
The CSV fixture blocks network and ADMIN writes and mocks persistence, mappings,
history loading and the Downloads watcher. It never launches a recording job.

`selected` is a synthetic backend selection: it does not test the OS file picker,
native selected-file chips or a real upload. The outer page mirrors the column
layout; the existing full `app.main()` AppTest fixture separately covers dynamic
audio/CSV placement. Do not describe this as an end-to-end live save test.

## Browser Check

1. Open the fixture with the enabled browser tool, not the live student-data tab.
2. Select each `Fixture state`: empty, selected, saving, completed. Then switch
   completed -> selected to catch stale completion locking a new file.
   Open the CSV expander before measuring; closed content is not mounted in the DOM.
3. Read a fresh DOM snapshot. Evaluate the read-only function in
   `scripts/check_ui_geometry.js` and require `passed: true` / empty `failures`.
4. Capture and inspect a screenshot in each state. Check borders, wrapping and
   text visually as well as geometry. Change states back and forth and inspect
   intermediate frames for duplicate CSV expanders; settled measurements alone
   cannot prove the absence of transient flicker.
5. Repeat at a wide desktop and a narrow viewport (target 375 CSS px). Read the
   actual `innerWidth`; browser zoom can make requested viewport dimensions differ.
6. Reset viewport overrides and close the fixture tab. Record the measured results
   and limitations with the task. Do not mark CSS substring tests as visual QA.

The function returns the measured boxes and failure reasons; it does not mutate
DOM, scroll, install observers, call APIs or write application data. Keep its
selectors grounded in `DESIGN.md` and the actual rendered Streamlit components.

## Required Assertions

| Surface | Pass condition |
| --- | --- |
| Upload box | Width <=300px (+2px measurement tolerance) |
| Generate action | Original label, below gray box, left aligned |
| Wide overview (>640px) | First history top within 2px of upload top; 16px track gap |
| Narrow overview (<=640px) | History below upload and action, no clipping |
| History | Exactly 3 strips; boxes/text stay within their bounds |
| Main headings on desktop | Top positions differ by <=2px |
| CSV workspace | Exactly one expander in every state |
| Empty/completed | No row table; original CSV action visible and disabled |
| Selected | Original CSV action enabled |
| Saving | Save and resume actions both absent |
| Page | No horizontal viewport overflow |

The screenshot baseline is a review aid, not a pixel-perfect image-diff gate:
native widget details vary with Streamlit/browser versions. Geometry and semantic
assertions remain the acceptance criteria. Retake screenshots when intentionally
changing this contract; do not silently bless a failing measurement.

## Fast Regression Check

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/check_quick.ps1
```

This includes the baseline's five state transitions in `check_ui_refresh.py`,
the full-main audio/CSV stable-slot check, CSV control/history checks and ADMIN
fragment checks. It does not start a browser or make production saves. Browser
geometry and screenshot review are a separate required pass for layout changes.

## Verified 2026-09-06

- Browser geometry passed all four states at 1920 CSS px and 375 CSS px, including
  completed -> selected. Desktop uploader width 300px, history top delta 0px,
  track gap 16px; narrow tracks stacked, labels contained, one CSV expander.
- Viewport heights were 900/1000px (one narrow selected check used 1600px).
  The in-app capture tool intermittently timed out or scaled/cropped oversized
  captures; those images were not used as full-page visual proof. Usable captures
  and DOM measurements agreed for the visible uploader/history/CSV surfaces.
- Streamlit mounts zero-size button copies for width measurement. The geometry
  check excludes these copies, not real visible duplicate buttons.
- Full quick checks passed 9/9, including five full-page state transitions.
  This does not prove every animation frame is flicker-free or test native files.

## CSV Worker Browser Check

Run `scripts/csv_worker_fixture.py` with Streamlit on another free test port.
It uses a temporary checkpoint/history, one synthetic row, and rejects real network
requests and ADMIN writes. The response gate expires after 120 seconds.

1. Open CSV and click the unchanged save action.
2. Confirm `fake_post_count: 1`, `worker_running: True`, `status: running`.
3. Reload the browser. The same worker and count must remain; save/resume are hidden.
4. Click `검사 응답 완료`. Confirm completed=1, worker_running=False, post count=1,
   the `저장 결과` panel and one `오늘 전체 완료 확인` button.
5. Reload the browser and confirm the same result panel remains. Click `오늘 전체 완료 확인`;
   the result panel and confirmation button must disappear while the disabled CSV
   save action remains.
6. Stop only this fixture server after completion. Restart it for a fresh test run.

This flow passed in the browser on 2026-09-06. It verifies browser disconnection
independence, not live Google Docs, power loss, or OS sleep recovery.
