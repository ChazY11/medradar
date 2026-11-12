"""MedRadar governance gates.

Stdlib-only tooling behind ``docs/governance/GOVERNANCE.md``:

* ``check_state``  — PROJECT_STATE.yaml is true to ``main`` and to its own contract;
* ``gen_views``    — derived views are generated, deterministic and untampered;
* ``check_frozen`` — frozen research artifacts are byte-identical, no new files;
* ``check_licence``— committed data respects per-source redistribution policy;
* ``check_links``  — relative documentation links resolve;
* ``record_tests`` — runs the offline suite and writes the test-count artifact;
* ``yamlmini``     — the documented YAML subset used by every governance file;
* ``common``       — shared root discovery, git queries, digest and report helpers.
"""
