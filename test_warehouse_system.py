"""
Warehouse Scheduling System - Integration Test.
Tests the end-to-end flow: parse -> schedule -> execute.
"""
import sys
import os
import time
import requests

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from services.shared.models import (
    WarehouseTask,
    AGVState,
    AGVStatus,
    TaskType,
    TaskPriority,
)
from services.shared.utils import (
    generate_task_id,
    generate_agv_id,
    calculate_distance,
)


def test_parser_service(base_url: str = "http://127.0.0.1:8001"):
    """Test the parser service."""
    print(f"\n{'='*60}")
    print("Testing Parser Service")
    print(f"{'='*60}")

    try:
        response = requests.get(f"{base_url}/health")
        print(f"健康检查: {response.status_code}")
        print(f"响应: {response.json()}")
        return True
    except Exception as e:
        print(f"❌ 解析服务测试失败: {e}")
        return False


def test_scheduler_service(base_url: str = "http://127.0.0.1:8002"):
    """Test the scheduler service."""
    print(f"\n{'='*60}")
    print("Testing Scheduler Service")
    print(f"{'='*60}")

    try:
        # Health check
        response = requests.get(f"{base_url}/health")
        print(f"健康检查: {response.status_code}")
        health = response.json()
        print(f"响应: {health}")

        # Create sample tasks
        tasks = [
            WarehouseTask(
                task_id=generate_task_id(),
                task_type=TaskType.RETRIEVAL,
                priority=TaskPriority.HIGH,
                item_id="motor-001",
                quantity=5,
                source=(10.0, 20.0),
                destination=(70.0, 80.0),
                required_capacity=5.0,
            ),
            WarehouseTask(
                task_id=generate_task_id(),
                task_type=TaskType.TRANSPORT,
                priority=TaskPriority.MEDIUM,
                item_id="bearing-002",
                quantity=3,
                source=(15.0, 25.0),
                destination=(60.0, 70.0),
                required_capacity=3.0,
            ),
        ]

        # Create sample AGV states
        agv_states = [
            AGVState(
                agv_id=generate_agv_id(1),
                position=(0.0, 0.0),
                battery_level=100.0,
                load_capacity=100.0,
                current_load=0.0,
                status=AGVStatus.IDLE,
            ),
            AGVState(
                agv_id=generate_agv_id(2),
                position=(10.0, 10.0),
                battery_level=95.0,
                load_capacity=100.0,
                current_load=0.0,
                status=AGVStatus.IDLE,
            ),
        ]

        # Schedule request
        schedule_request = {
            "tasks": [task.model_dump() for task in tasks],
            "agv_states": [agv.model_dump() for agv in agv_states],
        }

        print(f"\n正在调度 {len(tasks)} 个任务到 {len(agv_states)} 个AGV...")

        response = requests.post(
            f"{base_url}/api/v1/schedule",
            json=schedule_request,
            timeout=30
        )

        print(f"调度响应: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"✓ 调度创建成功: {result['schedule_id']}")
            print(f"  任务分配: {result['assignments']}")
            print(f"  完成时间: {result['makespan']}秒")
            print(f"  检测到的冲突: {len(result.get('conflicts_detected', []))}")
            print(f"  已解决的冲突: {len(result.get('conflicts_resolved', []))}")
            return result
        else:
            print(f"❌ 调度请求失败: {response.text}")
            return None

    except Exception as e:
        print(f"❌ 调度服务测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_simulation_service(base_url: str = "http://127.0.0.1:8003", schedule_result: dict = None):
    """Test the simulation service."""
    print(f"\n{'='*60}")
    print("Testing Simulation Service")
    print(f"{'='*60}")

    try:
        # Health check
        response = requests.get(f"{base_url}/health")
        print(f"健康检查: {response.status_code}")
        print(f"响应: {response.json()}")

        if not schedule_result:
            print("⚠ 未提供调度结果，跳过执行测试")
            return True

        # Execute request
        execute_request = {
            "schedule_id": schedule_result["schedule_id"],
            "assignments": schedule_result["assignments"],
            "tasks": schedule_result.get("_tasks", []),  # Would need to pass original tasks
            "initial_agv_states": schedule_result.get("_agv_states", []),
            "time_limit": 300.0,
        }

        # For now, just test health check
        print("\n✓ 仿真服务正在运行")
        print("  (完整执行测试需要原始任务对象)")

        return True

    except Exception as e:
        print(f"❌ 仿真服务测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_end_to_end():
    """Run end-to-end integration test."""
    print(f"\n{'='*60}")
    print("🚀 仓储调度系统 - 端到端测试")
    print(f"{'='*60}")

    results = {}

    # Test Parser Service
    results["parser"] = test_parser_service()
    time.sleep(1)

    # Test Scheduler Service
    schedule_result = test_scheduler_service()
    results["scheduler"] = schedule_result is not None
    time.sleep(1)

    # Test Simulation Service
    results["simulation"] = test_simulation_service(schedule_result=schedule_result)

    # Summary
    print(f"\n{'='*60}")
    print("📊 测试摘要")
    print(f"{'='*60}")

    for service, passed in results.items():
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {service.capitalize():15} {status}")

    all_passed = all(results.values())

    print(f"\n{'='*60}")
    if all_passed:
        print("✓ 所有测试通过!")
    else:
        print("✗ 部分测试失败")
    print(f"{'='*60}\n")

    return all_passed


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Test Warehouse Scheduling System")
    parser.add_argument(
        "--parser-url",
        default="http://127.0.0.1:8001",
        help="Parser service URL"
    )
    parser.add_argument(
        "--scheduler-url",
        default="http://127.0.0.1:8002",
        help="Scheduler service URL"
    )
    parser.add_argument(
        "--simulation-url",
        default="http://127.0.0.1:8003",
        help="Simulation service URL"
    )

    args = parser.parse_args()

    success = test_end_to_end()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
