# Deploying GridShield

Live demo: <https://gridshieldd.streamlit.app/>

GitHub stores the source. It does **not** run Streamlit: GitHub Pages serves
static files only, so the SCADA dashboard needs a Python host.

There are two supported paths:

| Path | Use it for | Data |
|---|---|---|
| Streamlit Community Cloud + `dashboard/demo_app.py` | public UI demo, no hardware | synthetic, regenerated on restart |
| Docker + Render / Railway / Fly.io | live MQTT telemetry from a real node | SQLite on a persistent volume |

## 1. Push the repository

From the project root:

```powershell
git init
git add .
git commit -m "GridShield SCADA"
git branch -M main
git remote add origin https://github.com/<user>/gridshield.git
git push -u origin main
```

`.gitignore` excludes `.env`, `firmware/.../secrets.h`, `build/` and all
SQLite databases. Do not force-add those files.

## 2. Streamlit Community Cloud (demo)

1. Open <https://share.streamlit.io> and sign in with GitHub.
2. Create an app from the `gridshield` repository and `main` branch.
3. Set **Main file path** to `dashboard/demo_app.py`.
4. Deploy.

`dashboard/demo_app.py` enables a self-contained synthetic feed:

- four virtual nodes from `config/nodes.json`
- 5 minutes of history on first render
- one new sample every dashboard refresh
- sag, harmonic, overload and swell events every 100 s
- operator buttons act on the in-process simulator
- data is written to `data/demo.db`

Community Cloud's filesystem is ephemeral, so the demo database is recreated
after a restart. That is expected. This path cannot run `cloud.ingest` as a
separate worker, so it is not suitable for a real ESP32 deployment.

## 3. Docker (live)

The included `Dockerfile` starts either the simulator or the MQTT ingestor and
then serves the dashboard.

```text
GRIDSHIELD_MODE=demo   # sim.run --mode local
GRIDSHIELD_MODE=live   # cloud.ingest, requires MQTT_* variables
```

Build and run locally:

```powershell
docker build -t gridshield .
docker run --rm -p 8501:8501 -v gridshield-data:/data gridshield
```

Open <http://localhost:8501>.

For a real installation:

```text
GRIDSHIELD_MODE=live
GRIDSHIELD_DB=/data/gridshield.db
MQTT_HOST=your-broker.example.com
MQTT_PORT=8883
MQTT_TLS=true
MQTT_USERNAME=...
MQTT_PASSWORD=...
MQTT_TOPIC_PREFIX=smart_grid
```

Mount a persistent volume at `/data`. Keep exactly one container replica:
SQLite with WAL supports one writer and many readers, not multiple network
writers.

### Render

`render.yaml` describes a Docker web service with a 1 GB disk at `/data` and
`GRIDSHIELD_MODE=demo`. Create a Blueprint from the repository, or create the
service manually and add the same environment variables and disk.

### Railway / Fly.io

Create a service from the GitHub repository, select the Dockerfile, add a
volume mounted at `/data`, and set the environment variables above. Fly.io
example:

```powershell
fly launch
fly volumes create gridshield_data --size 1
fly secrets set MQTT_HOST=... MQTT_PORT=8883 MQTT_TLS=true MQTT_USERNAME=... MQTT_PASSWORD=...
fly deploy
```

Render and Railway redeploy on every push to `main`. For Fly.io, add a GitHub
Actions workflow that runs `flyctl deploy` with a `FLY_API_TOKEN` repository
secret.

## 4. Before exposing the dashboard

The Flask/Streamlit app has no built-in login. The operator buttons can trip a
real relay if the ingestor is connected. For anything beyond a synthetic demo:

- make the app private, or add OIDC/`st.login` and an allow-list;
- put it behind Cloudflare Access or a VPN;
- use MQTT credentials with per-topic ACLs and TLS;
- keep the safety interlock authoritative on the ESP32.

This is a research prototype, not a certified protection device.
