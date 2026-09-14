"""Registry of built-in analyzer "tools" the orchestrator runs.

To add a new analyzer:

1. Create ``analyzers/my_check.py`` with a class implementing the
   :class:`~pr_review_agent.analyzers.base.Analyzer` interface (i.e. a
   ``name``, a ``description``, and an ``analyze(file_diff) -> list[Finding]``
   method).
2. Import it below and add ``"my_check": MyCheckAnalyzer`` to ``REGISTRY``.

That's it -- the CLI, the orchestrator, and ``--list-analyzers`` all pick
it up automatically.
"""

from __future__ import annotations

from pr_review_agent.analyzers.base import Analyzer, Finding, Severity
from pr_review_agent.analyzers.complexity import ComplexityAnalyzer
from pr_review_agent.analyzers.dangerous_calls import DangerousCallsAnalyzer
from pr_review_agent.analyzers.diff_size import DiffSizeAnalyzer
from pr_review_agent.analyzers.secrets import SecretsAnalyzer
from pr_review_agent.analyzers.sql_injection import SqlInjectionAnalyzer
from pr_review_agent.analyzers.todos import TodoAnalyzer

#: name -> Analyzer subclass. Order here is the order analyzers run in.
REGISTRY: dict[str, type[Analyzer]] = {
    "secrets": SecretsAnalyzer,
    "sql_injection": SqlInjectionAnalyzer,
    "dangerous_calls": DangerousCallsAnalyzer,
    "complexity": ComplexityAnalyzer,
    "todos": TodoAnalyzer,
    "diff_size": DiffSizeAnalyzer,
}


def build_analyzers(names: list[str] | None = None) -> list[Analyzer]:
    """Instantiate analyzers by name (default: all registered analyzers,
    in registry order)."""
    selected = names if names else list(REGISTRY.keys())
    instances: list[Analyzer] = []
    for name in selected:
        try:
            cls = REGISTRY[name]
        except KeyError as exc:
            valid = ", ".join(sorted(REGISTRY))
            raise ValueError(f"Unknown analyzer {name!r}. Valid analyzers: {valid}") from exc
        instances.append(cls())
    return instances


__all__ = [
    "Analyzer",
    "Finding",
    "Severity",
    "REGISTRY",
    "build_analyzers",
]
