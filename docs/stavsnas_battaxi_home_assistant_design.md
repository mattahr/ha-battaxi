# Stavsnäs Båttaxi – Home Assistant-integration

**Designförslag / implementation plan**  
**Version:** 0.1  
**Datum:** 2026-09-12  
**Status:** Förslag för MVP

---

## 1. Syfte

Skapa en read-only Home Assistant-integration för **Stavsnäs Båttaxi** som hämtar reguljära avgångar från bolagets webb-API och exponerar dem som Home Assistant-entiteter.

Integrationen ska vara generell och inte hårdkodas för Telegrafholmen.

Användaren ska i Home Assistants vanliga **config flow** kunna välja en sträcka, exempelvis:

> **Sandhamnslinjen – Stavsnäs Vinterhamn → Telegrafholmen**

När sträckan har lagts till skapas ett Home Assistant-device som innehåller sensorer för kommande avgång, ankomst, lediga platser m.m.

MVP:n innehåller **ingen bokning**.

---

## 2. Målbild

### Användarupplevelse

1. Användaren installerar integrationen.
2. Väljer **Lägg till integration → Stavsnäs Båttaxi**.
3. Integrationen hämtar linjer och bryggor från Båttaxis API.
4. Config flow visar en lista med valbara sträckor.
5. Användaren väljer exempelvis:

```text
Sandhamnslinjen – Stavsnäs Vinterhamn → Telegrafholmen
```

6. Ett device skapas:

```text
Stavsnäs Vinterhamn → Telegrafholmen
```

7. Devicet innehåller ett antal entiteter, exempelvis:

```text
Nästa avgång           2026-09-12 17:30
Nästa ankomst          2026-09-12 18:05
Lediga platser         42
Bokningsbar            Ja
Avgångar idag          3
```

Användaren ska inte behöva:

- skriva in bryggnamn,
- känna till interna pier-ID:n,
- ange API-nyckel,
- skriva YAML,
- känna till vilken API-endpoint som används.

---

# 3. Avgränsning

## Ingår i MVP

- Dynamisk hämtning av linjer och bryggor från API.
- UI-baserad konfiguration.
- Val av en sträcka mellan två bryggor.
- Automatisk hämtning av avgångar.
- Home Assistant-device per konfigurerad sträcka.
- Sensorer för nästa avgång och relaterad information.
- Felhantering och cache.
- HACS-kompatibel struktur.
- Svenska och engelska UI-strängar.
- Tester för API-parsning, config flow och sensorer.

## Ingår inte i MVP

- Bokning.
- Betalning.
- Hantering av befintliga bokningar.
- Inloggning.
- Waxholmsbolaget eller andra operatörer.
- Slutsats om att en tur är inställd om den försvinner ur API:t.
- Push-notifieringar från Båttaxi.
- Egna dashboards/cards.

---

# 4. API som identifierats

Bas-URL:

```text
https://api.battaxi.se
```

API:t saknar, såvitt vi vet, publik dokumentation. Integrationen måste därför behandla schemat som ett externt och potentiellt föränderligt API.

## 4.1 Bryggor

```http
GET /api/public/piers
```

Exempel:

```text
https://api.battaxi.se/api/public/piers
```

Användning:

- brygg-ID,
- bryggnamn,
- eventuella metadata om bryggan,
- uppslag mellan API-ID och användarvänligt namn.

Bryggorna ska **inte hårdkodas** i integrationen.

---

## 4.2 Linjer

```http
GET /api/public/lines
```

Exempel:

```text
https://api.battaxi.se/api/public/lines
```

Båttaxi publicerar bland annat reguljärtrafik under namn som:

- Sandhamnslinjen
- Nämdölinjen
- Runmarölinjen
- Bullerölinjen

`/lines` ska vara primär källa för vilka linjer och relationer som finns.

Integrationen ska inte anta att dagens linjenamn eller stopp finns kvar för alltid.

---

## 4.3 Avgångssökning

Identifierad endpoint:

```http
GET /api/search
```

Parametrar:

```text
origin=<pier-id>
dest=<pier-id>
date=YYYY-MM-DD
```

Verifierat exempel från 2026-09-12:

```text
https://api.battaxi.se/api/search?origin=6a31a5470bdad9fa1552c809&dest=6a31a5470bdad9fa1552c80a&date=2026-09-12
```

Detta är den centrala endpointen för integrationen.

Observerade uppgifter i resultatet inkluderar bland annat data motsvarande:

```json
{
  "departureId": "...",
  "lineId": "...",
  "lineName": "Sandhamnslinjen",
  "departureTime": "17:10",
  "arrivalTime": "17:15",
  "durationMinutes": 5,
  "availableSeats": 59,
  "bookable": true,
  "boardStopIndex": 1,
  "alightStopIndex": 2
}
```

Det exakta JSON-schemat ska fångas i test-fixtures innan implementationen betraktas som stabil.

### Viktig semantik

`bookable = false` får **inte** tolkas som att turen är inställd.

En tur kan exempelvis vara:

- passerad,
- fullbokad,
- för nära avgång för bokning,
- på annat sätt inte längre bokningsbar,

utan att vara inställd.

---

## 4.4 Availability

Identifierad endpoint:

```http
GET /api/public/availability
```

Exempel:

```text
https://api.battaxi.se/api/public/availability?origin=Sandhamn&dest=Telegrafholmen&from=2026-09-12&to=2026-09-30
```

Endpointen kan vara användbar för att hitta dagar med trafik längre fram.

### Beslut för MVP

**Använd inte `availability` som sanningskälla för avgångar eller trafikstatus ännu.**

Semantiken för exempelvis `state` är inte tillräckligt klarlagd. `/search` ska vara primär källa för konkreta avgångar.

`availability` kan tas in senare när dess betydelse är verifierad.

---

# 5. Domänmodell

API-modellen bör översättas till en liten intern modell så att resten av integrationen inte arbetar direkt med rå JSON.

```text
BattaxiPier
    id
    name

BattaxiLine
    id
    name
    stops[]

BattaxiRoute
    line_id
    origin
    destination

BattaxiDeparture
    id
    line_id
    line_name
    origin
    destination
    departure
    arrival
    duration_minutes
    available_seats
    bookable
```

Alla datum/tider konverteras så tidigt som möjligt till timezone-aware `datetime`.

För trafiken används normalt:

```text
Europe/Stockholm
```

men implementationen bör i första hand använda Home Assistants timezone-hantering och inte arbeta med naiva Python-datetime-objekt.

---

# 6. Vad betyder "linje" i config flow?

Ur användarens perspektiv är det intressanta egentligen inte bara linjenamnet utan en **riktad sträcka**.

Exempel:

```text
Sandhamnslinjen
```

är inte ett tillräckligt val.

Det användaren vill konfigurera är:

```text
Stavsnäs Vinterhamn → Telegrafholmen
```

Därför skiljer vi internt på:

```text
Line  = Sandhamnslinjen
Route = Stavsnäs Vinterhamn → Telegrafholmen
```

I UI kan vi ändå presentera båda:

```text
Sandhamnslinjen – Stavsnäs Vinterhamn → Telegrafholmen
```

Det minskar risken för tvetydighet om två linjer någon gång trafikerar samma bryggor.

---

# 7. Config flow

Integrationens domain föreslås vara:

```text
stavsnas_battaxi
```

Display name:

```text
Stavsnäs Båttaxi
```

## 7.1 Start

När config flow öppnas:

```text
Lägg till Stavsnäs Båttaxi

Hämtar linjer och bryggor...
```

Integrationen hämtar:

```text
GET /api/public/piers
GET /api/public/lines
```

Därefter skapas de val som användaren kan göra.

---

## 7.2 Val av sträcka

Föreslagen UI:

```text
Stavsnäs Båttaxi

Sträcka
┌─────────────────────────────────────────────────────────┐
│ Sandhamnslinjen – Stavsnäs Vinterhamn → Telegrafholmen ▼
└─────────────────────────────────────────────────────────┘

                                              [Skicka]
```

Alternativa exempel:

```text
Sandhamnslinjen – Stavsnäs Vinterhamn → Sandhamn
Sandhamnslinjen – Sandhamn → Telegrafholmen
Sandhamnslinjen – Telegrafholmen → Stavsnäs Vinterhamn
...
```

### Hur alternativen genereras

Om `/lines` innehåller en ordnad stopplista kan integrationen generera tillåtna riktade relationer.

Princip:

```text
Stavsnäs → Sandhamn → Telegrafholmen → ...
```

ger exempelvis:

```text
Stavsnäs → Sandhamn
Stavsnäs → Telegrafholmen
Sandhamn → Telegrafholmen
```

För motsatt riktning måste API-datan visa att den riktningen är giltig; integrationen ska inte automatiskt anta symmetrisk trafik.

### Validering

Innan config entry sparas gör integrationen ett testanrop mot `/search`.

Syftet är främst att verifiera:

- att API:t går att nå,
- att ID:n accepteras,
- att svaret går att parsa.

**Noll avgångar för dagens datum ska inte göra konfigurationen ogiltig.**

Det kan helt enkelt vara en dag utan trafik.

---

# 8. Config entry

MVP-förslaget är:

> **En config entry per sträcka.**

Exempel:

```text
Stavsnäs Vinterhamn → Telegrafholmen
```

Detta håller implementationen enkel och ger ett tydligt förhållande mellan config entry, coordinator och HA-device.

Föreslagen data:

```json
{
  "line_id": "...",
  "line_name": "Sandhamnslinjen",
  "origin_id": "...",
  "origin_name": "Stavsnäs Vinterhamn",
  "destination_id": "...",
  "destination_name": "Telegrafholmen"
}
```

### Unique ID

Exempel:

```text
<line_id>:<origin_id>:<destination_id>
```

Därmed går samma sträcka inte att lägga till dubbelt för samma linje.

Det är däremot möjligt att lägga till:

```text
Stavsnäs Vinterhamn → Telegrafholmen
Telegrafholmen → Stavsnäs Vinterhamn
```

som två separata entries.

### Senare möjlighet

En framtida version kan låta en config entry innehålla flera valda sträckor. Det är inte nödvändigt i MVP och gör reconfigure/device-lifecycle betydligt mer komplicerad.

---

# 9. Home Assistant-device

Varje konfigurerad sträcka representeras som ett device av typen **service**.

Exempel:

```text
Device:
  Stavsnäs Vinterhamn → Telegrafholmen

Manufacturer:
  Stavsnäs Båttaxi

Model:
  Sandhamnslinjen
```

Identifier:

```text
stavsnas_battaxi:<line_id>:<origin_id>:<destination_id>
```

Det följer Home Assistants modell där även externa tjänster kan representeras som devices.

---

# 10. Entiteter

Integrationen ska medvetet erbjuda två typer av sensorer:

1. **Maskinläsbara sensorer** för automationer, templates och annan HA-logik.
2. **Visningssensorer** med färdigformaterad text för dashboards och snabb överblick.

En textsammanfattning ska fortfarande implementeras som vanlig `SensorEntity` med ett strängvärde, inte som `TextEntity`. `TextEntity` används i Home Assistant för text som användaren kan ändra.

---

## 10.1 `sensor.next_departure`

**Primär maskinläsbar entitet.**

```text
Namn: Nästa avgång
Device class: timestamp
```

State:

```text
2026-09-12T17:10:00+02:00
```

Föreslagna attribut:

```yaml
line: Sandhamnslinjen
origin: Stavsnäs Vinterhamn
destination: Telegrafholmen
departure_id: ...
```

Sensorvärdet ska vara nästa avgång vars avgångstid ännu inte passerat.

---

## 10.2 `sensor.next_departure_text`

**Primär visningssensor.**

```text
Namn: Nästa avgång text
State type: string
```

Exempel:

```text
17:30 Stavsnäs Vinterhamn → 18:05 Telegrafholmen · 42 lediga
```

Om platsinformation saknas:

```text
17:30 Stavsnäs Vinterhamn → 18:05 Telegrafholmen
```

Om nästa avgång inte är bokningsbar kan texten valfritt markera detta:

```text
17:30 Stavsnäs Vinterhamn → 18:05 Telegrafholmen · ej bokningsbar
```

Målet är att denna sensor ska kunna läggas direkt på en dashboard utan att användaren behöver bygga en template.

Den ska inte vara primär källa för automationer. Där används de strukturerade sensorerna.

---

## 10.3 `sensor.next_arrival`

```text
Namn: Nästa ankomst
Device class: timestamp
```

State:

```text
2026-09-12T17:45:00+02:00
```

Entiteten avser samma avgång som `sensor.next_departure`.

---

## 10.4 `sensor.available_seats`

```text
Namn: Lediga platser
State: 42
```

Avser nästa avgång.

Om API:t inte lämnar platsinformation:

```text
unknown
```

inte `0`.

---

## 10.5 `binary_sensor.bookable`

```text
Namn: Bokningsbar
State: on/off
```

Avser nästa avgång.

Detta betyder endast att Båttaxis API anger turen som bokningsbar.

Det betyder **inte**:

```text
off = inställd
```

---

## 10.6 `sensor.departures_today`

```text
Namn: Avgångar idag
State: 3
```

State är antalet ännu ej passerade avgångar för den valda sträckan.

Sensorn får dessutom ett strukturerat attribut med dagens avgångar:

```yaml
departures:
  - departure: "15:10"
    arrival: "15:15"
    available_seats: 12
    bookable: false

  - departure: "17:10"
    arrival: "17:15"
    available_seats: 59
    bookable: true

  - departure: "19:40"
    arrival: "19:45"
    available_seats: 47
    bookable: true
```

Detta gör listan åtkomlig från templates:

```jinja2
{{ state_attr('sensor.departures_today', 'departures') }}
```

### Attributdesign

Attributlistan ska hållas kompakt och endast innehålla information som hör naturligt till dagens avgångar.

Vi ska undvika stora mängder duplicerad eller historisk data i `extra_state_attributes`, eftersom Recorder lagrar attribut tillsammans med state.

---

## 10.7 `sensor.departures_today_text`

**Visningssensor för alla kvarvarande avgångar idag.**

```text
Namn: Avgångar idag text
State type: string
```

Exempel:

```text
15:10 – 12 platser | 17:10 – 59 platser | 19:40 – 47 platser
```

Om platsinformation saknas för en avgång:

```text
15:10 | 17:10 – 59 platser | 19:40 – 47 platser
```

Om inga fler avgångar finns idag:

```text
Inga fler avgångar idag
```

Denna sensor är avsedd för dashboards och snabb presentation.

---

## 10.8 Sammanfattning av MVP-entiteter

| Entity | Typ | Primärt syfte |
|---|---|---|
| `sensor.next_departure` | timestamp | Automationer och logik |
| `sensor.next_departure_text` | string | Dashboard / läsbar sammanfattning |
| `sensor.next_arrival` | timestamp | Automationer och logik |
| `sensor.available_seats` | integer | Platstillgänglighet |
| `binary_sensor.bookable` | boolean | Bokningsstatus |
| `sensor.departures_today` | integer + attribut | Antal + strukturerad lista |
| `sensor.departures_today_text` | string | Dashboard / dagens avgångar |

Designprincipen är:

> Samma data får gärna exponeras både strukturerat och presenterat, så länge den strukturerade sensorn är sanningskällan och textsensorn endast är en bekvämlighetsrepresentation.

---

# 11. Entiteter som inte bör finnas i MVP

## "Inställd"

Skapa inte:

```text
binary_sensor.cancelled
```

förrän API:t har ett uttryckligt och verifierat sätt att ange inställd tur.

Att en avgång försvinner mellan två polls är inte tillräckligt för att säkert kalla den inställd.

## "Försenad"

Skapa inte:

```text
sensor.delay
```

förrän API:t faktiskt levererar realtid eller avvikelse från planerad avgång.

## "Tid kvar"

Skapa inte initialt:

```text
sensor.minutes_until_departure
```

Det skulle kräva lokala state-uppdateringar varje minut trots att API-informationen är oförändrad.

HA-användaren kan enkelt beräkna detta från timestamp-sensorn.

---

# 12. Calendar-entitet

En calendar-entitet är attraktiv eftersom avgångar naturligt är tidsbundna events.

Exempel:

```text
calendar.stavsnas_vinterhamn_telegrafholmen
```

Events:

```text
17:10 Stavsnäs Vinterhamn → Telegrafholmen
19:40 Stavsnäs Vinterhamn → Telegrafholmen
```

### Rekommendation

Lägg calendar-plattformen i **fas 2**, efter att sensor-MVP:n fungerar.

Skälet är att calendar kräver att integrationen på ett bra sätt kan hämta ett godtyckligt tidsintervall. `/search` är hittills identifierad som datum-baserad och kan därför innebära flera API-anrop.

---

# 13. Datahämtning

## 13.1 Referensdata

Följande förändras sällan:

```text
/piers
/lines
```

De behöver inte hämtas vid varje sensoruppdatering.

För MVP:

- hämta i config flow,
- hämta igen vid reconfigure,
- eventuellt cacha i config entry/runtime.

Vi ska undvika onödig belastning på ett odokumenterat tredjeparts-API.

---

## 13.2 Avgångsdata

`/search` är den dynamiska datakällan.

Förslag på initial polling:

```text
5 minuter
```

Det bör betraktas som preliminärt tills API:ts beteende och eventuella rate limits är bättre kända.

### Normal uppdatering

Coordinator frågar först efter dagens avgångar:

```http
GET /api/search?origin=...&dest=...&date=2026-09-12
```

Alla avgångar som redan passerat filtreras bort lokalt.

---

## 13.3 När dagens sista tur har gått

Vi behöver fortfarande kunna visa nästa avgång.

MVP:

1. Sök idag.
2. Om ingen framtida avgång finns: sök nästa dag.
3. Om även nästa dag saknar avgång: sök vidare stegvis, men använd cache och ett maximalt sökfönster.

Föreslaget maximalt fönster:

```text
14 dagar
```

Viktigt: vi ska **inte göra 14 API-anrop var femte minut**.

### Cachemodell

Resultat per datum cachas:

```text
2026-09-12 -> TTL kort
2026-09-13 -> TTL längre
2026-09-14 -> TTL längre
...
```

Exempelstrategi:

- idag: 5 min
- framtida datum: 6 timmar
- tomma framtida datum: 6 timmar

När vi hittat nästa aktiva trafikdag behöver efterföljande polling normalt endast uppdatera dagens data och den cachade nästa trafikdagen vid behov.

När `availability` är bättre förstådd kan den sannolikt ersätta den stegvisa sökningen.

---

# 14. Coordinator

Använd Home Assistants:

```python
DataUpdateCoordinator
```

Föreslagen struktur:

```text
custom_components/stavsnas_battaxi/
├── __init__.py
├── api.py
├── config_flow.py
├── const.py
├── coordinator.py
├── entity.py
├── models.py
├── sensor.py
├── binary_sensor.py
├── manifest.json
├── strings.json
└── translations/
    └── sv.json
```

`coordinator.py` ansvarar för:

- sökning av avgångar,
- datumcache,
- val av nästa avgång,
- normalisering av data,
- felhantering.

Sensorerna ska inte själva göra HTTP-anrop.

---

# 15. API-klient

`api.py` kapslar all kommunikation med `api.battaxi.se`.

Exempel på internt gränssnitt:

```python
class BattaxiApi:
    async def async_get_piers(self) -> list[BattaxiPier]: ...

    async def async_get_lines(self) -> list[BattaxiLine]: ...

    async def async_search(
        self,
        origin_id: str,
        destination_id: str,
        date: date,
    ) -> list[BattaxiDeparture]: ...
```

Använd Home Assistants gemensamma aiohttp-session:

```python
async_get_clientsession(hass)
```

Sätt explicita timeouts.

API-specifik JSON-parsning ska endast finnas i klient-/modellagret.

Det gör att en API-förändring inte behöver spridas till sensorimplementeringen.

---

# 16. Felhantering

## API otillgängligt

Vid timeout, HTTP-fel eller trasigt JSON:

- Coordinator kastar `UpdateFailed`.
- Home Assistant behåller tidigare state men markerar entiteter enligt Coordinator-modellen.
- Ingen exception-loop eller loggspam.

## Rate limiting

HTTP `429` ska hanteras som ett tillfälligt fel.

Ingen aggressiv retry-loop.

## Okänd API-version/schemaändring

Om obligatoriska fält saknas:

- logga ett tydligt fel,
- misslyckas kontrollerat,
- undvik `KeyError` som läcker ut genom integrationen.

## Tomt resultat

Tom lista från `/search` är ett legitimt resultat:

```text
inga avgångar denna dag
```

och inte ett API-fel.

---

# 17. Uppstart och återställning

Vid Home Assistant-start:

1. Config entry laddas.
2. API-klient skapas.
3. Coordinator gör första uppdatering.
4. Plattformarna forwardas:
   - `sensor`
   - `binary_sensor`
5. Device och entities skapas.

Om API:t är temporärt nere vid uppstart ska integrationen kunna återhämta sig vid senare coordinator-refresh utan omstart av Home Assistant.

---

# 18. Reconfigure

En modern HA-integration bör kunna ändras utan att först tas bort.

Reconfigure flow bör låta användaren välja en annan sträcka genom samma dynamiska API-lista.

MVP-alternativ:

```text
Inställningar
  → Konfigurera om
  → välj ny sträcka
```

Om unique ID förändras måste device/entity-lifecycle hanteras korrekt.

Det enklaste MVP-beteendet kan vara att låta varje route-entry vara fast och i första versionen hänvisa till "lägg till ny sträcka" för större förändringar, men designen bör inte blockera en senare riktig reconfigure flow.

---

# 19. Flera sträckor

En användare kan vilja ha:

```text
Stavsnäs Vinterhamn → Telegrafholmen
Telegrafholmen → Stavsnäs Vinterhamn
Sandhamn → Telegrafholmen
```

MVP-lösningen:

```text
en config entry per sträcka
```

Det ger tre devices.

Fördelar:

- enkel unique-ID-modell,
- enkel coordinator,
- enkel felsökning,
- sträckor kan tas bort individuellt,
- inga komplicerade multi-select-options.

---

# 20. Entity naming

Använd `_attr_has_entity_name = True`.

Device:

```text
Stavsnäs Vinterhamn → Telegrafholmen
```

Entities visas då exempelvis som:

```text
Stavsnäs Vinterhamn → Telegrafholmen Nästa avgång
Stavsnäs Vinterhamn → Telegrafholmen Nästa ankomst
Stavsnäs Vinterhamn → Telegrafholmen Lediga platser
Stavsnäs Vinterhamn → Telegrafholmen Bokningsbar
Stavsnäs Vinterhamn → Telegrafholmen Avgångar idag
```

Entity-ID:n genereras av Home Assistant och ska inte konstrueras manuellt utifrån svenska displaynamn.

---

# 21. Exempel på slutresultat i Home Assistant

```text
┌─────────────────────────────────────────────────────────┐
│ Stavsnäs Vinterhamn → Telegrafholmen                   │
│ Stavsnäs Båttaxi · Sandhamnslinjen                     │
├─────────────────────────────────────────────────────────┤
│ Nästa avgång                         17:10              │
│ Nästa avgång text                    17:10 Stavsnäs...  │
│ Nästa ankomst                        17:45              │
│ Lediga platser                       42                 │
│ Bokningsbar                          Ja                 │
│ Avgångar idag                        3                  │
│ Avgångar idag text                   17:10 · 19:40 ...  │
└─────────────────────────────────────────────────────────┘
```

En automation kan då exempelvis använda:

```yaml
trigger:
  - trigger: time
    at: sensor.stavsnas_vinterhamn_telegrafholmen_nasta_avgang
```

eller användaren kan bygga templates baserade på timestamp-sensorn.

---

# 22. Diagnostik

Integrationen bör stödja Home Assistants diagnostics.

Lämpligt innehåll:

```text
configured route
line id/name
origin id/name
destination id/name
last successful update
cached dates
number of departures parsed
API response metadata
```

Det finns i nuläget inga credentials att redigera bort, men rå API-data bör ändå inte dumpas obegränsat.

---

# 23. Loggning

Normal drift ska vara tyst.

`debug` kan exempelvis visa:

```text
Fetched 3 departures for 2026-09-12
Selected next departure at 17:10
Using cached result for 2026-09-13
```

`warning/error` reserveras för faktiska problem.

---

# 24. Teststrategi

## API-fixtures

Spara anonymiserade/representativa fixtures för:

```text
piers.json
lines.json
search_with_departures.json
search_empty.json
search_not_bookable.json
```

## Enhetstester

Testa minst:

1. Parsning av bryggor.
2. Parsning av linjer.
3. Generering av route-val.
4. Parsning av avgång.
5. Sortering av avgångar.
6. Filtrering av passerade avgångar.
7. Val av nästa avgång.
8. Övergång till nästa dag.
9. Dag utan trafik.
10. `bookable=false` behandlas inte som inställd.
11. Saknat `availableSeats` blir `unknown`.
12. HTTP-timeout.
13. HTTP 429.
14. HTTP 500.
15. Felaktig JSON.
16. API-schema med saknat obligatoriskt fält.
17. Europe/Stockholm och DST.

## Config flow

Testa:

- lyckad setup,
- API nere,
- tom linjelista,
- duplicate route,
- route utan avgång just idag,
- validering av dynamiska selections.

---

# 25. HACS / repository

Föreslaget repository:

```text
home-assistant-stavsnas-battaxi
```

Struktur:

```text
.github/
custom_components/
  stavsnas_battaxi/
tests/
README.md
LICENSE
hacs.json
pyproject.toml
```

Första målet bör vara en välskriven HACS custom integration.

Arkitekturen bör samtidigt ligga nära Home Assistants nuvarande integration standards så att en framtida submission till Home Assistant Core inte omöjliggörs.

---

# 26. Home Assistant-principer att följa

Designen bör följa nuvarande HA-rekommendationer:

- Config flow i UI.
- Config data i `ConfigEntry.data`.
- Common coordinator pattern.
- En gemensam API-fetch för de entities som delar data.
- Full async-I/O.
- Device registry.
- Tydlig dokumentation av polling.
- Config flow-testning.
- Unika config entries.
- Hanterbar reconfiguration.
- Typannoterad kod.

Referenser:

- https://developers.home-assistant.io/docs/core/integration/config_flow/
- https://developers.home-assistant.io/docs/core/integration-quality-scale/
- https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/config-flow/
- https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/common-modules/
- https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/devices/

---

# 27. Öppna API-frågor

Följande bör undersökas innan implementationen betraktas som färdig:

### 1. Exakt schema för `/lines`

Vi behöver fastställa om den ger:

- stoppens ordning,
- båda färdriktningarna,
- giltiga origin/destination-kombinationer,
- stabila line-ID:n.

### 2. Exakt schema för `/piers`

Verifiera vilka fält som är stabila och vilka som endast är presentation.

### 3. Cancellation

Finns det någon dold/annan endpoint eller ett fält som uttryckligen anger:

```text
cancelled
status
trafficInformation
```

Vi skapar ingen cancellationsensor innan detta är klarlagt.

### 4. Försening/realtid

Finns en faktisk realtidskälla eller är tiderna endast planerade tider?

### 5. `availability.state`

Vad betyder värden som:

```text
none
```

Semantiken måste verifieras innan endpointen används för beslut.

### 6. Rate limits

Det finns ingen identifierad publik rate-limit-dokumentation.

Integrationen ska därför polla konservativt och cacha aggressivt.

### 7. Stabilitet

API:t ligger på Båttaxis publika webbdomän men är inte identifierat som ett dokumenterat tredjeparts-API.

Vi bör därför räkna med att endpoints och JSON kan förändras.

---

# 28. MVP – konkret leveransordning

## Steg 1 – API-klient

Implementera och testa:

```text
get_piers()
get_lines()
search_departures()
```

Ingen Home Assistant-kod förrän API-modellerna är stabila.

## Steg 2 – Modeller

Skapa:

```text
BattaxiPier
BattaxiLine
BattaxiRoute
BattaxiDeparture
```

Skriv fixtures och parser-tester.

## Steg 3 – Route builder

Bygg funktion som från `/lines` + `/piers` returnerar:

```text
[
  "Sandhamnslinjen – Stavsnäs Vinterhamn → Telegrafholmen",
  ...
]
```

Detta är den viktigaste delen för config flow.

## Steg 4 – Config flow

UI:

```text
Välj sträcka
```

Testa API-anslutning och förhindra duplicate entries.

## Steg 5 – Coordinator

Implementera:

```text
today search
future search/cache
next departure
```

## Steg 6 – Device + primär sensor

Börja endast med:

```text
sensor.next_departure
```

När den fungerar stabilt läggs övriga entities till.

## Steg 7 – Övriga entiteter

Lägg till:

```text
sensor.next_arrival
sensor.available_seats
binary_sensor.bookable
sensor.departures_today
```

## Steg 8 – Robusthet

- timeouts,
- UpdateFailed,
- 429,
- malformed responses,
- schemaförändringar,
- cache.

## Steg 9 – HACS

- README,
- release,
- hacs.json,
- translations,
- diagnostics.

## Steg 10 – Fas 2

Överväg:

```text
calendar
availability-optimering
trafikstatus/cancellation
försening/realtid
```

endast när API-semantiken är verifierad.

---

# 29. Rekommenderad första MVP

Den minsta version jag skulle bygga är:

```text
Config flow:
    API-genererad dropdown med sträckor

Device:
    <origin> → <destination>

Entities:
    next_departure
    next_departure_text
    next_arrival
    available_seats
    bookable
    departures_today
    departures_today_text

API:
    /public/piers
    /public/lines
    /search

Polling:
    DataUpdateCoordinator
    initialt 5 minuter

Packaging:
    HACS custom integration
```

Detta ger redan en komplett och användbar integration utan att gissa om inställda turer, realtid eller bokningsfunktioner.

---

# 30. Designbeslut sammanfattade

| Fråga | Beslut |
|---|---|
| Operatör | Endast Stavsnäs Båttaxi |
| Bokning | Nej |
| Konfiguration | Home Assistant config flow |
| Bryggor | Hämtas från API |
| Linjer | Hämtas från API |
| Val i wizard | Riktad sträcka, t.ex. Stavsnäs Vinterhamn → Telegrafholmen |
| Entry-modell | En config entry per sträcka |
| Device-modell | Ett service-device per sträcka |
| Primär datakälla | `/api/search` |
| `availability` | Inte beslutsgrundande i MVP |
| Primär sensor | Nästa avgång (`timestamp`) |
| Visningssensor | Nästa avgång text (`string`) |
| Dagens avgångar | Antal som state + strukturerad lista i attribut |
| Dagens avgångar text | Kompakt dashboard-sträng |
| Cancellation | Inte implementerat utan explicit API-stöd |
| Polling | Coordinator, preliminärt 5 min |
| Distribution | HACS först |
| Arkitektur | Async, typed, testbar, nära HA Core-standard |

---

## Källor och verifierade endpoints

- Båttaxi API – linjer: https://api.battaxi.se/api/public/lines
- Båttaxi API – bryggor: https://api.battaxi.se/api/public/piers
- Båttaxi API – availability: https://api.battaxi.se/api/public/availability
- Båttaxi API – sökning: https://api.battaxi.se/api/search
- Stavsnäs Båttaxi: https://www.battaxi.se/
- Home Assistant Developer Docs: https://developers.home-assistant.io/


---

# 31. Verifierat API och beslut inför implementation (2026-09-12)

Detta avsnitt kompletterar §4, §7.2 och §27 med vad som faktiskt observerats mot `api.battaxi.se` samt de beslut som togs inför implementationen.

## 31.1 Verifierade scheman

### `/api/public/piers`

```json
{
  "items": [
    {
      "id": "6a31a5470bdad9fa1552c80a",
      "name": "Telegrafholmen",
      "area": "Sandhamn",
      "canBoard": true,
      "canAlight": true,
      "location": { "lat": 59.29, "lng": 18.92 }
    }
  ]
}
```

324 bryggor. `area` kan vara `null`. Obligatoriska fält för integrationen: `id`, `name`.

### `/api/public/lines`

```json
{
  "items": [
    {
      "id": "6a31a5470bdad9fa1552c80d",
      "name": "Sandhamnslinjen",
      "stops": ["<pier-id>", "..."],
      "passengerTypes": [ ... ],
      "fuelSurcharge": { "enabled": true, "amount": 2000 }
    }
  ]
}
```

5 linjer. `stops` är en **ordnad lista av brygg-ID:n som inkluderar returresan**. Sandhamnslinjen:

```text
Stavsnäs → Sandhamn → Telegrafholmen → Trouville → Lökholmen → Telegrafholmen → Sandhamn → Stavsnäs
```

Giltiga riktade sträckor är därmed par `(stops[i], stops[j])` med `i < j` och `stops[i] != stops[j]`. Integrationen behöver **inte** anta symmetrisk trafik – returriktningen finns explicit i listan.

Stopplistorna kan vara mycket långa: Nämdölinjen 227 stopp (169 unika), `namdo-runmaro-linjen` 348 stopp (288 unika). Alla `stops`-ID:n fanns i `/piers`. Obligatoriska fält: `id`, `name`, `stops`.

### `/api/search?origin=<id>&dest=<id>&date=YYYY-MM-DD`

```json
{
  "items": [
    {
      "departureId": "6a75c74b29f5bc095722dc32",
      "lineId": "6a31a5470bdad9fa1552c80d",
      "lineName": "Sandhamnslinjen",
      "departureTime": "19:10",
      "arrivalTime": "19:45",
      "durationMinutes": 35,
      "availableSeats": 60,
      "bookable": true,
      "boardStopIndex": 0,
      "alightStopIndex": 2,
      "prices": { "adult": 11000 },
      "passengerTypes": [ ... ],
      "fuelSurcharge": { "enabled": true, "amount": 2000 }
    }
  ]
}
```

- Tider är `HH:MM` i lokal svensk tid; datumet kommer från frågan.
- Sökningen är **inte linjebunden** – svaret kan innehålla flera `lineId`.
- Okänt brygg-ID ger `{"items": []}` med HTTP 200, inte ett fel.
- Saknad `date` ger HTTP 400 `{"error": "...", "statusCode": 400}`.
- Passerad avgång samma dag returneras med `bookable: false` (bekräftar §4.3).
- Obligatoriska fält: `departureId`, `lineId`, `lineName`, `departureTime`, `arrivalTime`, `bookable`. `availableSeats` och `durationMinutes` är valfria (saknas → `None`).

## 31.2 Beslut

| Fråga | Beslut |
|---|---|
| Config flow (ersätter §7.2) | Tre steg: **Linje** → **Från brygga** (linjens unika stopp i ordning) → **Till brygga** (endast bryggor som förekommer efter vald origin i stopplistan). Sökbara dropdowns. |
| Config entry-titel | `<origin> → <destination>` |
| Config entry unique_id | `<line_id>:<origin_id>:<destination_id>` (enligt §8) |
| Device-identifier (ersätter §9) | `(DOMAIN, entry.entry_id)` så att reconfigure av sträcka uppdaterar samma device i stället för att lämna föräldralösa devices/entities. Namn, manufacturer och model sätts från entry-data. |
| Entity unique_id | `<entry_id>_<key>` |
| Reconfigure (§18) | Samma tre steg som setup. Nytt unique_id sätts på entryn; krock med annan entry avbryter med `already_configured`. |
| Linjefilter | Coordinator behåller endast avgångar med konfigurerat `lineId`. |
| Tidszon | API-tider tolkas i `Europe/Stockholm` via `dt_util.get_time_zone`; "nu" via `dt_util.now()`. "Idag" = dagens datum i Stockholm. |
| Cache (§13.3) | Idag hämtas varje poll (5 min). Framtida datum cachas 6 h (även tomma). Lookahead max 14 dagar och körs bara när idag saknar kvarvarande avgångar. |
| Textsensorer | Svenska strängar enligt §10.2 och §10.7. Entity-namn översätts via `translations/sv.json` och `translations/en.json`. |
| `codeowners` | Tom lista tills GitHub-handle bestämts. |

## 31.3 Utvecklingsmiljö

- `docker-compose.yml` kör `ghcr.io/home-assistant/home-assistant:stable` med `./custom_components` monterad i `/config/custom_components` och `./dev/config` som `/config`. Portar 8123 (UI) och 5678 (debugpy).
- `dev/config/configuration.yaml` aktiverar `debugpy` (`start: true`, `wait: false`) och debug-loggning för integrationen.
- `.vscode/launch.json`: F5 startar containern (preLaunchTask väntar på port 5678) och attachar debuggern med `pathMappings` mot `/config/custom_components`.
- Lokala tester körs med `uv` och `pytest-homeassistant-custom-component` (Python ≥ 3.14, HA 2026.9.x).
