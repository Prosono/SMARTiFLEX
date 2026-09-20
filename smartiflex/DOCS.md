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
 kan målinger fortsatt deles. Kommunikasjonstesten krever bare aktivert testdeltakelse og forbindelse til Home Assistant, ikke måledata eller positivt effektanslag.

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

## Redigere en enhet

Velg **Rediger** ved enheten. Endre navn, effektanslag eller tidsgrense i bekreftelsen.
Bruk **Tilbake** for å endre effektsensor eller valgt enhet. Bekreft delingen og trykk
**Lagre endringer**. Historikk og enhets-ID beholdes. Når endringen er synkronisert,
må kommunikasjonstest aktiveres på nytt i portalen. Lokale pauser beholdes.

## Målestatus

Hver enhet viser om serveren har mottatt målingen, og hva Home Assistant rapporterer.
Målinger fra siste døgn sendes med sitt opprinnelige tidspunkt. Verdier eldre enn
45 sekunder teller ikke som tilgjengelig fleksibilitet. Ukjente/ugyldige verdier og
målinger eldre enn ett døgn sendes ikke; appen viser hvorfor. Den oppdaterer aldri
tidspunktet for å få en gammel sensorverdi til å se fersk ut.

## Sensorer som bare rapporterer endringer

Fra 0.4.0: Åpne enheten med **Rediger**, velg **Bare når verdien endres** under rapportering og lagre. Behold standardvalget for sensorer som rapporterer regelmessig. Eksisterende enheter endres ikke automatisk.

SMARTi viderefører en gyldig verdi mens appen kan lese sensoren i HA. Portalen viser separat tidspunkt for sensorrapporten og HA-kontrollen. Ved utilgjengelig sensor eller mistet forbindelse stopper nye datapunkter, og status utløper etter 45 sekunder. Tidligere hull i historikken fylles ikke ut. Videreførte verdier brukes ikke som verifisert markedskapasitet.

Fra 0.4.1 er endringsrapportering standard også for gamle oppsett uten lagret valg. Har enheten allerede «Regelmessig», velg «Bare når verdien endres» under Rediger dersom sensoren bare rapporterer endringer. En uendret verdi vises aktiv mens HA-kontrollen fortsetter, men regnes ikke som verifisert markedskapasitet.
