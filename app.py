# app.py - Corrected Graph Visualization (v10)

from fasthtml.common import *
import json
import networkx as nx
from typing import Optional, Tuple
import time
import os
import traceback

# Initialize app
app, rt = fast_app(
    secret_key=os.environ.get('SECRET_KEY'),
    #secret_key="total _bulshit",
    hdrs=(
        Script(src="https://unpkg.com/cytoscape@3.28.1/dist/cytoscape.min.js"),
        Script(src="https://unpkg.com/@popperjs/core@2"),
        Script(src="https://unpkg.com/cytoscape-popper@2.0.0/cytoscape-popper.js"),
        Script(src="https://unpkg.com/interact.js/dist/interact.min.js"),
    )
)

# ==============================================================================
# DATA STRUCTURES (Unchanged)
# ==============================================================================
class NodeData:
    def __init__(self, **kwargs):
        self.type = kwargs.get('type', 'DEFAULT')
        self.normalized_key = kwargs.get('normalized_key', '')
        self.texts = kwargs.get('texts', {})
        self.components = kwargs.get('components', [])
        for k, v in kwargs.items():
            if k not in ['type', 'normalized_key', 'texts', 'number', 'components']:
                setattr(self, k, v)

    def get_text(self, lang: str) -> str:
        if not isinstance(self.texts, dict): return "Invalid text data"
        text = self.texts.get(lang)
        if text: return text
        if lang and 'english' in lang.lower():
            for key, value in self.texts.items():
                if 'english' in key.lower(): return value
        return next(iter(self.texts.values()), "No text available")

    def get_demonstration(self, lang: str = None) -> Optional[str]:
        if not self.components: return None
        for comp in self.components:
            if comp.get('type') == 'DEMONSTRATION':
                texts = comp.get('texts', {})
                if lang and lang in texts: return texts[lang]
                return next(iter(texts.values()), None)
        return None

# ==============================================================================
# STYLES (Unchanged)
# ==============================================================================
graph_styles = Style("""
    body, html { margin: 0; padding: 0; overflow: hidden; }
    #cy { width: 100vw; height: 100vh; background-color: #f7f7f7; position: relative; }
    .tooltip { position: absolute; display: none; background-color: #282c34; color: white; padding: 8px 12px; border-radius: 6px; font-size: 14px; pointer-events: none; z-index: 9999; box-shadow: 0 2px 4px rgba(0,0,0,0.2); max-width: 400px; word-wrap: break-word; }
    .modal { display: none; position: fixed; z-index: 1000; background-color: rgba(0,0,0,0.4); width: 100%; height: 100%; top: 0; left: 0; }
    .modal-content { position: absolute; background-color: #fefefe; padding: 0; border: 1px solid #888; width: 80%; height: 80vh; overflow: hidden; resize: both; min-width: 400px; min-height: 300px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); top: 50px; left: 50px; display: flex; flex-direction: column; }
    .modal-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 20px; border-bottom: 1px solid #ccc; cursor: move; background-color: #f1f1f1; }
    .modal-body { flex-grow: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; min-height: 0; }
    .close-button { color: #aaa; font-size: 28px; font-weight: bold; cursor: pointer; line-height: 20px; }
    .close-button:hover { color: #000; }
    .proof-tree { display: flex; flex-direction: column; align-items: center; gap: 20px; padding: 20px; margin-bottom: 30px; }
    .proof-node { position: relative; cursor: pointer; display: flex; align-items: center; gap: 5px; }
    .proof-dot { width: 16px; height: 16px; border-radius: 50%; display: inline-block; }
    .proof-label { font-size: 12px; font-family: monospace; }
    .premises-container { display: flex; gap: 30px; justify-content: center; align-items: flex-start; }
    .tree-arrow { text-align: center; font-size: 20px; margin: -5px 0; color: #666; }
    .tree-arrow::before { content: '▼'; }
    .main-node-box { border: 2px solid #333; padding: 15px; margin: 10px; border-radius: 8px; background-color: #f9f9f9; cursor: pointer; position: relative; }
    .tab-buttons { display: flex; gap: 10px; margin-bottom: 15px; flex-shrink: 0; }
    .node-definition { background-color: #007bff; } .node-axiom { background-color: #dc3545; } .node-proposition { background-color: #28a745; } .node-theorem { background-color: #ffc107; }
    .node-appendice { background-color: #17a2b8; } .node-corollaire { background-color: #e83e8c; } .node-scolie { background-color: #fd7e14; } .node-default { background-color: #6c757d; }
""")

# ==============================================================================
# JSON PREPROCESSING AND GRAPH OPS (Unchanged)
# ==============================================================================
def fix_json_data(data: dict) -> dict:
    for vertex in data.get("vertices", []):
        if "'english_text'" in vertex.get("texts", {}): vertex["texts"]["english_text"] = vertex["texts"].pop("'english_text'")
        for comp in vertex.get("components", []):
            if "'english_text'" in comp.get("texts", {}): comp["texts"]["english_text"] = comp["texts"].pop("'english_text'")
    return data

def create_graph_from_data(items: list, edges: list) -> nx.DiGraph:
    G = nx.DiGraph()
    for item in items:
        if 'normalized_key' in item: G.add_node(item['normalized_key'], **item)
    for edge in edges:
        u, v = edge.get("source"), edge.get("target")
        if u and v and G.has_node(u) and G.has_node(v):
            G.add_edge(u, v, **{k: val for k, val in edge.items() if k not in ['source', 'target']})
    return G

def calculate_node_levels(graph: nx.DiGraph) -> dict:
    try:
        g_copy, levels, current_level = graph.copy(), {}, 0
        while g_copy.nodes():
            roots = [n for n, d in g_copy.in_degree() if d == 0]
            if not roots: raise nx.NetworkXError("Graph contains cycles")
            for node in roots: levels[node] = current_level
            g_copy.remove_nodes_from(roots)
            current_level += 1
        return levels
    except nx.NetworkXError: return {}

def get_local_subgraph(graph: nx.DiGraph, node: str) -> nx.DiGraph:
    if not graph.has_node(node): return nx.DiGraph()
    return graph.subgraph(nx.ancestors(graph, node).union({node}))

def serialize_graph_for_cytoscape(graph: nx.DiGraph, levels: dict) -> str:
    elements = []
    nodes_by_level = {level: [n for n, l in levels.items() if l == level] for level in set(levels.values())}
    for level, nodes in nodes_by_level.items():
        for i, key in enumerate(nodes):
            attrs = graph.nodes[key]
            x = (i - (len(nodes) - 1) / 2) * 200
            y = level * 150
            elements.append({
                "data": {"id": key, "label": key, "type": attrs.get("type", "DEFAULT").lower()},
                "position": {"x": x, "y": y}
            })
    for u, v in graph.edges():
        elements.append({"data": {"id": f"{u}->{v}", "source": u, "target": v}})
    return json.dumps(elements, indent=2)

# ==============================================================================
# JAVASCRIPT COMPONENTS (Unchanged)
# ==============================================================================
def cytoscape_init_script(container_id: str, elements_json: str) -> Script:
    return Script(f"""
    window.addEventListener('load', function() {{
        const container = document.getElementById('{container_id}');
        if (!container || typeof cytoscape === 'undefined') return;
        const elements = {elements_json};
        const tooltipDiv = document.createElement('div');
        tooltipDiv.className = 'tooltip';
        document.body.appendChild(tooltipDiv);
        let popperRef;
        if (typeof cytoscapePopper !== 'undefined' && !cytoscape.prototype.popper) {{
            cytoscape.use(cytoscapePopper);
        }}
        const cy = cytoscape({{
            container: container, elements: elements, layout: {{ name: 'preset', padding: 50 }},
            style: [
                {{ selector: 'node', style: {{
                    'background-color': function(ele) {{
                        const t = ele.data('type').toLowerCase();
                        if (t === 'definition') return '#007bff'; if (t === 'axiome' || t === 'axiom') return '#dc3545';
                        if (t === 'proposition') return '#28a745'; if (t === 'theorem') return '#ffc107';
                        if (t === 'appendice') return '#17a2b8'; if (t === 'corollaire') return '#e83e8c';
                        if (t === 'scolie') return '#fd7e14'; return '#6c757d';
                    }}, 'width': '12px', 'height': '12px'
                }} }},
                {{ selector: 'edge', style: {{ 'width': 1.5, 'line-color': '#ccc', 'target-arrow-color': '#ccc', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier' }} }}
            ],
            minZoom: 0.2, maxZoom: 3
        }});
        cy.on('mouseover', 'node', function(evt) {{
            popperRef = evt.target.popper({{
                content: function() {{
                    tooltipDiv.innerHTML = evt.target.data('label');
                    tooltipDiv.style.display = 'block';
                    return tooltipDiv;
                }}
            }});
        }});
        cy.on('mouseout', 'node', function() {{
            if (popperRef) popperRef.destroy();
            tooltipDiv.style.display = 'none';
        }});
        cy.on('tap', 'node', function(evt) {{
            htmx.ajax('GET', `/local_view/${{evt.target.id()}}`, {{ target: document.body, swap: 'beforeend' }});
        }});
        window.addEventListener('resize', function() {{ cy.resize(); cy.fit(null, 50); }});
    }});
    """)

def modal_interaction_script(modal_id: str) -> Script:
    return Script(f"""
    (function() {{
        function initModal() {{
            if (typeof interact === 'undefined') {{ setTimeout(initModal, 100); return; }}
            const modal = document.getElementById('{modal_id}');
            if (!modal) return;
            const modalContent = modal.querySelector('.modal-content');
            const header = modal.querySelector('.modal-header');
            const openModals = document.querySelectorAll('.modal[style*="display: block"]').length;
            const offset = (openModals > 1 ? openModals - 1 : 0) * 30;
            modalContent.style.top = (50 + offset) + 'px';
            modalContent.style.left = (50 + offset) + 'px';
            modal.style.display = 'block';
            interact(modalContent).draggable({{
                allowFrom: header,
                listeners: {{
                    move: function(event) {{
                        const target = event.target;
                        const x = (parseFloat(target.getAttribute('data-x')) || 0) + event.dx;
                        const y = (parseFloat(target.getAttribute('data-y')) || 0) + event.dy;
                        target.style.transform = 'translate(' + x + 'px, ' + y + 'px)';
                        target.setAttribute('data-x', x);
                        target.setAttribute('data-y', y);
                    }}
                }}
            }});
            interact(modalContent).resizable({{
                edges: {{ left: true, right: true, bottom: true, top: false }},
                listeners: {{
                    move: function(event) {{
                        let target = event.target;
                        let x = (parseFloat(target.getAttribute('data-x')) || 0);
                        let y = (parseFloat(target.getAttribute('data-y')) || 0);
                        target.style.width = event.rect.width + 'px';
                        target.style.height = event.rect.height + 'px';
                        x += event.deltaRect.left;
                        y += event.deltaRect.top;
                        target.style.transform = 'translate(' + x + 'px, ' + y + 'px)';
                        target.setAttribute('data-x', x);
                        target.setAttribute('data-y', y);
                        const cyContainer = event.target.querySelector('[id^="local-cy-"]');
                        if (cyContainer && cyContainer._cy) {{
                            cyContainer._cy.resize();
                        }}
                    }}
                }}
            }});
        }}
        initModal();
    }})();
    """)

def proof_tree_hover_script(container_id: str) -> Script:
    return Script(f"""
    (function() {{
        const js_container_id = '{container_id}';
        const tooltipId = 'tooltip-' + js_container_id;
        let tooltip = document.getElementById(tooltipId);
        if (!tooltip) {{
            tooltip = document.createElement('div');
            tooltip.className = 'tooltip';
            tooltip.id = tooltipId;
            document.body.appendChild(tooltip);
        }}
        const container = document.getElementById(js_container_id);
        if (!container) return;
        function showTip(content) {{ tooltip.innerHTML = content; tooltip.style.display = 'block'; }};
        function hideTip() {{ tooltip.style.display = 'none'; }};
        function moveTip(e) {{ tooltip.style.left = (e.pageX + 10) + 'px'; tooltip.style.top = (e.pageY - 30) + 'px'; }};
        container.addEventListener('mouseover', function(e) {{
            const proofNode = e.target.closest('.proof-node');
            const mainBox = e.target.closest('.main-node-box');
            if (proofNode) {{ showTip(proofNode.getAttribute('data-text'));
            }} else if (mainBox) {{
                const demo = mainBox.getAttribute('data-demonstration');
                if (demo && demo !== 'No Demonstration') {{ showTip('<strong>Demonstration:</strong><br>' + demo); }}
            }}
        }});
        container.addEventListener('mouseout', hideTip);
        container.addEventListener('mousemove', moveTip);
        const checkModal = setInterval(function() {{
            if (!document.getElementById(js_container_id)) {{
                tooltip.remove();
                clearInterval(checkModal);
            }}
        }}, 1000);
    }})();
    """)

# ==============================================================================
# COMPONENTS
# ==============================================================================
def create_modal(modal_id: str, node_key: str, content, selected_lang: str = None) -> Div:
    node_data = NodeData(**T_GRAPH.nodes[node_key])
    available_langs = list(node_data.texts.keys())
    selected_lang = selected_lang or (available_langs[0] if available_langs else 'french_text')
    def format_lang_name(k): return k.replace('_text', '').replace('_', ' ').title()
    lang_selector = ""
    if len(available_langs) > 1:
        lang_options = [Option(format_lang_name(k), value=k, selected=(k == selected_lang)) for k in available_langs]
        lang_selector = Select(*lang_options, hx_get=f"/update_modal_language/{node_key}", hx_target=f"#{modal_id} .modal-content", hx_swap="outerHTML", hx_trigger="change", name="lang", style="margin-left: auto;")
    close_button = Span("×", cls="close-button", onclick="this.closest('.modal').remove()")
    modal_content = Div(
        Div(Strong(f"Local Graph: {node_key}"), lang_selector, close_button, cls="modal-header"),
        Div(content, cls="modal-body"),
        cls="modal-content", data_current_lang=selected_lang
    )
    return Div(modal_content, modal_interaction_script(modal_id), id=modal_id, cls="modal")

def create_modal_content(node_key: str, content, selected_lang: str) -> Div:
    node_data = NodeData(**T_GRAPH.nodes[node_key])
    available_langs = list(node_data.texts.keys())
    def format_lang_name(k): return k.replace('_text', '').replace('_', ' ').title()
    lang_selector = ""
    if len(available_langs) > 1:
        lang_options = [Option(format_lang_name(k), value=k, selected=(k == selected_lang)) for k in available_langs]
        lang_selector = Select(*lang_options, hx_get=f"/update_modal_language/{node_key}", hx_target="closest .modal-content", hx_swap="outerHTML", hx_trigger="change", name="lang", style="margin-left: auto;")
    close_button = Span("×", cls="close-button", onclick="this.closest('.modal').remove()")
    # This function is called by the language updater, so it needs to return the full new modal-content
    return Div(
        Div(Strong(f"Local Graph: {node_key}"), lang_selector, close_button, cls="modal-header"),
        Div(content, cls="modal-body"),
        cls="modal-content", data_current_lang=selected_lang
    )

def create_tab_buttons(node_key: str, content_id: str, lang: str, active_tab: str = "visual") -> Div:
    return Div(
        Button("Visual", cls=f"tab-button {'active' if active_tab == 'visual' else ''}", hx_get=f"/local_view/visual/{node_key}?lang={lang}", hx_target=f"#{content_id}", hx_swap="innerHTML"),
        Button("Textual", cls=f"tab-button {'active' if active_tab == 'textual' else ''}", hx_get=f"/local_view/textual/{node_key}?lang={lang}", hx_target=f"#{content_id}", hx_swap="innerHTML"),
        cls="tab-buttons"
    )

def render_proof_tree_node(subgraph: nx.DiGraph, node_key: str, selected_lang: str) -> Div:
    predecessors = list(subgraph.predecessors(node_key))
    node_data = NodeData(**T_GRAPH.nodes[node_key])
    color_class = f"node-{node_data.type.lower().replace('axiome', 'axiom')}"
    tree_content = []
    if predecessors:
        premise_divs = [render_proof_tree_node(subgraph, p, selected_lang) for p in predecessors]
        tree_content.extend([Div(*premise_divs, cls="premises-container"), Div(cls="tree-arrow")])
    proof_node = Div(Span(cls=f"proof-dot {color_class}"), Span(node_key, cls="proof-label"), cls="proof-node", data_text=node_data.get_text(selected_lang))
    tree_content.append(proof_node)
    return Div(*tree_content, style="display: flex; flex-direction: column; align-items: center;")

def render_main_node_box(node_key: str, selected_lang: str) -> Div:
    node_data = NodeData(**T_GRAPH.nodes[node_key])
    main_text = node_data.get_text(selected_lang)
    # FIX: Corrected NameError by using `selected_lang` instead of `lang`.
    demonstration_text = node_data.get_demonstration(selected_lang)
    content_parts = [P(main_text)]
    if demonstration_text:
        content_parts.append(Hr())
        content_parts.append(H4("Demonstration"))
        content_parts.append(P(demonstration_text))
    demonstration_tooltip = demonstration_text or "No Demonstration"
    return Div(
        H3(f"{node_data.type}: {node_key}"),
        *content_parts,
        cls="main-node-box",
        data_demonstration=demonstration_tooltip
    )

# ==============================================================================
# ROUTES & RENDERING
# ==============================================================================
# FIX: Restored the missing `elements_json` definition.
@rt("/")
def get():
    try:
        if not T_GRAPH or T_GRAPH.number_of_nodes() == 0:
            return Titled("Graph Visualization - No Data", Div(P("No graph data loaded.")))
        elements_json = serialize_graph_for_cytoscape(T_GRAPH, NODE_LEVELS)
        return Titled("Livre I", graph_styles, Div(id="cy"), cytoscape_init_script("cy", elements_json))
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"--- SERVER ERROR IN / ROUTE ---\n{error_details}\n-----------------------------")
        return Titled("Server Error", H2("An error occurred on the server"), P("The following error was caught:"), Pre(Code(error_details), style="background-color: #eee; padding: 10px; border-radius: 5px;"), style="padding: 20px;")

# FIX: Restructured the returned Div to create a stable flex container for swapped content.
@rt("/local_view/{node_key}")
def get(node_key: str, lang: str = None):
    if node_key not in T_GRAPH: return Div(f"Node {node_key} not found", style="color: red;")
    node_data = NodeData(**T_GRAPH.nodes[node_key])
    lang = lang or next(iter(node_data.texts.keys()), 'french_text')
    subgraph = get_local_subgraph(T_GRAPH, node_key)
    modal_id = f"modal-{node_key.replace('.', '-')}-{int(time.time() * 1000)}"
    content_id = f"local-content-{node_key.replace('.', '-')}-{int(time.time() * 1000)}"
    
    visual_content = render_local_visual(subgraph, node_key, lang)
    
    swappable_container = Div(visual_content, id=content_id, style="flex-grow: 1; min-height: 0;")
    
    content_wrapper = Div(
        create_tab_buttons(node_key, content_id, lang, "visual"),
        swappable_container,
        style="display: flex; flex-direction: column; height: 100%;"
    )
    return create_modal(modal_id, node_key, content_wrapper, lang)

@rt("/local_view/visual/{node_key}")
def get(node_key: str, lang: str = None):
    node_data = NodeData(**T_GRAPH.nodes[node_key])
    lang = lang or next(iter(node_data.texts.keys()), 'french_text')
    return render_local_visual(get_local_subgraph(T_GRAPH, node_key), node_key, lang)

@rt("/local_view/textual/{node_key}")
def get(node_key: str, lang: str = None):
    try:
        if node_key not in T_GRAPH: return Div(f"Node {node_key} not found", style="color: red;")
        node_data = NodeData(**T_GRAPH.nodes[node_key])
        lang = lang or next(iter(node_data.texts.keys()), 'french_text')
        return render_local_textual(get_local_subgraph(T_GRAPH, node_key), node_key, lang)
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"--- SERVER ERROR IN /local_view/textual/{node_key} ---\n{error_details}\n--------------------------------------------------")
        return Div(H4("Error rendering textual view"), Pre(Code(error_details)), style="color: red; background: #fee; padding: 10px; border: 1px solid red;")

@rt("/update_modal_language/{node_key}")
def get(node_key: str, lang: str):
    subgraph = get_local_subgraph(T_GRAPH, node_key)
    content_id = f"local-content-{node_key.replace('.', '-')}-{int(time.time() * 1000)}"
    swappable_container = Div(render_local_visual(subgraph, node_key, lang), id=content_id, style="flex-grow: 1; min-height: 0;")
    content_wrapper = Div(
        create_tab_buttons(node_key, content_id, lang, "visual"),
        swappable_container,
        style="display: flex; flex-direction: column; height: 100%;"
    )
    # The language updater needs to return the full modal-content, not the wrapper
    return create_modal_content(node_key, content_wrapper, lang)

# ==============================================================================
# VISUAL & TEXTUAL RENDERING
# ==============================================================================
def render_local_visual(subgraph: nx.DiGraph, node_key: str, lang: str) -> Div:
    container_id = f"local-cy-{node_key.replace('.', '-')}-{int(time.time() * 1000)}"
    elements = []
    for n in subgraph.nodes():
        node_data = NodeData(**T_GRAPH.nodes[n])
        elements.append({"data": { "id": n, "label": n, "type": node_data.type.lower(), "full_text": node_data.get_text(lang), "demonstration": node_data.get_demonstration(lang) if n == node_key else None, "is_center": n == node_key }})
    for u, v in subgraph.edges():
        elements.append({"data": {"id": f"{u}->{v}", "source": u, "target": v}})
    elements_json = json.dumps(elements)

    init_script = Script(f"""
        (function() {{
            requestAnimationFrame(function() {{
                const container = document.getElementById('{container_id}');
                if (!container || container._cy || typeof cytoscape === 'undefined') return;
                const cy = cytoscape({{
                    container: container,
                    elements: {elements_json},
                    layout: {{ name: 'breadthfirst', directed: true, padding: 30, grid: true, roots: ['{node_key}'] }},
                    style: [
                        {{ selector: 'node', style: {{
                            'label': 'data("label")', 'text-opacity': 1, 'font-size': '10px', 'text-valign': 'center', 'text-halign': 'center', 'color': '#333',
                            'text-outline-width': 2, 'text-outline-color': '#fff',
                            'background-color': function(ele) {{
                                const t = ele.data('type').toLowerCase();
                                if (t === 'definition') return '#007bff'; if (t === 'axiome' || t === 'axiom') return '#dc3545';
                                if (t === 'proposition') return '#28a745'; if (t === 'theorem') return '#ffc107';
                                if (t === 'appendice') return '#17a2b8'; if (t === 'corollaire') return '#e83e8c';
                                if (t === 'scolie') return '#fd7e14'; return '#6c757d';
                            }},
                            'width': '40px', 'height': '40px',
                            'border-width': function(ele) {{ return ele.data('is_center') ? 3 : 2; }},
                            'border-color': function(ele) {{ return ele.data('is_center') ? '#000' : '#333'; }}
                        }} }},
                        {{ selector: 'edge', style: {{ 'width': 1.5, 'line-color': '#ccc', 'target-arrow-color': '#ccc', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier' }} }}
                    ],
                    minZoom: 0.2, maxZoom: 3
                }});
                container._cy = cy;
                const tooltipDiv = document.createElement('div');
                tooltipDiv.className = 'tooltip';
                document.body.appendChild(tooltipDiv);
                let popperRef;
                cy.on('mouseover', 'node', function(evt) {{
                    const node = evt.target;
                    let text = node.data('is_center') && node.data('demonstration') ? '<strong>Demonstration:</strong><br>' + node.data('demonstration') : node.data('full_text');
                    popperRef = node.popper({{ content: function() {{ tooltipDiv.innerHTML = text; tooltipDiv.style.display = 'block'; return tooltipDiv; }} }});
                }});
                cy.on('mouseout', 'node', function() {{ if(popperRef) popperRef.destroy(); tooltipDiv.style.display = 'none'; }});
                cy.on('tap', 'node', function(evt) {{ htmx.ajax('GET', `/local_view/${{evt.target.id()}}?lang={lang}`, {{ target: document.body, swap: 'beforeend' }}); }});
            }});
        }})();
    """)
    
    cytoscape_container = Div(id=container_id, style="height: 100%; width: 100%;")
    return Div(cytoscape_container, init_script, style="height: 100%; width: 100%;")

def render_local_textual(subgraph: nx.DiGraph, node_key: str, selected_lang: str) -> Div:
    container_id = f"textual-container-{node_key.replace('.', '-')}-{int(time.time() * 1000)}"
    return Div(
        H3("Proof Structure"),
        Div(render_proof_tree_node(subgraph, node_key, selected_lang), cls="proof-tree"),
        Hr(style="margin: 20px 0;"),
        render_main_node_box(node_key, selected_lang),
        proof_tree_hover_script(container_id),
        id=container_id,
        style="height: 100%; overflow-y: auto;"
    )

# ==============================================================================
# DATA LOADING (Unchanged)
# ==============================================================================
DATA_FILE = "graph.json"
T_GRAPH, NODE_LEVELS = nx.DiGraph(), {}
if not os.path.exists(DATA_FILE):
    print(f"ERROR: File '{DATA_FILE}' not found.")
else:
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
        if any("'english_text'" in v.get("texts", {}) for v in data.get("vertices", [])):
            data = fix_json_data(data)
            with open(DATA_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)
            print("Fixed and saved JSON data.")
        T_GRAPH = create_graph_from_data(data.get("vertices", []), data.get("edges", []))
        NODE_LEVELS = calculate_node_levels(T_GRAPH)
        print(f"Successfully loaded: {T_GRAPH.number_of_nodes()} nodes, {T_GRAPH.number_of_edges()} edges")
    except Exception as e: print(f"ERROR loading data: {e}")

# ==============================================================================
# RUN SERVER
# ==============================================================================
# NEW, CORRECTED CODE AT THE END OF app.py
if __name__ == "__main__":
    serve()
