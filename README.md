# Pantry v0.7.0

Additivt bygget oven på v0.6.9.1. Alt eksisterende er bevaret.

Nyt:
- Brug-knappen er tilbage på udfoldede lagerposter og kalder samme inventory/use-backend som Scan ud.
- Første opstart viser opsætning af 4-12 cifret Pantry-kode.
- Hele appen kræver login, bortset fra health, login, opsætning og statiske filer.
- PIN gemmes kun som Werkzeug password hash i SQLite.
- “Husk mig” giver permanent session i 30 dage; uden flueben gælder login indtil browser-sessionen slutter.
- Cookie: Secure, HttpOnly og SameSite=Lax.
- Mere > Sikkerhed: skift kode og log ud.
- TAILSCALE.md med privat adgang udefra uden offentlig port-forwarding.

Vigtigt: sæt SECRET_KEY i TrueNAS til en lang tilfældig og stabil værdi. Skift ikke SECRET_KEY mellem opdateringer, ellers logges huskede enheder ud.
