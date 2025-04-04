#!/usr/bin/env sh

# Rasa installation
if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: Python 3 was not found in the system."
  echo "Please install Python 3.10"
  exit 1
fi

PY_VERSION=$(python3 --version 2>/dev/null)

if echo "$PY_VERSION" | grep -q "Python 3.10"; then
  echo "Se detectó $PY_VERSION. Procediendo con la instalación..."
  
  pip3 install --upgrade pip
  pip3 install rasa[full] rasa-model-report pymongo

  #apt install rustc && apt install cargo

else
  echo "Error: Se requiere Python 3.10 activo. Versión detectada: $PY_VERSION"
  exit 1
fi

# MongoDB installation
if ! command -v docker >/dev/null 2>&1; then
  echo "Error: No se encontró Docker en el sistema."
  exit 1
fi

docker pull mongo:latest
