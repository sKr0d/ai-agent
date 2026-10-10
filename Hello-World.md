# Hello-World — project overview

A trial run of the multi-agent coding environment, building the simplest
possible **Hello World** website on an **nginx** container.

## What was built

- **File(s):** Dockerfile, index.html
  - `index.html` — a minimal page showing "Hello World"
  - `Dockerfile` — an nginx image that serves `index.html`
- **Image:** `helloworld-nginx` (served by `nginx:latest`)
- **Container:** `helloworld-web` — running on host port **8081**
- **Live URL:** http://127.0.0.1:8081/

## The team (each reported back to the coordinator)

| Agent        | Job                                        | Outcome (one line)                       |
|--------------|--------------------------------------------|------------------------------------------|
| Coding       | write `index.html` + `Dockerfile`          | Both files have been written successfully. Here is the report:    |
| CI/CD        | `docker build` + `docker run` the image    | ✅ CI/CD task complete.      |
| Monitoring   | check the live site for "Hello World"      | Health verdict: PASS            |
| Improvement  | propose fixes from the monitoring verdict  | Add a `HEALTHCHECK` instruction to the Dockerfile and run the container with `--restart=unless-stopp…            |

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

## How to reproduce

```bash
# 4a. build and run the container yourself
docker build -t helloworld-nginx ./trial/helloworld
docker run -d --name helloworld-web -p 8081:80 helloworld-nginx

# 4b. browse it
open http://127.0.0.1:8081/
curl -s http://127.0.0.1:8081/

# 4c. run the whole trial again (all four agents)
python -m trial.coordinator
```

## Currently running?

The CI/CD agent left a running container named **`helloworld-web`**.
Stop it with: `docker stop helloworld-web` (image can be removed with
`docker rmi helloworld-nginx`). The full agent conversation is in
`Hello-World-out.md`.
