"""Domínio: o processo e suas regras. Não depende de LLM, de tela nem de disco."""
from bpmn_agent.app.dominio.modelo import ModeloProcesso
from bpmn_agent.app.dominio.processo import GATEWAYS, HERDAM_RAIA, TIPOS, Elemento, ErroModelo, Fluxo, Processo

__all__ = ["ModeloProcesso", "ErroModelo", "Processo", "Elemento", "Fluxo", "GATEWAYS", "HERDAM_RAIA", "TIPOS"]
