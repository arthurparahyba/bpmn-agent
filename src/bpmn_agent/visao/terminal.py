"""
Versão de terminal. Conversa com o serviço pela API (suba antes: python -m bpmn_agent.api.servidor).
A cada resposta, `visualizar.html` é atualizado (abra no navegador e recarregue a página).

    python -m bpmn_agent.visao.terminal
    python -m bpmn_agent.visao.terminal --debug
    python -m bpmn_agent.visao.terminal --continuar sessoes/ab12cd34/processo.json

Comandos: /desfazer  /resumo  /pendencias  /sair
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from bpmn_agent.visao.cliente import MENSAGEM_FORA_DO_AR, ApiForaDoAr, ClienteApi, ErroDaApi
from bpmn_agent.visao.visualizador import html_visualizador


def main() -> None:
    load_dotenv()    # só para BPMN_API_URL; o modelo e a chave são assunto do servidor
    ap = argparse.ArgumentParser(description="Entrevista para desenhar processos em BPMN")
    ap.add_argument("--continuar", help="arquivo processo.json de uma sessão anterior")
    ap.add_argument("--debug", action="store_true", help="mostra as ações do agente")
    args = ap.parse_args()

    cliente = ClienteApi()
    try:
        processo = json.loads(Path(args.continuar).read_text(encoding="utf-8")) if args.continuar else None
        estado = cliente.criar_sessao(processo)
    except ApiForaDoAr:
        sys.exit(f"⚠️  {MENSAGEM_FORA_DO_AR}\n   Endereço: {cliente.base_url}  |  Para ligar: python -m bpmn_agent.api.servidor")
    except ErroDaApi as e:
        sys.exit(f"⚠️  {e.mensagem}\n   {e.detalhe}")
    except (OSError, ValueError) as e:
        sys.exit(f"⚠️  Não consegui ler {args.continuar}: {e}")

    id = estado["id"]
    visual = Path(tempfile.gettempdir()) / "bpmn-agent" / id / "visualizar.html"
    visual.parent.mkdir(parents=True, exist_ok=True)

    def atualizar_visual(destaque=None) -> dict:
        estado = cliente.estado(id)
        visual.write_text(html_visualizador(estado["bpmn_xml"], altura=800, destacar=destaque), encoding="utf-8")
        return estado

    atualizar_visual()
    print(f"\n📁 Arquivos (no servidor) em: {estado['pasta']}")
    print(f"🖼  Abra no navegador (e recarregue após cada resposta): {visual.as_uri()}\n")
    print(f"🧭 {estado['historico'][-1]['texto']}\n")

    while True:
        try:
            texto = input("você › ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not texto:
            continue
        if texto == "/sair":
            break
        try:
            if texto == "/desfazer":
                print(cliente.desfazer(id)["mensagem"]); atualizar_visual(); continue
            if texto == "/resumo":
                print(cliente.estado(id)["narrativa"], "\n"); continue
            if texto == "/pendencias":
                estado = cliente.estado(id)
                print("\n".join(estado["em_aberto"] + estado["pendencias"]) or "Nada em aberto."); continue
            r = cliente.enviar(id, texto)
            if args.debug:
                for a in r["acoes"]:
                    print(f"   🔧 {a}")
            atualizar_visual(r["alterados"])
            print(f"\n🧭 {r['texto']}\n")
        except ApiForaDoAr:
            print(f"⚠️  {MENSAGEM_FORA_DO_AR}\n")
        except ErroDaApi as e:
            print(f"⚠️  {e.mensagem}" + (f"\n   {e.detalhe}" if e.detalhe else "") + "\n")

    print(f"\nAté logo! Diagrama final (no servidor): {estado['pasta']}/processo.bpmn")


if __name__ == "__main__":
    main()
