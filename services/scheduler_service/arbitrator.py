"""
VLM Arbitrator.
Uses Vision Language Model to resolve scheduling conflicts.
"""
from typing import List, Dict, Optional
from datetime import datetime

from services.shared.models import (
    ConflictInfo,
    ArbitrationResult,
    WarehouseTask,
    AGVState,
)
from services.shared.utils import (
    generate_conflict_id,
    ServiceLogger,
)


class VLMArbitrator:
    """
    Arbitrates conflicts using VLM reasoning.
    Activates when traditional scheduling algorithms cannot resolve conflicts.
    """

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.logger = ServiceLogger.get_logger("VLMArbitrator")
        self._vlm = None

    def _get_vlm(self):
        """Lazy load VLM instance."""
        if self._vlm is None:
            try:
                from src.vlm import get_vlm_instance
                self._vlm = get_vlm_instance()
                self.logger.info("VLM arbitrator initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize VLM arbitrator: {e}")
                self._vlm = "error"
        return self._vlm

    def arbitrate(
        self,
        conflicts: List[ConflictInfo],
        tasks: List[WarehouseTask],
        agv_states: List[AGVState],
        current_assignments: Dict[str, str]
    ) -> List[ArbitrationResult]:
        """
        Arbitrate conflicts using VLM reasoning.

        Args:
            conflicts: List of detected conflicts
            tasks: All tasks being scheduled
            agv_states: Current AGV states
            current_assignments: Current task-to-AGV assignments

        Returns:
            List of arbitration results with proposed resolutions
        """
        if not conflicts:
            return []

        vlm = self._get_vlm()
        if vlm == "error":
            self.logger.error("VLM not available for arbitration")
            return []

        results = []

        for conflict in conflicts:
            try:
                result = self._arbitrate_single_conflict(
                    conflict,
                    tasks,
                    agv_states,
                    current_assignments
                )
                if result:
                    results.append(result)
            except Exception as e:
                self.logger.error(f"Failed to arbitrate conflict {conflict.conflict_id}: {e}")

        return results

    def _arbitrate_single_conflict(
        self,
        conflict: ConflictInfo,
        tasks: List[WarehouseTask],
        agv_states: List[AGVState],
        current_assignments: Dict[str, str]
    ) -> Optional[ArbitrationResult]:
        """Arbitrate a single conflict."""
        # Build context prompt
        context = self._build_conflict_context(
            conflict,
            tasks,
            agv_states,
            current_assignments
        )

        # Create arbitration prompt
        prompt = self._create_arbitration_prompt(context)

        # Query VLM
        try:
            vlm = self._get_vlm()

            # Use text-based reasoning
            response = vlm.extract_structured_info(text=prompt)

            # Parse response into ArbitrationResult
            return self._parse_arbitration_response(
                conflict.conflict_id,
                response,
                conflict
            )

        except Exception as e:
            self.logger.error(f"VLM arbitration failed: {e}")
            return None

    def _build_conflict_context(
        self,
        conflict: ConflictInfo,
        tasks: List[WarehouseTask],
        agv_states: List[AGVState],
        current_assignments: Dict[str, str]
    ) -> str:
        """Build context description of the conflict."""
        task_dict = {task.task_id: task for task in tasks}
        agv_dict = {agv.agv_id: agv for agv in agv_states}

        context = f"冲突类型: {conflict.conflict_type.value}\n"
        context += f"冲突描述: {conflict.description}\n"
        context += f"严重程度: {conflict.severity:.2f}\n\n"

        context += "涉及的AGV:\n"
        for agv_id in conflict.involved_agvs:
            if agv_id in agv_dict:
                agv = agv_dict[agv_id]
                context += f"  - {agv_id}: 位置{agv.position}, 电量{agv.battery_level}%, "
                context += f"载重{agv.current_load}/{agv.load_capacity}\n"

        context += "\n涉及的任务:\n"
        for task_id in conflict.involved_tasks:
            if task_id in task_dict:
                task = task_dict[task_id]
                context += f"  - {task_id}: 类型{task.task_type.value}, "
                context += f"优先级{task.priority.value}, "
                context += f"从{task.source}到{task.destination}\n"
                if task.deadline:
                    context += f"    截止时间: {task.deadline}\n"

        return context

    def _create_arbitration_prompt(self, context: str) -> str:
        """Create arbitration prompt for VLM."""
        prompt = f"""你是一个仓储调度的仲裁者。请分析以下冲突并提供解决方案。

{context}

请提供以下信息：
1. resolution: 推荐的解决方案策略（例如：重新分配任务、调整顺序、延迟某些任务等）
2. reasoning: 详细说明你推荐这个方案的原因
3. confidence: 你对这个方案的信心程度（0-1之间的浮点数）
4. new_assignments: 如果需要重新分配，提供新的任务-AGV分配（JSON格式，键为任务ID，值为AGV ID）
5. alternative_solutions: 考虑过的其他可选方案列表

请以JSON格式返回，包含以上所有字段。"""
        return prompt

    def _parse_arbitration_response(
        self,
        conflict_id: str,
        response: dict,
        original_conflict: ConflictInfo
    ) -> ArbitrationResult:
        """Parse VLM response into ArbitrationResult."""
        if not isinstance(response, dict):
            response = {}

        return ArbitrationResult(
            conflict_id=conflict_id,
            resolution=response.get("resolution", "No resolution provided"),
            new_assignments=response.get("new_assignments", {}),
            reasoning=response.get("reasoning", "No reasoning provided"),
            confidence=float(response.get("confidence", 0.5)),
            alternative_solutions=response.get("alternative_solutions", []),
        )

    def arbitrate_simple(
        self,
        conflict_description: str,
        available_agvs: List[str],
        task_priorities: Dict[str, str]
    ) -> Optional[str]:
        """
        Simple arbitration for quick decisions.

        Returns:
            Recommended resolution as string
        """
        vlm = self._get_vlm()
        if vlm == "error":
            return None

        prompt = f"""请为以下仓储调度冲突提供简短的解决方案建议。

冲突描述: {conflict_description}
可用AGV: {', '.join(available_agvs)}
任务优先级: {task_priorities}

请在50字以内说明推荐的解决方案。"""

        try:
            response = vlm.extract_structured_info(text=prompt)
            if isinstance(response, dict):
                return response.get("description", response.get("raw_response", ""))
            return str(response)
        except Exception as e:
            self.logger.error(f"Simple arbitration failed: {e}")
            return None
