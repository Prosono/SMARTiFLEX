# SMARTi Flex – brukerveiledning

Åpne appen gjennom **Åpne webgrensesnitt** i Home Assistant. Appen har ingen eksternt
eksponert webport og krever ikke YAML-konfigurasjon.

## Server og engangskode

Angi SMARTi-backendens grunnadresse, for eksempel `https://flex.example.no`, uten
`/api` eller andre stier. Adressen må være tilgjengelig fra Home Assistant og ha et
gyldig HTTPS-sertifikat. Bruk en ny kode fra portalens **Tilkobling**; koder utløper
etter ti minutter og kan bare brukes én gang.

Det finnes ingen innebygd offentlig SMARTi-server i denne utviklingsversjonen.
Backend må settes opp separat før sammenkobling kan testes.

## Enheter og målinger

Trykk **Hent enheter fra Home Assistant** og velg en switch-, climate- eller number-enhet,
en dedikert effektsensor i W/kW, navn, estimert effekt og lokal maksimal varighet.
Målingene synkroniseres normalt hvert 15. sekund. Gamle eller ugyldige sensorverdier
blir ikke rapportert som ferske målinger.

Aktiver enheten separat i SMARTi-portalen. **Test kommunikasjon** kontrollerer
kommandoflyten uten fysisk styring. Resultatet skal bli **Kommunikasjon bekreftet**.

## Pause og frakobling

**Pause lokalt** stopper deling av nye målinger for enheten og avviser nye tester.
Portalens siste måling kan fortsatt vises frem til den blir foreldet.
**Koble fra lokalt** fjerner de lagrede koblingene. Trekk også tilbake tilgangen
i portalen for å ugyldiggjøre installasjonens servertilgang.

## Feilsøking

- **Ingen forbindelse:** Kontroller backendens HTTPS-adresse og nettverkstilgang.
  `localhost` og `127.0.0.1` viser til appens egen maskin, ikke utviklerens Mac.
- **Ugyldig kode:** Lag en ny kode i portalen. En allerede tilkoblet installasjon
  må kobles fra i portalen før den kan pares på nytt.
- **Ingen effekt:** Sensoren må ha numeriske verdier i W eller kW og ferske oppdateringer.
- **Test avvist:** Kontroller samtykke, lokal pause, varighetsgrenser og målingenes alder.
- **Installasjon eller oppstart feiler:** Se appens logg. Rapportér feilen i repositoryets
  Issues, men ikke legg ved tilkoblingskoder, token eller private måledata.

Denne utgaven støtter ikke fysisk aktivering, leveranseverifikasjon eller oppgjør.
