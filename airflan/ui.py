"""
AirFlan Monitor - Enterprise Workflow Visualization
"""

import json
import sys
import time
from pathlib import Path

import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config

try:
    from airflan.storage.backend import DatabaseSession, DagRun, TaskInstance
    from sqlalchemy.orm import Session
except ImportError:
    st.error("Could not import AirFlan DatabaseBackend. Run `pip install -e .` First")
    st.stop()

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
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600&family=JetBrains+Mono:wght@400&display=swap');
    
    /* Core App Framework */
    .stApp {
        background-color: #0d1117; /* GitHub Deep Space Dark */
        color: #e6edf3;
    }
    
    h1, h2, h3, p, div, span {
        font-family: 'Outfit', sans-serif;
    }

    /* Top Navigation Bar */
    .header-container {
        background: transparent;
        padding: 1rem 0rem;
        border-bottom: 1px solid rgba(48, 54, 61, 0.5);
        margin: -4rem 0rem 2rem 0rem; 
        display: flex;
        align-items: center;
    }
    
    .brand-title {
        font-size: 1.4rem;
        font-weight: 600;
        background: linear-gradient(90deg, #2dd4bf 0%, #3b82f6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-right: 1.2rem;
        letter-spacing: -0.02em;
    }
    
    .brand-subtitle {
        font-size: 0.9rem;
        color: #8b949e;
        font-weight: 400;
        border-left: 1px solid #30363d;
        padding-left: 1.2rem;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }

    /* Metric Cards - Glassmorphism */
    .metric-container {
        background: rgba(22, 27, 34, 0.4);
        border: 1px solid rgba(48, 54, 61, 0.6);
        border-radius: 12px;
        padding: 1.5rem;
        backdrop-filter: blur(12px);
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
        transition: transform 0.2s ease, border-color 0.2s ease;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .metric-container:hover {
        transform: translateY(-2px);
        border-color: rgba(45, 212, 191, 0.5); /* Teal hover */
    }
    
    .metric-item {
        margin-bottom: 1.5rem;
    }
    .metric-item:last-child {
        margin-bottom: 0;
    }
    
    .metric-label {
        font-size: 0.75rem;
        font-weight: 500;
        color: #8b949e; 
        margin-bottom: 0.3rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    
    .metric-value {
        font-size: 2.2rem;
        font-weight: 600;
        color: #e6edf3;
        line-height: 1.1;
        letter-spacing: -0.02em;
    }
    
    /* Neon Data Tables */
    [data-testid="stDataFrame"] {
        background: rgba(22, 27, 34, 0.4);
        border: 1px solid rgba(48, 54, 61, 0.6);
        border-radius: 12px;
        padding: 0.5rem;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
    }
    [data-testid="stDataFrame"] table {
        color: #c9d1d9 !important;
    }
    [data-testid="stDataFrame"] th {
        background-color: transparent !important;
        border-bottom: 1px solid rgba(48, 54, 61, 0.8) !important;
        color: #8b949e !important;
        font-family: 'Outfit', sans-serif !important;
        font-weight: 500 !important;
        text-transform: uppercase;
        font-size: 0.75rem;
        letter-spacing: 0.05em;
    }
    [data-testid="stDataFrame"] td {
        border-bottom: 1px solid rgba(48, 54, 61, 0.3) !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.9rem;
    }

    /* Terminal/Logs */
    .log-viewer {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.8rem;
        background-color: #010409; 
        color: #a5d6ff; 
        padding: 1.5rem;
        border-radius: 12px;
        border: 1px solid #30363d;
        height: 400px;
        overflow-y: auto;
        white-space: pre-wrap;
        line-height: 1.6;
        box-shadow: inset 0 2px 4px rgba(0,0,0,0.5);
    }

    /* Hide Streamlit branding */
    #MainMenu, footer, header {visibility: hidden;}

    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #161b22;
        border-right: 1px solid #30363d;
    }
    
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
    """Safe log loading with efficient tailing for large files"""
    try:
        log_path = Path(LOG_FILE)
        if not log_path.exists(): return ""
        
        file_size = log_path.stat().st_size
        # Read last 50KB (~500 lines)
        read_size = min(file_size, 50 * 1024) 
        
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            if file_size > read_size:
                f.seek(file_size - read_size)
                # Discard partial line at start
                f.readline()
            
            content = f.read()
            
            # Simple ANSI cleanup
            content = content.replace("\033[95m", "").replace("\033[0m", "")
            content = content.replace("\033[94m", "").replace("\033[96m", "")
            content = content.replace("\033[92m", "").replace("\033[93m", "")
            content = content.replace("\033[91m", "").replace("\033[1m", "")
            
            return content
    except Exception:
        return "Error reading logs"

def get_all_runs():
    """Get list of past DAG Runs for the sidebar"""
    db = DatabaseSession()
    session = db.get_session()
    try:
        runs = session.query(DagRun).order_by(DagRun.start_time.desc()).limit(50).all()
        return [(r.run_id, f"{r.dag_id} ({r.start_time.strftime('%m-%d %H:%M:%S')}) - {r.status.upper()}") for r in runs]
    except Exception:
        return []
    finally:
        session.close()

def load_state_from_db(run_id=None):
    """Load latest workflow state directly from SQLite Database"""
    db = DatabaseSession()
    session = db.get_session()
    
    try:
        if run_id:
            target_run = session.query(DagRun).filter_by(run_id=run_id).first()
        else:
            target_run = session.query(DagRun).order_by(DagRun.start_time.desc()).first()
            
        if not target_run:
            return None
            
        tasks = session.query(TaskInstance).filter_by(run_id=target_run.run_id).all()
        
        # Build state dict expected by the UI graph 
        state = {
            "name": target_run.dag_id,
            "status": target_run.status,
            "start_time": target_run.start_time.isoformat() if target_run.start_time else None,
            "end_time": target_run.end_time.isoformat() if target_run.end_time else None,
            "tasks": {t.task_id: {"depends_on": []} for t in tasks},
            "results": {
                t.task_id: {
                    "status": t.status, 
                    "execution_time": t.execution_time
                } for t in tasks
            }
        }
        
        # Fallback to merge dependencies from JSON if available and matches dag_id
        # (This is a temporary hack until Dag structure is serialized in Phase 6)
        json_state = load_state_safe()
        if json_state and json_state.get('name') == target_run.dag_id:
            for t_id, data in json_state.get('tasks', {}).items():
                if t_id in state["tasks"]:
                    state["tasks"][t_id]["depends_on"] = data.get("depends_on", [])
                    
        return state
    except Exception as e:
        import traceback
        st.error(f"Error loading from DB: {e}\n{traceback.format_exc()}")
        return None
    finally:
        session.close()

def get_status_color(status):
    return {
        "running": "#00f2fe",   # Neon Cyan
        "completed": "#34d399", # Neon Emerald
        "failed": "#fb7185",    # Neon Rose/Red
        "pending": "#30363d",   # Dark Slate Border
        "skipped": "#9ca3af",   # Gray
        "timeout": "#fbbf24"    # Neon Amber
    }.get(status, "#30363d")

def get_status_font_color(status):
    if status in ["pending", "skipped"]:
        return "#8b949e"
    return "#ffffff"

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
@st.fragment(run_every=2)
def dashboard(selected_run_id):
    state = load_state_from_db(selected_run_id) or load_state_safe()
    logs = load_logs_safe()
    
    if not state:
        st.info("No workflow runs found. Waiting for tasks...")
        return
        
    results = state.get("results", {})
    tasks = state.get("tasks", {})
    
    total = len(tasks)
    completed = sum(1 for r in results.values() if r["status"] == "completed")
    failed = sum(1 for r in results.values() if r["status"] == "failed")
    running = sum(1 for r in results.values() if r["status"] == "running")
    
    import dateutil.parser
    from datetime import datetime
    
    duration_str = "0.0s"
    if state.get("start_time"):
        try:
            start_dt = dateutil.parser.isoparse(state["start_time"])
            if state.get("end_time"):
                end_dt = dateutil.parser.isoparse(state["end_time"])
                dur = (end_dt - start_dt).total_seconds()
            else:
                dur = (datetime.utcnow() - start_dt).total_seconds()
            duration_str = f"{dur:.1f}s"
        except:
            pass
    
    # --- Top Row: DAG Visualization ---
    st.markdown("<h3 style='margin-bottom: -1rem;'>DAG Visualization</h3>", unsafe_allow_html=True)
    
    # We want the Agraph to take full width up top like Prefect
    nodes = []
    edges = []
    
    for name in tasks.keys():
        status = results.get(name, {}).get("status", "pending")
        color = get_status_color(status)
        font_color = get_status_font_color(status)
        
        shadow = None
        if status in ["running", "completed", "failed"]:
            shadow = {'enabled': True, 'color': color, 'size': 15, 'x': 0, 'y': 0}
        
        nodes.append(Node(
            id=name,
            label=name.replace("_", "\n"),
            size=30,
            color={'background': '#0d1117', 'border': color, 'highlight': {'border': color, 'background': '#161b22'}},
            font={'color': font_color, 'face': 'Outfit', 'size': 14, 'weight': '500'},
            shape='box',
            shapeProperties={'borderRadius': 8},
            borderWidth=2,
            borderWidthSelected=3,
            shadow=shadow
        ))
        
        for dep in tasks[name].get("depends_on", []):
            edges.append(Edge(
                source=dep, 
                target=name,
                color={'color': '#4b5563', 'highlight': '#8b949e'},
                width=2,
                type='smooth',
                smooth={'type': 'cubicBezier', 'forceDirection': 'horizontal', 'roundness': 0.6}
            ))
    
    config = Config(
        height=400,
        width="100%",
        directed=True,
        physics=False,
        hierarchical=True,
        dagMode='LR',  # Left-to-Right like Prefect
        dagLevelDistance=160,
        nodeSpacing=100,
        staticGraph=False, # Allow dragging and zoom
        interaction={'dragNodes': False, 'dragView': True, 'zoomView': True},
        backgroundColor='transparent'
    )
    
    if nodes:
        agraph(nodes=nodes, edges=edges, config=config)
    
    st.markdown("<div style='height: 2rem'></div>", unsafe_allow_html=True)
    
    # --- Bottom Row: Metrics & Data ---
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.markdown(f"""
            <div class="metric-container">
                <div class="metric-label">Tasks Total</div>
                <div class="metric-value">{total}</div>
            </div>
        """, unsafe_allow_html=True)
        
    with col2:
        st.markdown(f"""
            <div class="metric-container">
                <div class="metric-label">Running</div>
                <div class="metric-value" style="color: #00f2fe; text-shadow: 0 0 10px rgba(0, 242, 254, 0.4);">{running}</div>
            </div>
        """, unsafe_allow_html=True)
        
    with col3:
        st.markdown(f"""
            <div class="metric-container">
                <div class="metric-label">Success</div>
                <div class="metric-value" style="color: #34d399; text-shadow: 0 0 10px rgba(52, 211, 153, 0.4);">{completed}</div>
            </div>
        """, unsafe_allow_html=True)
        
    with col4:
        st.markdown(f"""
            <div class="metric-container">
                <div class="metric-label">Failed Runs</div>
                <div class="metric-value" style="color: #fb7185; text-shadow: 0 0 10px rgba(251, 113, 133, 0.4);">{failed}</div>
            </div>
        """, unsafe_allow_html=True)
        
    with col5:
        st.markdown(f"""
            <div class="metric-container">
                <div class="metric-label">Run Time</div>
                <div class="metric-value" style="color: #c9d1d9;">{duration_str}</div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 2rem'></div>", unsafe_allow_html=True)
    
    # --- Tables & Logs Row ---
    if results or (logs and logs.strip()):
        col_t, col_l = st.columns([1, 1])
        
        with col_t:
            if results:
                data = []
                for name, res in results.items():
                    data.append({
                        "Task": name,
                        "Status": res["status"].upper(),
                        "Dur": f"{res.get('execution_time') or 0:.1f}s"
                    })
                st.dataframe(data, use_container_width=True, hide_index=True, height=300)
                
        with col_l:
            if logs and logs.strip():
                st.markdown(f'<div class="log-viewer" style="height: 300px;">{logs}</div>', unsafe_allow_html=True)

# Run Dashboard
runs = get_all_runs()
selected_run_id = None

if runs:
    st.sidebar.markdown("### Historical Runs")
    run_options = {r[1]: r[0] for r in runs}
    selected_label = st.sidebar.selectbox("Select Run", list(run_options.keys()))
    selected_run_id = run_options[selected_label]

dashboard(selected_run_id)
