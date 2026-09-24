# ⛳ Golflager

Et enkelt dashbord for kjøp og videresalg av brukt golfutstyr fra Finn.no. Appen kjører på Macen din, og alle dataene ligger i én fil på maskinen.

Dette får du:

- **Oversikt:** fortjeneste, omsetning, penger bundet i lager, budsjettvarsel og grafer.
- **Nye funn:** nye annonser fra Finn-søkene dine. Hver annonse er merket grønn (kjøp), gul (kanskje) eller rød (la være).
- **Lager:** alt du vurderer, har kjøpt og har solgt.
- **Prissjekk:** sjekk om en annonse lønner seg.
- **Markedspriser:** hva ting pleier å koste på Finn.
- **Finn-søk:** her legger du inn søkene scraperen skal følge med på.

---

## Slik starter du

### Første gang

1. **Last ned appen.** På GitHub-siden til prosjektet trykker du den grønne knappen **Code** og velger **Download ZIP**. Åpne ZIP-filen (dobbeltklikk), og flytt mappen dit du vil ha den, for eksempel til **Dokumenter**.
2. **Åpne Terminal.** Trykk `Cmd + mellomrom`, skriv `Terminal` og trykk Enter.
3. **Start appen.** Skriv `bash ` (med mellomrom etter), dra filen **start.sh** fra mappen inn i Terminal-vinduet, og trykk Enter.
4. Hvis Macen spør om å installere **utviklerverktøy** («command line developer tools»), trykk **Installer** og vent til det er ferdig. Gjør så steg 3 én gang til.
5. Første oppstart tar et minutt eller to. Så åpner appen seg i nettleseren på **http://localhost:8000**.

### Senere

Gjør steg 2 og 3 igjen. Da starter appen på noen sekunder.

Du kan også dobbeltklikke **Start.command** i mappen. Første gang må du høyreklikke den og velge **Åpne**, fordi Macen ikke kjenner filen fra før.

### Stoppe

Trykk `Ctrl + C` i Terminal-vinduet, eller lukk vinduet. Terminal-vinduet må stå åpent så lenge du bruker appen.

---

## Kom i gang

1. **Legg inn et Finn-søk.** Gjør et søk på finn.no, for eksempel på «Scotty Cameron» med makspris 3000 kr. Kopier adressen fra adressefeltet i nettleseren, gå til **Finn-søk** i appen og lim den inn.
2. **Vent litt.** Scraperen sjekker det nye søket med én gang, og etter det hvert 30. minutt. Nye annonser dukker opp under **Nye funn**.
3. **Ta stilling.** Trykk **Kjøpt** for å flytte en annonse rett inn i lageret, eller **Skjul** hvis den ikke er interessant. Har appen gjettet feil merke, modell eller type, trykker du **Rett**.
4. **Hold lageret oppdatert.** Registrer ekstra kostnader (grep, frakt, rengjøring), og sett status til **Solgt** med salgspris når tingen er solgt. Da blir tallene på forsiden riktige, og prissjekken lærer av dine egne salg.
5. **Sjekk innstillingene.** Sett budsjettet ditt og regelen for når noe er verdt å kjøpe.

---

## Slik fungerer prissjekken

1. Først sammenligner den med **dine egne salg** av samme merke, modell og type.
2. Har du ikke solgt noe lignende, bruker den **markedsprisene**, altså det selgere ber om på Finn. Ting selges ofte under utlagt pris, så den regner med 90 % av typisk utlagt pris. Du kan endre prosenten.
3. Prisen justeres litt for tilstand, standard 5 % per nivå.
4. **Forventet fortjeneste** = forventet salgspris − kjøpspris − ekstra kostnader.
5. Standardregelen er at noe er verdt å kjøpe når fortjenesten er **minst 30 % eller minst 500 kr**. Du kan endre regelen i Innstillinger, også slik at begge kravene må være oppfylt.

Fargene betyr:

- 🟢 **Kjøp:** oppfyller regelen, og det finnes nok å sammenligne med.
- 🟡 **Kanskje:** oppfyller regelen, men med lite data. Eller: gir litt fortjeneste, men under kravet ditt.
- 🔴 **La være:** tap eller for lav fortjeneste.

Prissjekken viser også **den høyeste prisen du kan betale** og fortsatt oppfylle regelen. Den er nyttig når du forhandler.

---

## Om scraperen

Scraperen følger disse reglene:

- Den **logger aldri inn** på noen Finn-konto, og sender ingen informasjonskapsler.
- Den **henter bare søkeresultatsidene**, aldri hver enkelt annonse.
- Den sjekker **sjelden**: standard er hvert 30. minutt, og minst hvert 15. minutt. Den venter 5–9 sekunder mellom hver side.
- Hvis Finn **blokkerer** den, viser en robot-sjekk eller svarer med en feilkode, **stopper den** og viser en rød melding i appen. Den prøver aldri å komme rundt en blokkering. Du slår den på igjen selv.
- Hvis Macen mister internett, prøver den igjen ved neste sjekk. Etter tre mislykkede forsøk på rad stopper den.
- Den går bare mens appen er åpen.

Du slår scraperen av og på under **Finn-søk**.

> **Merk:** Finns brukervilkår begrenser automatisk innhenting av data. Scraperen er laget for å være skånsom og kun til eget bruk, men du er selv ansvarlig for hvordan du bruker den. Hvis Finn endrer nettsiden sin, kan scraperen slutte å virke. Da stopper den og sier fra i stedet for å lagre feil data.

---

## Oppdatere til en ny versjon

1. Stopp appen (`Ctrl + C` i Terminal).
2. Last ned ZIP-filen på nytt fra GitHub (**Code → Download ZIP**), og bytt ut den gamle mappen med den nye.
3. Start appen som vanlig. Første oppstart etter en oppdatering tar et minutt eller to.

Søkene, lageret og innstillingene dine ligger i `~/Golflager` og blir med over av seg selv.

---

## Hvor ligger dataene?

Alt lagres i filen `golflager.db` i mappen **Golflager** i hjemmemappen din (`~/Golflager/`). Fordi filen ligger utenfor app-mappen, beholder du dataene når du laster ned en ny versjon av appen.

Du tar sikkerhetskopi under **Innstillinger → Last ned sikkerhetskopi**. Legg den gjerne i iCloud eller på en minnepinne av og til.

---

## Hvis noe går galt

| Problem | Løsning |
|---|---|
| «Fant ikke Python på Macen» | Installer utviklerverktøyene når Macen spør, og kjør `bash start.sh` på nytt. |
| Appen åpner seg ikke i nettleseren | Se i Terminal-vinduet hvilken adresse den kjører på (for eksempel `http://localhost:8001` hvis 8000 var opptatt), og åpne den selv. |
| «Scraperen har stoppet» | Les meldingen. Er det en blokkering (403, 429 eller robot-sjekk), bør du vente noen timer og gjerne sette opp tiden mellom sjekkene før du slår den på igjen. Har Finn endret nettsiden, ligger en kopi av siden i `~/Golflager/feilsøking/`, slik at scraperen kan oppdateres. |
| Et søk gir «Ingen treff» | Åpne lenken under Finn-søk og se om søket faktisk har treff på Finn. |
| «Noe gikk galt på denne siden» | Resten av appen virker som regel. Feilen lagres i `~/Golflager/feilsøking/feillogg.txt`. Send den filen, så blir feilen fikset. |
| Feil merke, modell eller type på en annonse | Trykk **Rett** på annonsen under Nye funn. |

---

## For utviklere

- Python 3.9 eller nyere, Flask, SQLite, requests og BeautifulSoup. Ingen byggesteg.
- `golflager/finn_parser.py` leser søkesidene. Den forstår dataene Finn bygger inn i siden (turbo-stream, JSON), og faller tilbake til HTML-kortene.
- `golflager/scraper.py` inneholder bakgrunnsjobben og reglene for blokkering og stopp.
- `golflager/pricing.py` er prissjekken. `golflager/stats.py` regner ut tallene til forsiden.

Slik kjører du testene:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```
