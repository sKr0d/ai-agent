# Hello-World on Kubernetes — project overview

A trial of the multi-agent coding environment: build the simplest possible
**Hello World** website and **deploy it to Kubernetes** in an **nginx** container.

## What was built

- **Artifacts:** `trial/helloworld/index.html`, `Dockerfile`, `k8s.yaml`
  - `index.html` — a minimal page showing "Hello World"
  - `Dockerfile` — an nginx image that serves `index.html`
  - `k8s.yaml` — a `Deployment` + `Service`
- **Image:** `helloworld-nginx` (served by `nginx:latest`)
- **Kubernetes:** `Deployment` + `Service` named **helloworld** in namespace **helloworld**
- **Browse:** `kubectl -n helloworld port-forward svc/helloworld 8081:80`,
  then open http://127.0.0.1:8081/

## The team (each reported back to the coordinator)

| Agent        | Job                                            | Outcome (one line)                       |
|--------------|------------------------------------------------|------------------------------------------|
| Coding       | write `index.html` + `Dockerfile`              | Both files have been written successfully. Here is the report:    |
| CI/CD        | build image + deploy to Kubernetes             | ✅ Deployment successful — the rollout reached Ready.      |
| Monitoring   | check the in-cluster Service via port-forward  | Verdict: PASS            |
| Improvement  | propose k8s fixes from the monitoring verdict  | Add liveness/readiness probes + CPU/memory limits to the Deployment (e.g. `livenessProbe: httpGet /:…   |

## Artifacts on disk

### index.html
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Hello World</title>
</head>
<body>
  <h1>Hello World</h1>
</body>
</html>

```

### Dockerfile
```dockerfile
FROM nginx:latest
COPY index.html /usr/share/nginx/html/index.html

```

### k8s.yaml
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: helloworld
  namespace: helloworld
  labels:
    app: helloworld
spec:
  replicas: 1
  selector:
    matchLabels:
      app: helloworld
  template:
    metadata:
      labels:
        app: helloworld
    spec:
      containers:
      - name: web
        image: helloworld-nginx
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: helloworld
  namespace: helloworld
  labels:
    app: helloworld
spec:
  selector:
    app: helloworld
  ports:
  - port: 80
    targetPort: 80

```

## How to reproduce

```bash
# run the whole trial again (all four agents, deploys to the cluster)
python -m trial.coordinator

# or deploy by hand:
kubectl apply -f trial/helloworld/k8s.yaml
kubectl -n helloworld rollout status deployment/helloworld
kubectl -n helloworld port-forward svc/helloworld 8081:80
curl -s http://127.0.0.1:8081/
```

## Currently running?

The CI/CD agent left a **Kubernetes Deployment** in namespace **`helloworld`**
(inspect with `kubectl -n helloworld get all`).
Tear it down with `kubectl delete namespace helloworld`.
The full agent conversation is in `Hello-World-out.md`.
