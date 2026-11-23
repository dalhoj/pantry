# Pantry v0.3.1
Safari/iPhone/iPad scanner-fix oven på v0.3.

- Start kamera-knap, så Safari får en eksplicit brugerhandling.
- ZXing Browser scanner EAN/UPC fra livevideo i stedet for BarcodeDetector API.
- Manuel stregkode bevares som fallback.
- Scan ind, Scan ud, søgning, grupper og eksisterende v0.3 database bevares.
- Kræver HTTPS for live kamera.

TrueNAS image: ghcr.io/dalhoj/pantry:0.3.1
Port: 8180:8080
Data: /mnt/Fast/Docker/pantry:/data
