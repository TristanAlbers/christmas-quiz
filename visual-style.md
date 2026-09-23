# Visuele stijl — Kerstmis Quiz

Dit document beschrijft de visuele richting voor de **Kerstmis Quiz** en vormt de basis voor toekomstige team-, overzichts- en Game Master-schermen.

De stijl moet herkenbaar kerstachtig zijn zonder te veranderen in een drukke of kinderlijke kerstpagina. De gewenste sfeer is die van een **kerstavond-escape-room / luxe bordspel**: donker, warm, sfeervol en duidelijk leesbaar.

---

## 1. Doel

De interface moet:

- direct als kerstspel herkenbaar zijn;
- feestelijk en spannend aanvoelen;
- op telefoon én groot scherm goed leesbaar blijven;
- gameplay-informatie altijd belangrijker maken dan decoratie;
- zonder externe frontend-CDN's of externe fonts kunnen draaien;
- bruikbaar blijven als animaties uitstaan;
- eenvoudig uitbreidbaar zijn naar latere spelonderdelen.

De visuele laag mag nooit spelregels, autorisatie of state-logica bepalen. Styling blijft presentatie.

---

## 2. Naamgeving en taal

De quiz wordt in het Nederlands gespeeld.

Gebruik in zichtbare vaste interface-tekst daarom Nederlandse termen. Voorbeelden:

| Engels / niet gebruiken | Nederlands / gebruiken |
|---|---|
| Christmas Quiz | Kerstmis Quiz |
| Team login | Teaminlog |
| Admin login | Game Master-inlog |
| Sign in | Inloggen / Naar de quiz |
| Back | Terug |
| Start game | Start quiz |
| Pause | Pauzeer |
| Resume | Hervat |
| Completed | Voltooid |
| Hint | Hint |
| Skip | Overslaan |

`Game Master` mag als spelterm Engelstalig blijven. Dit is een bewuste thematische rolnaam, geen generieke interface-term.

Game-package-inhoud kan later zijn eigen teksten bevatten. Deze stijlgids gaat vooral over **hardcoded applicatie-interface**.

---

## 3. Kerngevoel

Gebruik deze woorden als toetssteen bij nieuwe schermen:

- kerstavond;
- escape room;
- winteravond;
- warm licht;
- donker dennegroen;
- bordeauxrood;
- antiek goud;
- sneeuw;
- bordspel;
- mysterie;
- samen spelen.

Vermijd:

- fel primaire rood-groen-combinaties;
- overdreven cartoonkerstmannen;
- drukke patronen achter belangrijke tekst;
- grote hoeveelheden emoji;
- glanzende "casino"-effecten;
- moderne corporate SaaS-esthetiek;
- visuele effecten die de spelstatus minder duidelijk maken.

---

## 4. Kleuren

De gedeelde CSS-tokens staan in:

`quiz/static/quiz/theme.css`

### Hoofdkleuren

| Token | Waarde | Gebruik |
|---|---:|---|
| `--christmas-pine-950` | `#061813` | diepste achtergrond |
| `--christmas-pine-900` | `#0a211a` | donkere panelen |
| `--christmas-pine-800` | `#10382c` | groen verloop / secundair vlak |
| `--christmas-cream-50` | `#fffaf0` | hoofdtekst |
| `--christmas-cream-100` | `#f7edda` | zachte tekst |
| `--christmas-red-600` | `#a8242d` | primaire actie |
| `--christmas-gold-400` | `#e7c97f` | accent / decoratie |
| `--christmas-blue-200` | `#d8edf4` | ijs/freeze-accent |

### Semantiek

Gebruik **rood niet automatisch als foutkleur**. Rood is al de primaire kerst-actie- en merktoon.

Voor gameplay-statussen moet later een aparte semantische statusset worden toegevoegd, bijvoorbeeld:

- succes;
- waarschuwing;
- fout;
- freeze;
- actief;
- voltooid.

Die statuskleuren moeten eerst op contrast en onderscheidbaarheid worden getest.

---

## 5. Typografie

Gebruik geen externe webfonts.

### Displaytekst

Voor grote titels:

`Georgia, "Times New Roman", serif`

Gebruik deze serif alleen voor:

- paginatitels;
- grote quizmomenten;
- winnaarschermen;
- belangrijke hoofdstuk-/eventtitels.

### Interface

Voor formulieren, knoppen en spelinformatie:

`system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`

Interface-informatie moet snel scanbaar blijven.

---

## 6. Componenten

De gedeelde visuele basis gebruikt herbruikbare classes uit `theme.css`.

### `.theme-card`

Voor belangrijke panelen.

Kenmerken:

- donker transparant groen;
- subtiele gouden rand;
- zachte blur;
- ronde hoeken;
- duidelijke schaduw.

Gebruik dit voor:

- landing;
- login;
- puzzle cards;
- shop panels;
- Game Master-groepen;
- modale acties.

### `.theme-button`

Primaire actie.

Kenmerken:

- bordeaux/kerstrood;
- witte tekst;
- ruim klikvlak;
- subtiele gloed;
- duidelijke focus-state.

Gebruik per scherm bij voorkeur maar één dominante primaire actie.

### `.theme-text-link`

Voor secundaire navigatie zoals:

- terug;
- Game Master vanaf de landing;
- detailnavigatie;
- minder belangrijke acties.

### `.theme-eyebrow`

Kleine gouden uppercase contextregel boven een grote titel.

Voorbeelden:

- `KERST ESCAPE ROOM · 2026`
- `PUZZEL 7 VAN 25`
- `MUZIEKQUIZ`
- `TEAM A`

Gebruik spaarzaam.

---

## 7. Decoratie

Decoratie is toegestaan als die geen relevante informatie bedekt.

### Kerstlichtjes

De landing en auth-pagina gebruiken een lichtslinger.

Later bruikbaar voor:

- beginscherm;
- eindscherm;
- TV-overzicht;
- grote overgangsmomenten.

Niet gebruiken als constante decoratie rond ieder klein formulier.

### Sneeuw

Gebruik subtiele CSS-sneeuw als achtergrondlaag.

Regels:

- nooit nodig voor functionaliteit;
- geen JavaScript vereist;
- lage visuele dichtheid;
- moet uitgeschakeld of praktisch stil worden bij `prefers-reduced-motion`.

### Bos / sneeuwbank

Donkere dennenvormen en lichte sneeuw onderaan kunnen grote lege schermen sfeer geven.

De landing gebruikt hiervoor `winter-forest.svg`, een transparant herhalend silhouet. Gebruik geen grote `conic-gradient()`-tegels om bomen na te bootsen: op bepaalde viewport-verhoudingen kunnen de gevulde gradientvlakken als rechthoekige groene artefacten zichtbaar worden.

Niet gebruiken achter kleine, dichte mobiele gameplay-layouts als dit de ruimte beperkt. In lage landscape-weergaven mag het bos volledig verdwijnen.

---

## 8. Motion

Animaties moeten rustig zijn.

Wel:

- trage sneeuw;
- zachte lichtgloed;
- kleine hover-beweging van knoppen;
- korte feedbacktransities.

Niet:

- constante bouncing;
- snelle flitsen;
- grote parallax;
- animaties die timing of gameplay lijken te communiceren terwijl ze dat niet doen.

Altijd ondersteunen:

```css
@media (prefers-reduced-motion: reduce)
```

De interface moet zonder animatie volledig begrijpelijk blijven.

---

## 9. Mobiel eerst voor team en Game Master

Team- en Game Master-schermen worden hoofdzakelijk op telefoon gebruikt.

Daarom:

- minimale interactieve hoogte ongeveer `48px`;
- primaire knoppen liefst volle breedte;
- formulieren één kolom;
- invoervelden minimaal `16px` tekst zodat iOS niet automatisch inzoomt;
- belangrijke status boven de fold;
- geen hover-afhankelijke interactie;
- voldoende ruimte tussen sabotage/shop/antwoord-acties;
- geen decoratie die verticale ruimte opeet zonder gameplaywaarde;
- gebruik `100dvh`/`100svh` met een `100vh` fallback voor mobiele browserbalken;
- houd rekening met `env(safe-area-inset-*)` bij schermen met een notch/home indicator;
- test ten minste smalle portrait- en landscape-weergaven;
- decoratie mag in landscape of op zeer kleine schermen worden vereenvoudigd.

Landing en login mogen gecentreerd en filmischer zijn, maar moeten kunnen scrollen als het scherm of het geopende toetsenbord minder verticale ruimte beschikbaar maakt.

---

## 10. Groot scherm / TV

Het publieke overzicht wordt op een grote TV getoond.

Daar gelden andere prioriteiten:

1. voortgang van beide teams;
2. huidige globale quizstatus;
3. speeltijd;
4. grote event-status;
5. decoratie.

Gebruik daar:

- grote cijfers;
- grote progressie-indicatoren;
- sterke teamidentiteit;
- weinig kleine tekst;
- grotere afstanden;
- decoratie langs de randen, niet over kerninformatie.

---

## 11. Teamidentiteit

De kerststijl is globaal. Teamidentiteit moet daar later bovenop komen.

Team A en Team B mogen bijvoorbeeld ieder een eigen secundair accent krijgen, maar:

- niet uitsluitend via kleur communiceren;
- teamnaam altijd zichtbaar tonen;
- kleuren moeten binnen de donkere kerstbasis passen;
- teamkleuren mogen semantische statuskleuren niet verwarren.

Exacte teamkleuren zijn nog niet vastgelegd in deze versie van de stijlgids.

---

## 12. Freeze-, muziek- en finale-momenten

De basisstijl moet speciale spelmomenten duidelijk kunnen dragen.

### Freeze

Gebruik een koude blauwe/ijzige overlay bovenop de bestaande interface.

Belangrijk:

- huidige puzzel blijft herkenbaar;
- interacties zijn zichtbaar disabled;
- freeze-status is expliciet met tekst;
- kleur alleen is onvoldoende.

### Muziekquiz

Mag visueel meer podiumachtig zijn:

- donkerder;
- gouden lichtaccenten;
- grote vraag-/rondenummers;
- score prominent op TV.

### Winnaar / finale

Hier mag de stijl tijdelijk uitbundiger:

- confetti;
- goud;
- sterkere gloed;
- grotere displaytypografie.

Gebruik dit niet tijdens normale gameplay, zodat het finale-moment bijzonder blijft.

---

## 13. Bestandsstructuur

Voorgestelde scheiding:

```text
quiz/static/quiz/
├── app.css          # bestaande functionele/gameplay styling
├── theme.css        # gedeelde kerst-design-tokens en basiselementen
└── landing.css      # landing + login-specifieke styling
```

Later kan dit groeien naar bijvoorbeeld:

```text
quiz/static/quiz/
├── theme.css
├── app.css
├── landing.css
├── team.css
├── admin.css
└── overview.css
```

Voorkom één enorm stylesheet waarin alle schermspecifieke uitzonderingen door elkaar staan.

---

## 14. Implementatieregels voor toekomstige ontwikkeling

Bij nieuwe views:

1. gebruik eerst bestaande tokens uit `theme.css`;
2. voeg alleen nieuwe tokens toe als ze echt gedeeld zijn;
3. plaats schermspecifieke regels in het schermstylesheet;
4. kopieer geen kleurwaarden als er al een semantisch token bestaat;
5. gebruik normale HTML-controls waar mogelijk;
6. houd decoratie `aria-hidden`;
7. controleer toetsenbordfocus;
8. controleer contrast;
9. controleer telefoonbreedtes;
10. test `prefers-reduced-motion`.

UI-styling mag nooit een backendregel vervangen of verbergen.

---

## 15. Eerste concrete toepassing

De eerste implementatie van deze stijl omvat:

- `index.html`
  - Nederlandse landing;
  - kerstlichtjes;
  - subtiele sneeuw;
  - bos/sneeuwsilhouet;
  - prominente teamactie;
  - secundaire Game Master-link.

- `login.html`
  - zelfde visuele wereld;
  - aparte tekst voor team en Game Master;
  - bestaande Django-formulieren blijven leidend;
  - geen wijziging aan authenticatielogica.

- `theme.css`
  - gedeelde tokens en componenten.

- `landing.css`
  - decoratie en pagina-layout.

Dit is bewust alleen presentatie. Routes, authenticatie en spelregels blijven ongewijzigd.
