# Pantry v0.3.0
Scan ind -> skriv udløbsdato -> gem -> søg -> scan ud.

- OCR/Tesseract fjernet
- Open Food Facts stregkodeopslag
- Produkttype/brand/variant og batch-lager
- Søgefunktion
- Scan ud bruger ældste udløbsbatch først
- Automatisk migration af v0.2 items
- PWA manifest
- Manuel stregkodefallback

Live kamera kræver normalt HTTPS/sikker kontekst på mobil. Tag backup af `/mnt/Fast/Docker/pantry/pantry.db` før første v0.3-start.
