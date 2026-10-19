// Evaluate this read-only function in the isolated fixture's browser page.
() => {
  const failures = [];
  const check = (condition, name) => { if (!condition) failures.push(name); };
  const one = (selector) => document.querySelector(selector);
  const all = (selector) => [...document.querySelectorAll(selector)];
  const rect = (element) => {
    if (!element) return null;
    const box = element.getBoundingClientRect();
    return Object.fromEntries(["x", "y", "width", "height", "top", "bottom", "left", "right"]
      .map(key => [key, Math.round(box[key] * 100) / 100]));
  };
  const state = one("#ui-contract-state")?.dataset.state;
  if (!state) return {failures: ["Run only on ui_contract_fixture.py"], passed: false};
  const overview = rect(one(".st-key-audio-log-overview"));
  const upload = rect(one('.st-key-audio-upload-input [data-testid="stFileUploaderDropzone"]'));
  const actionNode = one(".st-key-audio-generate-action button");
  const action = rect(actionNode);
  const stripNodes = all(".log-history-strip");
  const history = stripNodes.map(rect);
  const headings = all(".st-key-contract-screen h3").slice(0, 3).map(rect);
  const csv = all('[data-testid="stExpander"] summary')
    .filter(node => node.textContent.includes("로그 CSV → 학생 Docs 추가"));
  // Streamlit also mounts zero-size button copies for width measurement.
  const buttons = all("button").filter(node => {
    const box = node.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
  });
  const save = buttons.filter(node => node.textContent.trim() === "선택한 기록을 학생 Docs에 추가");
  const resume = buttons.filter(node => node.textContent.includes("남은 작업 이어서 저장"));
  check(Boolean(overview && upload && action), "upload/action containers exist");
  check(history.length === 3, "exactly three history strips");
  check(csv.length === 1, "exactly one CSV expander");
  check(document.documentElement.scrollWidth <= innerWidth + 2, "no page horizontal overflow");
  if (overview && upload && action && history.length === 3) {
    check(upload.width <= 302, "uploader capped at 300 CSS px");
    check(action.top >= upload.bottom - 2, "generate action below gray uploader");
    check(Math.abs(action.left - upload.left) <= 2, "generate action left aligned");
    check(actionNode.textContent.trim() === "정리본 생성·복사", "unchanged generate label");
    check(actionNode.disabled === (state !== "selected"), "generate disabled state");
    if (overview.width > 640) {
      check(Math.abs(history[0].top - upload.top) <= 2, "upload/history top aligned");
      check(Math.abs(history[0].left - upload.right - 16) <= 2, "16px track gap");
    } else {
      check(history[0].top >= action.bottom - 2, "narrow history below upload/action");
    }
    history.forEach((box, index) => {
      check(box.right <= overview.right + 2 && box.left >= overview.left - 2, "history within overview");
      if (index) check(box.top >= history[index - 1].bottom, "history rows do not overlap");
      const labels = [...stripNodes[index].querySelectorAll("span, strong")]
        .filter(node => node.children.length === 0 && node.textContent.trim());
      for (const label of labels) {
        const text = rect(label);
        check(text.left >= box.left - 2 && text.right <= box.right + 2 &&
          text.top >= box.top - 2 && text.bottom <= box.bottom + 2, "history labels within strip");
        check(label.scrollWidth <= label.clientWidth + 2, "history labels have no scroll overflow");
      }
    });
  }
  const hint = one('.st-key-audio-upload-input [data-testid="stFileUploaderDropzoneInstructions"]');
  check(!hint || getComputedStyle(hint).display === "none", "recording size/type hint hidden");
  if (headings.length === 3 && headings[1].left > headings[0].right) {
    check(Math.max(...headings.map(x => x.top)) - Math.min(...headings.map(x => x.top)) <= 2,
      "three desktop headings top aligned");
  }
  if (state === "saving") {
    check(save.length === 0 && resume.length === 0, "both CSV actions hidden while saving");
  } else {
    check(save.length === 1, "original CSV action visible");
    check(save[0]?.disabled === (state !== "selected"), "CSV action enabled only for selected state");
  }
  const tables = all('.st-key-log-csv-workspace [data-testid="stDataFrame"]');
  if (["empty", "completed"].includes(state)) check(tables.length === 0, "completed/empty CSV list hidden");
  return {state, viewport: {width: innerWidth, height: innerHeight}, overview, upload, action,
    history, headings, csvExpanders: csv.length, failures: [...new Set(failures)], passed: failures.length === 0};
}
