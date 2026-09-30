#!/bin/bash
# Starter Golflager. Åpne Terminal og skriv:  bash start.sh
cd "$(dirname "$0")" || exit 1

echo ""
echo "  ⛳  Starter Golflager …"

# 1. Finnes Python 3.9 eller nyere?
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
  echo ""
  echo "  Fant ikke Python på Macen (eller versjonen er for gammel)."
  echo "  Hvis det dukket opp et vindu om å installere «utviklerverktøy», trykk Installer."
  echo "  Når installasjonen er ferdig, kjør denne kommandoen igjen:  bash start.sh"
  echo ""
  exit 1
fi

# 2. På en Mac installeres programmet i ~/Golflager/program.
#    Macen sperrer Dokumenter, Skrivebord og Nedlastinger for programmer uten tillatelse,
#    så Golflager-ikonet i Dock kan ikke starte appen derfra. ~/Golflager er ikke sperret.
ON_MAC=""
if [ "$(uname)" = "Darwin" ] || [ -n "$GOLFLAGER_FORCE_APP" ]; then ON_MAC=1; fi
PROGRAM_DIR="${GOLFLAGER_PROGRAM_DIR:-${GOLFLAGER_DATA_DIR:-$HOME/Golflager}/program}"

if [ -n "$ON_MAC" ]; then
  mkdir -p "$PROGRAM_DIR" || exit 1
  HERE_REAL="$(pwd -P)"
  PROGRAM_REAL="$(cd "$PROGRAM_DIR" && pwd -P)"
  if [ "$HERE_REAL" != "$PROGRAM_REAL" ]; then
    NEW_VERSION="$(cat VERSJON 2>/dev/null || echo 0)"
    OLD_VERSION="$(cat "$PROGRAM_DIR/VERSJON" 2>/dev/null || echo 0)"
    # Bytt aldri ut en nyere versjon (fra oppdateringsknappen) med en eldre nedlasting
    if python3 -c "import re, sys; v = lambda s: tuple(int(x) for x in re.findall(r'\d+', s)) or (0,); sys.exit(0 if v(sys.argv[1]) >= v(sys.argv[2]) else 1)" "$NEW_VERSION" "$OLD_VERSION"; then
      echo "  Installerer Golflager i $PROGRAM_DIR …"
      if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete --exclude '.venv' --exclude '__pycache__' --exclude '.git' ./ "$PROGRAM_DIR/" \
          || { echo "  Klarte ikke å kopiere Golflager til $PROGRAM_DIR."; exit 1; }
      else
        tar --exclude '.venv' --exclude '__pycache__' --exclude '.git' -cf - . | (cd "$PROGRAM_DIR" && tar -xf -) \
          || { echo "  Klarte ikke å kopiere Golflager til $PROGRAM_DIR."; exit 1; }
      fi
    else
      echo "  Golflager i $PROGRAM_DIR er nyere (versjon $OLD_VERSION) enn denne mappen, så den beholdes."
    fi
    bash "$PROGRAM_DIR/mac/lag-app.sh" "$PROGRAM_DIR" \
      || echo "  (Klarte ikke å lage Golflager-ikonet. Appen virker likevel.)"
    echo "  Mappen du lastet ned, trengs ikke lenger. Du kan slette den hvis du vil."
    cd "$PROGRAM_DIR" && GOLFLAGER_INSTALLERT=1 exec bash start.sh
    exit 1
  fi
fi

# 3. Første gang: lag et eget Python-miljø for appen
if [ ! -x ".venv/bin/python" ]; then
  echo "  Første gang: gjør klar appen. Det tar et minutt eller to …"
  python3 -m venv .venv || { echo "  Klarte ikke å gjøre klar Python-miljøet."; exit 1; }
fi

# 4. Installer det appen trenger (bare når noe er nytt)
WANTED="$(cksum requirements.txt | cut -d' ' -f1)"
if [ ! -f ".venv/.installert" ] || [ "$(cat .venv/.installert)" != "$WANTED" ]; then
  echo "  Installerer det appen trenger …"
  if ! .venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt; then
    echo "  Prøver igjen med nyere pip …"
    .venv/bin/python -m pip install --disable-pip-version-check -q --upgrade pip
    .venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt || {
      echo ""
      echo "  Klarte ikke å installere. Sjekk at Macen er koblet til internett, og prøv igjen."
      exit 1
    }
  fi
  echo "$WANTED" > .venv/.installert
fi

# 5. Oppdater Golflager-ikonet i Dock (når du starter fra Terminal i programmappen)
if [ -n "$ON_MAC" ] && [ -z "$GOLFLAGER_FRA_APP" ] && [ -z "$GOLFLAGER_INSTALLERT" ]; then
  bash mac/lag-app.sh "$PWD" || echo "  (Klarte ikke å lage Golflager-ikonet. Appen virker likevel.)"
fi

# 6. Start
exec .venv/bin/python run.py
