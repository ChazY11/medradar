# Static fixtures used by the state-scheme tests (copies of tests/governance/fixtures/)

The state-scheme flake fix replaces the old test seed that copied the **live**
repository's PROJECT_STATE.yaml and pyproject.toml with these committed static
fixtures:

* `00_state_schema_v2_fixture.yaml` — minimal, schema-compatible
  `medradar.project_state.v2` state (`git`/`verified`/`release` blocks in the new
  format; placeholder commit ids that bump_state replaces).
* `00_pyproject_fixture.toml` — minimal pyproject with a fixed version `9.9.9`,
  so `release.version` and generated-at assertions do not depend on the repo.

They live canonically under `tests/governance/fixtures/`; these copies are for
evidence review.
