# Endringslogg

## 0.8.1

- Holder enheten avslått under en aktiv styringsperiode; manuell påslåing slås av igjen ved neste lokale kontroll (normalt hvert andre sekund).
- Beholder opprinnelig tilstand for tilbakeføring ved periodeslutt eller stopp av styring.
- En tilbakeføringsfeil på én enhet trekker ikke tilbake tillatelsen for andre enheter.
- Godtar asynkrone HA-oppdateringer mens termostaten bekrefter avslått tilstand.
- Krever at appen kjører og har kontakt med HA og gyldig styringstillatelse. Dette er programvarestyring, ikke en fysisk sperre.

## 0.5.0

- Lokal tillatelse for av/på-pilot per bryter. Fysisk styring er av som standard og krever separat åpning på SMARTi-serveren.
- Varig tilbakeføringsjournal før styring, lokal overvåker og tilbakeføring ved utløp, pause, frakobling eller omstart.
- Resultatkvitteringer lagres og sendes på nytt; doble kommandoer og nyere manuelle endringer håndteres.
- Synlig stoppknapp og oppfølging når tilbakeføring må kontrolleres.
- Målinger og kommunikasjonstester fungerer fortsatt uten fysisk tillatelse. Ingen markedsordre eller utbetaling opprettes av appen.
- Krever oppdatert SMARTi-backend (migrering h031e0a8b719). Test på egnet utstyr før fysisk pilotbruk; brytere uten kontakt kan ikke garanteres tilbakeført.

## 0.4.1

- Endringsrapportering er standard for nye enheter og eldre oppsett uten rapporteringsvalg.
- Eksplisitt valgt regelmessig rapportering beholdes.
- Oppdatert portal viser videreførte, nylig kontrollerte verdier som aktive med søyler.

## 0.4.0

- Ny innstilling per enhet: regelmessig rapportering eller bare ved verdiendring.
- Videreførte verdier beholder sensorens tidspunkt og får separat kontrolltid fra HA.
- Utilgjengelige sensorer stopper sending; portalstatus utløper etter 45 sekunder.
- Videreførte verdier brukes ikke som verifisert fleksibilitet.
- Krever oppdatert SMARTi-backend og portal (migrering b27c419a8801).

## 0.3.1

- Rettet hjelpetekst: kommunikasjonstest krever ikke måledata eller positivt effektanslag.
- Tilhørende rettelse i SMARTi-backend og portal er nødvendig.

## 0.3.0

- Rediger eksisterende enheter: navn, valgt enhet/effektsensor, effektanslag og lokal varighet.
- Endringer synkroniseres til backend med samme enhets-ID; kommunikasjonstest må aktiveres på nytt.
- Målinger fra siste døgn sendes med opprinnelig tidspunkt. Eldre enn 45 sekunder gir fortsatt ingen tilgjengelig fleksibilitet.
- Målestatus per enhet viser sensorverdi, tidspunkt, leveringsstatus og konkrete feil.
- Feil ved sending for én enhet stopper ikke resten.
- Krever oppdatert SMARTi-backend med endepunktet for enhetskonfigurasjon.

## 0.2.0

- Ny veiviser: velg enhet, bekreft måling og legg til.
- Søkbare enheter og effektmålinger med navnebaserte forslag som brukeren må bekrefte.
- Automatisk navn, tidsgrenser i minutter og justerbart effektanslag fra fersk måling.
- Eksplisitt samtykke før deling; ingen automatisk aktivering for styring.
- Allerede valgte enheter og målinger skjules fra valgene.
- Kompakt tilkoblingsstatus, tydelig lokal pause og responsivt oppsett uten brede nedtrekkslister.

## 0.1.1

- Forklarer hvorfor localhost og Home Assistant-/Nabu Casa-adresser ikke er SMARTi-backenden.
- Egne feilmeldinger for utløpt kode, utilgjengelig server og feil serversvar.
- Tydeligere veiledning om HTTPS-adressen i tilkoblingsskjemaet.

## 0.1.0

- Første utviklingsutgave som Home Assistant App.
- Utgående HTTPS-tilkobling med engangskode.
- Lokal enhetsbinding og effektsensorer i W/kW.
- Lokal pause, samtykkekontroll og varighetsgrenser.
- Persistente kvitteringer for kommunikasjonstester uten fysisk styring.
- SMARTi-logo og mørkt/oransje brukergrensesnitt.
