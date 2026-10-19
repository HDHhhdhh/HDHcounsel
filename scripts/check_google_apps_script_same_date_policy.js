const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const scriptPath = path.join(__dirname, "google_apps_script_doPost.js");
let fakeNow = 0;
let uuidCounter = 0;
const propertyValues = new Map();
const scriptProperties = {
  getProperty(key) {
    return propertyValues.get(key) || null;
  },
  setProperty(key, value) {
    propertyValues.set(key, value);
  },
  deleteProperty(key) {
    propertyValues.delete(key);
  },
  getProperties() {
    return Object.fromEntries(propertyValues);
  },
};
const context = {
  Date: class extends Date {
    static now() {
      return fakeNow;
    }
  },
  LockService: {
    getScriptLock() {
      return {
        tryLock() {
          return true;
        },
        waitLock() {},
        releaseLock() {},
      };
    },
  },
  PropertiesService: {
    getScriptProperties() {
      return scriptProperties;
    },
  },
  Utilities: {
    getUuid() {
      uuidCounter += 1;
      return `lease-${uuidCounter}`;
    },
    sleep(milliseconds) {
      fakeNow += milliseconds;
    },
  },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(scriptPath, "utf8"), context, { filename: scriptPath });

function makeCell(text) {
  return {
    getText() {
      return text;
    },
  };
}

function makeRow(values) {
  return {
    getNumCells() {
      return values.length;
    },
    getCell(index) {
      return makeCell(values[index] || "");
    },
  };
}

function makeTable(entries) {
  const rows = [
    makeRow(["상담일자", "상담일자 / 상담자 / 세부내용"]),
    ...entries.map(([date, summary]) => makeRow([date, summary])),
  ];
  return {
    getNumRows() {
      return rows.length;
    },
    getRow(index) {
      return rows[index];
    },
  };
}

function find(entries, summary, counselingDate = "2026-08-24") {
  return context.findExistingCounselSummary_(makeTable(entries), summary, counselingDate);
}

const original = "진도(공통수학2): 3단원\n숙제:\n- 쎈: p.10-20";

const exactDuplicate = find([["2026-08-24", original]], original);
assert.strictEqual(exactDuplicate.action, undefined);
assert.strictEqual(exactDuplicate.duplicateReason, "content");

const formatChanged = find(
  [["2026-08-24", original]],
  "진도(공통수학2): 3단원\n\n숙제:\n- 쎈: p.10-20",
);
assert.strictEqual(formatChanged.action, "update_existing");
assert.strictEqual(formatChanged.duplicateReason, "same_date_replaced");

const progressChanged = find(
  [["2026-08-24", original]],
  "진도(공통수학2): 4단원\n숙제:\n- 쎈: p.10-20",
);
assert.strictEqual(progressChanged.action, "update_existing");
assert.strictEqual(progressChanged.duplicateReason, "same_date_replaced");

const contentChanged = find(
  [["2026-08-24", original]],
  "상담 참고사항\n- 시험 이후 학습 계획을 전면 조정함.",
);
assert.strictEqual(contentChanged.action, "update_existing");
assert.strictEqual(contentChanged.duplicateReason, "same_date_replaced");

const differentDate = find([["2026-08-23", original]], original);
assert.strictEqual(differentDate, null);

let singleTableCellReads = 0;
const largeSingleTableRows = [
  ["상담일자", "상담일자 / 상담자 / 세부내용"],
  ...Array.from({ length: 240 }, (_, index) => [
    `2026-08-${String((index % 28) + 1).padStart(2, "0")}`,
    `상담 기록 ${index + 1}`,
  ]),
];
const largeSingleTable = {
  getNumRows() {
    return largeSingleTableRows.length;
  },
  getRow(rowIndex) {
    const values = largeSingleTableRows[rowIndex];
    return {
      getNumCells() {
        return values.length;
      },
      getCell(cellIndex) {
        return {
          getText() {
            singleTableCellReads += 1;
            return values[cellIndex] || "";
          },
        };
      },
    };
  },
};
const selectedSingleTable = context.findCounselRecordTable_({
  getTables() {
    return [largeSingleTable];
  },
});
assert.strictEqual(selectedSingleTable, largeSingleTable);
assert.ok(singleTableCellReads <= 2, `single table selection read ${singleTableCellReads} cells`);

let legacyHeaderReads = 0;
const legacyRows = [
  ["상담세부내용", ""],
  ...Array.from({ length: 240 }, (_, index) => ["2026-08-23", `기존 기록 ${index}`]),
];
const legacyTable = {
  getNumRows() {
    return legacyRows.length;
  },
  getCell(rowIndex, cellIndex) {
    return this.getRow(rowIndex).getCell(cellIndex);
  },
  getRow(rowIndex) {
    const values = legacyRows[rowIndex];
    return {
      getNumCells() {
        return values.length;
      },
      getCell(cellIndex) {
        return {
          getText() {
            if (rowIndex === 0) legacyHeaderReads += 1;
            return values[cellIndex] || "";
          },
          getBackgroundColor() {
            return cellIndex === 0 ? "#7799dd" : "#ffffff";
          },
          setText(text) {
            values[cellIndex] = text;
          },
        };
      },
    };
  },
};
const lookup = {};
assert.strictEqual(context.findCounselRecordTable_({ getTables: () => [legacyTable] }, lookup), legacyTable);
assert.strictEqual(context.findExistingCounselSummary_(legacyTable, original, "2026-08-24", lookup.header), null);
const originalEnsure = context.ensureRowAndCells_;
try {
  context.ensureRowAndCells_ = () => ({ addedRow: true, maxCellCount: 2 });
  const next = context.findNextCounselRecordCell_(legacyTable, lookup.header);
  assert.strictEqual(next.rowIndex, 241);
  assert.strictEqual(next.colIndex, 1);
} finally {
  context.ensureRowAndCells_ = originalEnsure;
}
assert.ok(legacyHeaderReads <= 2, `one request reread the legacy header ${legacyHeaderReads} times`);

const laterPrimaryHeader = context.findCounselHeader_({
  getNumRows: () => 2,
  getRow: index => makeRow(index === 0
    ? ["상담세부내용", ""]
    : ["상담일자", "상담일자 / 상담자 / 세부내용"]),
});
assert.strictEqual(laterPrimaryHeader.headerRowIndex, 1);
assert.strictEqual(laterPrimaryHeader.detailColIndex, 1);

const malformedTable = { getNumRows: () => 1, getRow: () => makeRow(["알 수 없는 표"]) };
assert.throws(() => context.findCounselRecordTable_({ getTables: () => [malformedTable] }, {}));
const multipleLookup = {};
assert.strictEqual(context.findCounselRecordTable_({ getTables: () => [malformedTable, legacyTable] }, multipleLookup), legacyTable);
assert.strictEqual(multipleLookup.header.detailColIndex, 1);

let documentOpens = 0;
let documentSaves = 0;
context.DocumentApp = {
  openById(docId) {
    assert.strictEqual(docId, "synthetic-doc");
    documentOpens += 1;
    return {
      getBody: () => ({ getTables: () => [legacyTable] }),
      saveAndClose() {
        documentSaves += 1;
      },
    };
  },
};
context.ContentService = {
  MimeType: { JSON: "json" },
  createTextOutput: text => ({ setMimeType: () => JSON.parse(text) }),
};
function post(summary, verifyOnly = false) {
  return context.doPost({ postData: { contents: JSON.stringify({
    doc_id: "synthetic-doc",
    student_name: "TEST",
    counseling_date: "2026-08-23",
    summary,
    dedupe_key: "synthetic-key",
    verify_only: verifyOnly,
  }) } });
}
legacyHeaderReads = 0;
assert.strictEqual(post("기존 기록 239").duplicate_skipped, true);
assert.ok(legacyHeaderReads <= 2, `doPost reread the header ${legacyHeaderReads} times`);
assert.strictEqual(documentSaves, 1);
assert.strictEqual(propertyValues.has("document_lock:synthetic-doc"), false);

legacyHeaderReads = 0;
assert.strictEqual(post(original).updated_existing, true);
assert.strictEqual(legacyRows[240][1], original);
assert.strictEqual(legacyRows[239][1], "기존 기록 238");
assert.ok(legacyHeaderReads <= 2);
assert.strictEqual(documentSaves, 2);

legacyHeaderReads = 0;
const propertiesBeforeVerify = JSON.stringify([...propertyValues]);
assert.strictEqual(post(original, true).found_existing, true);
assert.ok(legacyHeaderReads <= 2);
assert.strictEqual(post("다른 내용", true).found_existing, false);
assert.strictEqual(JSON.stringify([...propertyValues]), propertiesBeforeVerify);
assert.strictEqual(documentSaves, 2);
const opensBeforeHealth = documentOpens;
assert.strictEqual(context.doGet().server_revision, "docs-speed-20261001");
assert.strictEqual(documentOpens, opensBeforeHealth);

const firstDocumentLease = context.acquireDocumentLease_("doc-a");
const otherDocumentLease = context.acquireDocumentLease_("doc-b");
assert.notStrictEqual(firstDocumentLease.propertyKey, otherDocumentLease.propertyKey);
assert.throws(
  () => context.acquireDocumentLease_("doc-a"),
  /document lock timeout/i,
);
context.releaseDocumentLease_(firstDocumentLease);
const reacquiredDocumentLease = context.acquireDocumentLease_("doc-a");
context.releaseDocumentLease_(reacquiredDocumentLease);
context.releaseDocumentLease_(otherDocumentLease);

process.stdout.write("same-date Google Docs policy checks passed\n");
