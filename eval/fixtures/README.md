# Eval fixtures

The golden workspace and adversarial cases for the Stage 13 benchmark. Document *text* lives
in these files (human-inspectable, versioned); the expected claim/retrieval/contradiction/
wiki-probe sets and per-document metadata (sensitivity, deletion, injection) live in
`src/metis_eval/golden.py` so the golden truth is deterministic and diffable.
