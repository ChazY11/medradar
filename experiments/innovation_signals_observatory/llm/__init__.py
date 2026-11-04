"""Phase 4 · WP1/WP3 local-model extraction on real job text.

This package is the experiment harness for one question:

    Can a locally hosted 4B open model, with no training, turn a real public
    Medtronic job posting into a *verifiable* structured record (function class,
    technology track, capability phrases, R&D evidence) whose every claim field
    cites a verbatim span of the posting?

It deliberately does **not** answer that question.  It only measures it.

Layout
------
``job_text_schema.py``   the new (job-text) extraction contract: closed vocabularies,
                         strict decoders, JSON Schema, parse boundary
``prompt_job_v1.py``     the single versioned prompt family for arm B
``subset.py``            the declared deterministic sampling rule
``run_job_text_experiment.py``  bounded runner (arm A rules / arm B model / arm C
                         NOT_RUN / offline stub)
``evaluate.py``          arm-agnostic scorer: schema, verbatim evidence, support
                         check, abstention and negative-control false positives

Reuse, not rebuild
------------------
The model stack, prompt/parse/evidence plumbing and run-gate discipline are
imported from :mod:`experiments.local_llm_event_extraction`.  That package's
*task schema* (regulatory events) is not compatible with job text, so this
package owns a new schema; it must never be described as reusing the event
schema or the event-specific QLoRA adapter (arm C = NOT_RUN, see the docs).

Nothing here imports torch/transformers at import time, opens a socket, or
writes outside ``results/2026-11-04/llm``.
"""

from __future__ import annotations

__version__ = "0.1.0"
