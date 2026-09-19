# Endringslogg

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
