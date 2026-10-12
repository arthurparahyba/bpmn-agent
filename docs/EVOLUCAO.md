# Evolução do agente (após `e0ae5e2`)

Resumo, para revisão, do que foi acrescentado ao projeto depois do commit `e0ae5e2`. São 14 commits, 27 arquivos,
cerca de 1650 linhas a mais. Os testes passam (92). Os detalhes de cada peça estão em `docs/pecas/`.

## Ideia central

O agente continua sendo a mesma arquitetura: a LLM chama ferramentas, o `ModeloProcesso` é a fonte da verdade e a
LLM nunca escreve XML. O que mudou foi uma **camada de verificação feita por código**, porque a LLM às vezes diz que
fez algo que não fez, ou supõe o que ninguém disse. O código compara o desenho antes e depois de cada turno e avisa.

## Por commit

| Commit | O que mudou | Por quê |
|---|---|---|
| `8214683` | Provedor `openai` (API Responses) | Rodar com os modelos da OpenAI |
| `8ff4792` | Pede confirmação quando o pedido não bate com o desenho | Evitar edição no lugar errado |
| `db48832` | Prompt pede confirmação também para assunto alheio ao objetivo | Mesmo motivo |
| `b536374` | "🔎 O que mudou de fato" depois de cada turno | A LLM afirmava mudanças que não aconteceram |
| `a57c7e3` | Opção `estado_no_fim` (padrão desligada) | Testada para melhorar o cache; cerca de 25% mais barata no A/B |
| `285077f` | Catálogo de sistemas e APIs como entidade (`Sistema`), separado de participantes | "Core Bancário" era tratado de forma inconsistente |
| `831c276` | Renomear sistema; aviso "sistema deduzido, não dito por você"; perguntar em vez de supor | A LLM inventava sistemas |
| `0cf645b` | Sistema aparece como segunda linha do passo no desenho | No BPMN não ficava claro qual sistema era |
| `c9df434` | Sistema da empresa vira raia; sistema de terceiros vira caixa separada com seta de mensagem | Forma recomendada de mostrar sistemas em BPMN |
| `3c2f204` | "⚠️ Ainda há pontos em aberto" quando o agente dá o processo por concluído | Ele dizia "pronto" com pendências |
| `92589d4` | Passo com `sistema` (executa) e `chama` (aciona de fora); aviso de chamada repetida; aviso também em pergunta de fechamento | Separar quem executa de quem é chamado |
| `16f33ba` | Raia do sistema da empresa vale também para passo de envio | Caso que ficou de fora |
| `0283cb3` | Condição estruturada, catálogo de dados, aviso de volta para dentro de bloco paralelo, desenho sem setas atravessando elementos, rótulos sem sobreposição, cor por sistema de terceiros | Saída parametrizável e desenho legível |
| `4392f7f` | Aviso de "sistema deduzido" considera o pedido guardado no turno de confirmação | Falso alarme quando o usuário respondia só "Sim" |

## Pontos principais

- **Sistemas.** Sistema da empresa vira raia. Sistema de terceiros vira caixa com seta de mensagem, de cor própria.
  Sistema nunca é responsável nem participante.
- **Condições estruturadas.** `Condicao(campo, op, valor, unidade, acao, regra)`, com o catálogo `Dado` por jornada.
  Operadores `= != < <= > >= contem em`. O valor separa número e unidade: `60 dias`, `R$ 1 milhão` vira
  1000000 + BRL, `4%`.
- **Desenho.** As setas desviam de elementos, as saídas da mesma decisão usam corredores separados e os rótulos
  procuram um lugar livre.
- **Avisos calculados por código**, e não pela LLM: o que mudou de fato, sistema deduzido, pontos em aberto, chamada
  repetida, volta para dentro de bloco paralelo.

## Como foi testado

Além dos testes automáticos (`tests/test_sistemas.py`, `test_condicoes.py`, `test_desenho.py`, `test_agente.py`),
rodamos jornadas completas: crédito, seguro de vida, delivery, manutenção de piscinas e inventário de espólio.
No espólio, uma lista de 57 itens deu cerca de 95%, e cerca de 98% depois de correções feitas conversando com o agente.
Ressalvas: a nota foi dada por nós, o roteiro era guiado e foi uma execução só.

## Limites conhecidos

- O catálogo de sistemas e de dados vale por jornada. Não unifica sinônimos nem há catálogo corporativo entre jornadas.
- A LLM ainda pode deduzir um sistema. O código só avisa.
- O aviso de passo duplicado só pega chamadas idênticas (mesmo sistema, operação, executor e responsável).
- O nome da decisão (texto ao lado do losango) não passa pela busca de lugar livre.
- As setas pontilhadas dos sistemas de terceiros atravessam as raias.
- A variação da LLM entre execuções continua.
