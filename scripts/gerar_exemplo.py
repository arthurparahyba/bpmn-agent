"""
Monta o processo de exemplo (reembolso) usando só as operações do modelo, sem LLM.
Útil para testar mudanças no layout/exportador:

    python scripts/gerar_exemplo.py exemplos/reembolso.bpmn
    node scripts/validar_bpmn.mjs exemplos/reembolso.bpmn
    python scripts/renderizar.py exemplos/reembolso.bpmn exemplos/reembolso.png
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bpmn_agent.exportar_bpmn import gerar_bpmn_xml  # noqa: E402
from bpmn_agent.modelo import ModeloProcesso  # noqa: E402

m = ModeloProcesso()
m.definir_processo("Reembolso de despesas", "Funcionário pede reembolso de despesas de viagem")
m.adicionar_elemento("tarefa_pessoa", "Enviar pedido com comprovantes", "Funcionário")
m.adicionar_elemento("tarefa_pessoa", "Analisar pedido", "Gestor", depois_de="Enviar pedido")
m.adicionar_elemento("decisao", "Pedido aprovado?", "Gestor", depois_de="Analisar pedido")
m.adicionar_elemento("tarefa_sistema", "Agendar pagamento", "Financeiro", depois_de="Pedido aprovado?", rotulo_conexao="Sim")
m.adicionar_elemento("fim", "Reembolso pago", "Financeiro", depois_de="Agendar pagamento")
m.adicionar_elemento("decisao", "Dá para corrigir?", "Gestor", depois_de="Pedido aprovado?", rotulo_conexao="Não")
m.adicionar_elemento("envio", "Avisar recusa", "Gestor", depois_de="Dá para corrigir?", rotulo_conexao="Não")
m.adicionar_elemento("fim", "Pedido recusado", "Gestor", depois_de="Avisar recusa")
m.adicionar_elemento("tarefa_pessoa", "Corrigir pedido", "Funcionário", depois_de="Dá para corrigir?", rotulo_conexao="Sim")
m.conectar("Corrigir pedido", "Analisar pedido")
m.adicionar_regra("Analisar pedido", "Prazo de 5 dias úteis")
m.adicionar_elemento("tarefa_sistema", "Conferir limite da política", "Financeiro", depois_de="Enviar pedido")
m.adicionar_elemento("espera", "Aguardar data de pagamento", "Financeiro", depois_de="Agendar pagamento")
assert not m.problemas(), m.problemas()

destino = Path(sys.argv[1] if len(sys.argv) > 1 else "exemplos/reembolso.bpmn")
destino.write_text(gerar_bpmn_xml(m), encoding="utf-8")
m.salvar(destino.with_suffix(".json"))
print(f"OK: {destino}")
