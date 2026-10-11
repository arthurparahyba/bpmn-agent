"""Domínio: o processo e suas regras. Não depende de LLM, de tela nem de disco."""
from bpmn_agent.app.dominio.modelo import ModeloProcesso
from bpmn_agent.app.dominio.processo import GATEWAYS, HERDAM_RAIA, TIPOS, Condicao, Dado, Elemento, ErroModelo, Fluxo, Processo, Sistema

__all__ = ["ModeloProcesso", "ErroModelo", "Processo", "Elemento", "Fluxo", "Sistema", "Condicao", "Dado", "GATEWAYS", "HERDAM_RAIA", "TIPOS"]
