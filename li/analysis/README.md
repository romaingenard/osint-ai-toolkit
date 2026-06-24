# Analysis scripts

Read-only scripts used to produce and audit the material for the LI Sahel report.
They query the local corpus database (`data/corpus.db`, gitignored) in read-only
mode and write human-readable outputs to `outputs/` (gitignored). They are kept
for traceability of the report's construction, not as part of the reusable toolkit.

- `_assemble_paire_b8.py`, `_assemble_paires_m5.py` — extract reformulation pairs
  (source/relay side by side) for on-the-record analysis.
- `_assemble_matiere_temps2.py` — assemble qualitative material by terrain.
- `export_echantillon_llm.py`, `export_audit_disarm_echantillon.py` — export the
  LLM classification of the control sample for human cross-checking (Centaur method).
