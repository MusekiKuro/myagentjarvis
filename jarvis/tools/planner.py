"""
tools/planner.py — Task Planner для многошаговых задач.

LLM разбивает сложную задачу на 3–7 шагов, каждый шаг — tool_call,
которые выполняются последовательно. Результаты накапливаются и
передаются обратно LLM для финального суммаризирующего ответа.

Пример:
    Пользователь: "Посмотри что написали в вотсапе про ноутбук и найди дешевле"
    Planner:
        Шаг 1: messenger.whatsapp_get_messages(chat="...", count=5)
        Шаг 2: search.web_search(query="ноутбук HP цена купить")
        Шаг 3: text_response (суммаризация)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Максимальное количество шагов в плане
MAX_PLAN_STEPS = 7


@dataclass
class PlanStep:
    """Один шаг плана выполнения."""
    step_num: int
    tool: str                  # Имя инструмента
    params: dict[str, Any]     # Параметры вызова
    description: str = ""      # Человекочитаемое описание шага
    result: Optional[str] = None  # Заполняется после выполнения
    error: Optional[str] = None


@dataclass
class ExecutionPlan:
    """Полный план выполнения задачи."""
    task: str                          # Исходная задача пользователя
    steps: list[PlanStep] = field(default_factory=list)
    summary: str = ""                  # Итоговая суммаризация после выполнения


_PLAN_SYSTEM_PROMPT = """\
Ты планировщик задач для голосового ИИ-ассистента JARVIS.
Получив задачу, разбей её на минимальное количество шагов (3-7).
Каждый шаг — это один вызов инструмента.

Доступные инструменты:
{tools_description}

Верни ТОЛЬКО валидный JSON (без пояснений):
{{
  "task": "<задача>",
  "steps": [
    {{
      "step": 1,
      "tool": "<имя инструмента>",
      "params": {{"param": "value"}},
      "description": "<краткое описание что делает этот шаг>"
    }},
    ...
  ]
}}

Если задача не требует инструментов — верни шаг с tool="text_response" и params={{"answer": "..."}}.
"""


def create_plan(task: str, dispatcher) -> ExecutionPlan:
    """
    Создать план выполнения задачи через LLM.

    Args:
        task: Задача пользователя.
        dispatcher: Экземпляр ToolDispatcher для получения описаний инструментов.

    Returns:
        ExecutionPlan с распарсенными шагами.
    """
    tools_desc = _build_tools_description(dispatcher)
    system_prompt = _PLAN_SYSTEM_PROMPT.format(tools_description=tools_desc)

    try:
        from jarvis.core.brain import Brain
        # Создаём временный Brain только для планировщика (без истории)
        from jarvis.memory.short_term import ShortTermMemory
        temp_stm = ShortTermMemory()
        planner_brain = Brain(short_term=temp_stm)

        response_chunks = []
        for chunk in planner_brain._stream_api(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Задача: {task}"},
            ],
        ):
            response_chunks.append(chunk)

        raw_response = "".join(response_chunks)
        logger.info("Planner: LLM ответ:\n%s", raw_response[:500])

        plan = _parse_plan_response(task, raw_response)
        return plan

    except Exception as e:
        logger.error("Planner: ошибка создания плана: %s", e)
        # Fallback: простой план с поиском
        return ExecutionPlan(
            task=task,
            steps=[
                PlanStep(
                    step_num=1,
                    tool="search",
                    params={"query": task},
                    description=f"Поиск по запросу: {task}",
                )
            ],
        )


def execute_plan(plan: ExecutionPlan, dispatcher, ltm=None) -> str:
    """
    Выполнить план пошагово.

    Args:
        plan: ExecutionPlan для выполнения.
        dispatcher: ToolDispatcher для вызова инструментов.
        ltm: LongTermMemory для сохранения истории задач (опционально).

    Returns:
        Финальная суммаризация результатов.
    """
    results_log = []

    for step in plan.steps:
        logger.info(
            "Planner: выполняю шаг %d/%d: %s(%r)",
            step.step_num, len(plan.steps), step.tool, step.params
        )

        # text_response — это финальный шаг, не tool_call
        if step.tool == "text_response":
            step.result = step.params.get("answer", "")
            results_log.append(f"Шаг {step.step_num} (итог): {step.result}")
            continue

        # Выполняем через dispatcher
        from .dispatcher import ToolCall
        tc = ToolCall(tool=step.tool, params=step.params)
        try:
            result = dispatcher.execute(tc)
            step.result = result
            results_log.append(
                f"Шаг {step.step_num}: {step.description or step.tool}\n"
                f"Результат: {result[:500]}{'…' if len(result) > 500 else ''}"
            )
        except Exception as e:
            step.error = str(e)
            results_log.append(f"Шаг {step.step_num}: ОШИБКА — {e}")
            logger.error("Planner: ошибка шага %d: %s", step.step_num, e)

    # Суммаризация через LLM
    all_results = "\n\n".join(results_log)
    summary = _summarize_results(plan.task, all_results)
    plan.summary = summary

    # Сохранить в историю задач
    if ltm is not None:
        try:
            ltm.save_task(
                task=plan.task,
                steps_count=len(plan.steps),
                result_summary=summary[:500],
                status="completed" if not any(s.error for s in plan.steps) else "partial",
            )
        except Exception as e:
            logger.warning("Planner: не удалось сохранить историю задачи: %s", e)

    return summary


def _build_tools_description(dispatcher) -> str:
    """Построить описание инструментов для промпта планировщика."""
    lines = []
    for name, spec in dispatcher.tools.items():
        params = ", ".join(f"{k}: {v}" for k, v in spec.parameters.items()) or "нет параметров"
        dangerous = " [⚠️ опасный]" if spec.dangerous else ""
        lines.append(f"- {name}{dangerous}: {spec.description} Параметры: {{{params}}}")
    lines.append("- text_response: Дать текстовый ответ без инструментов. Параметры: {answer: строка}")
    return "\n".join(lines)


def _parse_plan_response(task: str, raw: str) -> ExecutionPlan:
    """Разобрать JSON-ответ LLM в ExecutionPlan."""
    import re

    # Пробуем найти JSON в ответе
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        raise ValueError(f"Не найден JSON в ответе планировщика: {raw[:200]}")

    data = json.loads(json_match.group())
    steps_raw = data.get("steps", [])

    steps = []
    for s in steps_raw[:MAX_PLAN_STEPS]:
        steps.append(PlanStep(
            step_num=s.get("step", len(steps) + 1),
            tool=s.get("tool", "text_response"),
            params=s.get("params", {}),
            description=s.get("description", ""),
        ))

    if not steps:
        raise ValueError("Пустой план.")

    return ExecutionPlan(task=data.get("task", task), steps=steps)


def _summarize_results(task: str, results_text: str) -> str:
    """Суммаризировать результаты выполнения плана через LLM."""
    try:
        from jarvis.core.brain import Brain
        from jarvis.memory.short_term import ShortTermMemory

        temp_stm = ShortTermMemory()
        summarizer = Brain(short_term=temp_stm)

        prompt = (
            f"Пользователь просил: «{task}»\n\n"
            f"Я выполнил следующие шаги:\n\n{results_text}\n\n"
            f"Подведи итог на русском языке, кратко и чётко. "
            f"Отвечай от лица ИИ-ассистента JARVIS."
        )

        chunks = []
        for chunk in summarizer._stream_api(
            messages=[
                {"role": "system", "content": "Ты JARVIS — голосовой ИИ-ассистент. Отвечай кратко по-русски."},
                {"role": "user", "content": prompt},
            ],
        ):
            chunks.append(chunk)

        return "".join(chunks).strip()

    except Exception as e:
        logger.error("Planner: ошибка суммаризации: %s", e)
        # Fallback — вернуть сырые результаты
        return f"Задача «{task}» выполнена:\n\n{results_text}"
