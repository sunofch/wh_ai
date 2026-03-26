"""
Converter: PortInstruction to WarehouseTask.
Transforms port instruction parsing results into warehouse scheduling tasks.
"""
import re
from typing import Optional, List
from datetime import datetime, timedelta

from src.parser import PortInstruction
from services.shared.models import (
    WarehouseTask,
    TaskType,
    TaskPriority,
)
from services.shared.utils import (
    generate_task_id,
    ServiceLogger,
)


# Mapping of priority keywords to TaskPriority
PRIORITY_KEYWORDS = {
    'critical': TaskPriority.CRITICAL,
    '紧急': TaskPriority.CRITICAL,
    'urgent': TaskPriority.CRITICAL,
    'high': TaskPriority.HIGH,
    '高': TaskPriority.HIGH,
    '重要': TaskPriority.HIGH,
    'medium': TaskPriority.MEDIUM,
    'normal': TaskPriority.MEDIUM,
    'low': TaskPriority.LOW,
    '低': TaskPriority.LOW,
}

# Default warehouse locations (can be configured)
DEFAULT_STORAGE_LOCATIONS = {
    '电机': (10.0, 20.0),
    '传送带': (30.0, 40.0),
    '轴承': (15.0, 25.0),
    'default': (0.0, 0.0),
}

# Equipment locations in the warehouse
EQUIPMENT_LOCATIONS = {
    '1号传送带': (50.0, 60.0),
    '2号传送带': (60.0, 70.0),
    '3号传送带': (70.0, 80.0),
    '岸桥': (40.0, 50.0),
    '场桥': (45.0, 55.0),
    '正面吊': (55.0, 65.0),
}


class PortInstructionConverter:
    """Converts PortInstruction to WarehouseTask."""

    def __init__(self):
        self.logger = ServiceLogger.get_logger("PortInstructionConverter")

    def convert(
        self,
        instruction: PortInstruction,
        raw_input: Optional[str] = None
    ) -> WarehouseTask:
        """
        Convert PortInstruction to WarehouseTask.

        Args:
            instruction: Parsed port instruction
            raw_input: Original raw input text (for priority detection)

        Returns:
            WarehouseTask object
        """
        task_id = generate_task_id()
        task_type = self._determine_task_type(instruction, raw_input)
        priority = self._determine_priority(instruction, raw_input)

        # Determine source and destination
        source, destination = self._determine_locations(instruction)

        # Calculate required capacity based on quantity
        required_capacity = self._estimate_capacity(instruction)

        # Estimate duration
        estimated_duration = self._estimate_duration(source, destination)

        task = WarehouseTask(
            task_id=task_id,
            task_type=task_type,
            priority=priority,
            item_id=instruction.part_name,
            quantity=instruction.quantity or 1,
            source=source,
            destination=destination,
            required_capacity=required_capacity,
            deadline=self._determine_deadline(priority),
            estimated_duration=estimated_duration,
        )

        self.logger.info(
            f"Converted instruction to task: {task_id}, "
            f"type={task_type}, priority={priority}"
        )

        return task

    def _determine_task_type(
        self,
        instruction: PortInstruction,
        raw_input: Optional[str]
    ) -> TaskType:
        """Determine task type from instruction."""
        action = (instruction.action_required or "").lower()
        text = (raw_input or "").lower()

        if any(keyword in action or keyword in text for keyword in
               ['充电', 'charging', 'charge']):
            return TaskType.CHARGING

        if any(keyword in action or keyword in text for keyword in
               ['存放', '入库', 'storage', 'store', 'put']):
            return TaskType.STORAGE

        return TaskType.RETRIEVAL

    def _determine_priority(
        self,
        instruction: PortInstruction,
        raw_input: Optional[str]
    ) -> TaskPriority:
        """Determine task priority from instruction and raw input."""
        # Check in action_required
        if instruction.action_required:
            action_lower = instruction.action_required.lower()
            for keyword, priority in PRIORITY_KEYWORDS.items():
                if keyword in action_lower:
                    return priority

        # Check in description
        if instruction.description:
            desc_lower = instruction.description.lower()
            for keyword, priority in PRIORITY_KEYWORDS.items():
                if keyword in desc_lower:
                    return priority

        # Check in raw input
        if raw_input:
            raw_lower = raw_input.lower()
            for keyword, priority in PRIORITY_KEYWORDS.items():
                if keyword in raw_lower:
                    return priority

        return TaskPriority.MEDIUM

    def _determine_locations(
        self,
        instruction: PortInstruction
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        """
        Determine source and destination locations.
        Returns (source, destination) tuple.
        """
        # Try to find storage location based on part name
        source = DEFAULT_STORAGE_LOCATIONS.get('default', (0.0, 0.0))
        if instruction.part_name:
            for keyword, location in DEFAULT_STORAGE_LOCATIONS.items():
                if keyword and keyword in instruction.part_name:
                    source = location
                    break

        # Try to find equipment location
        destination = source  # Default to source if not found
        if instruction.installation_equipment:
            for keyword, location in EQUIPMENT_LOCATIONS.items():
                if keyword in instruction.installation_equipment:
                    destination = location
                    break
        elif instruction.location:
            # Try to parse location description
            for keyword, location in EQUIPMENT_LOCATIONS.items():
                if keyword in instruction.location:
                    destination = location
                    break

        return source, destination

    def _estimate_capacity(self, instruction: PortInstruction) -> float:
        """Estimate required capacity based on instruction."""
        base_capacity = 1.0  # Base capacity per item

        # Scale by quantity
        quantity = instruction.quantity or 1
        return base_capacity * quantity

    def _estimate_duration(
        self,
        source: tuple[float, float],
        destination: tuple[float, float],
        speed: float = 1.0
    ) -> float:
        """Estimate task duration in seconds."""
        from services.shared.utils import calculate_distance, estimate_travel_time

        distance = calculate_distance(source, destination)
        travel_time = estimate_travel_time(distance, speed)

        # Add loading/unloading time (default 30 seconds)
        handling_time = 30.0

        return travel_time + handling_time

    def _determine_deadline(self, priority: TaskPriority) -> Optional[datetime]:
        """Determine task deadline based on priority."""
        now = datetime.now()

        if priority == TaskPriority.CRITICAL:
            # 30 minutes for critical tasks
            return now + timedelta(minutes=30)
        elif priority == TaskPriority.HIGH:
            # 2 hours for high priority
            return now + timedelta(hours=2)
        elif priority == TaskPriority.MEDIUM:
            # 1 day for medium priority
            return now + timedelta(days=1)
        else:
            # No deadline for low priority
            return None


def convert_instruction_to_task(
    instruction: PortInstruction,
    raw_input: Optional[str] = None
) -> WarehouseTask:
    """
    Convenience function to convert PortInstruction to WarehouseTask.
    """
    converter = PortInstructionConverter()
    return converter.convert(instruction, raw_input)
