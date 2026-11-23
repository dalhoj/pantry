# Pantry v0.2.1
Dato-OCR rettelse: `Bedst før` og `sidste anvendelse` behandles begge som holdbarhedsdato. OCR bruger dansk/engelsk Tesseract, opskalering, flere kontrastvarianter og en dato-only pass til dot-matrix-print. Eksempel: `Bedst før: 19.02.2027` gemmes som `2027-02-19`; `09:39` ignoreres som tidspunkt.

Eksisterende database og uploads bevares i `/mnt/Fast/Docker/pantry:/data`.
