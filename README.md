# kubefall

A kubectl-mastery roguelike for SRE and platform-engineering interview prep. You
descend through a Kubernetes cluster, top to bottom, drilling the commands and
flags that come up in real on-call work and real interviews. Death wipes your
run but never your memory: a spaced-repetition scheduler tracks exactly which
commands you are still slow on and resurfaces them on later descents.

kubefall is a content pack built on the rootfall engine. The SM-2 scheduler, the
two-layer save model, and the recall/villager/solve battle loop are reused
unchanged. kubefall adds two things on top: dry-run-verified solve battles and a
kubectl-aware answer matcher.

## Requirements

- Python 3.9 or newer
- PyYAML (the only third-party dependency)
- kubectl, for dry-run-verified solve battles: `brew install kubernetes-cli`

No cluster and no Docker are needed. The creation-zone bosses validate your
command with `kubectl --dry-run=client`, which runs against the kubectl binary
alone. If kubectl is not installed, those battles fall back to honor-system
self-report, so the game still runs end to end.

## Running it

```
python kubefall.py
```

That runs straight from a checkout. Alternatively, `pip install -e .` exposes a
`kubefall` console command.

## How it plays

Each zone has three kinds of battle:

- RECALL: a timed retrieval drill. A prompt appears with a countdown and you type
  the command. The timer is the grader, and the items come from the
  spaced-repetition queue, not in zone order. The matcher is kubectl-aware: for a
  `kubectl ...` answer it treats resource short-names and singular/plural as
  equivalent (`po` == `pods` == `pod`) and treats `-n` and `--namespace` as the
  same flag, while still keeping distinct resources distinct (`pods` never grades
  as `deployments`).
- VILLAGER: a teaching encounter. An NPC explains the concept and the commands,
  then quiz-gates you before letting you pass, so recognition cannot stand in for
  recall. A passed quiz seeds those commands into your queue.
- SOLVE: a boss. There are two flavors:
  - Creation zones (pods, deployments, services, config) are dry-run verified.
    You type a real kubectl create-style command, kubefall appends
    `--dry-run=client -o yaml` and runs it, and on success you see the generated
    manifest as feedback. A kubectl error is surfaced and fed to the scheduler as
    a miss.
  - Debugging and triage zones are honor-system reasoning chains. These are read
    verbs (get, describe, logs, exec) and a `kubectl get` must never be dry-run
    validated, so you state or run the investigation and self-report. The triage
    boss is the real interview question: a pod is CrashLoopBackOff, walk me
    through it, in order.

A single HP bar spans the whole descent. Misses chip it; zero HP ends the run and
sends you back to the top with your spaced-repetition memory intact. Cleared
zones replay in compressed mode, so mastered commands with stretched intervals
stay buried and only what you are still slow on rises to meet you.

## The six zones, in descent order

1. Pods: the smallest deployable unit. run, get, describe, delete, get pods -o
   wide, the -n namespace selector, the -l label selector.
2. Deployments: the controller chain, deployment over replicaset over pods.
   create deployment, scale, rollout status, rollout undo, get rs, set image,
   --replicas.
3. Services: stable networking for ephemeral pods. expose, get svc, the
   ClusterIP, NodePort, and LoadBalancer types, --port, --target-port, --type,
   port-forward.
4. Config: configuration outside the image. create configmap, create secret,
   --from-literal, --from-file, env injection, get cm, get secret.
5. Debugging: the read-verb toolkit. logs, logs -f, logs --previous, exec -it,
   describe events, get events, top pod. Includes output-reading drills off a
   CrashLoopBackOff capture.
6. Cluster Triage: the boss zone. The full diagnostic chain combining zones 1
   through 5, with the tightest timers in the game. The boss accepts the correct
   ordered triage sequence: get pods, then describe pod, then logs and
   logs --previous, then check the configmap and the image.

## Architecture

kubefall reuses the rootfall engine:

- The SM-2 spaced-repetition scheduler. The recall timer is the grader: fast and
  correct stretches an item's interval, slow but correct holds it, wrong or timed
  out pulls it back to the front of the queue.
- The two-layer save model. Run state (HP, position) is wiped on death. Meta
  state (the scheduling queue and the set of cleared zones) survives every death,
  which is the entire point.

On top of that, kubefall adds two targeted changes:

- Dry-run verification for creation-zone solves. The submitted command is run
  through `kubectl --dry-run=client` with no cluster, and the generated manifest
  is shown as feedback. Read verbs are never dry-run validated, and a missing or
  unreachable kubectl degrades gracefully to honor-system rather than crashing or
  failing a correct answer.
- A kubectl-aware matcher. Resource short-name and singular/plural equivalence
  and -n/--namespace flag equivalence are added for `kubectl` answers only, so
  none of rootfall's original Linux-command matching behavior changes.

The campaign is data-driven YAML. The schema is rootfall's, with one
backward-compatible addition: a solve encounter may carry an optional `verify`
key set to `dry-run` or `honor` (the default). A solve without it behaves exactly
as it did in rootfall.

## Roadmap

- More zones: RBAC, jobs and cronjobs, ingress, persistent volumes, namespaces
  and quotas.
- A kustomize and `apply -f` track for declarative workflows.
- Server-side dry-run as an optional mode when a real cluster is configured, so
  the run and expose bosses verify fully instead of degrading.
- Per-resource stat tracking so the end-of-run summary shows your weakest verbs.
