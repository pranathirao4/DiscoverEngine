-- Empty discovery database. No author names or author ids.
-- Common schema: source, id, date, text, url, rating, country_or_subreddit, type.

CREATE TABLE IF NOT EXISTS harvest_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    source TEXT,
    status TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS utterances (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    date TEXT,
    text TEXT NOT NULL,
    url TEXT,
    rating TEXT,
    country_or_subreddit TEXT,
    type TEXT NOT NULL,
    parent_post_id TEXT,
    search_queries TEXT,
    harvest_run_id TEXT,
    FOREIGN KEY (harvest_run_id) REFERENCES harvest_runs(run_id)
);

CREATE TABLE IF NOT EXISTS relevance_labels (
    utterance_id TEXT PRIMARY KEY,
    relevance TEXT NOT NULL,
    confidence TEXT NOT NULL,
    exclude_reason TEXT,
    rationale TEXT,
    prompt_version TEXT,
    model_id TEXT,
    FOREIGN KEY (utterance_id) REFERENCES utterances(id)
);

CREATE TABLE IF NOT EXISTS retrieval_evidence (
    utterance_id TEXT PRIMARY KEY,
    photo_type TEXT,
    failure_type TEXT,
    memory_anchors TEXT,
    forgotten_anchors TEXT,
    retrieval_behaviors TEXT,
    quotes TEXT,
    confidence TEXT,
    prompt_version TEXT,
    model_id TEXT,
    FOREIGN KEY (utterance_id) REFERENCES utterances(id)
);

CREATE TABLE IF NOT EXISTS embeddings (
    utterance_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    model_id TEXT NOT NULL,
    dim INTEGER NOT NULL,
    cache_key TEXT,
    PRIMARY KEY (utterance_id, kind, model_id),
    FOREIGN KEY (utterance_id) REFERENCES utterances(id)
);

CREATE INDEX IF NOT EXISTS idx_utterances_source ON utterances(source);
CREATE INDEX IF NOT EXISTS idx_utterances_type ON utterances(type);
CREATE INDEX IF NOT EXISTS idx_relevance ON relevance_labels(relevance);
