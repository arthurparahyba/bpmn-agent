"""HTML que desenha o BPMN no navegador usando bpmn-js (o mesmo motor do bpmn.io)."""
from __future__ import annotations

import json

BPMN_JS_VERSAO = "18.31.0"
CDN = f"https://unpkg.com/bpmn-js@{BPMN_JS_VERSAO}/dist"


def html_visualizador(xml: str, altura: int = 600, base: str = CDN, destacar: list[str] | None = None) -> str:
    """
    Página autossuficiente com o diagrama (zoom com Ctrl+roda, arrastar para mover).
    `destacar`: ids de elementos alterados no último turno (ganham destaque visual).
    """
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link rel="stylesheet" href="{base}/assets/diagram-js.css">
<link rel="stylesheet" href="{base}/assets/bpmn-js.css">
<link rel="stylesheet" href="{base}/assets/bpmn-font/css/bpmn.css">
<style>
  html, body {{ margin:0; height:100%; font-family: system-ui, sans-serif; background:#fff; }}
  #canvas {{ height:{altura}px; border:1px solid #e3e3e3; border-radius:8px; }}
  .barra {{ position:absolute; top:8px; right:8px; z-index:10; display:flex; gap:4px; }}
  .barra button {{ border:1px solid #ccc; background:#fff; border-radius:6px; padding:2px 9px; cursor:pointer; font-size:14px; }}
  .novo:not(.djs-connection) .djs-visual > :nth-child(1) {{ stroke:#2e7d32 !important; stroke-width:3px !important; }}
  #erro {{ color:#b00020; padding:12px; }}
</style></head>
<body>
<div class="barra">
  <button onclick="zoom(1.2)" title="Aproximar">+</button>
  <button onclick="zoom(1/1.2)" title="Afastar">−</button>
  <button onclick="ajustar()" title="Ajustar à tela">⤢</button>
</div>
<div id="canvas"></div><div id="erro"></div>
<script src="{base}/bpmn-navigated-viewer.production.min.js"></script>
<script>
  const xml = {json.dumps(xml)};
  const destacar = {json.dumps(destacar or [])};
  const viewer = new BpmnJS({{ container: '#canvas' }});
  const canvas = () => viewer.get('canvas');
  function ajustar() {{ canvas().zoom('fit-viewport', 'auto'); }}
  function zoom(f) {{ canvas().zoom(canvas().zoom() * f); }}
  viewer.importXML(xml).then(() => {{
    ajustar();
    destacar.forEach(id => {{ try {{ canvas().addMarker(id, 'novo'); }} catch (e) {{}} }});
    window.__pronto = true;
  }}).catch(err => {{
    document.getElementById('erro').textContent = 'Não foi possível desenhar: ' + err.message;
    window.__pronto = true;
  }});
</script>
</body></html>"""
