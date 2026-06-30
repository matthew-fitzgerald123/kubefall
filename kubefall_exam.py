#!/usr/bin/env python3
"""
kubefall_exam.py  --  pure command-matching drill for the 8-zone kubectl list.

Each question describes what a command does. You type the command. It is
auto-graded. No essays, no self-grading.

Run:  python3 kubefall_exam.py            # menu: full drill or review missed
      python3 kubefall_exam.py --review   # jump straight to last run's misses
      python3 kubefall_exam.py --full     # skip the menu, full drill
      python3 kubefall_exam.py --reset    # clear the saved missed list

The grader understands kubectl conventions:
  - Resource aliases: po/pod/pods all match; svc/service; cm/configmap; ns/namespace; sa/serviceaccount; rs/replicaset.
  - Namespace flag: -n staging and --namespace staging and --namespace=staging all grade identically.
  - Flag reordering: short combined flags are sorted (-it == -ti).
  - Argument wildcards: <name>, <image>, <n> in templates match any single token.

Missed commands are saved to ~/.kubefall/missed.json. Getting one right in any
run removes it from the box; missing it adds it. At the end of a run you can
immediately retry the ones you just missed.

At the answer prompt, type the command or a colon-command:
  :n  next      :p  prev      :g N  jump to N      :l  overview
  :s  score     :r  next wrong/blank    :reveal  show answer (marks wrong)
  :h  help      :q  quit + report
"""

import json
import os
import re
import sys

# --------------------------------------------------------------------- color
NO_COLOR = bool(os.environ.get("NO_COLOR"))
def _c(code, s): return s if NO_COLOR else "\033[{}m{}\033[0m".format(code, s)
def bold(s):   return _c("1", s)
def dim(s):    return _c("2", s)
def green(s):  return _c("32", s)
def red(s):    return _c("31", s)
def yellow(s): return _c("33", s)
def cyan(s):   return _c("36", s)
def mag(s):    return _c("35", s)
def clear():   os.system("cls" if os.name == "nt" else "clear")

# --------------------------------------------------------------------- kubectl matcher

_RESOURCE_ALIASES = {
    "po": "pod", "pod": "pod", "pods": "pod",
    "deploy": "deployment", "deployment": "deployment", "deployments": "deployment",
    "svc": "service", "service": "service", "services": "service",
    "cm": "configmap", "configmap": "configmap", "configmaps": "configmap",
    "ns": "namespace", "namespace": "namespace", "namespaces": "namespace",
    "rs": "replicaset", "replicaset": "replicaset", "replicasets": "replicaset",
    "no": "node", "node": "node", "nodes": "node",
    "sa": "serviceaccount", "serviceaccount": "serviceaccount", "serviceaccounts": "serviceaccount",
    "secret": "secret", "secrets": "secret",
}


def _preprocess(s):
    """Expand -n <val> and --namespace=<val> to --namespace <val>."""
    tokens = re.sub(r"\s+", " ", s.strip()).split(" ")
    out = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "-n" and i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
            out.extend(["--namespace", tokens[i + 1]])
            i += 2
        elif tok.startswith("--namespace="):
            out.extend(["--namespace", tok.split("=", 1)[1]])
            i += 1
        else:
            out.append(tok)
            i += 1
    return " ".join(out)


def _norm_tok(tok):
    """Normalize one token: resource aliases and short-flag letter sorting."""
    lower = tok.lower()
    # Resource alias: bare words only (not flags, not paths, not key=val)
    if not tok.startswith("-") and "/" not in tok and "=" not in tok and lower in _RESOURCE_ALIASES:
        return _RESOURCE_ALIASES[lower]
    # Sort combined short flags: -it -> -it (already sorted i < t), -tl -> -lt
    if re.fullmatch(r"-[A-Za-z]{2,}", tok):
        return "-" + "".join(sorted(tok[1:]))
    # Strip leading ./ from paths
    if tok.startswith("./") and len(tok) > 2:
        tok = tok[2:]
    return tok


def normalize(s):
    s = _preprocess(s)
    s = re.sub(r"\s+", " ", s.strip())
    if not s:
        return ""
    return " ".join(_norm_tok(t) for t in s.split(" "))


def _match_template(ans_tokens, spec_str):
    """Match answer tokens against a template string.

    Template tokens:
      literal   must equal the normalized answer token
      <x>       required wildcard - matches any one token
      <x?>      optional wildcard - matches zero or one token
    """
    spec = spec_str.split(" ")
    i, n = 0, len(ans_tokens)
    for tok in spec:
        if tok.startswith("<") and tok.endswith(">"):
            optional = tok[1:-1].endswith("?")
            if i < n:
                i += 1
            elif not optional:
                return False
        else:
            if i < n and ans_tokens[i] == _norm_tok(tok):
                i += 1
            else:
                return False
    return i == n


def matches(ans, q):
    toks = normalize(ans).split(" ") if ans.strip() else []
    for t in q.get("templates", []):
        if _match_template(toks, t):
            return True
    rf = q.get("regex_full")
    if rf and re.fullmatch(rf, normalize(ans)):
        return True
    return False


# --------------------------------------------------------------------- questions

Q = [
    # Zone 1 - Pods
    {"zone": "Zone 1 - Pods",
     "q": "Create and start a pod named web from the nginx image.",
     "templates": ["kubectl run web --image=nginx", "kubectl run web --image nginx"],
     "answer": "kubectl run web --image=nginx"},
    {"zone": "Zone 1 - Pods",
     "q": "List all pods in the current namespace.",
     "templates": ["kubectl get pod", "kubectl get pods", "kubectl get po"],
     "answer": "kubectl get pods"},
    {"zone": "Zone 1 - Pods",
     "q": "List all pods with the wider output that includes node and pod IP.",
     "templates": ["kubectl get pod -o wide", "kubectl get pods -o wide"],
     "answer": "kubectl get pods -o wide"},
    {"zone": "Zone 1 - Pods",
     "q": "Show the full detail and events for the pod named web.",
     "templates": ["kubectl describe pod web", "kubectl describe po web"],
     "answer": "kubectl describe pod web"},
    {"zone": "Zone 1 - Pods",
     "q": "Delete the pod named web.",
     "templates": ["kubectl delete pod web", "kubectl delete po web"],
     "answer": "kubectl delete pod web"},
    {"zone": "Zone 1 - Pods",
     "q": "List the pods in the kube-system namespace.",
     "templates": ["kubectl get pod --namespace kube-system",
                   "kubectl get pods --namespace kube-system"],
     "answer": "kubectl get pods -n kube-system"},
    {"zone": "Zone 1 - Pods",
     "q": "List only the pods carrying the label app=web.",
     "templates": ["kubectl get pod -l app=web", "kubectl get pods -l app=web",
                   "kubectl get pod --selector app=web", "kubectl get pods --selector app=web",
                   "kubectl get pod --selector=app=web", "kubectl get pods --selector=app=web"],
     "answer": "kubectl get pods -l app=web"},

    # Zone 2 - Deployments
    {"zone": "Zone 2 - Deployments",
     "q": "Create a deployment named web from the nginx image.",
     "templates": ["kubectl create deployment web --image=nginx",
                   "kubectl create deployment web --image nginx"],
     "answer": "kubectl create deployment web --image=nginx"},
    {"zone": "Zone 2 - Deployments",
     "q": "Scale the deployment named web to 3 replicas.",
     "templates": ["kubectl scale deployment web --replicas=3",
                   "kubectl scale deployment web --replicas 3",
                   "kubectl scale deploy web --replicas=3",
                   "kubectl scale deploy web --replicas 3"],
     "answer": "kubectl scale deployment web --replicas=3"},
    {"zone": "Zone 2 - Deployments",
     "q": "Watch the rolling update of deployment web until it lands.",
     "templates": ["kubectl rollout status deployment web",
                   "kubectl rollout status deployment/web",
                   "kubectl rollout status deploy web",
                   "kubectl rollout status deploy/web"],
     "answer": "kubectl rollout status deployment web"},
    {"zone": "Zone 2 - Deployments",
     "q": "Roll deployment web back to its previous revision.",
     "templates": ["kubectl rollout undo deployment web",
                   "kubectl rollout undo deployment/web",
                   "kubectl rollout undo deploy web"],
     "answer": "kubectl rollout undo deployment web"},
    {"zone": "Zone 2 - Deployments",
     "q": "List the replicasets in the current namespace.",
     "templates": ["kubectl get rs", "kubectl get replicaset", "kubectl get replicasets"],
     "answer": "kubectl get rs"},
    {"zone": "Zone 2 - Deployments",
     "q": "Update the container web in deployment web to image nginx:1.25.",
     "templates": ["kubectl set image deployment/web web=nginx:1.25",
                   "kubectl set image deployment web web=nginx:1.25"],
     "answer": "kubectl set image deployment/web web=nginx:1.25"},
    {"zone": "Zone 2 - Deployments",
     "q": "Create a deployment named web from nginx with 3 replicas, in one command.",
     "templates": ["kubectl create deployment web --image=nginx --replicas=3",
                   "kubectl create deployment web --image nginx --replicas 3",
                   "kubectl create deployment web --image=nginx --replicas 3",
                   "kubectl create deployment web --image nginx --replicas=3"],
     "answer": "kubectl create deployment web --image=nginx --replicas=3"},

    # Zone 3 - Services
    {"zone": "Zone 3 - Services",
     "q": "List all services in the current namespace.",
     "templates": ["kubectl get svc", "kubectl get service", "kubectl get services"],
     "answer": "kubectl get svc"},
    {"zone": "Zone 3 - Services",
     "q": "Expose deployment web on port 80, forwarding to pod port 8080.",
     "templates": ["kubectl expose deployment web --port=80 --target-port=8080",
                   "kubectl expose deployment web --port 80 --target-port 8080",
                   "kubectl expose deploy web --port=80 --target-port=8080"],
     "answer": "kubectl expose deployment web --port=80 --target-port=8080"},
    {"zone": "Zone 3 - Services",
     "q": "Expose deployment web on port 80 as a NodePort service.",
     "templates": ["kubectl expose deployment web --port=80 --type=NodePort",
                   "kubectl expose deployment web --port 80 --type NodePort",
                   "kubectl expose deploy web --port=80 --type=NodePort"],
     "answer": "kubectl expose deployment web --port=80 --type=NodePort"},
    {"zone": "Zone 3 - Services",
     "q": "Expose deployment web on port 80 as a LoadBalancer service.",
     "templates": ["kubectl expose deployment web --port=80 --type=LoadBalancer",
                   "kubectl expose deployment web --port 80 --type LoadBalancer"],
     "answer": "kubectl expose deployment web --port=80 --type=LoadBalancer"},
    {"zone": "Zone 3 - Services",
     "q": "Which service type is internal-only and is the default?",
     "templates": ["ClusterIP", "clusterip"],
     "answer": "ClusterIP"},
    {"zone": "Zone 3 - Services",
     "q": "Forward local port 8080 to port 80 of the service named web.",
     "templates": ["kubectl port-forward service/web 8080:80",
                   "kubectl port-forward svc/web 8080:80"],
     "answer": "kubectl port-forward service/web 8080:80"},
    {"zone": "Zone 3 - Services",
     "q": "Forward local port 8080 to port 80 of the pod named web.",
     "templates": ["kubectl port-forward pod/web 8080:80",
                   "kubectl port-forward web 8080:80"],
     "answer": "kubectl port-forward pod/web 8080:80"},

    # Zone 4 - Config
    {"zone": "Zone 4 - Config",
     "q": "Create a configmap named web-config with key COLOR set to blue, inline.",
     "templates": ["kubectl create configmap web-config --from-literal=COLOR=blue"],
     "answer": "kubectl create configmap web-config --from-literal=COLOR=blue"},
    {"zone": "Zone 4 - Config",
     "q": "Create a configmap named web-config from the file app.properties.",
     "templates": ["kubectl create configmap web-config --from-file=app.properties",
                   "kubectl create configmap web-config --from-file app.properties"],
     "answer": "kubectl create configmap web-config --from-file=app.properties"},
    {"zone": "Zone 4 - Config",
     "q": "Create a generic secret named web-secret with key TOKEN set to abc123, inline.",
     "templates": ["kubectl create secret generic web-secret --from-literal=TOKEN=abc123"],
     "answer": "kubectl create secret generic web-secret --from-literal=TOKEN=abc123"},
    {"zone": "Zone 4 - Config",
     "q": "List all configmaps in the current namespace.",
     "templates": ["kubectl get cm", "kubectl get configmap", "kubectl get configmaps"],
     "answer": "kubectl get cm"},
    {"zone": "Zone 4 - Config",
     "q": "List all secrets in the current namespace.",
     "templates": ["kubectl get secret", "kubectl get secrets"],
     "answer": "kubectl get secret"},
    {"zone": "Zone 4 - Config",
     "q": "Show the configmap web-config as YAML.",
     "templates": ["kubectl get configmap web-config -o yaml",
                   "kubectl get cm web-config -o yaml"],
     "answer": "kubectl get configmap web-config -o yaml"},
    {"zone": "Zone 4 - Config",
     "q": "Name the two ways config (configmap/secret) reaches a pod. Two words.",
     "templates": ["env volume", "volume env", "env vars", "env mount"],
     "regex_full": r"env.*vol|vol.*env|env.*(var|var|mount|inject)|inject.*env",
     "answer": "env vars / volume mount"},

    # Zone 5 - Debugging
    {"zone": "Zone 5 - Debugging",
     "q": "Print the logs of the pod named web.",
     "templates": ["kubectl logs web"],
     "answer": "kubectl logs web"},
    {"zone": "Zone 5 - Debugging",
     "q": "Follow the logs of the pod named web live.",
     "templates": ["kubectl logs -f web", "kubectl logs web -f"],
     "answer": "kubectl logs -f web"},
    {"zone": "Zone 5 - Debugging",
     "q": "Show the logs from the previous, crashed instance of the pod named web.",
     "templates": ["kubectl logs web --previous", "kubectl logs --previous web",
                   "kubectl logs -p web", "kubectl logs web -p"],
     "answer": "kubectl logs web --previous"},
    {"zone": "Zone 5 - Debugging",
     "q": "Open an interactive shell (/bin/sh) inside the pod named web.",
     "templates": ["kubectl exec -it web -- /bin/sh", "kubectl exec -it web -- sh"],
     "answer": "kubectl exec -it web -- /bin/sh"},
    {"zone": "Zone 5 - Debugging",
     "q": "Show the recent cluster events.",
     "templates": ["kubectl get events", "kubectl get event"],
     "answer": "kubectl get events"},
    {"zone": "Zone 5 - Debugging",
     "q": "Show live CPU and memory use for every pod.",
     "templates": ["kubectl top pod", "kubectl top pods"],
     "answer": "kubectl top pod"},
    {"zone": "Zone 5 - Debugging",
     "q": "Show the full detail and the event trail for the pod named web.",
     "templates": ["kubectl describe pod web", "kubectl describe po web"],
     "answer": "kubectl describe pod web"},

    # Zone 6 - Cluster Triage
    {"zone": "Zone 6 - Cluster Triage",
     "q": "Triage step 1: get pod state and restart count for all pods.",
     "templates": ["kubectl get pod", "kubectl get pods", "kubectl get po"],
     "answer": "kubectl get pods"},
    {"zone": "Zone 6 - Cluster Triage",
     "q": "Triage step 2: read the events of the crashing pod named web.",
     "templates": ["kubectl describe pod web", "kubectl describe po web"],
     "answer": "kubectl describe pod web"},
    {"zone": "Zone 6 - Cluster Triage",
     "q": "Triage step 3: read the application logs of the pod named web.",
     "templates": ["kubectl logs web"],
     "answer": "kubectl logs web"},
    {"zone": "Zone 6 - Cluster Triage",
     "q": "Triage step 4: the pod restarted - read the crashed instance's logs. Pod is web.",
     "templates": ["kubectl logs web --previous", "kubectl logs --previous web",
                   "kubectl logs -p web", "kubectl logs web -p"],
     "answer": "kubectl logs web --previous"},
    {"zone": "Zone 6 - Cluster Triage",
     "q": "Triage step 5: the logs blame missing config. List all configmaps.",
     "templates": ["kubectl get cm", "kubectl get configmap", "kubectl get configmaps"],
     "answer": "kubectl get cm"},
    {"zone": "Zone 6 - Cluster Triage",
     "q": "Check the image tag and rollout history of deployment web.",
     "templates": ["kubectl describe deployment web", "kubectl describe deploy web",
                   "kubectl describe deployment/web"],
     "answer": "kubectl describe deployment web"},
    {"zone": "Zone 6 - Cluster Triage",
     "q": "Name the four triage verbs in order. Space separated.",
     "templates": ["get describe logs logs"],
     "answer": "get describe logs logs"},

    # Zone 7 - Namespaces and Contexts
    {"zone": "Zone 7 - Namespaces and Contexts",
     "q": "List all namespaces in the cluster.",
     "templates": ["kubectl get namespace", "kubectl get namespaces", "kubectl get ns"],
     "answer": "kubectl get namespaces"},
    {"zone": "Zone 7 - Namespaces and Contexts",
     "q": "Create a namespace named staging.",
     "templates": ["kubectl create namespace staging", "kubectl create ns staging"],
     "answer": "kubectl create namespace staging"},
    {"zone": "Zone 7 - Namespaces and Contexts",
     "q": "List all contexts from your kubeconfig.",
     "templates": ["kubectl config get-contexts"],
     "answer": "kubectl config get-contexts"},
    {"zone": "Zone 7 - Namespaces and Contexts",
     "q": "Show which context is currently active.",
     "templates": ["kubectl config current-context"],
     "answer": "kubectl config current-context"},
    {"zone": "Zone 7 - Namespaces and Contexts",
     "q": "Switch to the context named prod.",
     "templates": ["kubectl config use-context prod"],
     "answer": "kubectl config use-context prod"},
    {"zone": "Zone 7 - Namespaces and Contexts",
     "q": "Print the full kubeconfig file.",
     "templates": ["kubectl config view"],
     "answer": "kubectl config view"},
    {"zone": "Zone 7 - Namespaces and Contexts",
     "q": "Set the default namespace for the current context to staging.",
     "templates": ["kubectl config set-context --current --namespace=staging",
                   "kubectl config set-context --current --namespace staging"],
     "answer": "kubectl config set-context --current --namespace=staging"},

    # Zone 8 - Apply, Patch, and RBAC
    {"zone": "Zone 8 - Apply, Patch, and RBAC",
     "q": "Apply the manifest at deploy.yaml to the cluster.",
     "templates": ["kubectl apply -f deploy.yaml"],
     "answer": "kubectl apply -f deploy.yaml"},
    {"zone": "Zone 8 - Apply, Patch, and RBAC",
     "q": "Delete all resources described in deploy.yaml.",
     "templates": ["kubectl delete -f deploy.yaml"],
     "answer": "kubectl delete -f deploy.yaml"},
    {"zone": "Zone 8 - Apply, Patch, and RBAC",
     "q": "Which verb surgically updates a field of a live resource without a full reapply?",
     "templates": ["kubectl patch", "patch"],
     "answer": "kubectl patch"},
    {"zone": "Zone 8 - Apply, Patch, and RBAC",
     "q": "Add the label env=prod to the pod named web.",
     "templates": ["kubectl label pod web env=prod", "kubectl label po web env=prod"],
     "answer": "kubectl label pod web env=prod"},
    {"zone": "Zone 8 - Apply, Patch, and RBAC",
     "q": "Create a service account named deployer.",
     "templates": ["kubectl create serviceaccount deployer",
                   "kubectl create sa deployer"],
     "answer": "kubectl create serviceaccount deployer"},
    {"zone": "Zone 8 - Apply, Patch, and RBAC",
     "q": "Which command creates a Role granting specific API permissions?",
     "templates": ["kubectl create role", "create role"],
     "answer": "kubectl create role"},
    {"zone": "Zone 8 - Apply, Patch, and RBAC",
     "q": "Which command binds a Role to a user or service account?",
     "templates": ["kubectl create rolebinding", "create rolebinding"],
     "answer": "kubectl create rolebinding"},
    {"zone": "Zone 8 - Apply, Patch, and RBAC",
     "q": "Check if the current user can list pods in the current namespace.",
     "templates": ["kubectl auth can-i list pods", "kubectl auth can-i list pod"],
     "answer": "kubectl auth can-i list pods"},
]

# --------------------------------------------------------------------- persistence
MISS_FILE = os.path.expanduser("~/.kubefall/missed.json")


def load_missed():
    try:
        with open(MISS_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_missed(missed):
    try:
        os.makedirs(os.path.dirname(MISS_FILE), exist_ok=True)
        with open(MISS_FILE, "w") as f:
            json.dump(sorted(missed), f, indent=0)
    except Exception:
        pass


# --------------------------------------------------------------------- state
state = {}     # q-index -> {"response": str, "correct": bool, "done": bool}
ACTIVE = []    # the q-indices in play this session


def score_now():
    done = [i for i in ACTIVE if state.get(i, {}).get("done")]
    correct = sum(1 for i in done if state[i]["correct"])
    return correct, len(done), len(ACTIVE)


def status_tag(i):
    st = state.get(i)
    if not st or not st.get("done"):
        return dim("- blank")
    return green("v") if st["correct"] else red("x")


def all_done():
    return all(state.get(i, {}).get("done") for i in ACTIVE)


# --------------------------------------------------------------------- screens
def header(pos, mode):
    cor, ans, tot = score_now()
    idx = ACTIVE[pos]
    tag = "review" if mode == "review" else "drill"
    title = " kubefall - kubectl {} Q {}/{}  {}".format(tag, pos + 1, tot, Q[idx]["zone"])
    w = max(len(title) + 2, 60)
    print(mag("=" * w))
    print(bold(title))
    print(mag("=" * w))
    print(" score: {}/{} answered  {}  {} blank".format(
        green(str(cor)), ans, " " * 4, tot - ans))
    print()


def render(pos, mode):
    clear()
    header(pos, mode)
    q = Q[ACTIVE[pos]]
    print(bold("Does: ") + q["q"])
    print()
    st = state.get(ACTIVE[pos])
    if st and st.get("done"):
        print(dim("  you typed:  ") + (st["response"] or dim("(revealed)")))
        verdict = green("CORRECT") if st["correct"] else red("WRONG")
        print(dim("  verdict:    ") + verdict)
        print(dim("  command:    ") + cyan(q["answer"]))
        print()
    print(dim("  type the command, or :h for navigation"))
    print()


def overview(mode):
    clear()
    print(bold(" Overview"))
    print(mag("-" * 62))
    last = None
    for pos, idx in enumerate(ACTIVE):
        if Q[idx]["zone"] != last:
            print()
            print(cyan(Q[idx]["zone"]))
            last = Q[idx]["zone"]
        print("  {:>2}. {}  {}".format(pos + 1, status_tag(idx), Q[idx]["q"][:52]))
    cor, ans, tot = score_now()
    print()
    print(mag("-" * 62))
    print(" {} correct / {} answered / {} total".format(green(str(cor)), ans, tot))
    input(dim("\n  Enter to return..."))


def grade(idx, raw):
    q = Q[idx]
    ok = matches(raw, q)
    print(green("\n  CORRECT") if ok else red("\n  WRONG"))
    print(dim("  command:  ") + cyan(q["answer"]))
    if not ok:
        ov = input(yellow("\n  Override to correct? [y/N]: ")).strip().lower()
        ok = ov == "y"
    state[idx] = {"response": raw, "correct": ok, "done": True}
    input(dim("\n  Enter to continue..."))


def reveal(idx):
    q = Q[idx]
    print(dim("\n  command: ") + cyan(q["answer"]))
    print(red("  marked wrong (revealed)"))
    state[idx] = {"response": "", "correct": False, "done": True}
    input(dim("\n  Enter to continue..."))


def help_screen():
    clear()
    print(bold(" Navigation"))
    print(mag("-" * 42))
    for k, v in [
        ("<command>", "submit an answer"),
        (":n", "next"),
        (":p", "previous"),
        (":g N", "go to question N"),
        (":l", "overview grid"),
        (":s", "score"),
        (":r", "jump to next blank/wrong"),
        (":reveal", "show the answer (marks wrong)"),
        (":q", "quit + report"),
        (":h", "this help"),
    ]:
        print("  {:<22} {}".format(cyan(k), v))
    input(dim("\n  Enter to return..."))


def report(mode):
    clear()
    cor, ans, tot = score_now()
    pct = cor / tot * 100 if tot else 0
    label = "REVIEW REPORT" if mode == "review" else "REPORT"
    print(mag("=" * 62))
    print(bold(" {}   {}/{}   ({:.0f}%)".format(label, cor, tot, pct)))
    print(mag("=" * 62))
    zones = {}
    for idx in ACTIVE:
        z = Q[idx]["zone"]
        zones.setdefault(z, [0, 0])
        zones[z][1] += 1
        if state.get(idx, {}).get("correct"):
            zones[z][0] += 1
    print()
    for z, (gc, gt) in zones.items():
        bar = green("#" * gc) + dim("." * (gt - gc))
        print("  {:<30} {}  {}/{}".format(z, bar, gc, gt))
    missed = [Q[idx] for idx in ACTIVE
              if state.get(idx, {}).get("done") and not state[idx]["correct"]]
    blanks = [pos + 1 for pos, idx in enumerate(ACTIVE)
              if not state.get(idx, {}).get("done")]
    if missed:
        print()
        print(yellow(" Missed this run:"))
        for q in missed:
            print("   " + red("* ") + cyan(q["answer"]) + dim("   -- " + q["q"]))
    if blanks:
        print()
        print(dim(" Left blank: " + ", ".join(map(str, blanks))))
    if not missed and not blanks:
        print()
        print(green(" Clean sweep."))
    print()


# --------------------------------------------------------------------- session loop
def run_session(mode):
    pos, n = 0, len(ACTIVE)
    while True:
        render(pos, mode)
        try:
            raw = input(bold("cmd> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not raw:
            continue
        if raw.startswith(":"):
            c = raw[1:].strip()
            if c in ("q", "quit"):
                return
            elif c in ("n", "next", ""):
                pos = (pos + 1) % n
            elif c in ("p", "prev", "previous"):
                pos = (pos - 1) % n
            elif c in ("h", "help", "?"):
                help_screen()
            elif c in ("l", "list", "overview", "s", "score"):
                overview(mode)
            elif c in ("reveal", "a"):
                reveal(ACTIVE[pos])
                if all_done():
                    return
                pos = (pos + 1) % n
            elif c in ("r", "review"):
                nxt = next(
                    (k for k in range(n)
                     if not state.get(ACTIVE[k], {}).get("done")
                     or not state[ACTIVE[k]]["correct"]),
                    None,
                )
                if nxt is None:
                    input(dim("  nothing blank/wrong. Enter..."))
                else:
                    pos = nxt
            elif c.startswith("g"):
                mm = re.search(r"\d+", c)
                if mm and 0 <= int(mm.group()) - 1 < n:
                    pos = int(mm.group()) - 1
                else:
                    input(red("  usage: :g 12. Enter..."))
            else:
                input(red("  unknown ':{}'  (:h for help). Enter...".format(c)))
            continue
        grade(ACTIVE[pos], raw)
        if all_done():
            return
        pos = (pos + 1) % n


# --------------------------------------------------------------------- menu / main
def choose_order(full, review):
    while True:
        clear()
        print(bold("\n  kubefall -- kubectl command drill\n"))
        print("  [1] Full drill -- {} commands".format(len(full)))
        if review:
            print("  [2] Review missed -- {} from last run".format(len(review)))
        else:
            print(dim("  [2] Review missed -- (none saved yet)"))
        print("  [q] quit\n")
        c = input(bold("  > ")).strip().lower()
        if c in ("1", "full", ""):
            return list(full), "full"
        if c in ("2", "review") and review:
            return list(review), "review"
        if c in ("q", "quit"):
            return None, None


def update_box(missed_box):
    for idx in ACTIVE:
        st = state.get(idx)
        if st and st.get("done"):
            if st["correct"]:
                missed_box.discard(Q[idx]["q"])
            else:
                missed_box.add(Q[idx]["q"])
    save_missed(missed_box)


def main():
    args = set(sys.argv[1:])
    missed_box = load_missed()

    if "--reset" in args:
        save_missed(set())
        print("Cleared the saved missed list (~/.kubefall/missed.json).")
        return

    full = list(range(len(Q)))
    prompt_to_idx = {q["q"]: i for i, q in enumerate(Q)}
    review = sorted(prompt_to_idx[p] for p in missed_box if p in prompt_to_idx)

    if "--full" in args:
        order, mode = list(full), "full"
    elif "--review" in args:
        if not review:
            print("No missed commands saved yet -- run a full drill first.")
            return
        order, mode = list(review), "review"
    else:
        order, mode = choose_order(full, review)
        if order is None:
            print("Later.")
            return

    global ACTIVE
    ACTIVE = order

    while True:
        if mode != "retry":
            clear()
            tag = "Review of last run's misses" if mode == "review" else "Full drill"
            print(bold("\n  {} -- {} commands".format(tag, len(ACTIVE))))
            print(dim("  what it does -> you type it  auto-graded  :h for nav\n"))
            input(dim("  Enter to begin..."))
        run_session(mode)
        report(mode)
        update_box(missed_box)

        just_missed = [i for i in ACTIVE
                       if state.get(i, {}).get("done") and not state[i]["correct"]]
        if not just_missed:
            print(green("  Nothing left in the box from this run.\n"))
            break
        a = input(yellow("  Retry the {} you just missed now? [y/N]: ".format(
            len(just_missed)))).strip().lower()
        if a != "y":
            print(dim("\n  {} command(s) saved for next time. Run --review to drill them.\n".format(
                len(missed_box))))
            break
        for i in just_missed:
            state.pop(i, None)
        ACTIVE = just_missed
        mode = "retry"


if __name__ == "__main__":
    main()
