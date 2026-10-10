"""
Gravar e ler o processo em disco. É o único lugar do backend que toca em arquivos.

    sessoes/<id>/processo.json   o processo completo (dá para continuar depois)
    sessoes/<id>/processo.bpmn   o diagrama, para abrir em outras ferramentas
    sessoes/<id>/processo.md     a descrição em texto
"""
from __future__ import annotations

import json
from pathlib import Path

from bpmn_agent.app.dominio import ModeloProcesso
from bpmn_agent.app.exportacao.exportar_bpmn import gerar_bpmn_xml


def salvar_modelo(modelo: ModeloProcesso, caminho: str | Path) -> None:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(modelo.para_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def carregar_modelo(caminho: str | Path) -> ModeloProcesso:
    return ModeloProcesso.de_dict(json.loads(Path(caminho).read_text(encoding="utf-8")))


def salvar_artefatos(modelo: ModeloProcesso, pasta: str | Path) -> None:
    """Grava os três arquivos de uma sessão."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    salvar_modelo(modelo, pasta / "processo.json")
    (pasta / "processo.bpmn").write_text(gerar_bpmn_xml(modelo), encoding="utf-8")
    (pasta / "processo.md").write_text(modelo.narrativa(), encoding="utf-8")
