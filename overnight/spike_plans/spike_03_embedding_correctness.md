LAB TEST PLAN: SPIKE 3 - EMBEDDING CORRECTNESS (R-006)
VERSION: 11.6.0
REFERENCE: Appendix O.2 (Model Integrity), Appendix O.3 (Vector Space Validation)

1. MODEL HASH VERIFICATION
Objective: Ensure the integrity of the nomic-embed-text artifact.
Procedure:
- Calculate SHA-256 checksum of the local model weight file (e.g., model.safetensors).
- Compare against the verified baseline hash recorded in the LOCAL-SOC-SLM registry.
- Fail if mismatch occurs; trigger immediate quarantine of the model directory.
- Exit Code: 1 on hash mismatch.

2. DIMENSION CHECK
Objective: Validate vector output compatibility with pgvector schema.
Procedure:
- Pass a standardized test string ("SOC-LAB-TEST-VECTOR-001") through the inference pipeline.
- Extract the resulting embedding array.
- Verify array length equals exactly 768 dimensions.
- Verify data type is float32.
- Exit Code: 1 if dimension != 768.

3. PREFIX POLICY TEST
Objective: Validate adherence to nomic-embed-text prefix requirements (search_document vs search_query).
Procedure:
- Generate embeddings for the same input string using:
  a) No prefix.
  b) "search_document: " prefix.
  c) "search_query: " prefix.
- Calculate cosine similarity between (a) and (b), and (a) and (c).
- Verify that the model applies distinct transformations based on the prefix.
- Exit Code: 1 if prefix injection fails to alter the vector space.

4. TOP-K RECALL TEST
Objective: Benchmark semantic retrieval accuracy within the active window.
Procedure:
- Ingest a controlled set of 100 known security alerts into the vector store.
- Execute 10 known-query searches (Top-K=5).
- Calculate Mean Reciprocal Rank (MRR) for the retrieved results.
- Verify MRR meets the minimum threshold defined in Appendix O.3.
- Exit Code: 1 if recall falls below 0.85.

5. PREFIX IDEMPOTENCY TEST
Objective: Ensure repeated prefix application does not degrade embedding stability.
Procedure:
- Apply the prefix "search_document: " to a string.
- Apply the prefix "search_document: " to the *already prefixed* string.
- Compare the resulting embeddings using Euclidean distance.
- Verify distance is near-zero (floating point epsilon tolerance).
- Exit Code: 1 if non-idempotent behavior is detected.

TEST COMPLETION CRITERIA:
- All tests must return 0.
- Any failure requires a rollback to the previous verified model state.
- Results must be logged to the local SQLite ephemeral state for audit.