-- A store created by release-2026-10-02 (c7bdc31), upgraded and used by later builds: one finished run, its finding,
-- span and review. Its findings table has no ck_findings_status_source: SQLite cannot add a CHECK in place, and the
-- builds before 2026-10-30 did not rebuild the table (stress test, store evolution 4). Dumped with sqlite3 .dump.
PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE documents (
	id VARCHAR(32) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	media_type VARCHAR(64) NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	pages INTEGER, 
	parse_ms FLOAT, 
	parser_version VARCHAR(16), 
	tracked_changes INTEGER, 
	hidden_runs INTEGER, 
	coverage_json TEXT, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
INSERT INTO documents VALUES('d9e3dd4ba8054891','agreement.txt','text/plain','60f9c7eaa5eddc9cc6aeb2990c70a0a5e586aa7e8387cf6359afa182cd2a0697',NULL,0.8000000000000000444,'v15',0,0,'{"schema_version": 1, "reader_version": "v15", "source": "persisted", "parts": [{"part": "main_body", "status": "read", "count": 0, "note": "the whole file, decoded as UTF-8"}, {"part": "format_characters", "status": "absent", "count": 0, "note": "no invisible format characters"}]}','2026-10-30 13:58:18.103453');
CREATE TABLE guidance (
	id VARCHAR(32) NOT NULL, 
	text TEXT NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	source VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, "workspace_id" VARCHAR(32), 
	PRIMARY KEY (id)
);
INSERT INTO guidance VALUES('30498d5f808d4d3d','We can accept termination for convenience at 30 days'' notice or more. Anything below 30 days requires review.','0d9e219aca7618423ab18818213e88699674df524481336ef7b48473d61015a1','pasted','2026-10-30 13:58:18.151174','open');
CREATE TABLE batches (
	id VARCHAR(32) NOT NULL, 
	task VARCHAR(64) NOT NULL, 
	task_sha256 VARCHAR(64) NOT NULL, 
	corpus VARCHAR(255) NOT NULL, 
	model VARCHAR(128) NOT NULL, 
	prompt_version VARCHAR(64) NOT NULL, 
	concurrency INTEGER NOT NULL, 
	documents INTEGER NOT NULL, 
	requested INTEGER NOT NULL, 
	started_at DATETIME NOT NULL, 
	finished_at DATETIME, 
	PRIMARY KEY (id)
);
CREATE TABLE sections (
	id VARCHAR(32) NOT NULL, 
	document_id VARCHAR(32) NOT NULL, 
	ordinal INTEGER NOT NULL, 
	number VARCHAR(32) NOT NULL, 
	heading VARCHAR(512) NOT NULL, 
	text TEXT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
);
INSERT INTO sections VALUES('1d22f4b8ef1644ed','d9e3dd4ba8054891',0,'','SERVICES AGREEMENT','SERVICES AGREEMENT');
INSERT INTO sections VALUES('7da655cae9864d06','d9e3dd4ba8054891',1,'1','Term','This Agreement commences on the Effective Date and continues for twelve (12) months.');
INSERT INTO sections VALUES('cbb5cfa9c2c84514','d9e3dd4ba8054891',2,'2','Termination for Convenience','Customer may terminate this Agreement for convenience upon fifteen (15) days’ written notice to Provider. On termination, Customer pays all Fees accrued.');
INSERT INTO sections VALUES('ba58565866c14925','d9e3dd4ba8054891',3,'3','Governing Law','This Agreement is governed by the laws of the State of Delaware.');
CREATE TABLE runs (
	id VARCHAR(32) NOT NULL, 
	document_id VARCHAR(32) NOT NULL, 
	guidance_id VARCHAR(32), 
	question TEXT NOT NULL, 
	stage VARCHAR(32) NOT NULL, 
	provider VARCHAR(32) NOT NULL, 
	model VARCHAR(128) NOT NULL, 
	task VARCHAR(32), 
	routing_reason VARCHAR(255), 
	prompt_version VARCHAR(64) NOT NULL, 
	prompt_hash VARCHAR(64) NOT NULL, 
	options_json TEXT NOT NULL, 
	document_sha256 VARCHAR(64) NOT NULL, 
	guidance_sha256 VARCHAR(64), 
	candidates_json TEXT NOT NULL, 
	raw_output TEXT, 
	input_tokens INTEGER, 
	output_tokens INTEGER, 
	latency_ms FLOAT, 
	note TEXT, 
	error TEXT, 
	reason VARCHAR(32), 
	fingerprint VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	finished_at DATETIME, "relations_json" TEXT, "retrieval_mode" VARCHAR(32), "workspace_id" VARCHAR(32), 
	PRIMARY KEY (id), 
	CONSTRAINT ck_runs_stage CHECK (stage IN ('reading', 'finding_evidence', 'checking', 'verifying', 'complete', 'unresolved', 'failed')), 
	CONSTRAINT ck_runs_reason CHECK (reason IS NULL OR reason IN ('insufficient_evidence', 'citations_unverified', 'invalid_output', 'provider_error', 'internal_error')), 
	FOREIGN KEY(document_id) REFERENCES documents (id), 
	FOREIGN KEY(guidance_id) REFERENCES guidance (id)
);
INSERT INTO runs VALUES('6d2dc4c6b76149c8','d9e3dd4ba8054891','30498d5f808d4d3d','What is the termination notice period?','complete','fake','fake-1','guidance_comparison','no measured alternative for guidance_comparison; the default model','answer-v2','9dbeb12a871ece17872898b2168313a113ab03d7178c263081b5a86d5a1fc954','{"model": "qwen3:8b", "num_ctx": 16384, "policy_version": "policy-v16", "retrieval_aliases": "fe44dfcfc495", "retrieval_k": 6, "retrieval_version": "retrieval-v2", "section_window": 6000, "seed": 42, "temperature": 0.0, "verifier_version": "v11"}','60f9c7eaa5eddc9cc6aeb2990c70a0a5e586aa7e8387cf6359afa182cd2a0697','0d9e219aca7618423ab18818213e88699674df524481336ef7b48473d61015a1','[{"label": "sec_2", "section_id": "cbb5cfa9c2c84514", "number": "2", "heading": "Termination for Convenience"}]','{"findings": [{"topic": "Termination for convenience", "conclusion": "Customer may terminate for convenience on 15 days'' written notice; the guidance requires at least 30 days. [sec_2]", "status_hint": "pass", "evidence": [{"section_id": "sec_2", "quote": "Customer may terminate this Agreement for convenience upon fifteen (15) days\u2019 written notice to Provider."}], "guidance_reference": "at 30 days'' notice or more", "observed": "15 days'' written notice", "required": "at least 30 days", "suggested_position": "Change fifteen (15) days to thirty (30) days."}], "insufficient_evidence": false, "note": null}',100,50,12.5,NULL,NULL,NULL,'009384dba50dccb342215fbb75f6a7839c9ab05bf61e04bb2feb4bec9943211d','2026-10-30 13:58:18.200967','2026-10-30 13:58:18.552241','{"relations": [], "notes": {}}','lexical_match','open');
CREATE TABLE run_stages (
	id INTEGER NOT NULL, 
	run_id VARCHAR(32) NOT NULL, 
	stage VARCHAR(32) NOT NULL, 
	at DATETIME NOT NULL, 
	detail TEXT, 
	completed_at DATETIME, 
	duration_ms FLOAT, 
	status VARCHAR(16), 
	attempt INTEGER, 
	input_hash VARCHAR(64), 
	output_hash VARCHAR(64), 
	error_code VARCHAR(32), 
	owner VARCHAR(128), "rounds" INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(run_id) REFERENCES runs (id) ON DELETE CASCADE
);
INSERT INTO run_stages VALUES(1,'6d2dc4c6b76149c8','reading','2026-10-30 13:58:18.239992','4 sections','2026-10-30 13:58:18.288927',48.89999999999999858,'ok',NULL,'60f9c7eaa5eddc9cc6aeb2990c70a0a5e586aa7e8387cf6359afa182cd2a0697','2d4754ce1f81d11e3e540dba7e0d8de4bb6e8ea82c2baadb1954f9fc39d3df86',NULL,'LAPTOP-MACOCN3F:44400:134378422921826143',NULL);
INSERT INTO run_stages VALUES(2,'6d2dc4c6b76149c8','finding_evidence','2026-10-30 13:58:18.288927','1 candidate section','2026-10-30 13:58:18.388820',99.9000000000000056,'ok',NULL,'16bdb94764718a64ebd55ea424c862ef9c2425217f34623ab8fc5e67faf078de','d99bc9668a97a6a1ea9cf106bb745179d025121e0bea0b63bac9429b7f5b3066',NULL,'LAPTOP-MACOCN3F:44400:134378422921826143',NULL);
INSERT INTO run_stages VALUES(3,'6d2dc4c6b76149c8','checking','2026-10-30 13:58:18.388820','model answered','2026-10-30 13:58:18.471521',82.70000000000000284,'ok',1,'e72427f6f9ace242df76b089ccb62080116b7e598ca51ecf9f3dc3aaafbbc6b4','55c1e2477ac83b61d8600f8d60c0633a848889e32bd281175c1c53e38a1efeb3',NULL,'LAPTOP-MACOCN3F:44400:134378422921826143',1);
INSERT INTO run_stages VALUES(4,'6d2dc4c6b76149c8','verifying','2026-10-30 13:58:18.471521','1 of 1 quote verified','2026-10-30 13:58:18.552253',80.70000000000000284,'ok',NULL,'55c1e2477ac83b61d8600f8d60c0633a848889e32bd281175c1c53e38a1efeb3','efe84426be34a80bf91ea9611666097af3c852dd4c7c60aff257cd007dc87f24',NULL,'LAPTOP-MACOCN3F:44400:134378422921826143',NULL);
INSERT INTO run_stages VALUES(5,'6d2dc4c6b76149c8','complete','2026-10-30 13:58:18.552253',NULL,'2026-10-30 13:58:18.552253',0.0,'ok',NULL,NULL,NULL,NULL,'LAPTOP-MACOCN3F:44400:134378422921826143',NULL);
CREATE TABLE findings (
	id VARCHAR(32) NOT NULL, 
	run_id VARCHAR(32) NOT NULL, 
	ordinal INTEGER NOT NULL, 
	topic VARCHAR(255) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	status_source VARCHAR(32) NOT NULL, 
	status_reason TEXT, 
	conclusion TEXT NOT NULL, 
	guidance_reference VARCHAR(255), 
	observed VARCHAR(255), 
	required VARCHAR(255), 
	suggested_position TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_findings_status CHECK (status IN ('pass', 'needs_review', 'missing', 'unresolved')), 
	FOREIGN KEY(run_id) REFERENCES runs (id) ON DELETE CASCADE
);
INSERT INTO findings VALUES('ef5da0396761487d','6d2dc4c6b76149c8',0,'Termination for convenience','needs_review','computed_days','the contract provides 15 calendar days; the guidance requires at least 30 calendar days; that the quoted period and the guidance concern the same point is the model''s reading, not code''s','Customer may terminate for convenience on 15 days'' written notice; the guidance requires at least 30 days. §2','at 30 days'' notice or more','15 days'' written notice','at least 30 days','Change fifteen (15) days to thirty (30) days.');
CREATE TABLE batch_items (
	id INTEGER NOT NULL, 
	batch_id VARCHAR(32) NOT NULL, 
	document_id VARCHAR(32) NOT NULL, 
	field VARCHAR(64) NOT NULL, 
	run_id VARCHAR(32) NOT NULL, 
	reused BOOLEAN NOT NULL, 
	wall_ms FLOAT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(batch_id) REFERENCES batches (id) ON DELETE CASCADE, 
	FOREIGN KEY(document_id) REFERENCES documents (id), 
	FOREIGN KEY(run_id) REFERENCES runs (id)
);
CREATE TABLE memos (
	id VARCHAR(32) NOT NULL, 
	run_id VARCHAR(32) NOT NULL, 
	review_head VARCHAR(64), 
	docx_path VARCHAR(512) NOT NULL, 
	docx_sha256 VARCHAR(64) NOT NULL, 
	html TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(run_id) REFERENCES runs (id)
);
CREATE TABLE evidence_spans (
	id VARCHAR(32) NOT NULL, 
	finding_id VARCHAR(32) NOT NULL, 
	ordinal INTEGER NOT NULL, 
	section_id VARCHAR(32), 
	cited_section_label VARCHAR(32) NOT NULL, 
	start INTEGER NOT NULL, 
	"end" INTEGER NOT NULL, 
	quote TEXT NOT NULL, 
	verified BOOLEAN NOT NULL, 
	method VARCHAR(32) NOT NULL, 
	match_count INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(finding_id) REFERENCES findings (id) ON DELETE CASCADE, 
	FOREIGN KEY(section_id) REFERENCES sections (id)
);
INSERT INTO evidence_spans VALUES('a48037ba4e3b4fe2','ef5da0396761487d',0,'cbb5cfa9c2c84514','sec_2',0,105,'Customer may terminate this Agreement for convenience upon fifteen (15) days’ written notice to Provider.',1,'exact',1);
CREATE TABLE finding_reviews (
	id INTEGER NOT NULL, 
	finding_id VARCHAR(32) NOT NULL, 
	verdict VARCHAR(16) NOT NULL, 
	reviewer VARCHAR(80) NOT NULL, 
	note TEXT, 
	created_at DATETIME NOT NULL, "access_subject" VARCHAR(80), 
	PRIMARY KEY (id), 
	CONSTRAINT ck_finding_reviews_verdict CHECK (verdict IN ('confirmed', 'dismissed', 'cleared')), 
	FOREIGN KEY(finding_id) REFERENCES findings (id) ON DELETE CASCADE
);
INSERT INTO finding_reviews VALUES(1,'ef5da0396761487d','confirmed','probe',NULL,'2026-10-30 13:58:18.643080',NULL);
CREATE TABLE document_access (
	workspace_id VARCHAR(32) NOT NULL, 
	document_id VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	name VARCHAR(255), 
	PRIMARY KEY (workspace_id, document_id), 
	FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE
);
INSERT INTO document_access VALUES('open','d9e3dd4ba8054891','2026-10-30 13:58:18.107640','agreement.txt');
CREATE TABLE visitor_workspaces (
	workspace_id VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	expires_at DATETIME NOT NULL, 
	PRIMARY KEY (workspace_id)
);
CREATE TABLE document_versions (
	id INTEGER NOT NULL, 
	workspace_id VARCHAR(32) NOT NULL, 
	lineage_id VARCHAR(32) NOT NULL, 
	document_id VARCHAR(32) NOT NULL, 
	supersedes_document_id VARCHAR(32), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES documents (id), 
	FOREIGN KEY(supersedes_document_id) REFERENCES documents (id)
);
CREATE TRIGGER trg_runs_no_update_when_finished BEFORE UPDATE ON runs WHEN OLD.stage IN ('complete', 'unresolved', 'failed') BEGIN SELECT RAISE(ABORT, 'a finished run is immutable (runs)'); END;
CREATE TRIGGER trg_runs_no_delete_when_finished BEFORE DELETE ON runs WHEN OLD.stage IN ('complete', 'unresolved', 'failed') BEGIN SELECT RAISE(ABORT, 'a finished run is immutable (runs)'); END;
CREATE TRIGGER trg_run_stages_no_update_when_finished BEFORE UPDATE ON run_stages WHEN (SELECT stage FROM runs WHERE id = OLD.run_id) IN ('complete', 'unresolved', 'failed') BEGIN SELECT RAISE(ABORT, 'a finished run is immutable (run_stages)'); END;
CREATE TRIGGER trg_run_stages_no_delete_when_finished BEFORE DELETE ON run_stages WHEN (SELECT stage FROM runs WHERE id = OLD.run_id) IN ('complete', 'unresolved', 'failed') BEGIN SELECT RAISE(ABORT, 'a finished run is immutable (run_stages)'); END;
CREATE TRIGGER trg_findings_no_update_when_finished BEFORE UPDATE ON findings WHEN (SELECT stage FROM runs WHERE id = OLD.run_id) IN ('complete', 'unresolved', 'failed') BEGIN SELECT RAISE(ABORT, 'a finished run is immutable (findings)'); END;
CREATE TRIGGER trg_findings_no_delete_when_finished BEFORE DELETE ON findings WHEN (SELECT stage FROM runs WHERE id = OLD.run_id) IN ('complete', 'unresolved', 'failed') BEGIN SELECT RAISE(ABORT, 'a finished run is immutable (findings)'); END;
CREATE TRIGGER trg_evidence_spans_no_update_when_finished BEFORE UPDATE ON evidence_spans WHEN (SELECT r.stage FROM runs r JOIN findings f ON f.run_id = r.id WHERE f.id = OLD.finding_id) IN ('complete', 'unresolved', 'failed') BEGIN SELECT RAISE(ABORT, 'a finished run is immutable (evidence_spans)'); END;
CREATE TRIGGER trg_evidence_spans_no_delete_when_finished BEFORE DELETE ON evidence_spans WHEN (SELECT r.stage FROM runs r JOIN findings f ON f.run_id = r.id WHERE f.id = OLD.finding_id) IN ('complete', 'unresolved', 'failed') BEGIN SELECT RAISE(ABORT, 'a finished run is immutable (evidence_spans)'); END;
CREATE TRIGGER trg_sections_no_update_when_finished BEFORE UPDATE ON sections WHEN EXISTS (SELECT 1 FROM runs WHERE runs.document_id = OLD.document_id AND runs.stage IN ('complete', 'unresolved', 'failed')) BEGIN SELECT RAISE(ABORT, 'a finished run is immutable (sections)'); END;
CREATE TRIGGER trg_sections_no_delete_when_finished BEFORE DELETE ON sections WHEN EXISTS (SELECT 1 FROM runs WHERE runs.document_id = OLD.document_id AND runs.stage IN ('complete', 'unresolved', 'failed')) BEGIN SELECT RAISE(ABORT, 'a finished run is immutable (sections)'); END;
CREATE TRIGGER trg_documents_no_update_when_finished BEFORE UPDATE ON documents WHEN EXISTS (SELECT 1 FROM runs WHERE runs.document_id = OLD.id AND runs.stage IN ('complete', 'unresolved', 'failed')) BEGIN SELECT RAISE(ABORT, 'a finished run is immutable (documents)'); END;
CREATE TRIGGER trg_documents_no_delete_when_finished BEFORE DELETE ON documents WHEN EXISTS (SELECT 1 FROM runs WHERE runs.document_id = OLD.id AND runs.stage IN ('complete', 'unresolved', 'failed')) BEGIN SELECT RAISE(ABORT, 'a finished run is immutable (documents)'); END;
CREATE UNIQUE INDEX ux_documents_sha256_parser ON documents (sha256, parser_version);
CREATE INDEX ix_documents_sha256 ON documents (sha256);
CREATE INDEX ix_guidance_sha256 ON guidance (sha256);
CREATE INDEX ix_sections_document_id ON sections (document_id);
CREATE INDEX ix_runs_document_id ON runs (document_id);
CREATE UNIQUE INDEX ux_runs_fingerprint_active ON runs (fingerprint) WHERE stage != 'failed';
CREATE INDEX ix_run_stages_run_id ON run_stages (run_id);
CREATE INDEX ix_findings_run_id ON findings (run_id);
CREATE INDEX ix_batch_items_document_id ON batch_items (document_id);
CREATE INDEX ix_batch_items_batch_id ON batch_items (batch_id);
CREATE INDEX ix_batch_items_run_id ON batch_items (run_id);
CREATE INDEX ix_memos_run_id ON memos (run_id);
CREATE UNIQUE INDEX ux_memos_run_review ON memos (run_id, review_head);
CREATE INDEX ix_evidence_spans_finding_id ON evidence_spans (finding_id);
CREATE INDEX ix_finding_reviews_finding_id ON finding_reviews (finding_id);
CREATE INDEX ix_document_access_document_id ON document_access (document_id);
CREATE INDEX ix_visitor_workspaces_created_at ON visitor_workspaces (created_at);
CREATE INDEX ix_visitor_workspaces_expires_at ON visitor_workspaces (expires_at);
CREATE UNIQUE INDEX ux_document_versions_workspace_document ON document_versions (workspace_id, document_id);
CREATE INDEX ix_document_versions_lineage_id ON document_versions (lineage_id);
CREATE INDEX ix_document_versions_document_id ON document_versions (document_id);
CREATE INDEX ix_document_versions_workspace_id ON document_versions (workspace_id);
CREATE INDEX ix_guidance_workspace_id ON guidance (workspace_id);
CREATE INDEX ix_runs_workspace_id ON runs (workspace_id);
COMMIT;
