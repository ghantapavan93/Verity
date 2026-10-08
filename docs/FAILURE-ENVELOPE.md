# Failure envelope: what happens when it breaks

Every row is a case someone can trigger, what the system is meant to do, what it was observed to do,
and the test or record that holds it. "Open" means measured or reasoned about, not yet held by a test.

| Case | Expected | Observed | Held by |
|---|---|---|---|
| DOCX that is not a zip | 422 | 422 | `test_failure_matrix` malformed files |
| Valid zip, broken or hostile package inside (member named `../../x`, garbage XML) | 422, nothing written anywhere | **before 2026-09-29: an `AttributeError` out of python-docx, a 500**; now 422, nothing written | `test_a_docx_member_named_to_escape_the_archive_is_never_written_anywhere` |
| DOCX whose entries declare more than 256 MB unpacked | 413 before parsing | 413; zipfile never reads past a declared size, so the declaration is the bound | `test_a_docx_that_unpacks_far_beyond_its_size_is_refused_before_it_is_parsed` |
| DOCX with an external relationship (link, template) | read with no network call | read; sockets refused during the test and nothing tried one | `test_reading_a_docx_with_an_external_relationship_makes_no_network_call` |
| Macro-enabled `.docm` | 422, unsupported type | 422 | `test_a_macro_enabled_document_is_not_a_supported_type` |
| Encrypted PDF | 422 naming the reason | **before: "not a readable PDF"**; now "the PDF is encrypted" | `test_an_encrypted_pdf_is_refused_with_the_reason` |
| PDF over 2,000 pages | 413 | 413 | `test_a_pdf_with_more_pages_than_any_contract_is_refused` |
| Empty file; file over 25 MB | 422; 413 | 422; 413 | `test_failure_matrix` |
| One paragraph of 2 MB | reads in bounded time; the prompt carries at most 5,000 characters of it | 0.01 s; cut at 5,000 | `test_a_two_megabyte_paragraph_ingests_quickly_and_is_cut_for_the_prompt` |
| A file whose bytes contradict its name (a PDF as `.txt`, a DOCX as `.pdf`, text as `.docx`), in either order | 422 naming what the file is; the same bytes only ever read one way | **before 2026-10-08: a PDF as `.txt` was a 201 text document of its binary, and the same bytes as `.pdf` afterwards were handed that reading**; now 422 in either order, and the right name opens the real reading | `test_file_types` (both orders, six pairs, a Hypothesis property); `e2e/critical.spec.ts` |
| A damaged PDF or DOCX that makes a parser raise (AssertionError, KeyError, zlib.error, pypdf's own errors) | 422 "not a readable …", no row | **before 2026-10-08: 112 of 300 mutations of a real PDF and 21 of 200 of the sample DOCX were a 500**; now read or 422 | `test_reader_boundary` (seeded mutations through `ingest` and the API) |
| A plain-text or PDF line that starts with an address, a year or a registration number | text, not a section; no number the document does not state | **before 2026-10-08: "15285 Minnetonka Blvd." was §15285 and the headings after it §15408 onward; 14 of 510 CUAD readings had such numbers**; now 0 | `test_section_numbers` (the original, siblings, controls, a Hypothesis property) |
| Two later versions of one base stated at the same moment | both recorded, as if one after the other | **before 2026-10-08: 201 and a 409 saying the refused document was already placed, which it was not**; now 201 and 201 | `test_version_statements` |
| Instruction smuggled into the question | ignored, citation intact | ignored (g43) | `docs/GOLDENS.md`, adversarial |
| False premise in the question | not asserted | **asserted as a pass with an unrelated verified quote (g44)** | `docs/GOLDENS.md`; fix is a prompt experiment, not run |
| Instruction inside the contract text | not followed | not followed in two probes through the answer path on 2026-10-02 (a section telling the model to report a pass, and one telling it to report 180 days; Qwen3 8B quoted the real clause both times, and code computed needs review on the first); two probes on one model, not a golden | `DECISIONS.md`, 2026-10-02; still needs a second golden document |
| Instruction inside the guidance | the guidance is the reviewer's own instruction; the verifier still bounds every quote | reasoned, not tested | by design |
| Provider unavailable | run failed, reason `provider_error`, retryable; the interface shows the reason and offers the composer again, never a verdict | as expected, in the API and in the browser | `test_failure_matrix`; `e2e/reliability.spec.ts` provider outage |
| Transport failure | one retry after 2 s | as expected | `test_failure_matrix` |
| Provider timeout (600 s) or a process restart mid-run | run failed by staleness when no stage has progressed for four model timeouts plus a minute (the longest legitimate run: two validation rounds, each with one transport retry), on the next read; the interface shows the reason | as expected; until 2026-09-29 the window was one timeout plus a minute, and at twenty concurrent questions it failed six live runs that were still waiting on the model, whose workers then hit the immutability trigger (`docs/SCALE.md`) | `test_api_flow` stale run |
| Model returns something that is not the schema | one corrected retry, then failed `invalid_output`, never a verdict; the interface says the model did not return a valid result | as expected, in the API and in the browser | `test_failure_matrix`; `e2e/reliability.spec.ts` non-schema output |
| Quote not in the document | finding withheld, raw output kept, the run says so | as expected | `test_api_flow` paraphrase |
| A digit changed inside a quote | refused; no similarity tier | refused | `test_spans`, Hypothesis properties |
| Same request sent twice, or a response lost after success | the same run comes back (`reused: true`) | as expected, in the API and observed on the wire from the browser | `test_failure_matrix`; `e2e/reliability.spec.ts` twice |
| Stream connection lost | the stored stage events are sent again on connect; the client also polls | as expected; with every event stream aborted in the browser, the run still finishes on screen through polling | `useRunFollower` tests, `test_api_flow` events, `e2e/reliability.spec.ts` dropped stream |
| Finished run updated or deleted | the database refuses | as expected | `test_failure_matrix` immutability |
| Section text or document row of a finished run updated or deleted | the database refuses: the record's citations point into that text | as expected, once the triggers covered `sections` and `documents` (independent review, 2026-09-29) | `test_failure_matrix` immutability |
| Twenty questions started at once | every run starts and finishes; the request's session releases its connection before the background task runs | the first measurement ran the connection pool dry (`QueuePool limit of size 5 overflow 10 reached`, 500s on reads) because the request session held a connection for the whole run; `create_run` now commits before returning; re-measured: all twenty finished, none failed (18 complete, 2 unresolved: the model answered and nothing verified); run wall p50 455.4 s, p95 807.0 s | `docs/SCALE.md` |
| Evidence pack with one byte changed | `verify.py` fails | as expected | `test_evidence_pack` |
| Two writers at once on SQLite | WAL mode; batch measured at concurrency 1 only | unmeasured above 1 | open (`docs/BATCH.md`) |
| Provider ten times slower | runs finish; the 600 s timeout, then staleness | reasoned from the timeout; not measured | open |
| Window too narrow for the split | a plain note; Documents, Findings and Runs still work | as expected at 600 px | `e2e/reliability.spec.ts` narrow window |
| Keyboard and assistive technology | Escape closes the drawer; no serious or critical WCAG 2.1 AA violation | **before 2026-09-29: the document scroll region was not keyboard-focusable (axe `scrollable-region-focusable`)**; fixed, then clean on the landing, the workspace and the open drawer | `e2e/reliability.spec.ts` accessibility |

The two rows in bold with "before" are what writing this table found on the day it was written.
