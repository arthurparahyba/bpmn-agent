#!/usr/bin/env bash
# Sobe o serviço (API) e a interface de uma vez. Ctrl+C encerra os dois.
# Tudo fica acessível só nesta máquina (127.0.0.1).
#
#   ./rodar.sh             serviço + página web (abre o navegador)
#   ./rodar.sh terminal    serviço + conversa no terminal (com --debug)
#
# Variáveis opcionais:
#   BPMN_API_PORTA   porta do serviço      (padrão: a do .env, senão 8000)
#   PORTA_WEB        porta da página web   (padrão: 8501)
#   NAO_ABRIR=1      não abre o navegador sozinho
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
if [ ! -x "$PY" ]; then
  echo "⚠️  Ambiente não instalado. Rode antes:"
  echo "    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi
if [ ! -f .env ]; then
  echo "⚠️  Falta o arquivo .env. Rode: cp .env.example .env  e preencha o provedor e a chave."
  exit 1
fi

MODO="${1:-web}"
PORTA_API="${BPMN_API_PORTA:-$($PY -c "from dotenv import dotenv_values; print(dotenv_values('.env').get('BPMN_API_PORTA') or 8000)")}"
PORTA_WEB="${PORTA_WEB:-8501}"
export BPMN_API_PORTA="$PORTA_API"
export BPMN_API_URL="http://127.0.0.1:$PORTA_API"

no_ar() { curl -s -o /dev/null --max-time 2 "$BPMN_API_URL/saude"; }

PID_SERVIDOR=""
encerrar() {
  if [ -n "$PID_SERVIDOR" ] && kill -0 "$PID_SERVIDOR" 2>/dev/null; then
    kill "$PID_SERVIDOR" 2>/dev/null || true
    echo; echo "🛑 Serviço encerrado."
  fi
}
trap encerrar EXIT
trap 'exit 130' INT TERM

if no_ar; then
  echo "ℹ️  Já existe um serviço no ar em $BPMN_API_URL; vou usar esse."
else
  LOG="$(mktemp -t bpmn-servidor)"
  echo "🚀 Subindo o serviço em $BPMN_API_URL  (registro: $LOG)"
  "$PY" -m bpmn_agent.api.servidor >"$LOG" 2>&1 &
  PID_SERVIDOR=$!
  for _ in $(seq 1 40); do
    no_ar && break
    if ! kill -0 "$PID_SERVIDOR" 2>/dev/null; then
      echo "⚠️  O serviço não subiu. Últimas linhas do registro:"; tail -15 "$LOG"; exit 1
    fi
    sleep 0.5
  done
  no_ar || { echo "⚠️  O serviço demorou demais para responder. Veja $LOG"; exit 1; }
fi
echo "✅ Serviço no ar: $(curl -s "$BPMN_API_URL/saude")"
echo "   Rotas para explorar: $BPMN_API_URL/docs"

case "$MODO" in
  web)
    URL_WEB="http://localhost:$PORTA_WEB"
    echo "🖥  Página web em $URL_WEB  (Ctrl+C para encerrar tudo)"
    if [ -z "${NAO_ABRIR:-}" ]; then
      ( for _ in $(seq 1 40); do
          curl -s -o /dev/null --max-time 1 "$URL_WEB" && break; sleep 0.5
        done
        if command -v open >/dev/null; then open "$URL_WEB"; elif command -v xdg-open >/dev/null; then xdg-open "$URL_WEB"; fi
      ) >/dev/null 2>&1 &
    fi
    .venv/bin/streamlit run src/bpmn_agent/visao/web.py \
      --server.address 127.0.0.1 --server.port "$PORTA_WEB" \
      --server.headless true --browser.gatherUsageStats false
    ;;
  terminal)
    "$PY" -m bpmn_agent.visao.terminal --debug
    ;;
  *)
    echo "Uso: ./rodar.sh [web|terminal]"; exit 1
    ;;
esac
