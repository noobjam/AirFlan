import click
import os
import sys
import subprocess
from pathlib import Path
from loguru import logger

from airflan.scheduler_daemon import SchedulerDaemon
from airflan.storage.backend import DatabaseSession

@click.group()
def cli():
    """AirFlan Enterprise Workflow Orchestrator"""
    pass

@cli.command()
def initdb():
    """Initialize the AirFlan SQLite database"""
    db = DatabaseSession()
    db.init_db()
    click.echo(click.style("Database initialized successfully at airflan_metadata.db", fg="green"))

@cli.command()
@click.option('--workflows-dir', default='workflows', help='Directory containing dag files')
@click.option('--parse-interval', default=10, help='Seconds between directory rescans')
def scheduler(workflows_dir, parse_interval):
    """Start the Scheduler Daemon"""
    click.echo(click.style(f"Starting AirFlan Scheduler Daemon scanning directory: {workflows_dir}", fg="cyan", bold=True))
    daemon = SchedulerDaemon(workflows_dir=workflows_dir, parse_interval=parse_interval)
    daemon.run()

@cli.command()
@click.option('--port', default=6969, help='Port to run the webserver on')
def webserver(port):
    """Start the AirFlan UI Webserver"""
    click.echo(click.style(f"Starting AirFlan UI on port {port}", fg="blue", bold=True))
    
    ui_script = Path(__file__).parent / "ui.py"
    
    # Set up environment for Streamlit to know it's reading from DB
    env = os.environ.copy()
    env["AIRFLAN_USE_DB"] = "1"
    
    try:
        subprocess.run(
            ["streamlit", "run", str(ui_script), "--server.port", str(port)],
            env=env
        )
    except KeyboardInterrupt:
        click.echo("Webserver stopped.")

if __name__ == '__main__':
    cli()
