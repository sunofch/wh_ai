"""
Warehouse Scheduling System - Unified Startup Script.
Launches all three microservices: Parser, Scheduler, and Simulation.
"""
import sys
import os
import signal
import time
import subprocess
import argparse
from typing import List

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)


class ServiceManager:
    """Manages multiple warehouse services."""

    def __init__(self):
        self.processes: List[subprocess.Popen] = []
        self.services = [
            {
                "name": "parser_service",
                "module": "services.parser_service.main",
                "port": 8001,
                "description": "Instruction Parser Service"
            },
            {
                "name": "scheduler_service",
                "module": "services.scheduler_service.main",
                "port": 8002,
                "description": "Task Scheduler Service"
            },
            {
                "name": "simulation_service",
                "module": "services.simulation_service.main",
                "port": 8003,
                "description": "Simulation Execution Service"
            },
        ]

    def start_service(self, service: dict) -> subprocess.Popen:
        """Start a single service."""
        print(f"\n{'='*60}")
        print(f"Starting {service['description']}")
        print(f"Service: {service['name']}")
        print(f"Module: {service['module']}")
        print(f"Port: {service['port']}")
        print(f"{'='*60}\n")

        # Start service using uvicorn
        cmd = [
            sys.executable, "-m", "uvicorn",
            f"{service['module']}:app",
            "--host", "127.0.0.1",
            "--port", str(service['port']),
            "--log-level", "info"
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )

        return process

    def start_all(self, services_to_start: List[str] = None):
        """Start all or specified services."""
        if services_to_start:
            services = [s for s in self.services if s["name"] in services_to_start]
        else:
            services = self.services

        print(f"\n🚀 Starting Warehouse Scheduling System")
        print(f"Services to start: {[s['name'] for s in services]}")

        # Start each service
        for service in services:
            try:
                process = self.start_service(service)
                self.processes.append((service, process))
                time.sleep(2)  # Give each service time to start
            except Exception as e:
                print(f"❌ Failed to start {service['name']}: {e}")

        # Print status
        self.print_status()

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Monitor processes
        self.monitor()

    def stop_all(self):
        """Stop all services."""
        print("\n\n🛑 Stopping all services...")

        for service, process in self.processes:
            print(f"Stopping {service['name']}...")
            process.terminate()

        # Wait for processes to stop
        for service, process in self.processes:
            try:
                process.wait(timeout=5)
                print(f"✓ {service['name']} stopped")
            except subprocess.TimeoutExpired:
                print(f"⚠ {service['name']} did not stop gracefully, killing...")
                process.kill()

        print("\n✓ All services stopped")

    def print_status(self):
        """Print status of all services."""
        print(f"\n{'='*60}")
        print("📊 Service Status")
        print(f"{'='*60}")

        for service, process in self.processes:
            if process.poll() is None:
                status = "✓ Running"
                url = f"http://127.0.0.1:{service['port']}"
            else:
                status = "✗ Stopped"
                url = "N/A"

            print(f"\n{service['description']}")
            print(f"  Status: {status}")
            print(f"  URL: {url}")
            print(f"  Docs: {url}/docs" if url != "N/A" else "")

        print(f"\n{'='*60}\n")

    def monitor(self):
        """Monitor running processes."""
        print("Services are running. Press Ctrl+C to stop.\n")

        try:
            while True:
                # Check if any process died
                for service, process in self.processes:
                    if process.poll() is not None:
                        print(f"⚠ Service {service['name']} has stopped unexpectedly!")
                        print(f"   Exit code: {process.returncode}")

                time.sleep(5)

        except KeyboardInterrupt:
            pass

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.stop_all()
        sys.exit(0)


def check_dependencies():
    """Check if required dependencies are installed."""
    print("Checking dependencies...")

    missing = []

    # Check FastAPI
    try:
        import fastapi
        print("  ✓ FastAPI")
    except ImportError:
        missing.append("fastapi")
        print("  ✗ FastAPI (not installed)")

    # Check OR-Tools
    try:
        import ortools
        print("  ✓ OR-Tools")
    except ImportError:
        missing.append("ortools")
        print("  ✗ OR-Tools (not installed)")

    # Check Gymnasium
    try:
        import gymnasium
        print("  ✓ Gymnasium")
    except ImportError:
        missing.append("gymnasium")
        print("  ✗ Gymnasium (not installed)")

    if missing:
        print(f"\n⚠ Missing dependencies: {', '.join(missing)}")
        print("Install with: pip install " + " ".join(missing))
        return False

    print("\n✓ All dependencies installed\n")
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Warehouse Scheduling System - Unified Startup"
    )
    parser.add_argument(
        "command",
        choices=["start", "stop", "status", "check"],
        help="Command to execute",
        nargs="?",
        default="start"
    )
    parser.add_argument(
        "--services",
        nargs="+",
        choices=["parser_service", "scheduler_service", "simulation_service"],
        help="Specific services to start (default: all)"
    )

    args = parser.parse_args()

    if args.command == "check":
        check_dependencies()
        return

    if args.command == "start":
        if not check_dependencies():
            print("\n⚠ Please install missing dependencies before starting services")
            sys.exit(1)

        manager = ServiceManager()
        manager.start_all(args.services)


if __name__ == "__main__":
    main()
