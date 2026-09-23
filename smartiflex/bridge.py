"""Outbound Home Assistant bridge with an opt-in, locally bounded switch pilot."""
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
from typing import Literal
import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("smartiflex.bridge")
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
STATE_PATH = DATA_DIR / "state.json"
CSRF = secrets.token_urlsafe(32)
VERSION = "0.8.5"
runtime = {"connection": "UNKNOWN", "last_sync": None, "error": None, "cloud_control_enabled": False, "active_dispatch_ids": [], "control_lease_at": None}
state_lock = asyncio.Lock()
control_lock = asyncio.Lock()
blocked_local_ids = set()


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
    state = json.loads(STATE_PATH.read_text())
    if state.get("portal_managed") != 2:
        for binding in state.get("bindings", []):
            binding.update(local_enabled=not binding.get("pending_remove"), physical_control_enabled=not binding.get("pending_remove") and binding.get("entity_id", "").startswith(("switch.", "climate.")), portal_managed=True)
        state["portal_managed"] = 2
        save_state(state)
    repaired = False
    for binding in state.get("bindings", []):
        if binding.get("revision") and not binding.get("edit_permission_repaired") and not binding.get("pending_remove"):
            binding["physical_control_enabled"] = binding.get("entity_id", "").startswith(("switch.", "climate."))
            binding["edit_permission_repaired"] = True
            repaired = True
    if repaired:
        save_state(state)
    return state


def atomic_json(path, state):
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(state, output)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)
    directory = os.open(DATA_DIR, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def save_state(state):
    atomic_json(STATE_PATH, state)


def load_control():
    path = STATE_PATH.with_name("control.json")
    return json.loads(path.read_text()) if path.exists() else {"commands": {}, "outbox": []}


def save_control(journal):
    # Never discard an unresolved restore or an unacknowledged result.
    pending = {r["command_id"] for r in journal["outbox"]}
    completed = [key for key, value in journal["commands"].items() if value["state"] in ("RESTORED", "REJECTED") and key not in pending]
    for key in completed[:-1000]:
        del journal["commands"][key]
    atomic_json(STATE_PATH.with_name("control.json"), journal)


def queue_control_result(journal, command_id, status, error=None, **evidence):
    result = {"status": status, "evidence": evidence}
    if error:
        result["error"] = error
    entry = journal["commands"][command_id]
    entry["result"] = result
    if not any(item["command_id"] == command_id and item["result"] == result for item in journal["outbox"]):
        journal["outbox"].append({"id": str(uuid4()), "command_id": command_id, "installation_id": entry.get("installation_id"), "result": result})


def cloud_control_current():
    try:
        return runtime.get("cloud_control_enabled") is True and 0 <= (utcnow() - parse_time(runtime["control_lease_at"])).total_seconds() <= 45
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def locally_permitted(binding, journal):
    return bool(binding.get("physical_control_enabled") is True and binding.get("local_enabled") and not binding.get("needs_sync")
        and binding.get("local_id") not in blocked_local_ids and binding.get("entity_id", "").startswith(("switch.", "climate."))
        and not any(c["state"] == "RESTORE_FAILED" and (c.get("local_id") == binding.get("local_id") or c.get("entity_id") == binding.get("entity_id")) for c in journal["commands"].values()))


def control_ready(binding, entity, journal):
    return bool(locally_permitted(binding, journal) and entity and (entity.get("state") == "on" if binding.get("entity_id", "").startswith("switch.") else entity.get("state") not in (None, "off", "unknown", "unavailable") and "off" in entity.get("attributes", {}).get("hvac_modes", []))
        and not any(c["state"] not in ("RESTORED", "REJECTED") and (c.get("local_id") == binding.get("local_id") or c.get("entity_id") == binding.get("entity_id")) for c in journal["commands"].values()))



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


def power_sample(entity, max_age=45, hold=False):
    """Preserve sensor time; held states get a separate HA check time."""
    try:
        value = Decimal(entity["state"])
        unit = entity.get("attributes", {}).get("unit_of_measurement")
        if not value.is_finite() or unit not in ("W", "kW"):
            return None
        value *= 1000 if unit == "kW" else 1
        observed = parse_time(entity.get("last_reported") or entity["last_updated"])
        if (utcnow() - observed).total_seconds() < -10 or (not hold and (utcnow() - observed).total_seconds() > max_age):
            return None
        watts = int(value.to_integral_value())
        if abs(watts) > 10_000_000:
            return None
        return {"power_w": watts, "observed_at": observed.isoformat(), **({"checked_at": utcnow().isoformat()} if hold else {})}
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


def evaluate_command(command, binding, consent, *, physical_enabled=False):
    """Validate local and server permission before any service is called."""
    if not binding or not binding.get("local_enabled") or binding.get("needs_sync"):
        return {"status": "REJECTED", "error": "Local participation is disabled"}
    if not consent or not consent.get("enabled") or consent.get("consent_version") != command.get("consent_version"):
        return {"status": "REJECTED", "error": "Consent changed or is unavailable"}
    try:
        end, start = parse_time(command["expires_at"]), parse_time(command["period_from"])
        if end <= utcnow() or start > utcnow() or not 0 < (end-start).total_seconds() <= (consent["constraints"]["max_duration_seconds"] if binding.get("portal_managed") else min(binding["max_duration_seconds"], consent["constraints"]["max_duration_seconds"])):
            return {"status": "REJECTED", "error": "Command timing exceeds local constraints"}
    except (KeyError, ValueError, TypeError, AttributeError):
        return {"status": "REJECTED", "error": "Invalid command timing"}
    if command.get("command") == "VERIFY_CONNECTION" and command.get("simulation") is True:
        return {"status": "SIMULATED"}
    if (command.get("command") == "REDUCE_LOAD" and command.get("simulation") is False
        and physical_enabled is True and binding.get("physical_control_enabled") is True and binding.get("local_id") not in blocked_local_ids
        and binding.get("entity_id", "").startswith(("switch.", "climate."))):
        return {"status": "READY"}
    return {"status": "REJECTED", "error": "Physical control is not permitted for this device"}


async def ha_states():
    token = os.getenv("SUPERVISOR_TOKEN")
    if not token:
        raise ValueError("Supervisor access is not available")
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        response = await client.get("http://supervisor/core/api/states", headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        return response.json()


async def ha_entity(entity_id):
    if not entity_id.startswith(("switch.", "climate.")) or any(c in entity_id for c in ("/", "?", "#")):
        raise ValueError("Only local switch and climate entities are supported")
    token = os.getenv("SUPERVISOR_TOKEN")
    if not token:
        raise ValueError("Supervisor access is not available")
    async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
        response = await client.get("http://supervisor/core/api/states/" + entity_id, headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        entity = response.json()
        if entity.get("entity_id") != entity_id:
            raise ValueError("Unexpected Home Assistant entity")
        return entity


async def ha_switch(entity_id, service):
    if service not in ("turn_on", "turn_off") or not entity_id.startswith("switch."):
        raise ValueError("Unsupported local service")
    token = os.getenv("SUPERVISOR_TOKEN")
    if not token:
        raise ValueError("Supervisor access is not available")
    async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
        response = await client.post("http://supervisor/core/api/services/switch/" + service,
            headers={"Authorization": f"Bearer {token}"}, json={"entity_id": entity_id})
        response.raise_for_status()
        states = response.json()
        return next((e for e in states if e.get("entity_id") == entity_id), None) if isinstance(states, list) else None


CLIMATE_SETTINGS = {"temperature": ("set_temperature", "temperature"),
    "target_temp_low": ("set_temperature", "target_temp_low"), "target_temp_high": ("set_temperature", "target_temp_high"),
    "preset_mode": ("set_preset_mode", "preset_mode"), "fan_mode": ("set_fan_mode", "fan_mode"),
    "swing_mode": ("set_swing_mode", "swing_mode"), "swing_horizontal_mode": ("set_swing_horizontal_mode", "swing_horizontal_mode"),
    "humidity": ("set_humidity", "humidity")}


def prior_state(entity):
    return {"state": entity["state"], "attributes": {k: v for k, v in entity.get("attributes", {}).items()
        if k in CLIMATE_SETTINGS and v is not None}} if entity["entity_id"].startswith("climate.") else {"state": entity["state"], "attributes": {}}


def matches_prior(entity, prior):
    return entity.get("state") == prior["state"] and all(entity.get("attributes", {}).get(k) == v for k, v in prior.get("attributes", {}).items())


async def ha_climate(entity_id, service, data):
    if not entity_id.startswith("climate.") or service not in {"set_hvac_mode", *(v[0] for v in CLIMATE_SETTINGS.values())}:
        raise ValueError("Unsupported climate service")
    token = os.getenv("SUPERVISOR_TOKEN")
    if not token:
        raise ValueError("Supervisor access is not available")
    async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
        response = await client.post("http://supervisor/core/api/services/climate/" + service,
            headers={"Authorization": f"Bearer {token}"}, json={"entity_id": entity_id, **data})
        response.raise_for_status()
        states = response.json()
        return next((e for e in states if e.get("entity_id") == entity_id), None) if isinstance(states, list) else None


async def turn_off(entity_id):
    return await ha_climate(entity_id, "set_hvac_mode", {"hvac_mode": "off"}) if entity_id.startswith("climate.") else await ha_switch(entity_id, "turn_off")


async def confirmed_state(entity_id, predicate, *, expires_at=None):
    """A service response is acceptance, not synchronous device confirmation."""
    try:
        async with asyncio.timeout(8):
            for attempt in range(25):
                if expires_at and utcnow() >= parse_time(expires_at):
                    raise ValueError("Activation expired while awaiting HA confirmation")
                entity = await ha_entity(entity_id)
                if expires_at and utcnow() >= parse_time(expires_at):
                    raise ValueError("Activation expired while awaiting HA confirmation")
                if predicate(entity):
                    return entity
                await asyncio.sleep(0.25)
    except TimeoutError:
        pass
    raise ValueError("HA state was not confirmed within the verification window")


async def restore_state(item, entity, journal, command_id):
    if not item["entity_id"].startswith("climate."):
        await ha_switch(item["entity_id"], "turn_on")
        return
    prior = item["prior_state"]
    grouped = {}
    for key, value in prior["attributes"].items():
        if entity.get("attributes", {}).get(key) != value:
            service, field = CLIMATE_SETTINGS[key]
            grouped.setdefault(service, {})[field] = value
    for service, data in grouped.items():
        changed = await ha_climate(item["entity_id"], service, data)
        if changed and changed.get("state") == "off":
            item["off_signature"] = state_signature(changed)
            save_control(journal)
    await ha_climate(item["entity_id"], "set_hvac_mode", {"hvac_mode": prior["state"]})


def state_signature(entity):
    result = {"changed": entity.get("last_changed"), "context": entity.get("context", {}).get("id")}
    if entity.get("entity_id", "").startswith("climate."):
        result["settings"] = {k: v for k, v in entity.get("attributes", {}).items() if k in CLIMATE_SETTINGS}
    return result


def restore_failed(journal, command_id, message):
    item = journal["commands"][command_id]
    item["state"] = "RESTORE_FAILED"
    item["local_error"] = message
    queue_control_result(journal, command_id, "RESTORE_FAILED", message, restored=False)
    save_control(journal)


def restore_done(journal, command_id):
    item = journal["commands"][command_id]
    item["state"] = "RESTORED"
    item.pop("local_error", None)
    queue_control_result(journal, command_id, "RESTORED", restored=True, observed_at=utcnow().isoformat())
    save_control(journal)


async def restore_pending(*, force=False, local_id=None, preserve_active=False):
    """Independent of cloud retries, pairing, and the main synchronization lock."""
    async with control_lock:
        journal = load_control()
        try:
            bindings = {b["local_id"]: b for b in load_state()["bindings"]}
        except (ValueError, KeyError, TypeError):
            bindings = {}  # Corrupt/missing permission data must not extend a lease.
            force = True

        async def restore_one(command_id, item):
            binding = bindings.get(item["local_id"], {})
            # A planned process restart must not terminate a confirmed lease.
            # Keep the durable original state; expiry is still absolute.
            if (preserve_active and item["state"] == "ACTIVE" and item.get("hold_off")
                    and utcnow() < parse_time(item["expires_at"])
                    and locally_permitted(binding, journal)
                    and binding.get("entity_id") == item["entity_id"]):
                return
            try:
                entity = await ha_entity(item["entity_id"])
                prior = item.get("prior_state", {"state": "on", "attributes": {}})
                # Hold the saved original state until the live lease ends. A
                # manual ON is not a completed restoration during an activation.
                holding = (not force and item["state"] == "ACTIVE" and item.get("hold_off")
                    and utcnow() < parse_time(item["expires_at"]) and cloud_control_current()
                    and command_id in runtime.get("active_dispatch_ids", [])
                    and locally_permitted(binding, journal) and binding.get("entity_id") == item["entity_id"])
                if holding:
                    if entity.get("state") in (None, "unknown", "unavailable"):
                        item["local_error"] = "Kan ikke bekrefte avslått tilstand. Prøver igjen."
                        save_control(journal)
                        return
                    if entity.get("state") != "off":
                        item["reassert_attempt_at"] = utcnow().isoformat()
                        save_control(journal)
                        await turn_off(item["entity_id"])
                        entity = await ha_entity(item["entity_id"])
                        item["reassert_count"] = item.get("reassert_count", 0) + 1
                        logger.info("Reasserted off for active command %s", command_id)
                    if entity.get("state") != "off":
                        item["local_error"] = "Enheten bekreftet ikke avslått tilstand. Prøver igjen."
                    else:
                        item["off_signature"] = state_signature(entity)
                        item.pop("local_error", None)
                    save_control(journal)
                    return
                if matches_prior(entity, prior):
                    # The user/another automation may have already restored it.
                    restore_done(journal, command_id)
                    return
                if entity.get("state") != "off":
                    restore_failed(journal, command_id, "Enheten er utilgjengelig. Kontroller den i Home Assistant.")
                    return
                # A network read may itself have crossed the deadline or pause.
                due = (force or item["state"] in ("PREPARED", "RESTORE_FAILED") or utcnow() >= parse_time(item["expires_at"])
                    or not cloud_control_current() or command_id not in runtime.get("active_dispatch_ids", [])
                    or item["local_id"] in blocked_local_ids or not binding.get("local_enabled") or not binding.get("physical_control_enabled")
                    or binding.get("entity_id") != item["entity_id"] or binding.get("needs_sync"))
                if not due:
                    return
                signature = item.get("off_signature")
                if (signature and signature != state_signature(entity)) or (not signature and entity.get("context", {}).get("user_id")):
                    # Do not undo a newer manual/automation change to the switch.
                    restore_failed(journal, command_id, "Enheten ble endret etter styringen. Slå den på manuelt for å avslutte testen.")
                    return
                await restore_state(item, entity, journal, command_id)
                after = await confirmed_state(item["entity_id"], lambda value: matches_prior(value, prior))
                if not matches_prior(after, prior):
                    restore_failed(journal, command_id, "Enheten bekreftet ikke på. Kontroller den i Home Assistant.")
                    return
                restore_done(journal, command_id)
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                restore_failed(journal, command_id, "Kunne ikke gjenopprette enheten. Prøver igjen; kontroller Home Assistant.")

        # Independent switches must not wait in line behind an unavailable HA
        # entity. Journal updates are synchronous under the one journal lock;
        # await every task, including failures, before releasing that lock.
        outcomes = await asyncio.gather(*(restore_one(command_id, item) for command_id, item in list(journal["commands"].items())
            if item["state"] not in ("RESTORED", "REJECTED") and (not local_id or item["local_id"] == local_id)), return_exceptions=True)
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                raise outcome


async def execute_physical(command, binding, consent):
    async with control_lock:
        journal = load_control()
        command_id = command["id"]
        if command_id in journal["commands"]:
            return  # Durable execution history prevents a second turn_off.
        decision = evaluate_command(command, binding, consent, physical_enabled=cloud_control_current())
        if decision["status"] == "READY" and command_id not in runtime.get("active_dispatch_ids", []):
            decision = {"status": "REJECTED", "error": "Server control permission is no longer current"}
        if decision["status"] == "READY":
            try:
                entity = await ha_entity(binding["entity_id"])
                already_off = entity.get("state") == "off" and locally_permitted(binding, journal) and not any(
                    c["state"] not in ("RESTORED", "REJECTED") and c.get("entity_id") == binding["entity_id"] for c in journal["commands"].values())
                if not control_ready(binding, entity, journal) and not already_off:
                    decision = {"status": "REJECTED", "error": "Enheten må være på og uten uavklart tidligere styring"}
            except (httpx.HTTPError, ValueError, TypeError):
                decision = {"status": "REJECTED", "error": "Enheten kunne ikke kontrolleres i Home Assistant"}
            if decision["status"] == "READY":
                # Network reads may have crossed expiry or a local pause.
                decision = evaluate_command(command, binding, consent, physical_enabled=cloud_control_current())
                if decision["status"] == "READY" and command_id not in runtime.get("active_dispatch_ids", []):
                    decision = {"status": "REJECTED", "error": "Server control permission is no longer current"}
        if decision["status"] != "READY":
            journal["commands"][command_id] = {"state": "REJECTED", "installation_id": load_state().get("installation_id")}
            queue_control_result(journal, command_id, "REJECTED", decision.get("error", "Unsupported command"))
            save_control(journal)
            return
        # This independent journal is fsynced before the external effect. It is
        # retained on disconnect/edit and the watchdog restores after restart.
        item = {"state": "PREPARED", "installation_id": load_state().get("installation_id"), "entity_id": binding["entity_id"], "local_id": binding["local_id"],
            "device_id": command["device_id"], "expires_at": command["expires_at"], "prepared_at": utcnow().isoformat(), "prior_state": prior_state(entity), "hold_off": True}
        journal["commands"][command_id] = item
        save_control(journal)
        try:
            if entity.get("state") == "off":
                item["state"] = "ACTIVE"
                queue_control_result(journal, command_id, "EXECUTED", physical_execution=False, already_off=True, observed_at=utcnow().isoformat())
                save_control(journal)
                return
            changed = await turn_off(binding["entity_id"])
            # Capture action-owned identity before a verification read, so a
            # subsequent manual change cannot become our restoration target.
            if changed and changed.get("state") == "off":
                item["off_signature"] = state_signature(changed)
                save_control(journal)
            after = await confirmed_state(binding["entity_id"], lambda value: value.get("state") == "off", expires_at=command["expires_at"])
            if after.get("state") != "off":
                raise ValueError("Switch did not confirm off")
            # HA integrations may update context/attributes asynchronously while
            # remaining off. The confirmed off state is our restoration identity.
            item["off_signature"] = state_signature(after)
            item["state"] = "ACTIVE"
            queue_control_result(journal, command_id, "EXECUTED", physical_execution=True, observed_at=utcnow().isoformat())
            save_control(journal)
        except (httpx.HTTPError, ValueError, TypeError):
            # A timeout may have happened after HA applied turn_off. Never retry
            # the reduction; retain PREPARED and let restoration resolve it.
            queue_control_result(journal, command_id, "FAILED", "Enheten bekreftet ikke styringen. Gjenoppretting pågår.", physical_execution=False)
            save_control(journal)


async def flush_control_results(client):
    while True:
        async with control_lock:
            installation_id = load_state().get("installation_id")
            outbox = [item for item in load_control()["outbox"] if item.get("installation_id") == installation_id]
            if not outbox:
                return
            item = outbox[0]
        response = await client.post(f"/api/agent/commands/{item['command_id']}/result", json=item["result"])
        response.raise_for_status()
        async with control_lock:
            journal = load_control()
            journal["outbox"] = [r for r in journal["outbox"] if r["id"] != item["id"]]
            save_control(journal)


async def restore_watchdog():
    # Cloud outage/backoff must not extend a physical action. A process or HA
    # host outage cannot be timed out by software that is no longer running.
    while True:
        try:
            await restore_pending()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error("Local restoration failed (%s)", type(error).__name__)
            runtime["error"] = "Lokal gjenoppretting trenger tilsyn. Kontroller bryterne i Home Assistant."
        await asyncio.sleep(2)


async def _synchronize():
    async with state_lock:
        state = load_state()
        if not state.get("token"):
            return
        base = cloud_url(state["cloud_url"])
        async with httpx.AsyncClient(base_url=base, headers={"Authorization": f"Bearer {state['token']}"}, timeout=10, follow_redirects=False) as client:
            entities = {e["entity_id"]: e for e in await ha_states()}
            async def heartbeat():
                journal = load_control()
                ready = [b["device_id"] for b in state["bindings"] if b.get("device_id") and locally_permitted(b, journal)]
                states = []
                for b in state["bindings"]:
                    entity = entities.get(b.get("entity_id"), {})
                    b["ha_status"] = {"state": str(entity.get("state", "unavailable"))[:60], "action": str(entity.get("attributes", {}).get("hvac_action") or "")[:60], "checked_at": utcnow().isoformat()}
                    if b.get("device_id"):
                        states.append({"device_id": b["device_id"], "state": b["ha_status"]["state"], "action": b["ha_status"]["action"]})
                reply = await client.post("/api/agent/heartbeat", json={"version": VERSION, "control_ready_device_ids": ready, "device_states": states})
                reply.raise_for_status()
                payload = reply.json()
                active = payload.get("active_dispatch_ids")
                runtime.update(cloud_control_enabled=payload.get("physical_control_enabled") is True and isinstance(active, list),
                    active_dispatch_ids=active if isinstance(active, list) else [], control_lease_at=utcnow().isoformat())
                return {d["id"]: d for d in payload["devices"]}
            consents = await heartbeat()
            await restore_pending()
            await flush_control_results(client)
            for binding in list(state["bindings"]):
                try:
                    if binding.get("pending_remove"):
                        if binding.get("device_id"):
                            response = await client.post(f"/api/agent/devices/{binding['device_id']}/disconnect")
                            response.raise_for_status()
                        state["bindings"].remove(binding)
                        save_state(state)
                        continue
                    if not binding.get("device_id"):
                        response = await client.post("/api/agent/devices", json={k: binding[k] for k in ("local_id", "name", "kind", "capabilities", "estimated_w")})
                        response.raise_for_status()
                        binding["device_id"] = response.json()["id"]
                        save_state(state)
                    if binding.get("needs_sync"):
                        response = await client.post(f"/api/agent/devices/{binding['device_id']}/configuration", json={**{k: binding[k] for k in ("local_id", "name", "kind", "capabilities", "estimated_w")}, "revision": binding["revision"]})
                        response.raise_for_status()
                        binding["needs_sync"] = False
                        blocked_local_ids.discard(binding["local_id"])
                        consents.pop(binding["device_id"], None)
                        save_state(state)
                    permission = consents.get(binding.get("device_id"))
                    if permission and permission.get("constraints", {}).get("measurements_enabled") is False:
                        binding["measurement_status"] = "Måledeling er pauset i SMARTi Flex."
                        binding["portal_measurements_paused"] = True
                        continue
                    binding["portal_measurements_paused"] = False
                    if not binding.get("local_enabled"):
                        binding["measurement_status"] = "Deling er pauset lokalt."
                        continue
                    entity = entities.get(binding["power_entity"], {})
                    binding["sensor_state"] = str(entity.get("state", "ukjent"))[:100]
                    binding["sensor_unit"] = entity.get("attributes", {}).get("unit_of_measurement", "")
                    binding["sensor_observed_at"] = entity.get("last_reported") or entity.get("last_updated")
                    # Preserve observation time. On-change checks are display-only;
                    # they never qualify as fresh measured market capacity.
                    sample = power_sample(entity, max_age=86390, hold=binding.get("reporting_mode", "on_change") == "on_change")
                    if not sample:
                        binding["measurement_status"] = measurement_status(entity)
                        continue
                    binding["last_observed_at"] = sample["observed_at"]
                    binding["last_power_w"] = sample["power_w"]
                    sample_id = hashlib.sha256((binding["local_id"] + binding.get("revision", "") + sample.get("checked_at", sample["observed_at"]) + str(sample["power_w"])).encode()).hexdigest()
                    response = await client.post("/api/agent/telemetry", json={**sample, "sample_id": sample_id, "device_id": binding["device_id"]})
                    response.raise_for_status()
                    binding["last_upload_at"] = utcnow().isoformat()
                    age = (utcnow() - parse_time(sample["observed_at"])).total_seconds()
                    binding["measurement_status"] = "Videreført verdi · kontrollert i Home Assistant nå." if sample.get("checked_at") else "Måling mottatt av SMARTi." if age <= 45 else "Siste måling mottatt av SMARTi, men den er for gammel for fleksibilitet."
                except httpx.HTTPError as error:
                    code = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
                    binding["measurement_status"] = f"SMARTi avviste synkroniseringen (HTTP {code}). Prøv igjen eller kontroller serveren." if code else "Kunne ikke sende til SMARTi. Prøver igjen automatisk."
                finally:
                    save_state(state)
            response = await client.get("/api/agent/commands")
            response.raise_for_status()
            commands = response.json()
            if any(c.get("simulation") is False for c in commands):
                consents = await heartbeat()
                await restore_pending()
            for command in commands:
                if command.get("simulation") is False:
                    binding = next((b for b in state["bindings"] if b.get("device_id") == command["device_id"]), None)
                    await execute_physical(command, binding, consents.get(command["device_id"]))
                    continue
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
            await restore_pending()
            await flush_control_results(client)
            runtime.update(connection="ONLINE", last_sync=utcnow().isoformat(), error=None)


async def synchronize():
    try:
        await _synchronize()
    except Exception:
        # A telemetry/result upload failure is not a server cancellation. Keep
        # the last confirmed lease until its existing freshness deadline. The
        # independent watchdog still restores on expiry or explicit revocation.
        await restore_pending()
        raise


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
    # Reconcile durable commands with the server BEFORE the restoration
    # watchdog sees the empty in-memory lease after a process restart.
    while True:
        try:
            await _synchronize()
            break
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            logger.warning("Waiting for restart reconciliation (%s)", type(error).__name__)
            # HA/Core or the server can still be starting. Do not fabricate a
            # cancellation from that outage. Expired commands are restored.
            await restore_pending(force=True, preserve_active=True)
            active = any(c.get("state") == "ACTIVE" and c.get("hold_off")
                         and utcnow() < parse_time(c["expires_at"])
                         for c in load_control()["commands"].values())
            if not active:
                break
            await asyncio.sleep(2)
    await restore_pending()
    task = asyncio.create_task(worker())
    watchdog = asyncio.create_task(restore_watchdog())
    try:
        yield
    finally:
        task.cancel()
        watchdog.cancel()
        await asyncio.gather(task, watchdog, return_exceptions=True)
        await restore_pending(force=True, preserve_active=True)
        runtime.update(cloud_control_enabled=False, active_dispatch_ids=[])


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
        journal = load_control()
        controls = [{"device_id": c.get("device_id"), "local_id": c.get("local_id"), "status": c["state"], "expires_at": c.get("expires_at"), "error": c.get("local_error")} for c in journal["commands"].values() if c["state"] not in ("RESTORED", "REJECTED")]
        return {**runtime, "version": VERSION, "paired": bool(state.get("token")), "cloud_url": state.get("cloud_url"), "bindings": state["bindings"], "physical_control_enabled": cloud_control_current(), "controls": controls, "pending_control_results": len(journal["outbox"])}


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
    runtime.update(cloud_control_enabled=False, active_dispatch_ids=[], control_lease_at=None)
    await restore_pending(force=True)
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
    kind: Literal["HEAT_PUMP", "EV_CHARGER", "OVEN", "WATER_HEATER", "UNDERFLOOR_HEATING", "BATTERY", "HVAC", "SAUNA", "GENERIC_LOAD"] | None = None
    reporting_mode: Literal["periodic", "on_change"] = "on_change"
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
        state["bindings"].append({**body.model_dump(), "local_id": str(uuid4()), "device_id": None, "kind": body.kind or "GENERIC_LOAD", "capabilities": capabilities + ["READ_POWER"], "local_enabled": True, "physical_control_enabled": domain in ("switch", "climate"), "portal_managed": True})
        save_state(state)
        return {"ok": True}


class ParticipationRequest(BaseModel):
    enabled: bool


@app.post("/bindings/{local_id}/participation")
async def participation(local_id: str, body: ParticipationRequest):
    raise HTTPException(409, "Administrer måledeling og styring i SMARTi Flex-portalen.")


@app.post("/bindings/{local_id}/control")
async def local_control(local_id: str, body: ParticipationRequest):
    raise HTTPException(409, "Administrer måledeling og styring i SMARTi Flex-portalen.")


@app.post("/bindings/{local_id}/remove")
async def remove_binding(local_id: str):
    blocked_local_ids.add(local_id)
    await restore_pending(force=True, local_id=local_id)
    async with state_lock:
        state = load_state()
        binding = next((b for b in state["bindings"] if b["local_id"] == local_id), None)
        if not binding:
            raise HTTPException(404)
        if any(c.get("local_id") == local_id and c["state"] not in ("RESTORED", "REJECTED") for c in load_control()["commands"].values()):
            raise HTTPException(409, "Styringen må gjenopprettes før enheten kan fjernes. Kontroller enheten i Home Assistant.")
        binding.update(pending_remove=True, local_enabled=False, physical_control_enabled=False)
        save_state(state)
    return {"ok": True, "pending": True}


@app.post("/bindings/{local_id}/edit")
async def edit_binding(local_id: str, body: BindingRequest):
    try:
        items = {e["entity_id"]: e for e in await ha_states()}
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Home Assistant er ikke tilgjengelig")
    domain = body.entity_id.split(".")[0]
    if body.entity_id not in items or domain not in ("switch", "climate", "number") or items.get(body.power_entity, {}).get("attributes", {}).get("unit_of_measurement") not in ("W", "kW"):
        raise HTTPException(422, "Velg en støttet enhet og en effektsensor i W eller kW")
    blocked_local_ids.add(local_id)
    await restore_pending(force=True, local_id=local_id)
    async with state_lock:
        state = load_state()
        binding = next((b for b in state["bindings"] if b["local_id"] == local_id), None)
        if not binding:
            raise HTTPException(404)
        if any(b["local_id"] != local_id and (b["entity_id"] == body.entity_id or b["power_entity"] == body.power_entity) for b in state["bindings"]):
            raise HTTPException(409, "Enheten eller målingen brukes allerede av en annen enhet")
        if any(c.get("local_id") == local_id and c["state"] not in ("RESTORED", "REJECTED") for c in load_control()["commands"].values()):
            raise HTTPException(409, "Tidligere styring må tilbakeføres før du endrer entitet. Kontroller enheten i Home Assistant.")
        binding.update(body.model_dump(exclude_none=True))
        binding["physical_control_enabled"] = domain in ("switch", "climate")
        binding["edit_permission_repaired"] = True
        binding.update(revision=str(uuid4()), needs_sync=True, kind=body.kind or binding.get("kind", "GENERIC_LOAD"), capabilities={"switch": ["TURN_ON", "TURN_OFF"], "climate": ["SET_TEMPERATURE"], "number": []}[domain] + ["READ_POWER"], measurement_status="Endringen venter på synkronisering med SMARTi.")
        for key in ("last_observed_at", "last_power_w", "last_upload_at"):
            binding.pop(key, None)
        save_state(state)
    await restore_pending(force=True, local_id=local_id)
    return {"ok": True}
