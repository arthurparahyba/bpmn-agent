"""
Ponto de entrada do serviço. É o único lugar que lê o .env com o provedor, o modelo e a chave.

    python -m bpmn_agent.api.servidor                     # http://127.0.0.1:8000
    uvicorn bpmn_agent.api.servidor:aplicacao --reload    # para desenvolver

Sem autenticação: por isso escuta só nesta máquina (127.0.0.1), a menos que BPMN_API_HOST mude.
Sempre com um worker só: as sessões ficam na memória deste processo.
"""
from __future__ import annotations

import os

import uvicorn
from dotenv import load_dotenv

from bpmn_agent.api.rotas import criar_app

load_dotenv()
aplicacao = criar_app()


def main() -> None:
    host = os.getenv("BPMN_API_HOST", "127.0.0.1")
    porta = int(os.getenv("BPMN_API_PORTA", "8000"))
    if host not in {"127.0.0.1", "localhost", "::1"}:
        print(f"⚠️  Escutando em {host}: a API não tem autenticação e qualquer pessoa na rede poderá usá-la.")
    uvicorn.run(aplicacao, host=host, port=porta)


if __name__ == "__main__":
    main()
