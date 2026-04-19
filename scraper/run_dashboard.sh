#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Arranca el Dashboard de gestión de productos
#  Uso: ./run_dashboard.sh
# ─────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Entorno virtual ───────────────────────────────────────────
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
  echo "🐍  Creando entorno virtual…"
  python3 -m venv "$VENV_DIR"
fi

# Detectar nombre del ejecutable Python dentro del venv (python o python3)
PYTHON_BIN="$VENV_DIR/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then
  PYTHON_BIN="$VENV_DIR/bin/python3"
fi

echo "📦  Instalando/actualizando dependencias…"
"$PYTHON_BIN" -m pip install -q --upgrade pip
"$PYTHON_BIN" -m pip install -q -r "$SCRIPT_DIR/requirements.txt"

# ── Credenciales ──────────────────────────────────────────────
if [ ! -f "$SCRIPT_DIR/.env" ]; then
  echo ""
  echo "⚠️   No existe scraper/.env"
  echo "    Puedes configurar las credenciales desde la interfaz web"
  echo "    o copiar el ejemplo:"
  echo "    cp scraper/.env.example scraper/.env"
  echo ""
fi

# ── Lanzar ────────────────────────────────────────────────────
echo ""
echo "🚀  Iniciando dashboard en http://localhost:5050"
echo "    (Ctrl+C para detener)"
echo ""

"$PYTHON_BIN" "$SCRIPT_DIR/dashboard/app.py"
