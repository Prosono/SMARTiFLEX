# Felles styringssamtykke – HA 0.9.0

Kunden velger enhet, effektsensor, tidsgrense og eksplisitt styringssamtykke i HA.
Avkrysningen er av som standard. Måledeling kan brukes uten styringssamtykke.
Eksisterende serverlagrede samtykker beholdes ved oppdatering.

Endringer sendes med forventet samtykkeversjon og unik forespørsels-ID.
Gjentakelse etter tapt svar er idempotent. En forsinket godkjenning kan ikke
overstyre en nyere portalendring; kunden må bekrefte et nytt ja ved konflikt.
Tilbaketrekking forsøkes igjen med fersk versjon dersom det er nødvendig.

Ved tilbaketrekking sperres lokal utførelse før nettverkskall. Sperren og køen
lagres på disk. Pågående styring tilbakeføres gjennom eksisterende journal og
retry-løp. Serveren stopper ventende kommandoer og ber utførte kommandoer om
 tilbakeføring. Ved nettbrudd gjelder lokal sperre straks, mens UI viser at
serversynkronisering venter. Normal synkronisering går hvert 15. sekund.

Begge apper bruker samme serverberegnede status. Grønt krever samtykke, fersk
kontakt, støttet styring, ferske målinger og lokal/servermessig styringsklarhet.
Rødt angir manglende samtykke, suspensjon eller utilgjengelig enhet/HA. Oransje
angir venting, sperrer eller styringsfeil. HA overstyrer gammel serverstatus ved
frakobling eller lokalt usynkronisert samtykke. Tekst forklarer alltid fargen.
Grønn statusring animeres med respekt for redusert bevegelse.

Ingen ekstra portalaktivering er nødvendig for samtykke gitt i HA. NODES-
godkjenning, porteføljemedlemskap, gyldig handel og effekt-/tidsgrenser er fortsatt
markedsvilkår. Når installert effekt er ukjent, brukes kundens oppgitte
fleksibilitetsgrense som styringsgrense. Kjent installert effekt begrenser fortsatt;
vi oppretter ikke en fiktiv verdi for fysisk installert effekt.

Tester dekker samtykke begge veier, idempotens, konflikter, varig offline-
tilbaketrekking og tilbakeføring av utført kommando. Visuell HA-kontroll er gjort
med fiktive enheter. Fysisk ende-til-ende-verifisering krever oppdatert HA-app og
en separat autorisert aktivering.


Se README for installasjon og tilkobling.
