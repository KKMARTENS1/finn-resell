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

# 2. Første gang: lag et eget Python-miljø for appen
if [ ! -x ".venv/bin/python" ]; then
  echo "  Første gang: gjør klar appen. Det tar et minutt eller to …"
  python3 -m venv .venv || { echo "  Klarte ikke å gjøre klar Python-miljøet."; exit 1; }
fi

# 3. Installer det appen trenger (bare når noe er nytt)
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

# 4. Start
exec .venv/bin/python run.py
