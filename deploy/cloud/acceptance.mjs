// The deployment's acceptance check: what a release must do on a running site, checked against evidence and behaviour,
// not against its own wording. Run from the repository root, against the commit the site was built from:
//
//   BASE=https://verity.example.com SHA=$(git rev-parse HEAD) node deploy/cloud/acceptance.mjs
//   BASE=https://localhost:18443 INSECURE_TLS=1 node deploy/cloud/acceptance.mjs        (a rehearsal behind Caddy's own CA)
//
// It asks the live model two or three questions about the bundled sample, as any visitor could; nothing else is written.
// Evidence used, none of it the release's wording:
// - the /break record at the commit (git show <SHA or HEAD>:src/components/break/break-record.json), read here, not
//   through the page: the role key must show its decisive passages and section headings exactly, and each
//   rejected-fix score must equal the count computed from its verdict rows;
// - the sections /break publishes as handed to the model: each quoted heading, as rendered after CSS, must be one of
//   them exactly, and each definition must stand in its text;
// - the API's run record and the model's raw output: the withheld sentence must be the model's own sentence, only on
//   a "missing" finding, never blank, never the product's sentence;
// - the document's section text from the API: every verified quote must be that text at its offsets, under the
//   verifier's tier (backend verify/spans.py);
// - the card, the drawer, the HTML memo and the .docx memo must show exactly what the API sent, and only then; the
//   ledger must credit support to the model and the quote to code exactly when a quote was verified.
// Exit 0: every check OK. Exit 1: a check failed. Exit 2: nothing failed, but a behaviour was not exercised.
// Session cookies stay in memory; screenshots and the log go to OUT (default: verity-acceptance in the temp directory).
import { chromium } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { inflateRawSync } from "node:zlib";

const BASE = process.env.BASE ?? "https://ivo.pavankg.dev";
const API = process.env.API ?? BASE;
const SHA = process.env.SHA ?? "";
const REPO = process.env.REPO ?? ".";
const OUT = process.env.OUT ?? join(tmpdir(), "verity-acceptance");
const INSECURE_TLS = process.env.INSECURE_TLS === "1";
const NOT_FOUND = "The model did not find this in the sections it was given."; // models.NOT_FOUND_CONCLUSION
const QUESTIONS = ["Is there a most favoured nation clause?", "What is the limitation of liability?"];
const FALLBACK_NONE = "Does the agreement require the provider to carry cyber insurance?";
mkdirSync(OUT, { recursive: true });

const log = [];
const note = (step, ok, detail = "") => {
  const state = ok === null ? "NOT EXERCISED" : ok ? "OK" : "FAIL";
  log.push({ step, state, detail: String(detail) });
  console.log(`${state.padEnd(13)} ${step}${detail ? " | " + String(detail).slice(0, 220) : ""}`);
};
// Words as the looser verifier tiers compare them: letters and digits, case folded, a digit-group comma dropped
// ("1,500" is "1500").
const words = (s) => ((s ?? "").replace(/(\d),(?=\d{3}(?!\d))/g, "$1").match(/[\p{L}\p{N}]+/gu) ?? []).map((w) => w.toLowerCase()).join(" ");
const flat = (s) => (s ?? "").replace(/\s+/g, " ").trim();
// Letters and digits only, as the verifier compares a label (verify/spans.py _alnum).
const alnum = (s) => words(s).replace(/ /g, "");
// Offsets are counted in code points (backend and lib/text); a JS string slice counts UTF-16 units.
const cpSlice = (text, start, end) =>
  Array.from(text ?? "")
    .slice(start, end)
    .join("");
// The stored sentence is the model's with its sec_N handles replaced by the section's label (runs/prose.py
// label_handles): "§number", or the heading when the section has no number; a handle naming no section is dropped.
function labelHandles(text, labels) {
  return (text ?? "")
    .replace(/\[\s*sec_(\d+)\s*\]|\bsec_(\d+)\b/g, (_, a, b) => labels.get(`sec_${a ?? b}`) ?? "")
    .replace(/\(\s*\)|\[\s*\]/g, "")
    .replace(/\s+([.,;:)\]])/g, "$1")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}
const short = (s) => s.slice(0, 14).replace(/\W+/g, "-");

// ---------------------------------------------------------------- the record, read from git
const ref = SHA || execFileSync("git", ["-C", REPO, "rev-parse", "HEAD"], { encoding: "utf-8" }).trim();
const record = JSON.parse(
  execFileSync("git", ["-C", REPO, "show", `${ref}:src/components/break/break-record.json`], { encoding: "utf-8", maxBuffer: 64 << 20 }),
);
const headline = record.headline;
const citedSection = headline.sessions[0].finding.spans[0].sectionId;
const defining = headline.decisivePassages.filter((p) => p.sectionId !== citedSection);
function recordScore(set) {
  const wrong = record.rejectedFix.rows.filter((r) => r.set === set && r.label === "wrong_party");
  const cases = new Map();
  for (const r of wrong) cases.set(r.case, [...(cases.get(r.case) ?? []), r.flagged]);
  return {
    questions: cases.size,
    every: [...cases.values()].filter((v) => v.every(Boolean)).length,
    findings: wrong.length,
    caught: wrong.filter((r) => r.flagged).length,
  };
}

const browser = await chromium.launch();

// ---------------------------------------------------------------- /break
for (const width of [1440, 390]) {
  const context = await browser.newContext({ viewport: { width, height: width > 800 ? 900 : 844 }, ignoreHTTPSErrors: INSECURE_TLS });
  const page = await context.newPage();
  const api = [];
  page.on("request", (r) => new URL(r.url()).pathname.startsWith("/api/") && api.push(r.url()));
  await page.goto(`${BASE}/break`);
  await page.getByRole("figure", { name: /the question, the answer and the quote/i }).waitFor({ timeout: 30000 });

  // The role key, as rendered.
  const key = page.getByRole("group", { name: "Who is who in this clause" });
  const entries = (await key.count())
    ? await key.locator("li").evaluateAll((items) => items.map((li) => ({ rendered: li.innerText, definition: li.querySelector("q")?.textContent ?? "" })))
    : [];

  // The sections the page publishes as handed to the model: the heading as the region names it (untouched by CSS)
  // and the text, read together once the region shows the section just chosen.
  await page.getByRole("tab", { name: /Retrieved/ }).click();
  const slices = page.getByRole("list", { name: "Sections handed to the model, in rank order" }).getByRole("button");
  const handed = new Map();
  for (let i = 0; i < (await slices.count()); i++) {
    await slices.nth(i).click();
    await page.waitForFunction(
      (n) => document.querySelectorAll('ol[aria-label="Sections handed to the model, in rank order"] button')[n]?.getAttribute("aria-pressed") === "true",
      i,
    );
    const { label, text } = await page
      .locator('[role="region"][aria-label^="Section text: "]')
      .evaluate((r) => ({ label: r.getAttribute("aria-label"), text: r.innerText }));
    handed.set(label.slice("Section text: ".length), text);
  }
  for (const [heading, text] of handed) {
    const inRecord = Object.values(headline.sections).find((s) => s.heading === heading);
    note(
      `/break ${width}: published section "${heading}" is the record's text`,
      !!inRecord && flat(text).includes(flat(inRecord.text)),
      `${flat(text).length} chars`,
    );
  }

  note(
    `/break ${width}: the role key lists each defining passage of the record`,
    entries.length === defining.length,
    `${entries.length} shown, ${defining.length} in the record`,
  );
  for (const [i, e] of entries.entries()) {
    const heading = /defined in “([^”]+)”:/.exec(e.rendered)?.[1] ?? null;
    const p = defining[i];
    const section = p ? headline.sections[p.sectionId] : undefined;
    note(
      `/break ${width}: quoted heading, as rendered, is the record's section heading exactly`,
      !!section && heading === section.heading,
      `shown “${heading}”, record “${section?.heading}”`,
    );
    note(`/break ${width}: the quoted heading is a section the model was handed`, heading !== null && handed.has(heading));
    note(
      `/break ${width}: the definition is the record's passage, and stands in that section's text`,
      !!section && e.definition === p.quote && section.text.includes(p.quote) && flat(handed.get(heading) ?? "").includes(flat(p.quote)),
      e.definition.slice(0, 80),
    );
  }

  // The rejected fix: the scores against counts computed here from the record's verdict rows, and against the rows the
  // page shows beneath them.
  for (const [name, set] of [
    ["Cases it was built on", "diagnostic"],
    ["Unseen cases", "unseen"],
  ]) {
    const side = page.getByRole("region", { name, exact: true });
    if ((await side.count()) === 0) {
      note(`/break ${width}: "${name}" shown`, false, "no such region");
      continue;
    }
    const want = recordScore(set);
    const scored = flat(await side.innerText());
    const every = /(\d+)\s*of\s*(\d+)\s*wrong-party questions caught in every session/.exec(scored);
    const found = /(\d+) of (\d+) wrong-party findings caught/.exec(scored);
    note(
      `/break ${width}: "${name}" question score is the record's count`,
      !!every && Number(every[1]) === want.every && Number(every[2]) === want.questions,
      `shown ${every?.[1]} of ${every?.[2]}; record ${want.every} of ${want.questions}`,
    );
    note(
      `/break ${width}: "${name}" finding count is the record's count`,
      !!found && Number(found[1]) === want.caught && Number(found[2]) === want.findings,
      `shown ${found?.[1]} of ${found?.[2]}; record ${want.caught} of ${want.findings}`,
    );
    const marks = await side.getByRole("listitem").evaluateAll((items) =>
      items
        .map((li) => li.querySelector(":scope > button")?.children[1])
        .filter(Boolean)
        .map((m) => Array.from(m.children, (x) => /(caught|missed)\s*$/.exec(x.textContent ?? "")?.[1] ?? "?")),
    );
    note(
      `/break ${width}: "${name}" rows shown are the record's verdicts`,
      marks.length === want.questions && marks.flat().length === want.findings && marks.flat().filter((v) => v === "caught").length === want.caught,
      `${marks.length} rows, ${marks.flat().length} marks`,
    );
  }

  // The exhibit's quote against its section, by the page's own check in this browser (the record's quote and offsets
  // are checked against the filing's text by backend tests/test_break_record.py; this is that check, live).
  await page.getByRole("tab", { name: /What code checked/ }).click();
  await page.getByRole("button", { name: "Check it in your browser" }).click();
  const same = await page
    .getByText(/^Same \d+ words in the same order\./)
    .waitFor({ state: "visible", timeout: 10000 })
    .then(() => true)
    .catch(() => false);
  note(`/break ${width}: the quote is the section's text at its offsets (in-browser check)`, same);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  note(`/break ${width}: no horizontal overflow`, overflow <= 0, `${overflow}px`);
  note(`/break ${width}: the page asked the API nothing`, api.length === 0, api.join(" "));
  await page.screenshot({ path: `${OUT}/break-${width}.png` });
  await context.close();
}

// ---------------------------------------------------------------- workbench
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, ignoreHTTPSErrors: INSECURE_TLS });
const page = await context.newPage();
const problems = [];
page.on("pageerror", (e) => problems.push(`pageerror: ${e}`));
page.on("response", (r) => r.status() >= 500 && problems.push(`HTTP ${r.status()} ${new URL(r.url()).pathname}`));
const get = async (path) => (await page.request.get(`${API}${path}`)).json();

await page.goto(BASE);
await page.getByRole("button", { name: "try a sample agreement" }).click();
await page.waitForURL(/[?&]document=/, { timeout: 120000 });
await page.locator("section[data-section]").first().waitFor();
const cards = page.locator("article").filter({ has: page.getByRole("button", { name: "Inspect evidence" }) });

async function ask(question) {
  const composer = page.getByPlaceholder("Ask a question about this contract");
  await composer.fill(question);
  const started = page.waitForResponse((r) => r.url().includes("/api/runs") && r.request().method() === "POST", { timeout: 60000 });
  await composer.press("Enter");
  const runId = (await (await started).json()).id;
  let detail = {};
  for (let i = 0; i < 400; i++) {
    detail = await get(`/api/runs/${runId}/detail`);
    if (["complete", "unresolved", "failed"].includes(detail.stage)) break;
    await page.waitForTimeout(1500);
  }
  if (detail.stage === "complete") {
    // The panel shows the current run's findings only, in the API's order.
    await page.waitForFunction(
      ({ n, topic }) => {
        const shown = [...document.querySelectorAll("article")].filter((a) =>
          [...a.querySelectorAll("button")].some((b) => b.textContent === "Inspect evidence"),
        );
        return shown.length === n && shown[0].textContent.includes(topic);
      },
      { n: detail.findings.length, topic: detail.findings[0]?.topic ?? "" },
      { timeout: 60000 },
    );
  }
  note(
    `"${question}": the run completed`,
    detail.stage === "complete",
    `stage ${detail.stage}, statuses ${JSON.stringify((detail.findings ?? []).map((f) => f.status))}`,
  );
  return detail;
}

/** The text of each paragraph of a .docx's word/document.xml, read from the zip's local file headers. */
function docxParagraphs(buffer) {
  for (let at = 0; at + 30 <= buffer.length;) {
    if (buffer.readUInt32LE(at) !== 0x04034b50) break;
    const method = buffer.readUInt16LE(at + 8);
    const size = buffer.readUInt32LE(at + 18);
    const nameLength = buffer.readUInt16LE(at + 26);
    const extraLength = buffer.readUInt16LE(at + 28);
    const name = buffer.toString("utf-8", at + 30, at + 30 + nameLength);
    const start = at + 30 + nameLength + extraLength;
    if (name === "word/document.xml") {
      const raw = buffer.subarray(start, start + size);
      const xml = (method === 8 ? inflateRawSync(raw) : raw).toString("utf-8");
      const decode = (s) =>
        s
          .replace(/&lt;/g, "<")
          .replace(/&gt;/g, ">")
          .replace(/&quot;/g, '"')
          .replace(/&apos;/g, "'")
          .replace(/&amp;/g, "&");
      return xml.split("</w:p>").map((p) => decode([...p.matchAll(/<w:t(?:\s[^>]*)?>([^<]*)<\/w:t>/g)].map((m) => m[1]).join("")));
    }
    at = start + size;
  }
  return null;
}

let withheldSeen = 0;
let passagesSeen = 0;
async function check(question) {
  const detail = await ask(question);
  if (detail.stage !== "complete") return;
  const doc = await get(`/api/documents/${detail.documentId}`);
  const sections = new Map(doc.sections.map((s) => [s.id, s]));
  const handles = new Map((detail.candidates ?? []).map((c) => [c.label, c.number ? `§${c.number}` : c.heading]));
  let raw = [];
  try {
    raw = (JSON.parse(detail.rawOutput ?? "").findings ?? []).map((r) => labelHandles(r.conclusion, handles));
  } catch {
    raw = null;
  }
  note(
    `"${question}": the API's card count is the panel's`,
    (await cards.count()) === detail.findings.length,
    `${await cards.count()} cards, ${detail.findings.length} findings`,
  );

  for (const [i, f] of detail.findings.entries()) {
    const label = `"${question}" · ${f.topic} (${f.status})`;
    const own = (f.modelConclusion ?? "").trim();
    const expected = f.status === "missing" && own && own !== NOT_FOUND ? own : null;
    note(
      `${label}: the model's sentence is the one in the model's raw output`,
      raw !== null && raw.includes(own),
      raw === null ? "raw output not JSON" : own.slice(0, 80),
    );
    note(
      `${label}: the API's withheld sentence follows the rule`,
      (f.withheldConclusion ?? null) === expected,
      `withheld=${JSON.stringify(f.withheldConclusion ?? null).slice(0, 90)}`,
    );
    note(
      `${label}: the finding's sentence is the product's when not found, the model's otherwise`,
      f.status === "missing" ? f.conclusion === NOT_FOUND : f.conclusion === f.modelConclusion,
      f.conclusion.slice(0, 90),
    );
    // Every verified quote is the document's text at its offsets, under the verifier's tier: "exact" is the text
    // itself; the looser tiers are the same words in the same order; "unprefixed:<tier>" is a quote that begins with
    // its section's own label (number and heading, or the heading alone), located without it, so what precedes the
    // located text must be that label and no more.
    // "relocated:<method>" is a quote found in another section than the one cited; the span carries the section it
    // was found in, so it is checked there under <method>.
    for (const s of f.spans.filter((x) => x.verified)) {
      const section = sections.get(s.sectionId);
      const at = cpSlice(section?.text, s.start, s.end);
      const method = s.method.replace(/^relocated:/, "");
      const tier = method.replace(/^unprefixed:/, "");
      let ok = at.length > 0;
      if (ok && !method.startsWith("unprefixed:")) ok = tier === "exact" ? at === s.quote : words(at) === words(s.quote);
      else if (ok) {
        const all = words(s.quote);
        const tail = words(at);
        const head =
          tier === "exact" && s.quote.endsWith(at)
            ? s.quote.slice(0, s.quote.length - at.length)
            : all.endsWith(` ${tail}`)
              ? all.slice(0, all.length - tail.length - 1)
              : null;
        const bare = section.heading.replace(/^\s*\d+(?:\.\d+)*[.)]?\s+/, "");
        ok = !!head && alnum(head).length > 0 && [`${section.number} ${section.heading}`, section.heading, bare].map(alnum).includes(alnum(head));
      }
      note(`${label}: verified quote is the document's text at ${s.start}-${s.end} (${s.method})`, ok, s.quote.slice(0, 80));
    }
    if (expected) withheldSeen++;
    if (f.status !== "missing" && f.spans.some((x) => x.verified)) passagesSeen++;

    // The card, by position: its sentence, its withheld block, its ledger's credits.
    const card = cards.nth(i);
    note(`${label}: the card states the API's sentence`, flat(await card.locator("p").first().innerText()) === flat(f.conclusion));
    const block = card.locator("details");
    if (expected) {
      const open = await block.evaluate((d) => d.open).catch(() => null);
      const shown = flat(
        await block
          .locator("p")
          .first()
          .textContent()
          .catch(() => ""),
      );
      note(
        `${label}: the card keeps the model's sentence collapsed, exactly as the API sent it`,
        open === false && shown === flat(expected),
        shown.slice(0, 80),
      );
    } else {
      note(`${label}: the card shows no withheld block`, (await block.count()) === 0);
    }
    const credits = await card
      .locator('dl[aria-label="What was checked"] > div')
      .evaluateAll((divs) => divs.map((d) => ({ by: d.getAttribute("data-by"), label: d.querySelector("dt")?.textContent ?? "" })));
    const support = credits.find((r) => /^(Supports it\?|Absent\?)$/.test(r.label)) ?? null;
    const quoteRow = credits.find((r) => r.label === "Quote" || r.label === "Passages") ?? null;
    if (f.evidenceKind === "coverage" || f.spans.length > 0) {
      note(`${label}: whether the passage supports the answer is credited to the model, not code`, support?.by === "model", JSON.stringify(support));
    } else {
      note(`${label}: no passage cited, so no support row`, support === null, JSON.stringify(support));
    }
    const quoteBy = f.evidenceKind === "coverage" || !f.spans.some((x) => x.verified) ? "nobody" : "code";
    note(
      `${label}: the quote row is code's exactly when a quote was verified and relied on`,
      quoteRow?.by === quoteBy,
      `${JSON.stringify(quoteRow)}, expected ${quoteBy}`,
    );

    // The drawer: the same sentence, and only then.
    await card.getByRole("button", { name: "Inspect evidence" }).click();
    const drawer = page.locator('[aria-label="Evidence"]');
    await drawer.waitFor();
    const inDrawer = drawer.getByTestId("model-sentence");
    const drawerText = (await inDrawer.count()) > 0 ? flat(await inDrawer.innerText()) : null;
    note(
      `${label}: the drawer shows the withheld sentence exactly when the API sends one`,
      expected ? drawerText?.endsWith(flat(expected)) === true : drawerText === null,
      (drawerText ?? "none").slice(0, 80),
    );
    await page.getByRole("button", { name: "Close evidence" }).click();
  }

  // The memo, HTML and .docx: the product's sentence for each not-found finding; the model's once, after its label,
  // only where the API sent one.
  const memo = await (await page.request.post(`${API}/api/memos`, { data: { runId: detail.id } })).json();
  // Expected from the rule over the model's own sentences, not from the API's field, so a memo cannot pass by agreeing
  // with a wrong or missing field.
  const want = detail.findings
    .map((f) => ((f.modelConclusion ?? "").trim() && f.status === "missing" && f.modelConclusion.trim() !== NOT_FOUND ? f.modelConclusion.trim() : null))
    .filter(Boolean)
    .map(flat);
  const missing = detail.findings.filter((f) => f.status === "missing").length;
  const memoPage = await context.newPage();
  await memoPage.goto(`${API}${memo.htmlUrl}`);
  const htmlLines = (await memoPage.locator("p.withheld").allTextContents()).map(flat);
  note(
    `"${question}": the HTML memo carries each withheld sentence once, labelled, and no other`,
    htmlLines.length === want.length && want.every((w, k) => htmlLines[k].startsWith("The model also wrote") && htmlLines[k].endsWith(w)),
    `${htmlLines.length} line(s), ${want.length} expected`,
  );
  const memoText = flat(await memoPage.locator("body").innerText());
  note(
    `"${question}": the HTML memo states the product's sentence for each not-found finding`,
    memoText.split(NOT_FOUND).length - 1 === missing,
    `${missing} expected`,
  );
  await memoPage.screenshot({ path: `${OUT}/memo-${short(question)}.png`, fullPage: true });
  await memoPage.close();
  const docx = await page.request.get(`${API}${memo.docxUrl}`);
  const paragraphs = docxParagraphs(Buffer.from(await docx.body()));
  if (paragraphs === null) note(`"${question}": the .docx memo reads`, false, `HTTP ${docx.status()}`);
  else {
    const lines = paragraphs.map(flat).filter((p) => p.startsWith("The model also wrote"));
    note(
      `"${question}": the .docx memo carries each withheld sentence once, labelled, and no other`,
      lines.length === want.length && want.every((w, k) => lines[k].endsWith(w)),
      `${lines.length} paragraph(s), ${want.length} expected`,
    );
    note(
      `"${question}": the .docx memo states the product's sentence for each not-found finding`,
      paragraphs.map(flat).filter((p) => p === NOT_FOUND).length === missing,
      `${missing} expected`,
    );
  }
  await page.screenshot({ path: `${OUT}/card-${short(question)}.png` });
}

for (const question of QUESTIONS) await check(question);
if (withheldSeen === 0) await check(FALLBACK_NONE); // the real model may answer the first absence question otherwise
note("workbench: a withheld sentence was exercised", withheldSeen > 0 ? true : null, `${withheldSeen} finding(s)`);
note("workbench: a verified passage was exercised", passagesSeen > 0 ? true : null, `${passagesSeen} finding(s)`);

if (SHA) {
  await page.getByRole("button", { name: "Runs" }).click();
  const built = (
    await page
      .getByText(/Interface built from commit/)
      .first()
      .innerText()
  ).trim();
  note("the interface names the released commit", built.includes(SHA.slice(0, 12)), built.slice(0, 80));
}
note("workbench: no page errors, no 5xx", problems.length === 0, problems.join(" ; "));
await context.close();
await browser.close();

writeFileSync(`${OUT}/accept-log.json`, JSON.stringify({ base: BASE, sha: SHA, record: ref, at: new Date().toISOString(), log }, null, 1));
const failed = log.filter((x) => x.state === "FAIL").length;
const unexercised = log.filter((x) => x.state === "NOT EXERCISED").length;
console.log(`${log.length - failed - unexercised} of ${log.length} checks OK (${failed} failed, ${unexercised} not exercised)`);
process.exit(failed ? 1 : unexercised ? 2 : 0);
