# CLAUDE.md

Agente conversacional (LangChain + LangGraph) que entrevista uma pessoa leiga sobre um
processo de trabalho e desenha um BPMN 2.0 aos poucos. Leia `HANDOFF.md` para o estado
atual, decisões tomadas e próximos passos.

## Comandos

```bash
pip install -r requirements.txt
python -m pytest -q                                   # testes (sem API; usam LLM roteirizada)
streamlit run app.py                                  # app web
python cli.py --debug                                 # terminal
python scripts/gerar_exemplo.py exemplos/reembolso.bpmn   # monta exemplo sem LLM
cd scripts && npm install                             # uma vez, para os dois abaixo
node scripts/validar_bpmn.mjs <arquivo.bpmn>          # valida no parser oficial do bpmn.io
python scripts/renderizar.py <in.bpmn> <out.png>      # renderiza com bpmn-js (precisa playwright+chromium)
```

## Regras do projeto

- **Código, identificadores, prompts, mensagens e docs em português do Brasil.** A UI e o agente
  falam com leigos: nada de jargão (BPMN, gateway, raia, evento) nos textos para o usuário final.
- **O LLM nunca gera XML.** Toda mudança no diagrama passa por métodos de `ModeloProcesso`
  (`bpmn_agent/modelo.py`), expostos como tools em `ferramentas.py`. Nova capacidade de edição =
  método no modelo (com `self._snapshot()` antes de mutar) + tool + teste.
- Erros de uso viram `ErroModelo` com mensagem que ensina o LLM a se corrigir (ex.: listar ids
  candidatos). Não lance exceções genéricas dentro do modelo.
- Esquemas de tools simples: strings com default `""` em vez de `Optional`/`None`
  (modelos baratos erram menos). Descrições dos parâmetros via `Annotated`.
- Depois de mexer em `exportar_bpmn.py`: rode os testes, `validar_bpmn.mjs` (tem que dar 0 avisos)
  e **olhe** o PNG de `renderizar.py` — layout bom só se confirma vendo.
- Nomes de modelos de LLM mudam rápido: ficam só em `PROVEDORES` (`llm.py`) e são sobrescrevíveis
  por `LLM_MODELO`. Confira na documentação do provedor antes de trocar um padrão.
- Nunca commitar `.env` nem `sessoes/`.
