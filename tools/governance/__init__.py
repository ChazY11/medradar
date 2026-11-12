"""MedRadar governance gates.

Stdlib-only tooling behind ``docs/governance/GOVERNANCE.md``:

* ``check_state``       — PROJECT_STATE.yaml is true to ``main`` and to its contract;
* ``gen_views``         — derived views are generated, deterministic and untampered;
* ``check_frozen``      — per-file freeze digests, manifests and audited re-baselines;
* ``check_licence``     — positive data inventory + content classification + PR diff;
* ``check_links``       — relative documentation links resolve;
* ``check_rule_audit``  — governance rule changes require an approved decision;
* ``bump_state``        — deterministic ``main``-block bump after main advances;
* ``record_tests``      — runs the offline suite and writes the test-count artifact;
* ``yamlmini``          — the documented YAML subset used by every governance file;
* ``common``            — shared root discovery, git queries, digest and report helpers.
"""
