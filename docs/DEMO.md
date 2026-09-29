# The 90-second walkthrough

Everything below is what the build does today. Nothing is staged: the model call is real, the
stage list is the API's own progress, and every citation was located by code before it was
shown. Warm the model first (ask one question and discard it) so the recorded run is not the
cold-start one.

**Before recording.** Ollama running with `qwen3:8b`; API on 8000; interface on 3900; browser
window about 1280 px wide; a fresh tab on `/`.

| Time | On screen | Say |
|---|---|---|
| 0–8 s | The composer: "What are you reviewing?" Click **try a sample agreement** (Common Paper's Cloud Service Agreement, CC BY 4.0). | "I wanted the model to be one part of the system. Every answer here has evidence that code verified against the file." |
| 8–18 s | The composer becomes the file, reads "Reading document → Ready", and the workspace opens: the contract on paper, the Assistant beside it. Click **Add guidance**, keep the default rule (30 days' notice for termination for convenience), click **Use**. | "Guidance is first-class: a lawyer's rule the review is checked against." |
| 18–25 s | Click the suggestion **What notice is needed to terminate for convenience?** | "Now the run." |
| 25–75 s | The stage list fills from the API's events: Reading contract (11 pages · 123 sections) → Finding relevant language (6 candidate sections) → Checking against guidance → Verifying citations (3 of 3 quotes verified). | "These are the pipeline's real stages, not a spinner and not chain-of-thought. The wait is the local 8B model." |
| 75–85 s | The finding appears as an object: topic, status **Not found**, conclusion, and the evidence rows with the quoted passages. | "It did not find a convenience right in the sections it read, and it says so as a statement about what it read." |
| 85–92 s | Click the first evidence row. The document scrolls to §5.4 and the exact sentence is marked. | "Exact span, from stored offsets, not a page number." |
| 92–98 s | Click **Inspect evidence**. The drawer shows each quote marked verified, the guidance, the model, the prompt version and hash, the latency. | "The second layer: versioned prompt, verified quotes, run metadata." |
| 98–104 s | Click **Generate review memo**, then **Open**. | "The memo is a projection of the stored, verified findings. No second model call." |
| 104–110 s | Rail → **Runs**, open the run. Hashes, options with the model, task and routing reason, timing per stage, sections handed to the model, per-quote location method, raw JSON, the evidence pack link. Scroll to the golden set (forty-two questions, previous answer / new answer / what changed / better or worse), the batch over the public corpus, the document families, and the three killed experiments. | "Prompt and model changes are kept only if this table moves. The same repository carries the experiments that killed three features before I built this." |

Stop there. Let them click.

**If the model is slow.** The stage list keeps reporting; do not talk over it. If a run ends
"No supporting passage found", that is the honest state for a question the sections cannot
answer; ask a different one rather than re-running the same question.

**Failure states worth showing if asked.** Ask for a most-favoured-nation clause: the run ends
with "No supporting passage found" and lists the sections it searched. Stop Ollama and ask
again: "The model could not be reached", with **Try again**. A quote the verifier cannot match
never appears as evidence; the run says the finding was withheld.
