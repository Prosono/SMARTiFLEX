"""Home Assistant App: outbound-only pilot, no physical actuation in v0.1."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit
from uuid import uuid4
import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("smartiflex.bridge")
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
STATE_PATH = DATA_DIR / "state.json"
CSRF = secrets.token_urlsafe(32)
runtime = {"connection": "UNKNOWN", "last_sync": None, "error": None}
state_lock = asyncio.Lock()


def utcnow():
    return datetime.now(timezone.utc)


def parse_time(value):
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("Timezone required")
    return t.astimezone(timezone.utc)


def load_state():
    if not STATE_PATH.exists():
        return {"bindings": [], "processed": {}}
    return json.loads(STATE_PATH.read_text())


def save_state(state):
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = STATE_PATH.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(state, output)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(STATE_PATH)


def cloud_url(value):
    value = value.strip()
    parsed = urlsplit(value)
    local_test = parsed.scheme == "http" and os.getenv("SMARTIFLEX_ALLOW_LOCAL_HTTP") == "1" and parsed.hostname in ("localhost", "127.0.0.1")
    if parsed.hostname in ("localhost", "127.0.0.1", "::1") and not local_test:
        raise ValueError("localhost peker på Home Assistant-appen selv. Bruk HTTPS-adressen til SMARTi-backenden på Macen eller serveren.")
    if parsed.hostname and parsed.hostname.endswith(".ui.nabu.casa"):
        raise ValueError("Dette er Home Assistants Nabu Casa-adresse. Bruk HTTPS-adressen til SMARTi Flex-backenden i stedet.")
    if (parsed.scheme != "https" and not local_test) or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("Bruk en HTTPS-adresse uten sti, brukernavn eller parametere")
    return value.rstrip("/")


def power_sample(entity, max_age=45):
    """Retain actual sensor observation time; never relabel stale values as current."""
    try:
        value = Decimal(entity["state"])
        unit = entity.get("attributes", {}).get("unit_of_measurement")
        if not value.is_finite() or unit not in ("W", "kW"):
            return None
        value *= 1000 if unit == "kW" else 1
        observed = parse_time(entity.get("last_reported") or entity["last_updated"])
        if not -10 <= (utcnow() - observed).total_seconds() <= max_age:
            return None
        watts = int(value.to_integral_value())
        if abs(watts) > 10_000_000:
            return None
        return {"power_w": watts, "observed_at": observed.isoformat()}
    except (KeyError, ValueError, InvalidOperation, TypeError, AttributeError):
        return None


def measurement_status(entity):
    if not entity:
        return "Fant ikke effektsensoren. Velg en ny under Rediger."
    if entity.get("state") in ("unknown", "unavailable", None):
        return "Effektsensoren er utilgjengelig i Home Assistant."
    if entity.get("attributes", {}).get("unit_of_measurement") not in ("W", "kW"):
        return "Sensoren må vise effekt i W eller kW."
    return "Ingen gyldig måling fra siste døgn. Kontroller verdien og oppdateringene i Home Assistant."


def evaluate_command(command, binding, consent):
    """Fail closed. The only enabled command is a non-actuating protocol test."""
    if not binding or not binding.get("local_enabled") or binding.get("needs_sync"):
        return {"status": "REJECTED", "error": "Local participation is disabled"}
    if not consent or not consent.get("enabled") or consent.get("consent_version") != command.get("consent_version"):
        return {"status": "REJECTED", "error": "Consent changed or is unavailable"}
    try:
        end, start = parse_time(command["expires_at"]), parse_time(command["period_from"])
        if end <= utcnow() or start > utcnow() or (end-start).total_seconds() > min(binding["max_duration_seconds"], consent["constraints"]["max_duration_seconds"]):
            return {"status": "REJECTED", "error": "Command timing exceeds local constraints"}
    except (KeyError, ValueError, TypeError):
        return {"status": "REJECTED", "error": "Invalid command timing"}
    if command.get("command") != "VERIFY_CONNECTION" or command.get("simulation") is not True:
        return {"status": "REJECTED", "error": "Physical control is not enabled in this release"}
    return {"status": "SIMULATED"}


async def ha_states():
    token = os.getenv("SUPERVISOR_TOKEN")
    if not token:
        raise ValueError("Supervisor access is not available")
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        response = await client.get("http://supervisor/core/api/states", headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        return response.json()


async def synchronize():
    async with state_lock:
        state = load_state()
        if not state.get("token"):
            return
        base = cloud_url(state["cloud_url"])
        async with httpx.AsyncClient(base_url=base, headers={"Authorization": f"Bearer {state['token']}"}, timeout=10, follow_redirects=False) as client:
            response = await client.post("/api/agent/heartbeat")
            response.raise_for_status()
            consents = {d["id"]: d for d in response.json()["devices"]}
            entities = {e["entity_id"]: e for e in await ha_states()}
            for binding in state["bindings"]:
                try:
                    if not binding.get("device_id"):
                        response = await client.post("/api/agent/devices", json={k: binding[k] for k in ("local_id", "name", "kind", "capabilities", "estimated_w")})
                        response.raise_for_status()
                        binding["device_id"] = response.json()["id"]
                        save_state(state)
                    if binding.get("needs_sync"):
                        response = await client.post(f"/api/agent/devices/{binding['device_id']}/configuration", json={**{k: binding[k] for k in ("local_id", "name", "kind", "capabilities", "estimated_w")}, "revision": binding["revision"]})
                        response.raise_for_status()
                        binding["needs_sync"] = False
                        consents.pop(binding["device_id"], None)
                        save_state(state)
                    if not binding.get("local_enabled"):
                        binding["measurement_status"] = "Deling er pauset lokalt."
                        continue
                    entity = entities.get(binding["power_entity"], {})
                    binding["sensor_state"] = str(entity.get("state", "ukjent"))[:100]
                    binding["sensor_unit"] = entity.get("attributes", {}).get("unit_of_measurement", "")
                    binding["sensor_observed_at"] = entity.get("last_reported") or entity.get("last_updated")
                    # Preserve observation time. Historical values are useful in the portal,
                    # but the server still excludes readings older than 45s from availability.
                    sample = power_sample(entity, max_age=86390)
                    if not sample:
                        binding["measurement_status"] = measurement_status(entity)
                        continue
                    binding["last_observed_at"] = sample["observed_at"]
                    binding["last_power_w"] = sample["power_w"]
                    sample_id = hashlib.sha256((binding["local_id"] + binding.get("revision", "") + sample["observed_at"] + str(sample["power_w"])).encode()).hexdigest()
                    response = await client.post("/api/agent/telemetry", json={**sample, "sample_id": sample_id, "device_id": binding["device_id"]})
                    response.raise_for_status()
                    binding["last_upload_at"] = utcnow().isoformat()
                    age = (utcnow() - parse_time(sample["observed_at"])).total_seconds()
                    binding["measurement_status"] = "Måling mottatt av SMARTi." if age <= 45 else "Siste måling mottatt av SMARTi, men den er for gammel for fleksibilitet."
                except httpx.HTTPError as error:
                    code = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
                    binding["measurement_status"] = f"SMARTi avviste synkroniseringen (HTTP {code}). Prøv igjen eller kontroller serveren." if code else "Kunne ikke sende til SMARTi. Prøver igjen automatisk."
                finally:
                    save_state(state)
            response = await client.get("/api/agent/commands")
            response.raise_for_status()
            for command in response.json():
                processed = state.setdefault("processed", {})
                result = processed.get(command["id"])
                if not result:
                    binding = next((b for b in state["bindings"] if b.get("device_id") == command["device_id"]), None)
                    result = evaluate_command(command, binding, consents.get(command["device_id"]))
                    processed[command["id"]] = result
                    # Durable before ACK. Bound local history; the server enforces expiry.
                    state["processed"] = dict(list(processed.items())[-1000:])
                    save_state(state)
                response = await client.post(f"/api/agent/commands/{command['id']}/result", json=result)
                if response.status_code != 409:
                    response.raise_for_status()
            runtime.update(connection="ONLINE", last_sync=utcnow().isoformat(), error=None)


async def worker():
    backoff = 15
    while True:
        try:
            await synchronize()
            backoff = 15
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # No URLs, response bodies, customer values or credentials in logs.
            runtime.update(connection="OFFLINE", error="Forbindelsen kunne ikke oppdateres. Kontroller server og tilkobling.")
            logger.warning("Synchronization failed (%s)", type(error).__name__)
            backoff = min(backoff * 2, 120)
        await asyncio.sleep(backoff)


@asynccontextmanager
async def lifespan(_):
    task = asyncio.create_task(worker())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="SMARTi Flex Home Assistant App", lifespan=lifespan)


@app.middleware("http")
async def ingress_only(request: Request, call_next):
    allowed = {"172.30.32.2"}
    if os.getenv("SMARTIFLEX_ALLOW_LOCAL_HTTP") == "1":
        allowed |= {"127.0.0.1", "::1", "testclient"}
    if not request.client or request.client.host not in allowed:
        return Response(status_code=403)
    if request.method != "GET" and not secrets.compare_digest(request.headers.get("x-csrf-token", ""), CSRF):
        return Response(status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/", response_class=HTMLResponse)
def ui():
    return Path(__file__).with_name("index.html").read_text().replace("__CSRF__", CSRF)


@app.get("/logo.png")
def logo():
    return FileResponse(Path(__file__).with_name("logo.png"), media_type="image/png")


@app.get("/app.js")
def script():
    return FileResponse(Path(__file__).with_name("app.js"), media_type="text/javascript")


@app.get("/style.css")
def stylesheet():
    return FileResponse(Path(__file__).with_name("style.css"), media_type="text/css")


@app.get("/status")
async def status():
    async with state_lock:
        state = load_state()
        return {**runtime, "paired": bool(state.get("token")), "cloud_url": state.get("cloud_url"), "bindings": state["bindings"], "physical_control_enabled": False}


class PairRequest(BaseModel):
    cloud_url: str = Field(max_length=300)
    code: str = Field(min_length=30, max_length=128)


@app.post("/pair")
async def pair(body: PairRequest):
    try:
        base = cloud_url(body.cloud_url)
    except ValueError as error:
        raise HTTPException(422, str(error))
    async with state_lock:
        state = load_state()
        if state.get("token"):
            raise HTTPException(409, "Koble fra den eksisterende installasjonen først")
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            try:
                response = await client.post(base + "/api/agent/pair", json={"code": body.code})
                response.raise_for_status()
            except httpx.HTTPStatusError as error:
                if error.response.status_code == 401:
                    raise HTTPException(400, "Engangskoden er ugyldig eller utløpt. Lag en ny kode i SMARTi-portalen.")
                if error.response.status_code == 429:
                    raise HTTPException(429, "For mange tilkoblingsforsøk. Vent ett minutt og prøv igjen.")
                raise HTTPException(400, "Serveren avviste tilkoblingen. Kontroller at adressen går til SMARTi-backenden, ikke Home Assistant.")
            except httpx.HTTPError:
                raise HTTPException(400, "SMARTi-backenden kunne ikke nås over HTTPS. Kontroller at serveren eller testtunnelen kjører og er tilgjengelig fra Home Assistant.")
        try:
            paired = response.json()
            if not isinstance(paired, dict) or not all(isinstance(paired.get(k), str) and paired[k] for k in ("token", "installation_id")):
                raise ValueError()
        except (ValueError, TypeError):
            raise HTTPException(400, "Adressen svarte, men ikke som en SMARTi-backend. Kontroller serveradressen.")
        state.update(cloud_url=base, token=paired["token"], installation_id=paired["installation_id"])
        save_state(state)
        return {"paired": True}


@app.post("/disconnect")
async def disconnect():
    async with state_lock:
        save_state({"bindings": [], "processed": {}})
        runtime.update(connection="UNKNOWN", last_sync=None, error=None)
    return {"ok": True}


@app.get("/entities")
async def entities():
    try:
        states = await ha_states()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Home Assistant er ikke tilgjengelig")
    result = []
    for entity in states:
        domain = entity["entity_id"].split(".")[0]
        attributes = entity.get("attributes", {})
        unit = attributes.get("unit_of_measurement")
        if domain not in ("switch", "climate", "number") and unit not in ("W", "kW"):
            continue
        sample = power_sample(entity)
        result.append({"entity_id": entity["entity_id"], "name": attributes.get("friendly_name", entity["entity_id"]), "unit": unit, "domain": domain, "power_w": sample["power_w"] if sample else None})
    return result


class BindingRequest(BaseModel):
    entity_id: str = Field(max_length=200)
    power_entity: str = Field(max_length=200)
    name: str = Field(min_length=1, max_length=120)
    estimated_w: int = Field(ge=0, le=1_000_000)
    max_duration_seconds: int = Field(ge=30, le=3600)


@app.post("/bindings")
async def bind(body: BindingRequest):
    try:
        items = {e["entity_id"]: e for e in await ha_states()}
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Home Assistant er ikke tilgjengelig")
    domain = body.entity_id.split(".")[0]
    if body.entity_id not in items or domain not in ("switch", "climate", "number") or items.get(body.power_entity, {}).get("attributes", {}).get("unit_of_measurement") not in ("W", "kW"):
        raise HTTPException(422, "Velg en støttet enhet og en effektsensor i W eller kW")
    capabilities = {"switch": ["TURN_ON", "TURN_OFF"], "climate": ["SET_TEMPERATURE"], "number": []}[domain]
    async with state_lock:
        state = load_state()
        if not state.get("token"):
            raise HTTPException(409, "Koble til SMARTi først")
        if any(b["entity_id"] == body.entity_id or b["power_entity"] == body.power_entity for b in state["bindings"]):
            raise HTTPException(409, "Enheten eller effektsensoren er allerede valgt")
        state["bindings"].append({**body.model_dump(), "local_id": str(uuid4()), "device_id": None, "kind": "THERMOSTAT" if domain == "climate" else "GENERIC_LOAD" if domain == "number" else "SWITCH", "capabilities": capabilities + ["READ_POWER"], "local_enabled": True})
        save_state(state)
        return {"ok": True}


class ParticipationRequest(BaseModel):
    enabled: bool


@app.post("/bindings/{local_id}/participation")
async def participation(local_id: str, body: ParticipationRequest):
    async with state_lock:
        state = load_state()
        binding = next((b for b in state["bindings"] if b["local_id"] == local_id), None)
        if not binding:
            raise HTTPException(404)
        binding["local_enabled"] = body.enabled
        save_state(state)
    return {"ok": True}


@app.post("/bindings/{local_id}/edit")
async def edit_binding(local_id: str, body: BindingRequest):
    try:
        items = {e["entity_id"]: e for e in await ha_states()}
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Home Assistant er ikke tilgjengelig")
    domain = body.entity_id.split(".")[0]
    if body.entity_id not in items or domain not in ("switch", "climate", "number") or items.get(body.power_entity, {}).get("attributes", {}).get("unit_of_measurement") not in ("W", "kW"):
        raise HTTPException(422, "Velg en støttet enhet og en effektsensor i W eller kW")
    async with state_lock:
        state = load_state()
        binding = next((b for b in state["bindings"] if b["local_id"] == local_id), None)
        if not binding:
            raise HTTPException(404)
        if any(b["local_id"] != local_id and (b["entity_id"] == body.entity_id or b["power_entity"] == body.power_entity) for b in state["bindings"]):
            raise HTTPException(409, "Enheten eller målingen brukes allerede av en annen enhet")
        binding.update(body.model_dump())
        binding.update(revision=str(uuid4()), needs_sync=True, kind="THERMOSTAT" if domain == "climate" else "GENERIC_LOAD" if domain == "number" else "SWITCH", capabilities={"switch": ["TURN_ON", "TURN_OFF"], "climate": ["SET_TEMPERATURE"], "number": []}[domain] + ["READ_POWER"], measurement_status="Endringen venter på synkronisering med SMARTi.")
        for key in ("last_observed_at", "last_power_w", "last_upload_at"):
            binding.pop(key, None)
        save_state(state)
    return {"ok": True}
