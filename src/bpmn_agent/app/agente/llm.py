"""
Fábrica de LLMs. Troque de provedor só mudando variáveis de ambiente (.env).

Provedores baratos/gratuitos com suporte a chamada de ferramentas (tool calling):
  - deepseek   : muito barato; API compatível com OpenAI.
  - gemini     : Google AI Studio tem camada gratuita (modelos Flash / Flash-Lite).
  - groq       : camada gratuita sem cartão, modelos abertos e muito rápidos.
  - openrouter : modelos ":free" e o roteador "openrouter/free".
  - anthropic  : Claude (Haiku = mais barato; Sonnet = mais caprichado).
  - ollama     : roda local, de graça (precisa de um modelo bom em tool calling).

Os nomes de modelo mudam com frequência; todos podem ser sobrescritos com LLM_MODELO.
"""
from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel

PROVEDORES = {
    "deepseek": {
        "modelo": "deepseek-flash",
        "env_chave": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com",
        "obter_chave": "https://platform.deepseek.com/api_keys",
    },
    "gemini": {
        "modelo": "gemini-3.8-flash",
        "env_chave": "GEMINI_API_KEY",
        "obter_chave": "https://aistudio.google.com/apikey",
    },
    "groq": {
        "modelo": "openai/gpt-oss-120b",
        "env_chave": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "obter_chave": "https://console.groq.com/keys",
    },
    "openrouter": {
        "modelo": "openrouter/free",
        "env_chave": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "obter_chave": "https://openrouter.ai/keys",
    },
    "anthropic": {
        "modelo": "claude-haiku-5-5",
        "env_chave": "ANTHROPIC_API_KEY",
        "obter_chave": "https://console.anthropic.com/settings/keys",
    },
    "ollama": {
        "modelo": "qwen3:8b",
        "env_chave": None,
        "base_url": "http://localhost:11434/v1",
        "obter_chave": "https://ollama.com/download",
    },
}


def criar_llm(provedor: str | None = None, modelo: str | None = None,
              api_key: str | None = None, temperatura: float = 0.3) -> BaseChatModel:
    provedor = (provedor or os.getenv("LLM_PROVEDOR") or "deepseek").lower()
    if provedor not in PROVEDORES:
        raise ValueError(f"Provedor '{provedor}' desconhecido. Opções: {', '.join(PROVEDORES)}")
    cfg = PROVEDORES[provedor]
    modelo = modelo or os.getenv("LLM_MODELO") or cfg["modelo"]
    chave = api_key or (os.getenv(cfg["env_chave"]) if cfg["env_chave"] else "ollama")
    if not chave:
        raise ValueError(f"Defina {cfg['env_chave']} (crie a chave em {cfg['obter_chave']}).")

    if provedor == "anthropic":
        from langchain_anthropic import ChatAnthropic
        # Sem `temperature`: os modelos Claude 5 recusam o parâmetro (400 "temperature is deprecated").
        return ChatAnthropic(model=modelo, api_key=chave, max_tokens=2048, max_retries=3)

    if provedor == "gemini":
        # Integração nativa: preserva as "thought signatures" que o Gemini exige entre chamadas de ferramentas.
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=modelo, google_api_key=chave, max_retries=3)

    from langchain_openai import ChatOpenAI
    extra = {}
    if provedor == "deepseek":
        # O modo "pensamento" do DeepSeek exige reenviar o raciocínio a cada chamada com ferramentas;
        # para uma entrevista conversacional o modo direto é suficiente, mais rápido e mais barato.
        extra["extra_body"] = {"thinking": {"type": "disabled"}}
    return ChatOpenAI(model=modelo, api_key=chave, base_url=cfg["base_url"],
                      temperature=temperatura, max_retries=3, **extra)
