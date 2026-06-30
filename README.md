# kubefall

A kubectl-mastery roguelike for SRE and platform-engineering interview prep. You
descend through a Kubernetes cluster, top to bottom, drilling the commands and
flags that come up in real on-call work and real interviews. Death wipes your
run but never your memory: a spaced-repetition scheduler tracks exactly which
commands you are still slow on and resurfaces them on later descents.

kubefall is a content pack built on the rootfall engine. The SM-2 scheduler, the
two-layer save model, and the recall/villager/solve battle loop are reused
unchanged. kubefall adds three things on top: dry-run-verified solve battles, a
sequence solve mode for investigation chains, and a kubectl-aware answer matcher.

## Requirements

- Python 3.9 or newer
- PyYAML (the only third-party dependency)
- kubectl, for dry-run-verified solve battles: `brew install kubernetes-cli`

No cluster is needed. Creation-zone bosses validate your command with
`kubectl --dry-run=client`, which runs against the kubectl binary alone. If
kubectl is not installed those battles fall back to honor-system self-report.
Investigation-chain bosses (zones 5 and 6) use string matching with no kubectl
or cluster required.

## Running it

```
python kubefall.py
```

That runs straight from a checkout. Alternatively, `pip install -e .` exposes a
`kubefall` console command.

## How it plays

Each zone has three kinds of battle:

- **RECALL**: a timed retrieval drill. A prompt appears with a countdown and you
  type the command. The timer is the grader, and items come from the
  spaced-repetition queue, not in zone order. The matcher is kubectl-aware: for a
  `kubectl ...` answer it treats resource short-names and singular/plural as
  equivalent (`po` == `pods` == `pod`) and treats `-n` and `--namespace` as the
  same flag, while still keeping distinct resources distinct (`pods` never grades
  as `deployments`).
- **VILLAGER**: a teaching encounter. An NPC explains the concept and the
  commands, then quiz-gates you before letting you pass, so recognition cannot
  stand in for recall. A passed quiz seeds those commands into your queue.
- **SOLVE**: a boss. There are three flavors:
  - *Dry-run*: creation-zone bosses (pods, deployments, services, config,
    namespaces, RBAC). You type a real kubectl create-style command, kubefall
    appends `--dry-run=client -o yaml` and runs it, and on success you see the
    generated manifest as feedback. A kubectl error is surfaced and fed to the
    scheduler as a miss. If kubectl cannot reach a cluster the battle falls back
    to string matching against a list of accepted answers so you are never stuck.
  - *Sequence*: investigation-chain bosses (debugging, cluster triage). You type
    each diagnostic command in turn and the game checks it with the same
    kubectl-aware string matcher used in recall battles. No cluster needed.
  - *Honor*: reserved for commands that cannot be checked offline or by string
    match. You run the command yourself and self-report the result.

A single HP bar spans the whole descent. Misses chip it; zero HP ends the run and
sends you back to the top with your spaced-repetition memory intact. Cleared
zones replay in compressed mode, so mastered commands with stretched intervals
stay buried and only what you are still slow on rises to meet you.

## The eight zones, in descent order

1. **Pods**: the smallest deployable unit. run, get, describe, delete, get pods
   -o wide, the -n namespace selector, the -l label selector.
2. **Deployments**: the controller chain, deployment over replicaset over pods.
   create deployment, scale, rollout status, rollout undo, get rs, set image,
   --replicas.
3. **Services**: stable networking for ephemeral pods. expose, get svc, the
   ClusterIP, NodePort, and LoadBalancer types, --port, --target-port, --type,
   port-forward.
4. **Config**: configuration outside the image. create configmap, create secret,
   --from-literal, --from-file, env injection, get cm, get secret.
5. **Debugging**: the read-verb toolkit. logs, logs -f, logs --previous, exec -it,
   describe pod, get events, top pod. Includes output-reading recalls off a
   CrashLoopBackOff capture. The boss is a four-step sequence solve: get pods,
   describe pod, logs, logs --previous.
6. **Cluster Triage**: the boss zone. The full diagnostic chain combining zones 1
   through 5. The boss is a six-step sequence solve: get pods, describe pod, logs,
   logs --previous, get configmap, describe deployment.
7. **Namespaces and Contexts**: isolation and navigation. get namespaces, create
   namespace, config get-contexts, config current-context, config use-context,
   config view, config set-context --current --namespace.
8. **Apply and RBAC**: declarative workflows and access control. apply -f, delete
   -f, patch, label, create serviceaccount, create role, create rolebinding,
   auth can-i.

## Architecture

kubefall reuses the rootfall engine:

- The SM-2 spaced-repetition scheduler. The recall timer is the grader: fast and
  correct stretches an item's interval, slow but correct holds it, wrong or timed
  out pulls it back to the front of the queue.
- The two-layer save model. Run state (HP, position) is wiped on death. Meta
  state (the scheduling queue and the set of cleared zones) survives every death,
  which is the entire point.

On top of that, kubefall adds:

- **Dry-run verification** for creation-zone solves. The submitted command is run
  through `kubectl --dry-run=client` with no cluster, and the generated manifest
  is shown as feedback. If kubectl cannot reach the API server (e.g. for
  `kubectl expose`, which needs the live resource to derive a label selector) and
  the encounter yaml includes an `answers` list, the battle falls back to string
  matching rather than blocking or degrading to honor-system. Read verbs are
  rejected immediately without calling kubectl.
- **Sequence solve mode** for investigation chains. The battle walks through a
  list of steps defined in the encounter yaml; each step shows a prompt and checks
  the typed command with `matches()`. Wrong answers show the correct command and
  loop. No cluster required.
- **A kubectl-aware matcher**. Resource short-name and singular/plural equivalence
  and -n/--namespace flag equivalence are added for `kubectl` answers only, so
  none of rootfall's original Linux-command matching behavior changes.

The campaign is data-driven YAML. Solve encounters support a `verify` key with
three values: `dry-run`, `sequence`, and `honor` (the default). Sequence solves
also carry a `steps` list, each with `prompt` and `answers` fields.
