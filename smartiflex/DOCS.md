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

Fysisk av/på-pilot for brytere er tilgjengelig fra 0.5.0, avslått som standard.
Appen utfører ikke leveranseverifikasjon eller oppgjør.

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

## Av/på-pilot for brytere (0.5.0)

Vanlig måling og kommunikasjonstest virker som før. Ingen fysisk styring blir automatisk
aktivert når du oppdaterer appen.

For en egnet bryter kan du velge **Tillat av/på-test** og bekrefte lokalt. Deling må være
aktiv, samtykke må være gitt i portalen, og SMARTi-operatøren må særskilt ha åpnet
pilotstyring på serveren. Termostater og tallstyringer har fortsatt bare målinger og
kommunikasjonstest. Velg bare utstyr som tåler å avbrytes og slås på igjen.

En fysisk test kontrollerer at bryteren er på før den slås av. Lokal og sentral tidsgrense
må overholdes. Appen lagrer en egen tilbakeføringsjournal før den slår av bryteren, og
kontrollerer deretter tilstanden i Home Assistant. **Stopp styring** ber om tilbakeføring.
Pause, redigering og frakobling opphever den lokale tillatelsen.

En lokal overvåker forsøker å slå på igjen når tiden er ute, når tillatelsen forsvinner,
eller når forbindelsen til SMARTi svikter. Den virker uavhengig av sending av måledata.
Tilbakeføringsjournalen beholdes også ved frakobling og omstart. Ikke slett den for å
fjerne en feilmelding. Appen må kjøre og nå bryteren for å kunne tilbakeføre; en avslått
eller havarert HA-maskin kan ikke garantere tidsfristen.

Hvis bryteren er endret manuelt eller av en annen automasjon etter testen, blir dette
ikke automatisk overstyrt. Ved uavklart tilbakeføring vises en feil, og ny fysisk styring
sperres. Kontroller bryteren i Home Assistant og slå den på manuelt når det er riktig.
Etter frakobling kan operatøren også måtte følge opp en gammel kommando som ikke fikk
levert siste kvittering.

«Utført» og «Tilbakeført» beskriver bryterens HA-tilstand. De beviser ikke levert
fleksibilitet og utløser ingen betaling. Oppdater SMARTi-backenden før appen brukes
(migrering h031e0a8b719). Fysisk pilotstyring krever separat validering på den installerte
Supervisor-appen før den åpnes på serveren.
