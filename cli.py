"""
Versão de terminal. A cada resposta, o diagrama é salvo em sessoes/<id>/ e
`visualizar.html` é atualizado (abra no navegador e recarregue a página).

    python cli.py                       # usa LLM_PROVEDOR do .env
    python cli.py --provedor gemini
    python cli.py --continuar sessoes/ab12cd34/processo.json

Comandos: /desfazer  /resumo  /pendencias  /sair
"""
from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from bpmn_agent.agente import Sessao
from bpmn_agent.llm import criar_llm
from bpmn_agent.modelo import ModeloProcesso
from bpmn_agent.visualizador import html_visualizador


def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(description="Entrevista para desenhar processos em BPMN")
    ap.add_argument("--provedor")
    ap.add_argument("--modelo")
    ap.add_argument("--continuar", help="arquivo processo.json de uma sessão anterior")
    ap.add_argument("--debug", action="store_true", help="mostra as ações do agente")
    args = ap.parse_args()

    modelo = ModeloProcesso.carregar(args.continuar) if args.continuar else None
    sessao = Sessao(criar_llm(args.provedor, args.modelo), modelo=modelo)
    sessao.salvar()
    visual = sessao.pasta / "visualizar.html"

    def atualizar_visual(destaque=None):
        visual.write_text(html_visualizador(sessao.bpmn_xml(), altura=800, destacar=destaque), encoding="utf-8")

    atualizar_visual()
    print(f"\n📁 Arquivos em: {sessao.pasta.resolve()}")
    print(f"🖼  Abra no navegador (e recarregue após cada resposta): {visual.resolve().as_uri()}\n")
    print(f"🧭 {sessao.historico_visivel()[-1][1]}\n")

    while True:
        try:
            texto = input("você › ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not texto:
            continue
        if texto == "/sair":
            break
        if texto == "/desfazer":
            print(sessao.modelo.desfazer()); sessao.salvar(); atualizar_visual(); continue
        if texto == "/resumo":
            print(sessao.modelo.narrativa(), "\n"); continue
        if texto == "/pendencias":
            print("\n".join(sessao.modelo.problemas() + sessao.modelo.p.pendencias) or "Nada em aberto."); continue
        try:
            r = sessao.enviar(texto)
        except Exception as e:
            print(f"⚠️  Erro ao falar com o modelo: {e}\n"); continue
        if args.debug:
            for a in r.acoes:
                print(f"   🔧 {a}")
        atualizar_visual(r.alterados)
        print(f"\n🧭 {r.texto}\n")

    print(f"\nAté logo! Diagrama final: {(sessao.pasta / 'processo.bpmn').resolve()}")


if __name__ == "__main__":
    main()
