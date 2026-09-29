"""Use cases. Each module is one thing the product does, expressed as a function over a session:
routes call these; these call ingestion, retrieval, analysis, verification, memo and persistence.
Nothing here talks HTTP, and nothing here calls the model directly."""
