"""Experimental, isolated research code.

This package deliberately does **not** ship inside the installable ``medradar``
distribution: ``pyproject.toml`` only packages ``medradar*``, so nothing here is
imported by the product code path, the CLI, or the existing test suite unless a
test explicitly imports it.

Each subpackage is an experiment with its own README, its own configuration and,
where needed, its own optional dependency group.  Experiments are allowed to be
incomplete; what they may not do is quietly change the behaviour of the
``medradar`` package itself.
"""
