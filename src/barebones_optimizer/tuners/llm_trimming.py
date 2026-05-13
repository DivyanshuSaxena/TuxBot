#!/usr/bin/env python3
"""LLM-based trimming tuner for search-space narrowing."""

import copy
import logging
from typing import Any, Dict, List, Optional, Tuple

from barebones_optimizer.parameter_manager import get_parameter_description
from barebones_optimizer.tuners.base import TunerResponse
from barebones_optimizer.tuners.llm import LLMTuner

logger = logging.getLogger(__name__)

TRIMMING_SUGGEST_PARAMS = True
TRIMMING_LOG_RANGES = True


class LLMTrimmingTuner(LLMTuner):
    """LLM tuner that adjusts effective parameter ranges before tuning proper."""

    def __init__(self, config, agent_type: str = "single"):
        self._suggest_params = getattr(config, "trimming_suggest_params", TRIMMING_SUGGEST_PARAMS)
        super().__init__(config, agent_type=agent_type)
        self.agent_type = "trimming"
        self._original_ranges: Dict[str, Any] = copy.deepcopy(self.parameter_ranges)
        self.effective_ranges: Dict[str, Any] = copy.deepcopy(self.parameter_ranges)
        self._trimming_actions: List[Dict[str, Any]] = []
        self._eliminated_params: Dict[str, Any] = {}
        logger.info("LLMTrimmingTuner initialized (suggest_params=%s)", self._suggest_params)

    def _create_base_prompt(self) -> str:
        base_prompt = super()._create_base_prompt()
        trimming_instructions = f"""
TRIMMING PHASE INSTRUCTIONS:
You are in the SEARCH SPACE TRIMMING phase. Your primary goal is to adjust the
parameter ranges to narrow or widen the search space based on observed
performance.

CURRENT EFFECTIVE PARAMETER RANGES:
{self._format_effective_ranges()}

FOR EACH CYCLE you should:
1. Observe the performance metrics from the latest configuration.
2. Decide which parameter ranges, if any, to adjust.
3. Include a "suggested_ranges" object with adjustments:
   - Numeric parameters: {{"min": <new_min>, "max": <new_max>}}
   - Categorical parameters: {{"values": [<subset of valid values>]}}
   - Include only parameters whose ranges should change.
   - You may narrow ranges to focus on promising regions.
   - You may widen ranges again, but never beyond the original bounds.
4. If a parameter appears to have no significant impact, you may list it in
   "eliminated_params". Eliminated parameters are fixed at the current value
   and excluded from future tuning for this run.
5. {"Also suggest parameter values to try in this cycle." if self._suggest_params else "Focus only on range adjustments; the system will choose parameter values."}

IMPORTANT:
- You do not need to adjust every parameter every cycle.
- Omitting a parameter from suggested_ranges leaves its range unchanged.
- An empty suggested_ranges object means no range changes this cycle.
- An empty eliminated_params list means no parameters are eliminated this cycle.
"""
        return base_prompt + trimming_instructions

    def _create_update_message(
        self,
        metrics,
        current_params,
        iteration,
        best_reward,
        history=None,
        baseline_index=0,
        aggregation_interval_s=None,
    ) -> str:
        base_msg = super()._create_update_message(
            metrics,
            current_params,
            iteration,
            best_reward,
            history,
            baseline_index,
            aggregation_interval_s,
        )

        if self._trimming_actions:
            base_msg += "\n[Trimming History]\n"
            for action in self._trimming_actions:
                base_msg += (
                    f"  Cycle {action['cycle']}: {action['param']} changed from "
                    f"{self._format_range_value(action['old_range'])} to "
                    f"{self._format_range_value(action['new_range'])}\n"
                )

        if self._eliminated_params:
            base_msg += "\n[Eliminated Parameters (fixed, no longer tuned)]\n"
            for param_name, fixed_val in self._eliminated_params.items():
                base_msg += f"  {param_name} = {fixed_val}\n"

        base_msg += f"\n[Current Effective Ranges]\n{self._format_effective_ranges()}\n"
        return base_msg

    def _build_response_schema(self) -> Optional[Dict[str, Any]]:
        try:
            properties = {}
            property_order = []

            if self._suggest_params:
                for param_name, param_range in self.parameter_ranges.items():
                    property_order.append(param_name)
                    if isinstance(param_range, tuple):
                        properties[param_name] = {
                            "type": "integer",
                            "description": get_parameter_description(param_name),
                        }
                    elif isinstance(param_range, list):
                        if all(isinstance(v, bool) for v in param_range):
                            properties[param_name] = {
                                "type": "boolean",
                                "description": get_parameter_description(param_name),
                            }
                        elif all(isinstance(v, str) for v in param_range):
                            properties[param_name] = {
                                "type": "string",
                                "enum": param_range,
                                "description": get_parameter_description(param_name),
                            }
                        else:
                            properties[param_name] = {
                                "type": "string",
                                "description": get_parameter_description(param_name),
                            }
                    else:
                        properties[param_name] = {
                            "type": "string",
                            "description": get_parameter_description(param_name),
                        }

            range_properties = {}
            for param_name, param_range in self.parameter_ranges.items():
                if isinstance(param_range, tuple):
                    range_properties[param_name] = {
                        "type": "object",
                        "description": f"New range for {param_name}",
                        "properties": {
                            "min": {"type": "integer", "description": "New minimum value"},
                            "max": {"type": "integer", "description": "New maximum value"},
                        },
                    }
                elif isinstance(param_range, list):
                    range_properties[param_name] = {
                        "type": "object",
                        "description": f"New values for {param_name}",
                        "properties": {
                            "values": {
                                "type": "array",
                                "description": "Subset of valid values to keep",
                                "items": {"type": "string"},
                            }
                        },
                    }

            properties["suggested_ranges"] = {
                "type": "object",
                "description": "Parameter range adjustments. Include only changed ranges.",
                "properties": range_properties,
            }
            property_order.append("suggested_ranges")

            all_param_names = list(self.parameter_ranges)
            properties["eliminated_params"] = {
                "type": "array",
                "description": (
                    "Parameter names to eliminate from tuning and fix at the current value. "
                    f"Valid parameter names: {all_param_names}"
                ),
                "items": {"type": "string"},
            }
            property_order.append("eliminated_params")

            properties["justification"] = {
                "type": "string",
                "description": "Brief justification for range adjustments and parameter choices",
            }
            property_order.append("justification")

            properties["converged"] = {
                "type": "boolean",
                "description": "True if the search space has been sufficiently narrowed",
            }
            property_order.append("converged")

            return {
                "type": "object",
                "properties": properties,
                "propertyOrdering": property_order,
                "description": "Trimming response with range adjustments and optional parameter values",
            }
        except Exception as exc:
            logger.warning("Failed to build trimming response schema: %s", exc)
            return None

    def _parse_structured_response(self, parsed_data: Any) -> tuple[Dict[str, Any], Optional[str], List[str]]:
        if isinstance(parsed_data, dict):
            params_dict = dict(parsed_data)
        elif hasattr(parsed_data, "__dict__"):
            params_dict = dict(parsed_data.__dict__)
        else:
            logger.warning("Unexpected structured response format: %s", type(parsed_data))
            return {}, None, []

        suggested_ranges = params_dict.pop("suggested_ranges", None)
        eliminated_params = params_dict.pop("eliminated_params", None)

        if suggested_ranges and isinstance(suggested_ranges, dict):
            self._apply_range_adjustments(suggested_ranges)
        if eliminated_params and isinstance(eliminated_params, list):
            self._apply_eliminations(eliminated_params, params_dict)

        return super()._parse_structured_response(params_dict)

    def _apply_range_adjustments(self, suggested_ranges: Dict[str, Any]) -> None:
        current_iteration = len(self.trial_history) + 1

        for param_name, adjustment in suggested_ranges.items():
            if param_name not in self._original_ranges:
                logger.warning("Trimming: unknown parameter %r in suggested_ranges", param_name)
                continue
            if not isinstance(adjustment, dict):
                logger.warning("Trimming: invalid adjustment for %r: %r", param_name, adjustment)
                continue

            original = self._original_ranges[param_name]
            old_effective = self.effective_ranges[param_name]
            if isinstance(original, tuple):
                new_range = self._adjust_numeric_range(param_name, adjustment, original)
            elif isinstance(original, list):
                new_range = self._adjust_categorical_range(param_name, adjustment, original)
            else:
                new_range = None

            if new_range is not None and new_range != old_effective:
                self._trimming_actions.append(
                    {
                        "cycle": current_iteration,
                        "param": param_name,
                        "old_range": old_effective,
                        "new_range": new_range,
                    }
                )
                self.effective_ranges[param_name] = new_range
                if TRIMMING_LOG_RANGES:
                    logger.info(
                        "Trimming [%s]: %s -> %s",
                        param_name,
                        self._format_range_value(old_effective),
                        self._format_range_value(new_range),
                    )

    def _adjust_numeric_range(
        self,
        param_name: str,
        adjustment: Dict[str, Any],
        original: Tuple[int, int],
    ) -> Optional[Tuple[int, int]]:
        orig_min, orig_max = original
        try:
            current = self.effective_ranges[param_name]
            new_min = int(adjustment.get("min", current[0]))
            new_max = int(adjustment.get("max", current[1]))
        except (ValueError, TypeError) as exc:
            logger.warning("Trimming: invalid numeric values for %r: %s", param_name, exc)
            return None

        new_min = max(orig_min, min(orig_max, new_min))
        new_max = max(orig_min, min(orig_max, new_max))
        if new_min > new_max:
            new_min, new_max = new_max, new_min
        if new_min == new_max:
            new_min = max(orig_min, new_min - 1)
            new_max = min(orig_max, new_max + 1)
        return (new_min, new_max)

    def _adjust_categorical_range(self, param_name: str, adjustment: Dict[str, Any], original: List[Any]) -> Optional[List[Any]]:
        values = adjustment.get("values")
        if not isinstance(values, list) or not values:
            logger.warning("Trimming: missing or empty values for %r", param_name)
            return None

        valid_values = []
        for value in values:
            if value in original:
                valid_values.append(value)
                continue
            for original_value in original:
                if str(original_value).lower() == str(value).lower():
                    valid_values.append(original_value)
                    break
            else:
                logger.warning("Trimming: value %r not in original range for %r", value, param_name)

        return valid_values or None

    def _apply_eliminations(self, eliminated_params: List[str], params_dict: Dict[str, Any]) -> None:
        current_iteration = len(self.trial_history) + 1

        for param_name in eliminated_params:
            if not isinstance(param_name, str):
                continue
            if param_name in self._eliminated_params or param_name not in self._original_ranges:
                continue
            if param_name not in self.effective_ranges:
                continue

            if param_name in params_dict:
                fixed_value = params_dict.pop(param_name)
            else:
                param_range = self.effective_ranges[param_name]
                if isinstance(param_range, tuple):
                    fixed_value = (param_range[0] + param_range[1]) // 2
                elif isinstance(param_range, list) and param_range:
                    fixed_value = param_range[0]
                else:
                    fixed_value = None

            old_range = self.effective_ranges.pop(param_name)
            self._eliminated_params[param_name] = fixed_value
            self._trimming_actions.append(
                {
                    "cycle": current_iteration,
                    "param": param_name,
                    "old_range": old_range,
                    "new_range": f"ELIMINATED (fixed={fixed_value})",
                }
            )
            logger.info(
                "Trimming: eliminated parameter %r (was %s, fixed at %r)",
                param_name,
                self._format_range_value(old_range),
                fixed_value,
            )

    def get_effective_ranges(self) -> Dict[str, Any]:
        return copy.deepcopy(self.effective_ranges)

    def get_eliminated_params(self) -> Dict[str, Any]:
        return copy.deepcopy(self._eliminated_params)

    def get_trimming_summary(self) -> str:
        if not self._trimming_actions and not self._eliminated_params:
            return "No trimming actions taken."

        lines = ["Trimming Summary:"]
        for action in self._trimming_actions:
            lines.append(
                f"  Cycle {action['cycle']}: {action['param']} "
                f"{self._format_range_value(action['old_range'])} -> "
                f"{self._format_range_value(action['new_range'])}"
            )
        if self._eliminated_params:
            lines.append("\nEliminated Parameters (fixed at current value):")
            for param_name, fixed_val in self._eliminated_params.items():
                lines.append(f"  {param_name} = {fixed_val}")
        lines.append("\nFinal Effective Ranges:")
        for param_name, effective in self.effective_ranges.items():
            original = self._original_ranges[param_name]
            marker = " [CHANGED]" if effective != original else ""
            lines.append(f"  {param_name}: {self._format_range_value(effective)}{marker}")
        return "\n".join(lines)

    def _format_effective_ranges(self) -> str:
        lines = []
        for param_name, effective in self.effective_ranges.items():
            original = self._original_ranges[param_name]
            if isinstance(effective, tuple):
                eff_str = f"[{effective[0]:,}, {effective[1]:,}]"
                if effective != original:
                    orig_str = f"[{original[0]:,}, {original[1]:,}]"
                    lines.append(f"  {param_name}: {eff_str} (original: {orig_str})")
                else:
                    lines.append(f"  {param_name}: {eff_str}")
            elif isinstance(effective, list):
                if effective != original:
                    lines.append(f"  {param_name}: {effective} (original: {original})")
                else:
                    lines.append(f"  {param_name}: {effective}")
            else:
                lines.append(f"  {param_name}: {effective}")
        return "\n".join(lines) if lines else "  (none)"

    @staticmethod
    def _format_range_value(value: Any) -> str:
        if isinstance(value, tuple):
            return f"[{value[0]:,}, {value[1]:,}]"
        if isinstance(value, list):
            return str(value)
        return str(value)
