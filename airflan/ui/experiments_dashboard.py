"""
AirFlan MLOps Experiments Dashboard

Streamlit-based dashboard for experiment tracking, run comparison,
and artifact management.
"""

import sys
from pathlib import Path
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from airflan.mlops import MetricsStore, ArtifactStore


def format_time(timestamp_str):
    """Format timestamp for display"""
    try:
        dt = datetime.fromisoformat(timestamp_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return str(timestamp_str)


def format_duration(start_time, end_time):
    """Calculate and format duration"""
    if not end_time:
        return "Running..."
    try:
        start = datetime.fromisoformat(start_time)
        end = datetime.fromisoformat(end_time)
        duration = (end - start).total_seconds()
        return f"{duration:.2f}s"
    except:
        return "N/A"


def main():
    st.set_page_config(
        page_title="AirFlan Experiments",
        layout="wide"
    )
    
    # Custom CSS
    st.markdown("""
        <style>
        .metric-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            border-radius: 10px;
            color: white;
        }
        .status-completed { color: #28a745; font-weight: bold; }
        .status-failed { color: #dc3545; font-weight: bold; }
        .status-running { color: #ffc107; font-weight: bold; }
        </style>
    """, unsafe_allow_html=True)
    
    # Initialize stores
    db_path = "airflan_experiments.db"
    metrics_store = MetricsStore(db_path)
    artifact_store = ArtifactStore()
    
    # Sidebar navigation
    st.sidebar.title("AirFlan MLOps")
    page = st.sidebar.radio(
        "Navigate",
        ["Experiments", "Run Details", "Compare Runs"]
    )
    
    if page == "Experiments":
        show_experiments_page(metrics_store)
    elif page == "Run Details":
        show_run_details_page(metrics_store, artifact_store)
    elif page == "Compare Runs":
        show_comparison_page(metrics_store)


def show_experiments_page(metrics_store: MetricsStore):
    """Show all experiments and runs"""
    st.title("Experiments Dashboard")
    st.markdown("---")
    
    # Get all experiments
    experiments = metrics_store.list_experiments()
    
    if not experiments:
        st.info("No experiments found. Run a workflow with experiment tracking enabled!")
        st.code("""
# Enable experiment tracking:
from airflan import WorkflowOrchestrator

wf = WorkflowOrchestrator(
    name="my_workflow",
    experiment_name="my_experiment"  # <- Add this!
)
        """, language="python")
        return
    
    # Display experiments
    for exp in experiments:
        with st.expander(f"{exp['experiment_name']}", expanded=True):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                if exp['description']:
                    st.write(exp['description'])
                st.caption(f"Created: {format_time(exp['created_at'])}")
            
            with col2:
                # Get runs count
                runs = metrics_store.list_runs(exp['experiment_id'])
                st.metric("Total Runs", len(runs))
            
            # Show runs table
            if runs:
                runs_data = []
                for run in runs:
                    runs_data.append({
                        "Run ID": run['run_id'][:8] + "...",
                        "Run Name": run['run_name'] or "Unnamed",
                        "Status": run['status'],
                        "Started": format_time(run['start_time']),
                        "Duration": format_duration(run['start_time'], run['end_time']),
                        "Workflow": run['workflow_name'] or "N/A"
                    })
                
                df = pd.DataFrame(runs_data)
                
                # Apply status coloring
                def highlight_status(val):
                    if val == 'completed':
                        return 'color: #28a745; font-weight: bold'
                    elif val == 'failed':
                        return 'color: #dc3545; font-weight: bold'
                    elif val == 'running':
                        return 'color: #ffc107; font-weight: bold'
                    return ''
                
                styled_df = df.style.applymap(highlight_status, subset=['Status'])
                st.dataframe(styled_df, use_container_width=True, hide_index=True)
                
                # Quick stats
                col1, col2, col3, col4 = st.columns(4)
                completed = sum(1 for r in runs if r['status'] == 'completed')
                failed = sum(1 for r in runs if r['status'] == 'failed')
                running = sum(1 for r in runs if r['status'] == 'running')
                
                col1.metric("Completed", completed)
                col2.metric("Failed", failed)
                col3.metric("Running", running)
                col4.metric("Success Rate", 
                           f"{(completed/len(runs)*100):.1f}%" if runs else "0%")


def show_run_details_page(metrics_store: MetricsStore, artifact_store: ArtifactStore):
    """Show detailed view of a single run"""
    st.title("Run Details")
    st.markdown("---")
    
    # Get all runs
    experiments = metrics_store.list_experiments()
    if not experiments:
        st.warning("No experiments found")
        return
    
    all_runs = []
    for exp in experiments:
        runs = metrics_store.list_runs(exp['experiment_id'])
        for run in runs:
            run['experiment_name'] = exp['experiment_name']
            all_runs.append(run)
    
    if not all_runs:
        st.warning("No runs found")
        return
    
    # Run selector
    run_options = {
        f"{r['experiment_name']} / {r['run_name'] or r['run_id'][:8]}": r['run_id']
        for r in all_runs
    }
    
    selected_run_label = st.selectbox("Select Run", list(run_options.keys()))
    selected_run_id = run_options[selected_run_label]
    
    # Get run details
    run_info = metrics_store.get_run(selected_run_id)
    
    if not run_info:
        st.error("Run not found")
        return
    
    # Display run info
    col1, col2, col3, col4 = st.columns(4)
    
    status = run_info['status']
    
    col1.metric("Status", status.upper())
    col2.metric("Started", format_time(run_info['start_time']))
    col3.metric("Duration", format_duration(run_info['start_time'], run_info['end_time']))
    col4.metric("Workflow", run_info['workflow_name'] or "N/A")
    
    st.markdown("---")
    
    # Tabs for different sections
    tab1, tab2, tab3 = st.tabs(["Metrics", "Parameters", "Artifacts"])
    
    with tab1:
        show_metrics_tab(metrics_store, selected_run_id)
    
    with tab2:
        show_parameters_tab(metrics_store, selected_run_id)
    
    with tab3:
        show_artifacts_tab(metrics_store, artifact_store, selected_run_id)


def show_metrics_tab(metrics_store: MetricsStore, run_id: str):
    """Show metrics for a run"""
    st.subheader("Metrics")
    
    metric_names = metrics_store.get_metric_names(run_id)
    
    if not metric_names:
        st.info("No metrics logged for this run")
        st.code("""
# Log metrics in your task:
@wf.task(name="train")
def train_model(context):
    for epoch in range(10):
        loss = train_one_epoch()
        context.log_metric("loss", loss, step=epoch)
        """, language="python")
        return
    
    # Metric selector
    selected_metrics = st.multiselect(
        "Select Metrics to Display",
        metric_names,
        default=metric_names[:3] if len(metric_names) >= 3 else metric_names
    )
    
    if selected_metrics:
        # Get metric data
        for metric_name in selected_metrics:
            metrics_data = metrics_store.get_metrics(run_id, metric_name)
            
            if metrics_data:
                # Create dataframe
                df = pd.DataFrame(metrics_data)
                
                # Plot
                fig = go.Figure()
                
                if 'step' in df.columns and df['step'].notna().any():
                    # Step-based plot
                    fig.add_trace(go.Scatter(
                        x=df['step'],
                        y=df['metric_value'],
                        mode='lines+markers',
                        name=metric_name,
                        line=dict(width=2),
                        marker=dict(size=6)
                    ))
                    fig.update_xaxes(title="Step")
                else:
                    # Time-based plot
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    fig.add_trace(go.Scatter(
                        x=df['timestamp'],
                        y=df['metric_value'],
                        mode='lines+markers',
                        name=metric_name,
                        line=dict(width=2),
                        marker=dict(size=6)
                    ))
                    fig.update_xaxes(title="Time")
                
                fig.update_layout(
                    title=f"{metric_name}",
                    yaxis_title="Value",
                    hovermode='x unified',
                    template='plotly_white',
                    height=400
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Show last value
                last_value = df['metric_value'].iloc[-1]
                st.metric(f"Latest {metric_name}", f"{last_value:.4f}")


def show_parameters_tab(metrics_store: MetricsStore, run_id: str):
    """Show parameters for a run"""
    st.subheader("Parameters")
    
    params = metrics_store.get_params(run_id)
    
    if not params:
        st.info("No parameters logged for this run")
        st.code("""
# Log parameters in your task:
@wf.task(name="train")
def train_model(context):
    context.log_params({
        "learning_rate": 0.001,
        "batch_size": 32,
        "epochs": 10
    })
        """, language="python")
        return
    
    # Display as table
    params_data = [{"Parameter": k, "Value": str(v)} for k, v in params.items()]
    df = pd.DataFrame(params_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Also show as JSON
    with st.expander("View as JSON"):
        st.json(params)


def show_artifacts_tab(metrics_store: MetricsStore, artifact_store: ArtifactStore, run_id: str):
    """Show artifacts for a run"""
    st.subheader("Artifacts")
    
    artifacts = metrics_store.get_artifacts(run_id)
    
    if not artifacts:
        st.info("No artifacts logged for this run")
        st.code("""
# Log artifacts in your task:
@wf.task(name="train")
def train_model(context):
    # Save model
    torch.save(model.state_dict(), "model.pth")
    context.log_artifact("model.pth", artifact_type="model")
    
    # Save plot
    plt.savefig("metrics.png")
    context.log_artifact("metrics.png", artifact_type="plot")
        """, language="python")
        return
    
    # Display artifacts table
    artifacts_data = []
    for artifact in artifacts:
        size_mb = artifact['size_bytes'] / (1024 * 1024) if artifact['size_bytes'] else 0
        artifacts_data.append({
            "Name": artifact['artifact_name'],
            "Type": artifact['artifact_type'] or "Unknown",
            "Size": f"{size_mb:.2f} MB" if size_mb > 0 else "N/A",
            "Created": format_time(artifact['created_at'])
        })
    
    df = pd.DataFrame(artifacts_data)
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Artifact viewer
    st.markdown("### Artifact Viewer")
    artifact_names = [a['artifact_name'] for a in artifacts]
    selected_artifact = st.selectbox("Select Artifact", artifact_names)
    
    if selected_artifact:
        artifact_path = artifact_store.get_artifact_path(run_id, selected_artifact)
        
        if artifact_path and artifact_path.exists():
            # Check file type
            suffix = artifact_path.suffix.lower()
            
            if suffix in ['.png', '.jpg', '.jpeg', '.gif']:
                # Display image
                st.image(str(artifact_path))
            elif suffix in ['.txt', '.log', '.py', '.md', '.json']:
                # Display text
                with open(artifact_path, 'r') as f:
                    content = f.read()
                st.code(content, language=suffix[1:] if suffix[1:] in ['py', 'json', 'md'] else None)
            else:
                # Provide download button
                with open(artifact_path, 'rb') as f:
                    st.download_button(
                        label=f"Download {selected_artifact}",
                        data=f,
                        file_name=selected_artifact,
                        mime='application/octet-stream'
                    )
        else:
            st.warning("Artifact file not found")


def show_comparison_page(metrics_store: MetricsStore):
    """Compare multiple runs"""
    st.title("Compare Runs")
    st.markdown("---")
    
    # Get all runs
    experiments = metrics_store.list_experiments()
    if not experiments:
        st.warning("No experiments found")
        return
    
    all_runs = []
    for exp in experiments:
        runs = metrics_store.list_runs(exp['experiment_id'])
        for run in runs:
            run['experiment_name'] = exp['experiment_name']
            all_runs.append(run)
    
    if not all_runs:
        st.warning("No runs found")
        return
    
    # Run selector
    run_options = {
        f"{r['experiment_name']} / {r['run_name'] or r['run_id'][:8]}": r['run_id']
        for r in all_runs
    }
    
    selected_runs = st.multiselect(
        "Select Runs to Compare (max 5)",
        list(run_options.keys()),
        max_selections=5
    )
    
    if len(selected_runs) < 2:
        st.info("Select at least 2 runs to compare")
        return
    
    selected_run_ids = [run_options[label] for label in selected_runs]
    
    # Compare parameters
    st.subheader("Parameters Comparison")
    
    params_comparison = {}
    for run_label, run_id in zip(selected_runs, selected_run_ids):
        params = metrics_store.get_params(run_id)
        params_comparison[run_label] = params
    
    if params_comparison:
        # Create comparison dataframe
        all_param_names = set()
        for params in params_comparison.values():
            all_param_names.update(params.keys())
        
        comparison_data = []
        for param_name in sorted(all_param_names):
            row = {"Parameter": param_name}
            for run_label in selected_runs:
                params = params_comparison[run_label]
                row[run_label] = str(params.get(param_name, "N/A"))
            comparison_data.append(row)
        
        df = pd.DataFrame(comparison_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Compare metrics
    st.subheader("Metrics Comparison")
    
    # Get common metric names
    all_metric_names = set()
    for run_id in selected_run_ids:
        metric_names = metrics_store.get_metric_names(run_id)
        all_metric_names.update(metric_names)
    
    if all_metric_names:
        selected_metric = st.selectbox("Select Metric", sorted(all_metric_names))
        
        if selected_metric:
            # Plot comparison
            fig = go.Figure()
            
            for run_label, run_id in zip(selected_runs, selected_run_ids):
                metrics_data = metrics_store.get_metrics(run_id, selected_metric)
                
                if metrics_data:
                    df = pd.DataFrame(metrics_data)
                    
                    if 'step' in df.columns and df['step'].notna().any():
                        fig.add_trace(go.Scatter(
                            x=df['step'],
                            y=df['metric_value'],
                            mode='lines+markers',
                            name=run_label,
                            line=dict(width=2),
                            marker=dict(size=6)
                        ))
            
            fig.update_layout(
                title=f"Comparison: {selected_metric}",
                xaxis_title="Step",
                yaxis_title="Value",
                hovermode='x unified',
                template='plotly_white',
                height=500
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Show final values table
            final_values = []
            for run_label, run_id in zip(selected_runs, selected_run_ids):
                metrics_data = metrics_store.get_metrics(run_id, selected_metric)
                if metrics_data:
                    last_value = metrics_data[-1]['metric_value']
                    final_values.append({
                        "Run": run_label,
                        f"Final {selected_metric}": f"{last_value:.4f}"
                    })
            
            if final_values:
                st.dataframe(pd.DataFrame(final_values), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
