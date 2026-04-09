"""
AirFlan Monitor - Workflow Operations Console
"""

import json
import sys
import time
from datetime import datetime
from html import escape
from pathlib import Path

import dateutil.parser
import streamlit as st
from streamlit_agraph import Config, Edge, Node, agraph

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from airflan.storage.backend import DagRun, DatabaseSession, TaskInstance
except ImportError:
    st.error("Could not import AirFlan DatabaseBackend. Run `pip install -e .` First")
    st.stop()


if len(sys.argv) > 2:
    STATE_FILE = sys.argv[1]
    LOG_FILE = sys.argv[2]
else:
    STATE_FILE = "workflow_state.json"
    LOG_FILE = "workflow_logs.txt"


st.set_page_config(
    page_title="AirFlan Monitor",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

    :root {
        --bg: #0b1220;
        --bg-2: #101827;
        --panel: rgba(15, 23, 36, 0.92);
        --panel-soft: rgba(15, 23, 36, 0.78);
        --line: rgba(148, 163, 184, 0.16);
        --line-strong: rgba(148, 163, 184, 0.24);
        --text: #ecf3fb;
        --muted: #94a3b8;
        --blue: #4ba3ff;
        --green: #2fd39a;
        --amber: #f4b740;
        --rose: #ff5f7d;
        --slate: #7f93a8;
    }

    .stApp {
        background: linear-gradient(180deg, #0b1220 0%, #0a101a 100%);
        color: var(--text);
    }

    [data-testid="stAppViewContainer"] > .main {
        padding-top: 1.2rem;
    }

    h1, h2, h3, h4, p, div, span, label {
        font-family: 'Space Grotesk', sans-serif !important;
    }

    code, pre, [data-testid="stDataFrame"] td {
        font-family: 'IBM Plex Mono', monospace !important;
    }

    #MainMenu, footer, header {
        visibility: hidden;
    }

    [data-testid="stSidebar"] {
        background: #0f1724;
        border-right: 1px solid var(--line);
    }

    [data-testid="stSidebar"] * {
        color: var(--text) !important;
    }

    [data-testid="stSidebar"] .stSelectbox label {
        color: var(--muted) !important;
        text-transform: uppercase;
        font-size: 0.76rem;
        letter-spacing: 0.12em;
    }

    .shell {
        margin-top: -1rem;
    }

    .hero {
        display: grid;
        grid-template-columns: 1.5fr 1fr;
        gap: 1rem;
        margin-bottom: 1rem;
    }

    .hero-card, .panel {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 14px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
    }

    .hero-card {
        padding: 1.15rem 1.2rem;
    }

    .eyebrow {
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-size: 0.72rem;
        margin-bottom: 0.55rem;
    }

    .title-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        margin-bottom: 0.55rem;
    }

    .main-title {
        font-size: 1.55rem;
        line-height: 1;
        font-weight: 600;
        letter-spacing: -0.04em;
        color: var(--text);
    }

    .subtitle {
        color: var(--muted);
        font-size: 0.9rem;
        max-width: 42rem;
        line-height: 1.45;
    }

    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.42rem 0.78rem;
        border-radius: 999px;
        border: 1px solid currentColor;
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        background: rgba(255, 255, 255, 0.02);
        white-space: nowrap;
    }

    .status-dot {
        width: 0.48rem;
        height: 0.48rem;
        border-radius: 50%;
        background: currentColor;
        box-shadow: none;
    }

    .metric-strip {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.8rem;
        margin-top: 1.2rem;
    }

    .metric-tile {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 0.8rem 0.9rem;
    }

    .metric-kicker {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        color: var(--muted);
        margin-bottom: 0.45rem;
    }

    .metric-number {
        font-size: 1.25rem;
        font-weight: 600;
        letter-spacing: -0.04em;
        color: var(--text);
    }

    .side-summary {
        padding: 1.1rem 1.15rem;
    }

    .summary-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 0.9rem;
        margin-top: 1rem;
    }

    .summary-item {
        border-top: 1px solid var(--line);
        padding-top: 0.7rem;
    }

    .summary-label {
        color: var(--muted);
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.14em;
    }

    .summary-value {
        margin-top: 0.25rem;
        font-size: 1rem;
        color: var(--text);
        font-weight: 600;
        line-height: 1.35;
        word-break: break-word;
    }

    .panel {
        padding: 0.95rem 1rem 1rem 1rem;
        margin-bottom: 1rem;
    }

    .panel-header {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 1rem;
        margin-bottom: 0.9rem;
    }

    .panel-title {
        color: var(--text);
        font-size: 1rem;
        font-weight: 700;
        letter-spacing: -0.02em;
    }

    .panel-caption {
        color: var(--muted);
        font-size: 0.8rem;
    }

    .log-viewer {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.8rem;
        background: #0a1220;
        color: #cdd9e6;
        border: 1px solid var(--line);
        border-radius: 12px;
        padding: 1rem;
        min-height: 320px;
        white-space: pre-wrap;
        overflow-y: auto;
        line-height: 1.55;
    }

    [data-testid="stDataFrame"] {
        background: transparent;
        border: 1px solid var(--line);
        border-radius: 14px;
        overflow: hidden;
    }

    [data-testid="stDataFrame"] th {
        background: rgba(255, 255, 255, 0.03) !important;
        color: var(--muted) !important;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-size: 0.72rem;
        border-bottom: 1px solid var(--line) !important;
    }

    [data-testid="stDataFrame"] td {
        color: var(--text) !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.04) !important;
    }

    .sidebar-note {
        color: var(--muted);
        font-size: 0.78rem;
        line-height: 1.55;
        margin-top: 0.5rem;
    }

    .empty-state {
        padding: 1.2rem 1.3rem;
        border-radius: 16px;
        border: 1px dashed var(--line-strong);
        background: rgba(255, 255, 255, 0.02);
        color: var(--muted);
    }

    @media (max-width: 1100px) {
        .hero {
            grid-template-columns: 1fr;
        }

        .metric-strip {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
    }
</style>
""",
    unsafe_allow_html=True,
)


STATUS_COLORS = {
    "running": "#4ba3ff",
    "completed": "#2fd39a",
    "failed": "#ff5f7d",
    "pending": "#7f93a8",
    "skipped": "#93a5b8",
    "timeout": "#f4b740",
}


def load_state_safe():
    """Robustly load state with retries."""
    for _ in range(3):
        try:
            if not Path(STATE_FILE).exists():
                return None
            with open(STATE_FILE, "r") as f:
                content = f.read().strip()
                if not content:
                    return None
                return json.loads(content)
        except Exception:
            time.sleep(0.05)
    return None


def load_logs_safe():
    """Safe log loading with efficient tailing for large files."""
    try:
        log_path = Path(LOG_FILE)
        if not log_path.exists():
            return ""

        file_size = log_path.stat().st_size
        read_size = min(file_size, 50 * 1024)

        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            if file_size > read_size:
                f.seek(file_size - read_size)
                f.readline()

            content = f.read()
            for code in ("\033[95m", "\033[0m", "\033[94m", "\033[96m", "\033[92m", "\033[93m", "\033[91m", "\033[1m"):
                content = content.replace(code, "")
            return content
    except Exception:
        return "Error reading logs"


def get_all_runs():
    """Get list of recent DAG runs for the sidebar."""
    db = DatabaseSession()
    session = db.get_session()
    try:
        runs = session.query(DagRun).order_by(DagRun.start_time.desc()).limit(50).all()
        return [
            (
                r.run_id,
                f"{r.dag_id} ({r.start_time.strftime('%m-%d %H:%M:%S')}) - {r.status.upper()}",
            )
            for r in runs
        ]
    except Exception:
        return []
    finally:
        session.close()


def load_state_from_db(run_id=None):
    """Load workflow state directly from the metadata database."""
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

        state = {
            "name": target_run.dag_id,
            "status": target_run.status,
            "start_time": target_run.start_time.isoformat() if target_run.start_time else None,
            "end_time": target_run.end_time.isoformat() if target_run.end_time else None,
            "tasks": {t.task_id: {"depends_on": []} for t in tasks},
            "results": {
                t.task_id: {
                    "status": t.status,
                    "execution_time": t.execution_time,
                }
                for t in tasks
            },
        }

        try:
            struct_file = f"{target_run.dag_id}_structure.json"
            if Path(struct_file).exists():
                with open(struct_file, "r") as f:
                    json_state = json.load(f)
                for task_id, data in json_state.get("tasks", {}).items():
                    if task_id in state["tasks"]:
                        state["tasks"][task_id]["depends_on"] = data.get("depends_on", [])
        except Exception:
            pass

        return state
    except Exception as e:
        import traceback

        st.error(f"Error loading from DB: {e}\n{traceback.format_exc()}")
        return None
    finally:
        session.close()


def get_status_color(status: str) -> str:
    return STATUS_COLORS.get(status, STATUS_COLORS["pending"])


def render_status_badge(status: str) -> str:
    color = get_status_color(status)
    label = escape(status.upper())
    return (
        f"<span class='status-badge' style='color:{color};'>"
        f"<span class='status-dot'></span>{label}</span>"
    )


def format_duration(start_time, end_time):
    if not start_time:
        return "0.0s"
    try:
        start_dt = dateutil.parser.isoparse(start_time)
        if end_time:
            end_dt = dateutil.parser.isoparse(end_time)
        else:
            end_dt = datetime.utcnow()
        duration = max((end_dt - start_dt).total_seconds(), 0)
        return f"{duration:.1f}s"
    except Exception:
        return "0.0s"


def compute_metrics(state):
    results = state.get("results", {})
    tasks = state.get("tasks", {})

    total = len(tasks)
    completed = sum(1 for r in results.values() if r["status"] == "completed")
    failed = sum(1 for r in results.values() if r["status"] in {"failed", "timeout"})
    running = sum(1 for r in results.values() if r["status"] == "running")
    skipped = sum(1 for r in results.values() if r["status"] == "skipped")
    pending = max(total - len(results), 0)
    success_rate = f"{(completed / total * 100):.0f}%" if total else "0%"

    return {
        "total": total,
        "completed": completed,
        "failed": failed,
        "running": running,
        "skipped": skipped,
        "pending": pending,
        "success_rate": success_rate,
        "duration": format_duration(state.get("start_time"), state.get("end_time")),
    }


def render_metric_tile(label: str, value: str, accent: str = None):
    style = f"color:{accent};" if accent else ""
    st.markdown(
        f"""
        <div class="metric-tile">
            <div class="metric-kicker">{escape(label)}</div>
            <div class="metric-number" style="{style}">{escape(str(value))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_graph(tasks, results):
    nodes = []
    edges = []

    for name in tasks.keys():
        status = results.get(name, {}).get("status", "pending")
        color = get_status_color(status)

        nodes.append(
            Node(
                id=name,
                label=name.replace("_", " "),
                size=28,
                color={
                    "background": "#091521",
                    "border": color,
                    "highlight": {"background": "#102030", "border": color},
                },
                font={"color": "#eaf2fa", "face": "Space Grotesk", "size": 15, "weight": "600"},
                shape="box",
                shapeProperties={"borderRadius": 8},
                borderWidth=2,
                borderWidthSelected=3,
                shadow={"enabled": status in {"running", "failed", "timeout"}, "color": color, "size": 12, "x": 0, "y": 0},
            )
        )

        for dep in tasks[name].get("depends_on", []):
            edges.append(
                Edge(
                    source=dep,
                    target=name,
                    color={"color": "rgba(143, 167, 192, 0.55)", "highlight": color},
                    width=2,
                    arrows="to",
                    type="smooth",
                    smooth={"type": "cubicBezier", "forceDirection": "horizontal", "roundness": 0.45},
                )
            )

    config = Config(
        height=460,
        width="100%",
        directed=True,
        physics=False,
        hierarchical=True,
        dagMode="LR",
        dagLevelDistance=190,
        nodeSpacing=120,
        staticGraph=False,
        interaction={"dragNodes": False, "dragView": True, "zoomView": True},
        backgroundColor="transparent",
    )

    return nodes, edges, config


st.sidebar.markdown("## AirFlan")
st.sidebar.markdown("#### Workflow Console")
st.sidebar.markdown(
    "<div class='sidebar-note'>Operational view of DAG execution, scheduler state, and task outcomes.</div>",
    unsafe_allow_html=True,
)

runs = get_all_runs()
selected_run_id = None

if runs:
    run_options = {label: run_id for run_id, label in runs}
    selected_label = st.sidebar.selectbox("Run", list(run_options.keys()))
    selected_run_id = run_options[selected_label]
else:
    st.sidebar.markdown(
        "<div class='sidebar-note'>No persisted runs yet. Execute a workflow to populate the console.</div>",
        unsafe_allow_html=True,
    )


@st.fragment(run_every=2)
def dashboard(selected_run_id):
    state = load_state_from_db(selected_run_id) or load_state_safe()
    logs = load_logs_safe()

    st.markdown("<div class='shell'>", unsafe_allow_html=True)

    if not state:
        st.markdown(
            "<div class='empty-state'>No workflow runs found. The console will populate as soon as the orchestrator writes metadata.</div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)
        return

    results = state.get("results", {})
    tasks = state.get("tasks", {})
    metrics = compute_metrics(state)
    workflow_name = state.get("name", "workflow")
    status = state.get("status", "running")

    st.markdown(
        f"""
        <div class="hero">
            <div class="hero-card">
                <div class="eyebrow">AirFlan Control Room</div>
                <div class="title-row">
                    <div class="main-title">{escape(workflow_name)}</div>
                    {render_status_badge(status)}
                </div>
                <div class="subtitle">
                    Selected workflow run, task states, and recent execution output.
                </div>
                <div class="metric-strip">
                    <div class="metric-tile">
                        <div class="metric-kicker">Tasks</div>
                        <div class="metric-number">{metrics["total"]}</div>
                    </div>
                    <div class="metric-tile">
                        <div class="metric-kicker">Success Rate</div>
                        <div class="metric-number" style="color:#2fd39a;">{metrics["success_rate"]}</div>
                    </div>
                    <div class="metric-tile">
                        <div class="metric-kicker">Active</div>
                        <div class="metric-number" style="color:#4ba3ff;">{metrics["running"]}</div>
                    </div>
                    <div class="metric-tile">
                        <div class="metric-kicker">Failures</div>
                        <div class="metric-number" style="color:#ff5f7d;">{metrics["failed"]}</div>
                    </div>
                </div>
            </div>
            <div class="hero-card side-summary">
                <div class="eyebrow">Run Snapshot</div>
                <div class="panel-title">Execution Envelope</div>
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="summary-label">Started</div>
                        <div class="summary-value">{escape(state.get("start_time") or "N/A")}</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-label">Finished</div>
                        <div class="summary-value">{escape(state.get("end_time") or "In Progress")}</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-label">Pending</div>
                        <div class="summary-value">{metrics["pending"]}</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-label">Skipped</div>
                        <div class="summary-value">{metrics["skipped"]}</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-label">Completed</div>
                        <div class="summary-value">{metrics["completed"]}</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-label">Run Time</div>
                        <div class="summary-value">{metrics["duration"]}</div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="panel">
            <div class="panel-header">
                <div class="panel-title">Dependency Graph</div>
                <div class="panel-caption">Left-to-right execution topology with live status encoding.</div>
            </div>
        """,
        unsafe_allow_html=True,
    )
    nodes, edges, config = build_graph(tasks, results)
    if nodes:
        agraph(nodes=nodes, edges=edges, config=config)
    st.markdown("</div>", unsafe_allow_html=True)

    col_a, col_b = st.columns([1.05, 0.95], gap="large")

    with col_a:
        st.markdown(
            """
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">Task Ledger</div>
                    <div class="panel-caption">Status, execution time, and task-level terminal state.</div>
                </div>
            """,
            unsafe_allow_html=True,
        )
        if results:
            rows = []
            for name, res in results.items():
                rows.append(
                    {
                        "Task": name,
                        "Status": res["status"].upper(),
                        "Duration": f"{res.get('execution_time') or 0:.2f}s",
                    }
                )
            st.dataframe(rows, use_container_width=True, hide_index=True, height=360)
        else:
            st.markdown("<div class='empty-state'>No task results have been persisted yet.</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_b:
        st.markdown(
            """
            <div class="panel">
                <div class="panel-header">
                    <div class="panel-title">Execution Tail</div>
                    <div class="panel-caption">Recent orchestrator output and task logs.</div>
                </div>
            """,
            unsafe_allow_html=True,
        )
        if logs and logs.strip():
            st.markdown(f"<div class='log-viewer'>{escape(logs)}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='empty-state'>No logs available for the selected run.</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


dashboard(selected_run_id)
