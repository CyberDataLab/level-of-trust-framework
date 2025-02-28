#!/usr/bin/env sh

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: No se encontró python3 en el sistema."
  exit 1
fi

PY_VERSION=$(python3 --version 2>/dev/null)

if echo "$PY_VERSION" | grep -q "Python 3.10"; then
  echo "Se detectó $PY_VERSION. Procediendo con la instalación..."
  
  pip3 install --upgrade pip
  pip3 install rasa[full]

  #apt install rustc && apt install cargo

else
  echo "Error: Se requiere Python 3.10 activo. Versión detectada: $PY_VERSION"
  exit 1
fi
