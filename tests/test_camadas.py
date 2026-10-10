"""Garante as regras de camada: quem pode importar quem (ver docs/README.md)."""
import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "bpmn_agent"

PROIBIDO = {   # pasta -> prefixos de módulo que os arquivos dela não podem importar
    "app": ["bpmn_agent.api", "bpmn_agent.visao", "fastapi", "starlette", "uvicorn", "httpx", "streamlit", "dotenv"],
    "app/dominio": ["bpmn_agent.app.agente", "bpmn_agent.app.exportacao", "bpmn_agent.app.persistencia",
                    "bpmn_agent.app.sessao", "langchain", "langgraph", "json", "pathlib"],
    "app/agente": ["bpmn_agent.app.exportacao", "bpmn_agent.app.persistencia", "bpmn_agent.app.sessao"],
    "api": ["bpmn_agent.visao", "streamlit", "httpx"],
    "visao": ["bpmn_agent.app", "bpmn_agent.api", "fastapi", "langchain", "langgraph"],
}


def importados(arquivo: Path) -> set[str]:
    nomes = set()
    for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
        if isinstance(no, ast.Import):
            nomes |= {a.name for a in no.names}
        elif isinstance(no, ast.ImportFrom) and no.module:
            nomes.add(no.module)
    return nomes


@pytest.mark.parametrize("pasta", PROIBIDO)
def test_camada_nao_importa_o_que_nao_pode(pasta):
    violacoes = [f"{arquivo.relative_to(SRC)} importa {nome}"
                 for arquivo in sorted((SRC / pasta).rglob("*.py"))
                 for nome in sorted(importados(arquivo))
                 for proibido in PROIBIDO[pasta]
                 if nome == proibido or nome.startswith(proibido + ".")]
    assert not violacoes, "\n".join(violacoes)
