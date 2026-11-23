# Pantry v0.1

Selvhostet Pantry-webapp til TrueNAS SCALE.

## Funktioner
- Lageroversigt
- Tilfoej varer med antal, placering, kategori og udloebsdato
- Foto fra mobilkamera eller fil
- +/- antal og sletning
- Udlober snart/udlobet-status
- SQLite-data og uploads gemmes persistent i `/data`
- Responsivt layout til mobil og iPad

## GitHub Container Registry
Workflowet `.github/workflows/docker.yml` bygger automatisk:

`ghcr.io/dalhoj/pantry:latest`

ved push til `main`.

Hvis GitHub-repositoriet er privat, skal TrueNAS have credentials til GHCR. Den nemmeste foerste test er at goere package-imaget public i GitHub Packages, mens selve repositoryet stadig kan vaere privat.

## TrueNAS
1. Opret et dataset, fx `/mnt/tank/apps/pantry`.
2. Ret `POOL` i `docker-compose.yml` til dit poolnavn.
3. Skift `SECRET_KEY`.
4. Apps -> Discover Apps -> menu -> Install via YAML.
5. Indsaet YAML fra `docker-compose.yml` og installer.
6. Aabn `http://TRUENAS-IP:8080`.

## Lokal Docker-test
`docker compose up -d`

Bemærk: Ret volume-stien foerst, hvis du tester uden for TrueNAS.
