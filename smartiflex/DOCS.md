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

Trykk **Legg til enhet** og følg tre steg:

1. **Enhet:** Søk på navnet og velg en bryter, termostat eller tallstyring fra Home Assistant.
2. **Måling:** Velg effektmålingen for denne enheten. Mulige matcher foreslås ut fra navn,
   men du må selv bekrefte at målingen tilhører enheten. Ikke velg totalmåleren for boligen.
3. **Bekreft:** Navnet fylles inn automatisk. Velg lokal testgrense i minutter og bekreft
   at du vil dele effektmålingene med SMARTi.

Under **Tilpass effektgrensen** kan du endre anslaget. Det forhåndsutfylles fra en positiv,
 fersk effektmåling når den finnes, ellers 0. Dette er ikke en verifisert kapasitet. Ved 0
 kan målinger deles, men kommunikasjonstest krever at et positivt anslag er konfigurert.

Enheter og målinger som allerede er lagt til, vises ikke som nye valg.
Synkronisering skjer normalt hvert 15. sekund. **Kommunikasjonstest** aktiveres separat
 i portalen og gir ingen fysisk styring.

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
