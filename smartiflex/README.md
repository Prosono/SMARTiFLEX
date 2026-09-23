## Versjon 0.7.0 – styr valgene i SMARTi Flex

HA-appen brukes til å legge til og fjerne enheter. Nye enheter deler målinger og er tilgjengelige for støttet styring. Måledeling, styring/test og tidsgrenser administreres i SMARTi Flex-portalen. Eksisterende valg i portalen beholdes ved oppdatering; gamle lokale av/på-valg erstattes av portalstyring.

Fysisk styring støttes foreløpig for brytere. Portalens tillatelse, administratorens sperrer, fersk styringsforbindelse og gjenopprettingskontroll gjelder fortsatt. HA-appen og serveren må kjøre for automatisk gjenoppretting.

Fjerning stopper enheten lokalt og synkroniserer frakoblingen med serveren. Ved nettverksbrudd vises fjerningen som ventende og forsøkes igjen. Målehistorikken beholdes. Gjenoppretting av pågående styring må lykkes før fjerning. Serveren setter registrerte assets inaktive i NODES; dette kansellerer ikke inngåtte handler automatisk.

Serveren må oppdateres før HA-appen til denne versjonen.

---

# SMARTi Flex Home Assistant App

Outbound HTTPS pairing, local device selection, power metering and a communication test. Version 0.5.0 also provides a guarded physical switch pilot, disabled by default. This is a Supervisor App, not a custom integration.

The app never contacts NODES and contains no market credentials. Cloud connectivity requires a reachable HTTPS SMARTi backend; a developer laptop's loopback address is not reachable from another Home Assistant host.

The installable App repository is [Prosono/SMARTiFLEX](https://github.com/Prosono/SMARTiFLEX), with a local checkout at `/Users/vetle.nikolai.prebensen.norman/Documents/GitHub/SMARTiFLEX`. Add its GitHub URL to the Home Assistant App store, install SMARTi Flex and open the Web UI. Supervisor builds the App from its Dockerfile; no prebuilt image is published. Pair with the ten-minute code created in the SMARTi portal. No customer YAML editing is required.

This workspace retains the platform development copy. Release changes must be synchronized into the GitHub checkout's `smartiflex/` directory and the App version incremented before pushing updates. The initial 0.1.0 release was pushed on 2026-09-19.

Select a supported entity and a dedicated W/kW sensor. Only selected power readings leave the App; local entity IDs remain in `/data/state.json`. The UI is accessible exclusively through Supervisor Ingress (172.30.32.2); do not enable host networking or expose its port.

Official references: [App communication](https://developers.home-assistant.io/docs/apps/communication/), [Ingress](https://developers.home-assistant.io/docs/apps/presentation/). Docker and real Supervisor installation still require validation; unit tests exercise local policy and bridge logic.

## Reporting mode (0.4.0)

Under Rediger, choose “Bare når verdien endres” only for sensors whose HA state remains valid until a change. Default remains periodic reporting. The app polls HA every 15 seconds and sends a separate `checked_at` with the original `observed_at`; unavailable/unknown, invalid units/values or failed HA reads stop sending. The portal expires the checked status after 45 seconds without a successful reading. Held values are display-only and never qualify as available market capacity. HA availability is not proof of physical device connectivity. No history is backfilled before the setting was enabled. Requires backend migration b27c419a8801 and the matching portal.

## 0.4.1
Change-reporting is now the default for new devices and existing bindings without a reporting mode. Explicit periodic selections are retained. The portal counts recently checked held states as active and shows their bars, without treating them as verified market capacity.

## 0.5.0 — guarded switch pilot

Existing and new devices retain physical control **off**. The customer must select **Tillat av/på-test** on each switch in this local UI, keep sharing enabled, and grant current consent in the SMARTi portal. The backend must separately be started with `SMARTIFLEX_CONTROL_ENABLED=true`. Do not enable this flag for an unattended deployment. Test the installed App on noncritical equipment before operational use. Thermostats and number entities still support metering and communication tests only.

A physical `REDUCE_LOAD` command is accepted only for an opted-in `switch` that a fresh HA API read confirms is on. The command must be within both local and server duration limits and have current consent. The bridge requests another heartbeat after fetching commands to obtain the new server lease. The heartbeat advertises abstract opted-in device IDs and version 0.5.0; local entity IDs never leave HA. An active switch being off does not withdraw its own lease. Different switches can be controlled concurrently; duplicate commands for a switch are blocked.

Before `switch.turn_off`, a restoration intent is atomically saved and fsynced to `/data/control.json`. An independent watchdog checks every two seconds, outside the telemetry/network lock. It attempts `switch.turn_on` at expiry, on permission loss, a failed/expired cloud lease, local stop/pause, disconnect, edit, and restart. Every return to on must be confirmed by a fresh HA API read. `EXECUTED` reports that HA confirmed off; it does **not** prove delivered power or earn a payment. `RESTORED` reports that HA confirmed on.

Restoration intent survives unpairing, editing, and process restart. Failed/ambiguous turn-off calls are never retried: the journal drives restoration instead. Newer off-state timestamps or HA contexts are treated as possible manual/automation overrides and are not overwritten. The UI then asks the customer to turn the switch on manually. A restore failure blocks further physical commands until HA confirms on. After an ambiguous timeout, a context with a user ID can also require manual recovery because ownership cannot be established safely.

The watchdog runs only while the App and HA are running. A stopped host, unavailable switch or process crash cannot be guaranteed to restore on schedule; startup retries restoration. Use only equipment safe to interrupt, with its own protection where needed. This pilot is not a hardware safety controller.

Result transitions are durably queued and retried until the server acknowledges them. They are scoped to the original installation, so unpairing cannot send an old result under a newly paired account. If the original credential is revoked or removed before acknowledgement, the retained journal remains available locally but the operator must reconcile the old server lease. Never delete `control.json` to dismiss a restore fault.

The local UI's Stop and Pause actions request restoration promptly even during a slow cloud synchronization. Editing revokes local physical permission; it must be explicitly granted again after synchronization. The existing communication test remains non-actuating and independent of physical opt-in.

Validation uses fake HA state/service adapters and an in-process App → SMARTi API round trip, including cancellation, expired leases, retry, restart, pause, manual override and restore failure. No actual household switches were operated during development. A real Supervisor installation still needs validation before enabling the pilot.

Service integration follows [Home Assistant's REST API](https://developers.home-assistant.io/docs/api/rest/) and its service-call returned states. The App remains a single-process service; do not start multiple workers sharing its local journal.
