# ⛳ Golflager

Et enkelt dashbord for kjøp og videresalg av brukt golfutstyr fra Finn.no. Appen kjører på Macen din, og alle dataene ligger i én fil på maskinen.

Dette får du:

- **Oversikt:** fortjeneste, omsetning, penger bundet i lager, budsjettvarsel og grafer.
- **Nye funn:** nye annonser fra Finn-søkene dine. Hver annonse er merket grønn (kjøp), gul (kanskje) eller rød (la være).
- **Lager:** alt du vurderer, har kjøpt og har solgt.
- **Prissjekk:** sjekk om en annonse lønner seg.
- **Markedspriser:** hva ting pleier å koste på Finn.

På **Nye funn**, **Lager** og **Markedspriser** kan du bla etter **type** (putter, driver, jernsett …) og **merke**. Hver knapp viser hvor mange det er, og valgene kan kombineres, for eksempel «Putter» + «Scotty Cameron». Med **Sorter** kan du ordne listene etter for eksempel pris, fortjeneste eller alder.

### Solgte annonser

Golflager oppdager når annonser er solgt, uten å åpne enkeltannonser:

- Viser Finn «Solgt» på en annonse i søkeresultatene, merkes den med én gang.
- Hver 6. time blar scraperen gjennom alle sidene i hvert søk (maks 5 sider). Annonser som ikke lenger er med, merkes «Trolig solgt». Det kan også bety at selgeren har tatt den bort eller satt opp prisen over maksprisen i søket.
- Solgte annonser flyttes fra Nye funn til fanen **Solgt / borte**, der du ser hvor lenge de lå ute.
- Søk med mer enn 5 sider kan ikke sjekkes. Gjør dem smalere, for eksempel med makspris.
- Ser det ut som over halvparten av annonsene i et søk forsvant på én gang, merkes ingenting. Da er det trolig noe rart med svaret fra Finn.
- Du kan endre hvor ofte, eller slå det av, under **Innstillinger → Scraper**.

### Rydding

- **Skjul alle** i Nye funn skjuler alle annonsene som vises. Filtrer for eksempel på «La være» først.
- Under **Skjulte** kan du slette annonser én og én, eller alle som vises.
- Golflager rydder også selv: nye funn eldre enn 30 dager skjules, og skjulte annonser eldre enn 60 dager slettes. Du kan endre dette, eller slå det av, under **Innstillinger → Rydding i Nye funn**.
- Slettede annonser vises ikke lenger, men prisene brukes fortsatt i markedsprisene. De dukker heller ikke opp igjen som nye når scraperen ser dem på Finn.
- **Finn-søk:** her legger du inn søkene scraperen skal følge med på.

---

## Slik starter du

### Første gang

1. **Last ned appen.** På GitHub-siden til prosjektet trykker du den grønne knappen **Code** og velger **Download ZIP**. Åpne ZIP-filen (dobbeltklikk), og flytt mappen dit du vil ha den, for eksempel til **Dokumenter**.
2. **Åpne Terminal.** Trykk `Cmd + mellomrom`, skriv `Terminal` og trykk Enter.
3. **Start appen.** Skriv `bash ` (med mellomrom etter), dra filen **start.sh** fra mappen inn i Terminal-vinduet, og trykk Enter.
4. Hvis Macen spør om å installere **utviklerverktøy** («command line developer tools»), trykk **Installer** og vent til det er ferdig. Gjør så steg 3 én gang til.
5. Første oppstart tar et minutt eller to. Golflager installeres i mappen **Golflager** i hjemmemappen din (`~/Golflager/program`), appen åpner seg i nettleseren, og **Golflager-ikonet** (et gult flagg på grønn bakgrunn) legges i Dock.
6. Mappen du lastet ned, trengs ikke lenger. Du kan slette den.

### Senere: klikk på ikonet

Klikk på **Golflager-ikonet i Dock**. Appen starter i bakgrunnen og åpner seg i nettleseren. Du trenger ikke Terminal lenger.

- Ikonet ligger også i **Programmer**. Du finner det med `Cmd + mellomrom` ved å skrive **Golflager**.
- Kjører Golflager allerede, åpner ikonet bare nettleseren.

### Stoppe

Golflager kjører i bakgrunnen og sjekker Finn til du slår av Macen. Vil du stoppe den før det, gå til **Innstillinger** og trykk **Slå av Golflager**.

Har du startet med `bash start.sh` i Terminal, kan du også trykke `Ctrl + C` der.

### Hvorfor ligger programmet i ~/Golflager?

Macen sperrer mappene Dokumenter, Skrivebord og Nedlastinger for programmer som ikke har fått tillatelse. Derfor installeres Golflager i `~/Golflager/program`, der ikonet alltid får starte appen. Dataene dine ligger i samme mappe.

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
3. Prisen justeres for tilstand. Standard er at «Slitt» er verdt 60 % og «Brukbar» 80 % av samme ting i «God» stand, mens «Meget god» er verdt 105 % og «Som ny» 115 %. Verdiene kan endres i Innstillinger.
4. **Forventet fortjeneste** = forventet salgspris − kjøpspris − ekstra kostnader.
5. Standardregelen er at noe er verdt å kjøpe når fortjenesten er **minst 30 % eller minst 500 kr**. Du kan endre regelen i Innstillinger, også slik at begge kravene må være oppfylt.

### Tilstanden på annonser fra Finn

Scraperen leser bare søkeresultatlisten, ikke hver annonse. Den ser derfor ikke beskrivelsen og bare ett bilde. Slik håndteres tilstanden:

- Ord i **tittelen** som «oppripet», «slitt», «riper», «defekt», «pent brukt» og «som ny» brukes til å anslå tilstanden automatisk.
- Står det ingenting om tilstanden i tittelen, er den **ukjent**, og kortet sier fra om at du bør se på bildene.
- Er annonsen **mye billigere enn vanlig** (under halvparten) og tilstanden er ukjent, blir den gul med «Sjekk tilstand». Det er ofte et tegn på skader.
- Har du sett bildene, kan du sette tilstanden selv under **Rett**. Da regnes prissjekken ut på nytt.

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

Golflager ser selv etter nye versjoner et par ganger om dagen. Når det finnes en, dukker det opp en grønn melding med knappen **Oppdater nå**. Trykk på den, så gjør appen resten:

1. Laster ned den nye versjonen fra GitHub.
2. Prøvekjører den på en kopi av dataene dine. Hvis noe er galt, stopper den og endrer ingenting.
3. Tar vare på den gamle versjonen i `~/Golflager/forrige-versjon`, bytter til den nye og starter på nytt.

Du kan også se etter oppdatering selv under **Innstillinger → Oppdatering**.

Søkene, lageret og innstillingene dine ligger i `~/Golflager` og blir med over av seg selv.

Oppdateringsknappen krever at GitHub-prosjektet er offentlig. Virker den ikke, kan du alltid oppdatere for hånd: last ned ZIP-filen på nytt, bytt ut mappen og kjør `bash start.sh` én gang (se «Første gang»).

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
