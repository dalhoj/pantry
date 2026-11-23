# Pantry v0.2

Selvhostet Pantry-webapp til TrueNAS SCALE med stregkodeopslag og lokal OCR af datomærkning.

## Nyt i v0.2
- AI-scan-side med produktfoto/stregkode og separat datofoto
- EAN/UPC-aflæsning med ZBar/pyzbar
- Produktopslag i Open Food Facts
- Lokal Tesseract OCR med flere billedvarianter
- Danske datoformater: DD.MM.YY, DD/MM/YYYY, DD-MM-YY og DDMMYY
- Resultatside med sikkerhed, kontrol og valg af placering
- Automatisk databasemigrering fra v0.1
- Eksisterende data i /data bevares

## TrueNAS-opdatering
1. Upload indholdet af denne mappe til roden af dalhoj/pantry.
2. Vent på grønt GitHub Actions-build.
3. I TrueNAS: Apps -> pantry -> Update eller redeploy/restart med pull af nyeste image.
4. Behold volume `/mnt/Fast/Docker/pantry:/data` og port `8180:8080`.
5. Åbn `http://TRUENAS-IP:8180`.

## Vigtigt
- Open Food Facts kræver internetadgang fra containeren for produktnavn/kategori.
- OCR og stregkodeaflæsning sker lokalt.
- Resultater skal altid kontrolleres før gemning.
- Et foto af datomærkningen tæt på, uden genskin, giver bedst resultat.
