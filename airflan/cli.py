import click
import os
import sys
import subprocess
from pathlib import Path
from loguru import logger

from airflan.scheduler_daemon import SchedulerDaemon
from airflan.storage.backend import DatabaseSession
from airflan.worker import WorkerDaemon

@click.group()
def cli():
    """AirFlan Enterprise Workflow Orchestrator"""
    pass

@cli.command()
@click.option('--db-url', default=None, help='Metadata database URL')
def initdb(db_url):
    """Initialize the AirFlan SQLite database"""
    db = DatabaseSession(db_url)
    db.init_db()
    click.echo(click.style(f"Database initialized successfully: {db.db_url}", fg="green"))

@cli.command()
@click.option('--workflows-dir', default='workflows', help='Directory containing dag files')
@click.option('--parse-interval', default=10, help='Seconds between directory rescans')
@click.option('--db-url', default=None, help='Metadata database URL')
def scheduler(workflows_dir, parse_interval, db_url):
    """Start the Scheduler Daemon"""
    click.echo(click.style(f"Starting AirFlan Scheduler Daemon scanning directory: {workflows_dir}", fg="cyan", bold=True))
    daemon = SchedulerDaemon(workflows_dir=workflows_dir, parse_interval=parse_interval, db_url=db_url)
    daemon.run()

@cli.command()
@click.option('--workflows-dir', default='workflows', help='Directory containing dag files')
@click.option('--poll-interval', default=5, help='Seconds between queue polls')
@click.option('--once', is_flag=True, help='Process one queue step and exit')
@click.option('--db-url', default=None, help='Metadata database URL')
@click.option('--worker-id', default=None, help='Stable worker identifier')
@click.option('--heartbeat-interval', default=5, help='Seconds between task heartbeats')
@click.option('--heartbeat-timeout', default=60, help='Seconds before a running task is considered stale')
def worker(workflows_dir, poll_interval, once, db_url, worker_id, heartbeat_interval, heartbeat_timeout):
    """Start a worker that executes queued workflow runs"""
    click.echo(click.style(f"Starting AirFlan Worker scanning directory: {workflows_dir}", fg="cyan", bold=True))
    daemon = WorkerDaemon(
        workflows_dir=workflows_dir,
        poll_interval=poll_interval,
        db_url=db_url,
        worker_id=worker_id,
        heartbeat_interval=heartbeat_interval,
        heartbeat_timeout=heartbeat_timeout,
    )
    if once:
        did_work = daemon.run_once()
        if not did_work:
            click.echo("No queued workflow runs found.")
        return
    daemon.run()

@cli.command()
@click.option('--port', default=6969, help='Port to run the webserver on')
@click.option('--db-url', default=None, help='Metadata database URL')
def webserver(port, db_url):
    """Start the AirFlan UI Webserver"""
    click.echo(click.style(f"Starting AirFlan UI on port {port}", fg="blue", bold=True))
    
    ui_script = Path(__file__).parent / "ui.py"
    
    # Set up environment for Streamlit to know it's reading from DB
    env = os.environ.copy()
    env["AIRFLAN_USE_DB"] = "1"
    if db_url:
        env["AIRFLAN_DATABASE_URL"] = db_url
    
    try:
        subprocess.run(
            ["streamlit", "run", str(ui_script), "--server.port", str(port)],
            env=env
        )
    except KeyboardInterrupt:
        click.echo("Webserver stopped.")

if __name__ == '__main__':
    cli()
