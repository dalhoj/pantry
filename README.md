# Pantry v0.6.7

Additiv patch direkte oven på v0.6.6. Alt eksisterende er bevaret.

Nyt:
- Lokal produktdatabase prioriteres før eksternt opslag.
- Open Food Facts bruges kun som fallback for ukendte stregkoder.
- Ukendt stregkode giver tydelig Ny stregkode-formular og Gem og husk produkt.
- Brugerens gemte rettelser og standardplacering vinder ved senere scanninger.
- Ny source-kolonne registrerer local/openfoodfacts.
- Standardiserede Pantry-produkttyper via product_types-tabellen.
- Bl.a. Dåsemad og Tørvarer / Kolonial, så makrel/tun kan samles under Dåsemad og mel/sukker mv. under Tørvarer / Kolonial.
- Produkttyper har standardplacering og icon_key klar til senere editor.
- Pantry anbefaler placering, men kun blandt brugerens eksisterende placeringer. Forslaget kan altid ændres før Gem.
- Kendte produkters tidligere placering har første prioritet.

TrueNAS image: ghcr.io/dalhoj/pantry:0.6.7
