# Pantry v0.4.0

Oven på v0.3.1:
- BRUG SNART øverst på forsiden, maks 5 batches og sorteret efter udløbsdato.
- Farver: rød = udløbet/i dag, orange = 1-3 dage, gul = 4-7 dage.
- /expiry viser alle daterede varer sorteret efter udløb.
- 'Ingen holdbarhedsdato' ved Scan ind. Valget huskes per stregkode.
- Varer uden dato kommer aldrig i BRUG SNART.
- Type-regler udvidet med opvaskemiddel, opvaskemaskinesalt og sæbe.
- v0.3.1 live ZXing-scanner og database bevares.

TrueNAS image: ghcr.io/dalhoj/pantry:0.4
Port: 8180:8080
Data: /mnt/Fast/Docker/pantry:/data
