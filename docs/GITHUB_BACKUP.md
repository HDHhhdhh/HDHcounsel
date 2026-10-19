# Source Backup

This public snapshot starts a new history. Operational account identifiers and
Apps Script project details are omitted; the original private repository is not
made public or rewritten. Configure integrations privately for each installation.

The 2026-10-19 snapshot includes the current local application source, helper
modules, prompts, launcher scripts, browser extension, experiments and tests.
Files present only in the earlier repository snapshot are retained.

This is a code backup, not a release package or a backup of student records.
The following remain local and are not included:

- Student mappings, private service configuration and all other `data/` files.
- Counseling recordings, transcripts, drafts, save histories and result exports.
- Experiment samples and transcript-derived outputs.
- Credentials, local Python environments, downloaded models and caches.
- Generated installers, archives and diagnostic captures.

A new checkout needs its own Python environment and private configuration before
starting the app. Restore the required `data/students/google_docs_map.csv` and
`data/students/google_apps_script_webapp_url.txt` locally through an authorized
private channel; do not commit them. Follow the existing installation scripts
for dependencies. Optional OpenVINO dependencies are listed separately in
`requirements-openvino.txt`.

Pushing this source does not deploy Google Apps Script, update another computer,
or execute any ADMIN or Google Docs write.
