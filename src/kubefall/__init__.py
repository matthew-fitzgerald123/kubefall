"""kubefall: a roguelike for drilling kubectl, built on the rootfall engine.

The descent is a Kubernetes cluster, top to bottom: pods, deployments, services,
config, debugging, and a final triage gauntlet. The player descends through
themed zones, dies back to the top, and keeps only a spaced-repetition memory of
which commands still need work.

This is a content pack plus two targeted additions over the rootfall engine:
dry-run-verified solve battles and a kubectl-aware answer matcher. The SM-2
scheduler, the two-layer save model, and the recall/villager/solve loop are
reused unchanged.
"""

__version__ = "0.1.0"
