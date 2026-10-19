# Counsel Note Agent Guide

## Installation root

- Work from the user's active local checkout. Confirm the running process
  command line and application root before changing runtime behavior.
- Do not edit or launch stale copies or another installation without explicit
  user direction. No machine-specific path is authoritative in this public copy.

## Private configuration

- This repository contains source only, not student records or credentials.
- Student mappings and the Apps Script web-app URL belong in local, ignored
  files under `data/students/`. Restore them through an authorized private
  channel, never through commits, issues, screenshots or diagnostic output.
- Verify the authorized Google account, project and existing deployment using
  the installation's private configuration. No production project identifier,
  account, deployment ID or web-app URL is published here.
- Do not print private configuration values when reporting verification.

## Apps Script maintenance

- Local source of truth: `scripts/google_apps_script_doPost.js`.
- Regression check: `scripts/check_google_apps_script_same_date_policy.js`.
- Apps Script deployment requires an explicit user request for that action.
- Before deployment, run:
  `node scripts/check_google_apps_script_same_date_policy.js` and
  `node --check scripts/google_apps_script_doPost.js`.
- Compare the authorized project's `Code.gs` with the local source. Review
  unrelated newer remote changes before replacing them.
- Update only the existing, privately verified deployment through
  `Deploy` -> `Manage deployments` -> `Edit` -> `New version`.
- Confirm the project is saved, record the resulting version, and verify that
  the deployment ID and configured web-app URL did not change.
- Do not create another deployment or replace the configured URL as routine
  maintenance.
- A real Google Docs POST needs separate explicit authorization. State clearly
  when live-write verification was not performed.

### Policies to preserve

- Same date and exactly identical content: do not add a duplicate.
- Same date with changed content or formatting: replace that date's record.
- Different date: add a new record even when the content is identical.
- For a document with one counseling table, validate that table directly
  instead of scanning every cell in the full document.

## Chrome launcher

- Chrome new-tab shortcuts do not accept custom protocol or file URLs.
- The local shortcut targets `http://127.0.0.1:8765/open`; its HTTP launcher
  waits for Streamlit and redirects the current tab to `http://localhost:8501`.
- Launcher registration scripts are
  `scripts/install_connect_log_http_launcher.ps1` and
  `scripts/install_connect_log_protocol.ps1`.
- Register launchers only when requested, passing the current installation
  root through `-AppRoot`. Never register a stale checkout.
- `run_app.ps1` starts Streamlit locally and opens the application in Chrome.

## Agent and visual QA policy

- Read `DESIGN.md` before layout work and `docs/OPERATIONS.md` before changing
  completion, reset, retry, ADMIN or Docs behavior. Processing finished and
  confirmed storage success are distinct states.
- Use `docs/UI_BASELINE.md` for the isolated four-state browser check. AppTest
  checks alone do not prove pixel alignment or the absence of visible flicker.
- Handle routine edits, debugging, tests and browser checks in the current task.
- Do not spawn review or visual-QA subagents merely because a UI file changed.
  Independent visual review requires an explicit user request.

## Safety

- Do not modify student data, existing logs, CSV outputs, recordings,
  transcripts or consumed-note registries for maintenance or publication.
- ADMIN writes, Apps Script deployment, ZIP publishing, installer creation
  and live Docs POST each require explicit authorization for that action.
- Never commit private data, credentials, local environments or model caches.
