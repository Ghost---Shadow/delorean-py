"""Objective fidelity scoring for the DeLorean model.

Runs in system Python (numpy + opencv), never inside Blender: the bundled
interpreter is not to be pip-polluted, and scoring has to work in CI without
Blender installed.
"""

__all__ = ["compare", "edges", "score"]
