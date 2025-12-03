"""
AirFlan Monitor - Enterprise Workflow Visualization
"""

import json
import sys
import time
from pathlib import Path

import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config

# ----------------------------------
# Configuration
# ----------------------------------
if len(sys.argv) > 2:
    STATE_FILE = sys.argv[1]
    LOG_FILE = sys.argv[2]
else:
    STATE_FILE = "workflow_state.json"
    LOG_FILE = "workflow_logs.txt"

st.set_page_config(
    page_title="AirFlan Monitor",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ----------------------------------
# Enterprise Design System
# ----------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Roboto+Mono:wght@400&display=swap');
    
    /* Global Styles */
    .stApp {
        background-color: #f8fafc; /* Slate 50 */
    }
    
    h1, h2, h3, p, div, span {
        font-family: 'Inter', sans-serif;
        color: #0f172a; /* Slate 900 */
    }

    /* Header */
    .header-container {
        background-color: #ffffff;
        padding: 1rem 2rem;
        border-bottom: 1px solid #e2e8f0;
        margin: -6rem -4rem 2rem -4rem; /* Negative margin to span full width */
        display: flex;
        align-items: center;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    }
    
    .brand-title {
        font-size: 1.25rem;
        font-weight: 600;
        color: #0f172a;
        margin-right: 1rem;
    }
    
    .brand-subtitle {
        font-size: 0.875rem;
        color: #64748b;
        font-weight: 400;
        border-left: 1px solid #cbd5e1;
        padding-left: 1rem;
    }

    /* Metric Cards */
    .metric-container {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1.5rem;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
    }
    
    .metric-label {
        font-size: 0.875rem;
        font-weight: 500;
        color: #64748b; /* Slate 500 */
        margin-bottom: 0.5rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    
    .metric-value {
        font-size: 2rem;
        font-weight: 600;
        color: #0f172a;
        line-height: 1;
    }

    /* Tables */
    [data-testid="stDataFrame"] {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem;
    }

    /* Logs */
    .log-viewer {
        font-family: 'Roboto Mono', monospace;
        font-size: 0.85rem;
        background-color: #1e293b; /* Slate 800 */
        color: #f8fafc; /* Slate 50 */
        padding: 1.5rem;
        border-radius: 8px;
        height: 400px;
        overflow-y: auto;
        white-space: pre-wrap;
        line-height: 1.5;
    }

    /* Hide Streamlit Elements */
    #MainMenu, footer, header {visibility: hidden;}
    
</style>
""", unsafe_allow_html=True)

# ----------------------------------
# Helper Functions
# ----------------------------------
def load_state_safe():
    """Robustly load state with retries"""
    for _ in range(3):
        try:
            if not Path(STATE_FILE).exists():
                return None
            with open(STATE_FILE, 'r') as f:
                content = f.read().strip()
                if not content: return None
                return json.loads(content)
        except:
            time.sleep(0.05)
    return None

def load_logs_safe():
    """Safe log loading"""
    try:
        if not Path(LOG_FILE).exists(): return ""
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
            # Clean ANSI codes
            clean = [l.replace("\033[95m", "").replace("\033[0m", "") for l in lines[-200:]]
            return "".join(clean)
    except:
        return ""

def get_status_color(status):
    return {
        "running": "#3b82f6",   # Blue
        "completed": "#10b981", # Emerald
        "failed": "#ef4444",    # Red
        "pending": "#cbd5e1",   # Slate 300
        "skipped": "#94a3b8",   # Slate 400
        "timeout": "#f59e0b"    # Amber
    }.get(status, "#cbd5e1")

# ----------------------------------
# Layout & Components
# ----------------------------------

# Header
st.markdown("""
    <div class="header-container">
        <span class="brand-title">AirFlan</span>
        <span class="brand-subtitle">Workflow Monitor</span>
    </div>
""", unsafe_allow_html=True)

# ----------------------------------
# Main Dashboard (Fragment)
# ----------------------------------
@st.fragment(run_every=1)
def dashboard():
    state = load_state_safe()
    logs = load_logs_safe()
    
    col_metrics, col_graph = st.columns([1, 3])
    
    if state:
        results = state.get("results", {})
        tasks = state.get("tasks", {})
        
        # 1. Metrics Panel
        total = len(tasks)
        completed = sum(1 for r in results.values() if r["status"] == "completed")
        failed = sum(1 for r in results.values() if r["status"] == "failed")
        running = sum(1 for r in results.values() if r["status"] == "running")
        
        with col_metrics:
            st.markdown(f"""
                <div class="metric-container">
                    <div style="margin-bottom: 1.5rem;">
                        <div class="metric-label">Total Tasks</div>
                        <div class="metric-value">{total}</div>
                    </div>
                    <div style="margin-bottom: 1.5rem;">
                        <div class="metric-label">Running</div>
                        <div class="metric-value" style="color: #3b82f6;">{running}</div>
                    </div>
                    <div style="margin-bottom: 1.5rem;">
                        <div class="metric-label">Completed</div>
                        <div class="metric-value" style="color: #10b981;">{completed}</div>
                    </div>
                    <div>
                        <div class="metric-label">Failed</div>
                        <div class="metric-value" style="color: #ef4444;">{failed}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            st.markdown("<div style='height: 20px'></div>", unsafe_allow_html=True)
            
            if results:
                data = []
                for name, res in results.items():
                    data.append({
                        "Task": name,
                        "Status": res["status"].upper(),
                        "Time": f"{res.get('execution_time', 0):.2f}s"
                    })
                st.dataframe(
                    data, 
                    use_container_width=True,
                    hide_index=True,
                    height=400
                )

        # 3. Graph Visualization & Logs
        with col_graph:
            nodes = []
            edges = []
            
            for name in tasks.keys():
                status = results.get(name, {}).get("status", "pending")
                color = get_status_color(status)
                
                nodes.append(Node(
                    id=name,
                    label=name.replace("_", "\n"),
                    size=400,
                    color=color,
                    font={'color': 'white', 'face': 'Inter', 'size': 14},
                    shape='box',
                    shapeProperties={'borderRadius': 4},
                    borderWidth=0
                ))
                
                for dep in tasks[name].get("depends_on", []):
                    edges.append(Edge(
                        source=dep, 
                        target=name,
                        color='#cbd5e1',
                        width=2,
                        type='curvedCW'
                    ))
            
            config = Config(
                height=500,
                width="100%",
                directed=True,
                physics=False,
                hierarchical=True,
                dagMode='TB',
                dagLevelDistance=80,
                staticGraph=True,
                interaction={'dragNodes': False, 'dragView': False, 'zoomView': False}
            )
            
            if nodes:
                # Removed 'key' argument to fix TypeError
                agraph(nodes=nodes, edges=edges, config=config)

            st.markdown("<div style='height: 20px'></div>", unsafe_allow_html=True)
            st.markdown(f'<div class="log-viewer">{logs}</div>', unsafe_allow_html=True)

# Run Dashboard
dashboard()
