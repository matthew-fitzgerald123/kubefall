# Implementation notes

## kubectl dry-run offline behavior

Engine change 1 verifies creation-zone solves with `kubectl --dry-run=client`,
which is meant to need only the kubectl binary and no cluster. That holds for
client-side generators but not for every create-style verb. Tested against
kubectl v1.32.2:

- `kubectl create deployment`, `kubectl create configmap`, `kubectl create
  secret`, and `kubectl create service` validate fully offline. Zones 2 and 4
  bosses are verified end to end with no cluster.
- `kubectl run` and `kubectl expose` perform API discovery even under
  `--dry-run=client` and fail with a connection error when no cluster is
  reachable. Zones 1 and 3 bosses use these verbs.

To keep this honest, `_run_dry_run` classifies a failure as one of pass, fail, or
unverifiable. A connectivity error (connection refused, server API group list,
dial tcp, and similar) is unverifiable, not a miss, so a possibly-correct answer
is never graded wrong. An unverifiable result degrades to honor-system
self-report, the same path used when kubectl is absent entirely. With a real
cluster configured, the run and expose bosses verify for real.

This is a kubectl-version behavior, not a schema limitation. The campaign schema
expressed everything the content needed.

## Schema extension

The only schema change over rootfall is one optional, backward-compatible key on
solve encounters: `verify`, set to `dry-run` or `honor` (the default when
absent). Solves without it behave exactly as rootfall's did. A solve may also
carry an optional `fixture` path naming a capture under world/ for the player to
read. Both are validated in campaign.py.
