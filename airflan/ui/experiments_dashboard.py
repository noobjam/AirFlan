"""
AirFlan MLOps Experiments Dashboard
"""

import sys
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from airflan.mlops import ArtifactStore, MetricsStore


STATUS_COLORS = {
    "completed": "#2fd39a",
    "failed": "#ff5f7d",
    "running": "#f4b740",
}


def format_time(timestamp_str):
    """Format timestamp for display."""
    try:
        dt = datetime.fromisoformat(timestamp_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(timestamp_str)


def format_duration(start_time, end_time):
    """Calculate and format duration."""
    if not end_time:
        return "Running"
    try:
        start = datetime.fromisoformat(start_time)
        end = datetime.fromisoformat(end_time)
        return f"{(end - start).total_seconds():.2f}s"
    except Exception:
        return "N/A"


def status_badge(status):
    color = STATUS_COLORS.get(status, "#8fa7c0")
    return (
        f"<span class='status-badge' style='color:{color};'>"
        f"<span class='status-dot'></span>{escape(status.upper())}</span>"
    )


def apply_theme():
    st.set_page_config(page_title="AirFlan Experiments", layout="wide")
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap');

            :root {
                --bg: #0b1220;
                --panel: rgba(15, 23, 36, 0.92);
                --panel-soft: rgba(15, 23, 36, 0.78);
                --line: rgba(148, 163, 184, 0.16);
                --text: #ecf3fb;
                --muted: #94a3b8;
            }

            .stApp {
                background: linear-gradient(180deg, #0b1220 0%, #0a101a 100%);
                color: var(--text);
            }

            h1, h2, h3, h4, p, div, span, label {
                font-family: 'Space Grotesk', sans-serif !important;
                color: var(--text);
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

            .page-hero {
                display: flex;
                justify-content: space-between;
                align-items: flex-end;
                gap: 0.8rem;
                margin-bottom: 1.1rem;
                padding: 1rem 1.1rem 0.95rem 1.1rem;
                border-radius: 14px;
                border: 1px solid var(--line);
                background: var(--panel);
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
            }

            .hero-eyebrow {
                color: var(--muted);
                text-transform: uppercase;
                letter-spacing: 0.12em;
                font-size: 0.72rem;
                margin-bottom: 0.45rem;
            }

            .hero-title {
                font-size: 1.5rem;
                font-weight: 600;
                letter-spacing: -0.05em;
                line-height: 1;
                margin-bottom: 0.45rem;
            }

            .hero-copy {
                color: var(--muted);
                max-width: 40rem;
                line-height: 1.45;
                font-size: 0.92rem;
            }

            .panel {
                background: var(--panel);
                border: 1px solid var(--line);
                border-radius: 14px;
                padding: 0.95rem 1rem 1rem 1rem;
                margin-bottom: 1rem;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
            }

            .panel-head {
                display: flex;
                justify-content: space-between;
                align-items: baseline;
                gap: 1rem;
                margin-bottom: 0.9rem;
            }

            .panel-title {
                font-size: 1rem;
                font-weight: 700;
                letter-spacing: -0.02em;
            }

            .panel-caption {
                color: var(--muted);
                font-size: 0.8rem;
            }

            .summary-grid {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 0.8rem;
                margin-top: 0.8rem;
            }

            .summary-tile {
                border: 1px solid var(--line);
                border-radius: 12px;
                padding: 0.75rem 0.85rem;
                background: rgba(255, 255, 255, 0.03);
            }

            .summary-kicker {
                color: var(--muted);
                text-transform: uppercase;
                font-size: 0.7rem;
                letter-spacing: 0.13em;
                margin-bottom: 0.35rem;
            }

            .summary-value {
                font-size: 1.1rem;
                font-weight: 600;
                letter-spacing: -0.04em;
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
                background: rgba(255, 255, 255, 0.04);
            }

            .status-dot {
                width: 0.48rem;
                height: 0.48rem;
                border-radius: 50%;
                background: currentColor;
                box-shadow: none;
            }

            .experiment-block {
                border: 1px solid var(--line);
                border-radius: 14px;
                padding: 1rem;
                background: rgba(255, 255, 255, 0.02);
                margin-bottom: 0.9rem;
            }

            .experiment-title {
                font-size: 1.05rem;
                font-weight: 700;
                letter-spacing: -0.02em;
            }

            .experiment-meta {
                color: var(--muted);
                margin-top: 0.2rem;
                margin-bottom: 0.9rem;
                font-size: 0.88rem;
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

            .empty-state {
                padding: 1rem 1.1rem;
                border-radius: 16px;
                border: 1px dashed rgba(130, 157, 189, 0.34);
                background: rgba(255, 255, 255, 0.02);
                color: var(--muted);
            }

            [data-baseweb="select"] > div,
            [data-baseweb="input"] > div {
                background: rgba(255, 255, 255, 0.03) !important;
                border-color: rgba(130, 157, 189, 0.25) !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(title, copy):
    st.markdown(
        f"""
        <div class="page-hero">
            <div>
                <div class="hero-eyebrow">AirFlan Experiments</div>
                <div class="hero-title">{escape(title)}</div>
                <div class="hero-copy">{escape(copy)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def panel_start(title, caption):
    st.markdown(
        f"""
        <div class="panel">
            <div class="panel-head">
                <div class="panel-title">{escape(title)}</div>
                <div class="panel-caption">{escape(caption)}</div>
            </div>
        """,
        unsafe_allow_html=True,
    )


def panel_end():
    st.markdown("</div>", unsafe_allow_html=True)


def render_summary_tiles(items):
    tiles = []
    for label, value, color in items:
        style = f"style='color:{color};'" if color else ""
        tiles.append(
            f"""
            <div class="summary-tile">
                <div class="summary-kicker">{escape(label)}</div>
                <div class="summary-value" {style}>{escape(str(value))}</div>
            </div>
            """
        )
    st.markdown(f"<div class='summary-grid'>{''.join(tiles)}</div>", unsafe_allow_html=True)


def apply_plot_style(fig, title, x_title, y_title):
    fig.update_layout(
        title=title,
        xaxis_title=x_title,
        yaxis_title=y_title,
        hovermode="x unified",
        height=380,
        margin=dict(l=12, r=12, t=54, b=24),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(8, 20, 33, 0.25)",
        font=dict(color="#ecf3fb", family="Space Grotesk"),
        xaxis=dict(gridcolor="rgba(143, 167, 192, 0.12)", zerolinecolor="rgba(143, 167, 192, 0.12)"),
        yaxis=dict(gridcolor="rgba(143, 167, 192, 0.12)", zerolinecolor="rgba(143, 167, 192, 0.12)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )


def collect_runs(metrics_store: MetricsStore):
    experiments = metrics_store.list_experiments()
    all_runs = []
    for exp in experiments:
        runs = metrics_store.list_runs(exp["experiment_id"])
        for run in runs:
            run["experiment_name"] = exp["experiment_name"]
            all_runs.append(run)
    return experiments, all_runs


def main():
    apply_theme()

    metrics_store = MetricsStore("airflan_experiments.db")
    artifact_store = ArtifactStore()

    st.sidebar.markdown("## AirFlan")
    st.sidebar.markdown("#### MLOps Console")
    page = st.sidebar.radio("Navigate", ["Experiments", "Run Details", "Compare Runs"])

    if page == "Experiments":
        show_experiments_page(metrics_store)
    elif page == "Run Details":
        show_run_details_page(metrics_store, artifact_store)
    else:
        show_comparison_page(metrics_store)


def show_experiments_page(metrics_store: MetricsStore):
    page_header(
        "Experiments Registry",
        "Experiment groups, recent runs, and outcomes.",
    )

    experiments = metrics_store.list_experiments()
    if not experiments:
        st.markdown(
            "<div class='empty-state'>No experiments found. Enable experiment tracking on a workflow to start building lineage.</div>",
            unsafe_allow_html=True,
        )
        st.code(
            """
from airflan import WorkflowOrchestrator

wf = WorkflowOrchestrator(
    name="my_workflow",
    experiment_name="my_experiment"
)
            """,
            language="python",
        )
        return

    total_runs = sum(len(metrics_store.list_runs(exp["experiment_id"])) for exp in experiments)
    completed_runs = sum(
        1
        for exp in experiments
        for run in metrics_store.list_runs(exp["experiment_id"])
        if run["status"] == "completed"
    )
    failed_runs = sum(
        1
        for exp in experiments
        for run in metrics_store.list_runs(exp["experiment_id"])
        if run["status"] == "failed"
    )
    success_rate = f"{(completed_runs / total_runs * 100):.0f}%" if total_runs else "0%"

    panel_start("Portfolio Summary", "High-level experiment health across the registry.")
    render_summary_tiles(
        [
            ("Experiments", len(experiments), None),
            ("Runs", total_runs, None),
            ("Failed", failed_runs, "#ff5f7d"),
            ("Success Rate", success_rate, "#2fd39a"),
        ]
    )
    panel_end()

    for exp in experiments:
        runs = metrics_store.list_runs(exp["experiment_id"])
        completed = sum(1 for r in runs if r["status"] == "completed")
        failed = sum(1 for r in runs if r["status"] == "failed")
        running = sum(1 for r in runs if r["status"] == "running")
        success = f"{(completed / len(runs) * 100):.0f}%" if runs else "0%"

        st.markdown(
            f"""
            <div class="experiment-block">
                <div class="experiment-title">{escape(exp['experiment_name'])}</div>
                <div class="experiment-meta">
                    Created {escape(format_time(exp['created_at']))}
                    {' | ' + escape(exp['description']) if exp.get('description') else ''}
                </div>
            """,
            unsafe_allow_html=True,
        )
        render_summary_tiles(
            [
                ("Runs", len(runs), None),
                ("Completed", completed, "#2fd39a"),
                ("Failed", failed, "#ff5f7d"),
                ("Live", running, "#f4b740"),
            ]
        )

        if runs:
            rows = []
            for run in runs:
                rows.append(
                    {
                        "Run": run["run_name"] or run["run_id"][:8],
                        "Status": run["status"].upper(),
                        "Started": format_time(run["start_time"]),
                        "Duration": format_duration(run["start_time"], run["end_time"]),
                        "Workflow": run["workflow_name"] or "N/A",
                        "Success": success,
                    }
                )
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.markdown("<div class='empty-state'>No runs recorded for this experiment.</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)


def show_run_details_page(metrics_store: MetricsStore, artifact_store: ArtifactStore):
    page_header(
        "Run Inspection",
        "Inspect one run, its metrics, parameters, and artifacts.",
    )

    experiments, all_runs = collect_runs(metrics_store)
    if not experiments or not all_runs:
        st.markdown("<div class='empty-state'>No runs found.</div>", unsafe_allow_html=True)
        return

    run_options = {
        f"{r['experiment_name']} / {r['run_name'] or r['run_id'][:8]}": r["run_id"]
        for r in all_runs
    }
    selected_label = st.selectbox("Run", list(run_options.keys()))
    run_info = metrics_store.get_run(run_options[selected_label])

    if not run_info:
        st.error("Run not found")
        return

    panel_start("Run Envelope", "Execution metadata for the selected training run.")
    st.markdown(status_badge(run_info["status"]), unsafe_allow_html=True)
    render_summary_tiles(
        [
            ("Started", format_time(run_info["start_time"]), None),
            ("Duration", format_duration(run_info["start_time"], run_info["end_time"]), None),
            ("Workflow", run_info["workflow_name"] or "N/A", None),
            ("Run ID", run_info["run_id"][:8], None),
        ]
    )
    panel_end()

    tab1, tab2, tab3 = st.tabs(["Metrics", "Parameters", "Artifacts"])
    with tab1:
        show_metrics_tab(metrics_store, run_info["run_id"])
    with tab2:
        show_parameters_tab(metrics_store, run_info["run_id"])
    with tab3:
        show_artifacts_tab(metrics_store, artifact_store, run_info["run_id"])


def show_metrics_tab(metrics_store: MetricsStore, run_id: str):
    metric_names = metrics_store.get_metric_names(run_id)
    panel_start("Metric Traces", "Step or time-series curves logged during execution.")

    if not metric_names:
        st.markdown("<div class='empty-state'>No metrics logged for this run.</div>", unsafe_allow_html=True)
        panel_end()
        return

    selected_metrics = st.multiselect(
        "Metrics",
        metric_names,
        default=metric_names[:3] if len(metric_names) >= 3 else metric_names,
    )

    for metric_name in selected_metrics:
        metrics_data = metrics_store.get_metrics(run_id, metric_name)
        if not metrics_data:
            continue

        df = pd.DataFrame(metrics_data)
        fig = go.Figure()
        if "step" in df.columns and df["step"].notna().any():
            fig.add_trace(
                go.Scatter(
                    x=df["step"],
                    y=df["metric_value"],
                    mode="lines+markers",
                    name=metric_name,
                    line=dict(width=3, color="#4ba3ff"),
                    marker=dict(size=7, color="#2fd39a"),
                )
            )
            x_title = "Step"
        else:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            fig.add_trace(
                go.Scatter(
                    x=df["timestamp"],
                    y=df["metric_value"],
                    mode="lines+markers",
                    name=metric_name,
                    line=dict(width=3, color="#4ba3ff"),
                    marker=dict(size=7, color="#2fd39a"),
                )
            )
            x_title = "Time"

        apply_plot_style(fig, metric_name, x_title, "Value")
        st.plotly_chart(fig, use_container_width=True)
        render_summary_tiles([("Latest", f"{df['metric_value'].iloc[-1]:.4f}", "#2fd39a")])

    panel_end()


def show_parameters_tab(metrics_store: MetricsStore, run_id: str):
    params = metrics_store.get_params(run_id)
    panel_start("Parameter Ledger", "Run configuration and serialized parameter values.")

    if not params:
        st.markdown("<div class='empty-state'>No parameters logged for this run.</div>", unsafe_allow_html=True)
        panel_end()
        return

    df = pd.DataFrame([{"Parameter": k, "Value": str(v)} for k, v in params.items()])
    st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("Raw Parameter JSON"):
        st.json(params)

    panel_end()


def show_artifacts_tab(metrics_store: MetricsStore, artifact_store: ArtifactStore, run_id: str):
    artifacts = metrics_store.get_artifacts(run_id)
    panel_start("Artifacts", "Files produced by the selected run and their metadata.")

    if not artifacts:
        st.markdown("<div class='empty-state'>No artifacts logged for this run.</div>", unsafe_allow_html=True)
        panel_end()
        return

    rows = []
    for artifact in artifacts:
        size_mb = artifact["size_bytes"] / (1024 * 1024) if artifact["size_bytes"] else 0
        rows.append(
            {
                "Name": artifact["artifact_name"],
                "Type": artifact["artifact_type"] or "Unknown",
                "Size": f"{size_mb:.2f} MB" if size_mb else "N/A",
                "Created": format_time(artifact["created_at"]),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    selected_artifact = st.selectbox("Artifact", [a["artifact_name"] for a in artifacts])
    artifact_path = artifact_store.get_artifact_path(run_id, selected_artifact) if selected_artifact else None

    if artifact_path and artifact_path.exists():
        suffix = artifact_path.suffix.lower()
        if suffix in [".png", ".jpg", ".jpeg", ".gif"]:
            st.image(str(artifact_path), use_container_width=True)
        elif suffix in [".txt", ".log", ".py", ".md", ".json"]:
            with open(artifact_path, "r") as f:
                st.code(
                    f.read(),
                    language=suffix[1:] if suffix[1:] in ["py", "json", "md"] else None,
                )
        else:
            with open(artifact_path, "rb") as f:
                st.download_button(
                    label=f"Download {selected_artifact}",
                    data=f,
                    file_name=selected_artifact,
                    mime="application/octet-stream",
                )
    else:
        st.markdown("<div class='empty-state'>Artifact file not found.</div>", unsafe_allow_html=True)

    panel_end()


def show_comparison_page(metrics_store: MetricsStore):
    page_header(
        "Run Comparison",
        "Compare parameter settings and metric outcomes across runs.",
    )

    experiments, all_runs = collect_runs(metrics_store)
    if not experiments or not all_runs:
        st.markdown("<div class='empty-state'>No runs found.</div>", unsafe_allow_html=True)
        return

    run_options = {
        f"{r['experiment_name']} / {r['run_name'] or r['run_id'][:8]}": r["run_id"]
        for r in all_runs
    }
    selected_runs = st.multiselect("Runs", list(run_options.keys()), max_selections=5)

    if len(selected_runs) < 2:
        st.markdown("<div class='empty-state'>Select at least two runs to compare.</div>", unsafe_allow_html=True)
        return

    selected_ids = [run_options[label] for label in selected_runs]

    panel_start("Parameter Diff", "Side-by-side view of configuration across the selected runs.")
    params_comparison = {}
    for run_label, run_id in zip(selected_runs, selected_ids):
        params_comparison[run_label] = metrics_store.get_params(run_id)

    all_param_names = set()
    for params in params_comparison.values():
        all_param_names.update(params.keys())

    rows = []
    for param_name in sorted(all_param_names):
        row = {"Parameter": param_name}
        for run_label in selected_runs:
            row[run_label] = str(params_comparison[run_label].get(param_name, "N/A"))
        rows.append(row)

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.markdown("<div class='empty-state'>No parameters available for comparison.</div>", unsafe_allow_html=True)
    panel_end()

    panel_start("Metric Comparison", "Overlay metric trajectories and inspect final values.")
    all_metric_names = set()
    for run_id in selected_ids:
        all_metric_names.update(metrics_store.get_metric_names(run_id))

    if not all_metric_names:
        st.markdown("<div class='empty-state'>No common metrics available for comparison.</div>", unsafe_allow_html=True)
        panel_end()
        return

    selected_metric = st.selectbox("Metric", sorted(all_metric_names))
    fig = go.Figure()
    final_values = []

    for run_label, run_id in zip(selected_runs, selected_ids):
        metrics_data = metrics_store.get_metrics(run_id, selected_metric)
        if not metrics_data:
            continue

        df = pd.DataFrame(metrics_data)
        if "step" in df.columns and df["step"].notna().any():
            x_data = df["step"]
            x_title = "Step"
        else:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            x_data = df["timestamp"]
            x_title = "Time"

        fig.add_trace(
            go.Scatter(
                x=x_data,
                y=df["metric_value"],
                mode="lines+markers",
                name=run_label,
                line=dict(width=3),
                marker=dict(size=6),
            )
        )
        final_values.append({"Run": run_label, f"Final {selected_metric}": f"{df['metric_value'].iloc[-1]:.4f}"})

    apply_plot_style(fig, f"Comparison: {selected_metric}", x_title, "Value")
    st.plotly_chart(fig, use_container_width=True)

    if final_values:
        st.dataframe(pd.DataFrame(final_values), use_container_width=True, hide_index=True)

    panel_end()


if __name__ == "__main__":
    main()
