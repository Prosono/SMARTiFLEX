# SMARTi Flex for Home Assistant

Home Assistant App for tilkobling til SMARTi Flex, valg av enheter og deling av effektmålinger.

![SMARTi](smartiflex/logo.png)

## Installer

Legg til dette repositoryet i Home Assistants appbutikk:

```text
https://github.com/Prosono/SMARTiFLEX
```

[Åpne repositoryet i Home Assistant](https://my.home-assistant.io/redirect/supervisor_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FProsono%2FSMARTiFLEX)

Finn **SMARTi Flex**, velg **Installer**, deretter **Start** og **Åpne webgrensesnitt**.
Appen bygges fra kildekoden på din Home Assistant-maskin. Støtter amd64 og aarch64.
Home Assistant OS med Supervisor kreves; appen installeres ikke gjennom HACS.

## Koble til

1. Skaff en tilgjengelig HTTPS-adresse til SMARTi Flex-backenden.
2. Opprett et anlegg og en engangskode under **Tilkobling** i SMARTi-portalen.
3. Angi serveradressen og koden i appens webgrensesnitt. Koden gjelder i ti minutter.
4. Velg en enhet og en tilhørende effektsensor i W eller kW.
5. Aktiver enheten for test i portalen og velg **Test kommunikasjon**.

En vellykket test vises som **Kommunikasjon bekreftet**. Du kan pause delingen lokalt
eller trekke tilbake installasjonens tilgang fra portalen.

## Status: utviklingsversjon 0.3.0

- Målinger, lokal pause, samtykkekontroll og kommunikasjonstester er implementert.
- **Ingen fysisk styring eller markedshandel.** Tester slår ikke utstyret av eller på.
- Appen er ennå ikke verifisert på en faktisk Supervisor-installasjon.
- Backend og portal driftes separat og er ikke inkludert i dette app-repositoryet.
- En backend som bare kjører på en annen maskins `127.0.0.1`, er ikke tilgjengelig for appen.
- Appen kommuniserer utgående over HTTPS; webgrensesnittet åpnes via Supervisor Ingress.
- Home Assistant entity-ID-er og Supervisor-token beholdes lokalt. NODES-nøkler skal aldri legges i appen.

Se [brukerveiledningen](smartiflex/DOCS.md) for feilsøking.
