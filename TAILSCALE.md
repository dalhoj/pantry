# Privat adgang til Pantry udefra med Tailscale

1. Installer Tailscale på TrueNAS SCALE fra Apps.
2. Log TrueNAS og iPhone/iPad ind på samme Tailscale-konto.
3. Behold Pantry og Nginx Proxy Manager uden offentlig port-forwarding.
4. Åbn Pantry via TrueNAS' Tailscale-IP eller et MagicDNS-navn.
5. Hvis HTTPS-navnet kun findes i lokal DNS, kan du fortsat bruge NPM via subnet routing, eller oprette et internt navn der peger på NPM.

Pantrys PIN-login beskytter appen oven på Tailscale-forbindelsen. Kameraet kræver fortsat HTTPS/sikker browserkontekst.
