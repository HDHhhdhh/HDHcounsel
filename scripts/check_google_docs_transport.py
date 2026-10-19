from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import requests


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from scripts.check_csv_worker import load_app, transfer_args


class JsonResponse:
    status_code = 200

    def __init__(self, payload: dict[str, str | bool]) -> None:
        self.payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self) -> dict[str, str | bool]:
        return self.payload


class StalledReusableSession:
    def post(self, *_args, **_kwargs) -> JsonResponse:
        raise requests.exceptions.ReadTimeout("synthetic stale pooled connection")

    def close(self) -> None:
        return None


def main() -> None:
    app = load_app(ROOT_DIR, None)
    request = transfer_args(app)
    request["web_app_url"] = "https://script.google.com/macros/s/test-deployment/exec"

    with tempfile.TemporaryDirectory(prefix="docs-transport-test-") as directory:
        folder = Path(directory)
        checkpoint = folder / "run.json"
        history_path = folder / "history.json"
        with (
            patch.object(app, "LOG_CSV_DOCS_STATE_PATH", checkpoint),
            patch.object(app, "LOG_CSV_PROCESSING_HISTORY_PATH", history_path),
            patch.object(app, "GOOGLE_DOCS_TIMEOUT_VERIFY_PAUSE_SECONDS", 0),
            patch.object(app, "save_log_csv_to_docs_result_log", return_value=folder / "result.csv"),
            patch("requests.Session", return_value=StalledReusableSession()),
            patch(
                "requests.post",
                return_value=JsonResponse({"ok": True, "message": "added"}),
            ) as fresh_post,
        ):
            app.execute_log_csv_transfer(**request)

        saved = app.load_log_csv_batch_state(checkpoint)

    outcomes = [app.classify_google_docs_save_result(result)["count_key"] for result in saved["results"]]
    observed = [(result.get("result_status"), result.get("result_message"), result.get("review_category")) for result in saved["results"]]
    assert outcomes == ["new_saved", "new_saved"], observed
    assert fresh_post.call_count == 2
    print("PASS: Docs batch uses a fresh HTTP request per row")


if __name__ == "__main__":
    main()
