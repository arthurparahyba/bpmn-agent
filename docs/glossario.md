# Glossário

Todo termo técnico usado na documentação está aqui, em ordem alfabética. Os nomes entre
crases são nomes que aparecem no código.

## Termos do domínio (processos e diagramas)

| Termo | Significado |
|---|---|
| **BPMN** | Padrão internacional para desenhar processos de trabalho com símbolos combinados (retângulo = tarefa, losango = decisão, círculo = início ou fim). A sigla vem de *Business Process Model and Notation*. Usamos a versão 2.0. |
| **Arquivo `.bpmn`** | Arquivo de texto no formato XML que descreve um diagrama BPMN. Abre em ferramentas como bpmn.io, Camunda Modeler e Bizagi. |
| **Conexão** (`Fluxo`) | A seta que liga dois elementos e diz "depois disto vem aquilo". No padrão BPMN chama-se *sequence flow*. |
| **Decisão** | Ponto do processo onde o caminho se divide conforme uma resposta ("Aprovado?" → Sim / Não). No padrão BPMN chama-se *exclusive gateway* e é desenhada como um losango. |
| **DI** | Parte do arquivo `.bpmn` que guarda as posições na tela: onde fica cada caixa e por onde passa cada seta. Vem de *Diagram Interchange*. Sem ela o arquivo descreve o processo, mas nenhuma ferramenta sabe como desenhá-lo. |
| **Elemento** | Qualquer coisa que aparece no desenho e não é seta: início, fim, tarefa, decisão, paralelo, espera. |
| **Espera** | Ponto em que o processo fica parado aguardando um prazo ou uma data. |
| **Gateway** | Nome que o padrão BPMN dá aos losangos. No projeto são dois: decisão e paralelo. |
| **Layout** | O cálculo das posições: em que coluna, raia e linha cada elemento fica, e que caminho cada seta faz. |
| **Paralelo** | Losango que divide o processo em caminhos que acontecem ao mesmo tempo, ou que junta esses caminhos de volta. |
| **Participante** | Quem executa passos: uma pessoa, um cargo, uma área ou um sistema. |
| **Pendência** | Lembrete que o agente anota para perguntar depois ("e se o diretor recusar?"). |
| **Piscina** (*pool*) | O retângulo grande que envolve o processo inteiro no desenho. |
| **Ponto em aberto** | Problema que o próprio código detecta no diagrama, como um passo sem saída ou uma decisão com um caminho só. Sai de `ModeloProcesso.problemas()`. |
| **Raia** (*lane*) | Faixa horizontal dentro da piscina. Cada participante tem a sua, e os passos dele ficam dentro dela. |
| **Regra** | Texto livre preso a um elemento: prazo, valor-limite, documento exigido. |
| **Rótulo** | Texto escrito sobre uma conexão, normalmente a resposta de uma decisão ("Sim", "Acima de R$ 5 mil"). |
| **Volta** | Conexão que retorna para um passo anterior (retrabalho). Forma um ciclo no desenho. |

## Termos de inteligência artificial

| Termo | Significado |
|---|---|
| **LLM** | O modelo de linguagem: o programa de IA que lê texto e responde texto (Claude, Gemini, DeepSeek...). A sigla vem de *Large Language Model*. |
| **Provedor** | A empresa que oferece a LLM pela internet (Anthropic, Google, DeepSeek, Groq, OpenRouter) ou o programa que a roda na sua máquina (Ollama). |
| **Chave de API** | Senha longa que identifica a sua conta no provedor. Fica no arquivo `.env` e nunca vai para o git. |
| **Prompt de sistema** | Texto de instruções enviado à LLM antes da conversa: quem ela é, como deve falar, que regras seguir. O usuário não o vê. |
| **Tool** (ferramenta) | Função Python que a LLM pode pedir para executar. A LLM não executa nada sozinha: ela responde "quero chamar `conectar` com estes dados" e o nosso código é que chama. |
| **Chamada de tool** (*tool call*) | O pedido da LLM para executar uma tool, com nome e argumentos. |
| **Esquema da tool** | A descrição que a LLM recebe de cada tool: nome, para que serve e quais parâmetros aceita. |
| **Token** | Pedaço de texto (mais ou menos uma sílaba) que é a unidade de cobrança e de limite das LLMs. |
| **Turno** | Uma mensagem do usuário mais tudo o que acontece até o agente responder em texto. |
| **Agente** | Programa em que a LLM decide os próximos passos e usa tools em um laço, em vez de só responder uma vez. |
| **LLM roteirizada** | LLM falsa usada nos testes, que devolve respostas escritas de antemão. Permite testar sem internet e sem custo. |

## Termos das bibliotecas usadas

| Termo | Significado |
|---|---|
| **LangChain** | Biblioteca Python que dá uma forma única de falar com LLMs de provedores diferentes e de declarar tools. |
| **LangGraph** | Biblioteca da mesma família que organiza o agente como um grafo: caixas (nós) que fazem trabalho e setas que dizem quem vem depois. |
| **Grafo** | Conjunto de pontos ligados por setas. Aparece em dois sentidos: o grafo do LangGraph (os passos do agente) e o próprio diagrama do processo (elementos ligados por conexões). |
| **Nó** | Uma caixa do grafo do LangGraph. Temos dois: `agente` e `ferramentas`. |
| **Estado do grafo** (`MessagesState`) | O que o LangGraph carrega de um nó para o outro. Aqui é só a lista de mensagens da conversa. |
| **Checkpointer** (`MemorySaver`) | Componente do LangGraph que guarda o estado entre um turno e o próximo. O `MemorySaver` guarda na memória do programa, então a conversa se perde ao reiniciar. |
| **`thread_id`** | Identificador que diz ao checkpointer de qual conversa estamos falando. Usamos o id da sessão. |
| **`HumanMessage`, `AIMessage`, `ToolMessage`, `SystemMessage`** | Os quatro tipos de mensagem do LangChain: fala do usuário, resposta da LLM, resultado de uma tool e instruções de sistema. |
| **`bind_tools`** | Método do LangChain que entrega à LLM a lista de tools disponíveis. |
| **Streamlit** | Biblioteca Python para fazer páginas web simples sem escrever HTML. Roda o script inteiro de novo a cada clique. |
| **`st.session_state`** | A "memória" do Streamlit entre uma execução do script e a próxima. É onde a `Sessao` vive. |
| **bpmn-js** | Biblioteca JavaScript do projeto bpmn.io que desenha um arquivo `.bpmn` no navegador. |
| **bpmn-moddle** | Biblioteca do mesmo projeto que lê um `.bpmn` e aponta erros de formato. Usada em `scripts/validar_bpmn.mjs`. |
| **CDN** | Servidor público de onde o navegador baixa bibliotecas. Usamos o unpkg para o bpmn-js. |
| **Playwright** | Biblioteca que controla um navegador por código. Usada só para gerar PNG em `scripts/renderizar.py`. |

## Termos de programação

| Termo | Significado |
|---|---|
| **Closure** | Função criada dentro de outra, que "lembra" as variáveis de onde nasceu. As tools são closures que lembram a qual sessão pertencem. |
| **Dataclass** | Classe Python que só guarda dados, declarada de forma curta. `Elemento`, `Fluxo` e `Processo` são dataclasses. |
| **Determinístico** | Que dá sempre o mesmo resultado para a mesma entrada. O modelo e o exportador são assim; a LLM não é. |
| **Snapshot** | Cópia completa do processo tirada antes de cada alteração. É o que torna o "desfazer" possível. |
| **Ordem topológica** | Ordenar os elementos de modo que cada um apareça depois de todos os que levam até ele. Usada para decidir as colunas do desenho. |
| **Busca em profundidade** (DFS) | Jeito de percorrer um grafo seguindo um caminho até o fim antes de tentar o próximo. Usada para achar as voltas. |
| **XML** | Formato de texto com marcações entre `<` e `>`. O arquivo `.bpmn` é um XML. |
| **`.env`** | Arquivo local com configurações e segredos (provedor, modelo, chave de API). |
