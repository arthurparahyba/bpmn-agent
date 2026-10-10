"""
Renderiza um .bpmn em PNG com o bpmn-js (o mesmo visualizador do app), sem internet.
Serve para conferir o layout automático visualmente.

Pré-requisitos (uma vez):
    pip install playwright && python -m playwright install chromium
    cd scripts && npm install

Uso:
    python scripts/renderizar.py exemplos/reembolso.bpmn saida.png [ids para destacar...]
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from playwright.sync_api import sync_playwright  # noqa: E402

from bpmn_agent.visualizador import html_visualizador  # noqa: E402

DIST = RAIZ / "scripts" / "node_modules" / "bpmn-js" / "dist"


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    if not DIST.exists():
        sys.exit("bpmn-js não encontrado: rode `cd scripts && npm install`.")
    entrada, saida, destacar = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    html = html_visualizador(entrada.read_text(encoding="utf-8"), altura=700,
                             base=DIST.as_uri(), destacar=destacar)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
    with sync_playwright() as pw:
        navegador = pw.chromium.launch()
        pagina = navegador.new_page(viewport={"width": 1500, "height": 760})
        erros: list[str] = []
        pagina.on("pageerror", lambda e: erros.append(str(e)))
        pagina.goto(Path(f.name).as_uri())
        pagina.wait_for_function("window.__pronto === true", timeout=15000)
        falha = pagina.inner_text("#erro")
        pagina.screenshot(path=str(saida))
        navegador.close()
    if erros or falha:
        sys.exit(f"Falhou ao desenhar: {falha or erros}")
    print(f"OK: {saida}")


if __name__ == "__main__":
    main()
