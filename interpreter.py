from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Union

from constant import ExecState, FrameType, ScopeType
from oper import Oper, create_oper, ScriptRegistryAdapter

import json


class Frame:
    """분기점과 분기점 사이의 코드(Oper) 덩어리를 담당합니다."""

    def __init__(self, step_list: List[Oper], frame_type: FrameType):
        self.step_list = step_list
        self.frame_type = frame_type
        self.pc: int = 0
        self.vars: Dict[str, Any] = {}
        self.else_flag: bool = False
        self.return_flag: bool = False
        self.return_value: Any = None

    def get_current_step(self) -> Optional[Oper]:
        if self.pc < len(self.step_list):
            return self.step_list[self.pc]
        return None

    def get_return_flag(self) -> bool:
        return self.return_flag

    def set_return_flag(self, val: bool = True) -> None:
        self.return_flag = val

    def get_result_value(self) -> Any:
        return self.return_value

    def set_return_value(self, val: Any) -> None:
        self.return_value = val

    def set_else_flag(self, value: bool = True) -> None:
        self.else_flag = value

    def get_else_flag(self) -> bool:
        return self.else_flag

    def inc_pc(self) -> None:
        self.pc += 1
        self.set_else_flag(False)

    def to_dict(self) -> dict:
        return {
            "step_list": [step.model_dump(by_alias=True) for step in self.step_list],
            "frame_type": self.frame_type.name,
            "pc": self.pc,
            "vars": self.vars,
            "else_flag": self.else_flag,
            "return_flag": self.return_flag,
            "return_value": self.return_value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Frame":
        steps = [create_oper(s) for s in data["step_list"]]
        frame = cls(steps, FrameType[data["frame_type"]])
        frame.pc = data["pc"]
        frame.vars = data["vars"]
        frame.else_flag = data["else_flag"]
        frame.return_flag = data["return_flag"]
        frame.return_value = data["return_value"]
        return frame


class Script:
    """함수처럼 인자를 받고 실행되는 코드 덩어리를 담당합니다."""

    def __init__(self, name: str, kwargs: Dict[str, Any], steps: List[Oper]):
        self.name = name
        self.kwargs = kwargs
        self.frame_stack: List[Frame] = [Frame(steps, FrameType.SCRIPT)]

    def get_top_frame(self) -> Frame:
        if not self.frame_stack:
            raise RuntimeError("Frame stack is empty")
        return self.frame_stack[-1]

    def pop_frame(self) -> Frame:
        return self.frame_stack.pop()

    def get_current_step(self) -> Optional[Oper]:
        if not self.frame_stack:
            return None
        return self.get_top_frame().get_current_step()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kwargs": self.kwargs,
            "frame_stack": [f.to_dict() for f in self.frame_stack]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Script":
        script = cls(data["name"], data["kwargs"], [])
        script.frame_stack = [Frame.from_dict(f) for f in data["frame_stack"]]
        return script

class Interpreter:
    """전체 실행을 조율하고 API를 제공하는 메인 엔진입니다."""

    def __init__(
        self,
        script_registry: Dict[str, dict],
        function_registry: Optional[Dict[str, Callable]] = None,
    ):
        self.script_registry: Dict[str, Dict[str, Any]] = script_registry
        self._parsed_registry = ScriptRegistryAdapter.validate_python(script_registry)
        
        self.function_registry = function_registry or {}
        self.script_stack: List[Script] = []
        self.global_vars: Dict[str, Any] = {}
        self.exec_state: ExecState = ExecState.FINISHED
        self._block_flag: bool = False

    def execute(self, start_script_name: str, kwargs: Optional[Dict[str, Any]] = None) -> ExecState:
        """스크립트를 시작해 BLOCKED 또는 FINISHED 상태가 될 때까지 실행합니다."""
        if kwargs is None:
            kwargs = {}
        self.call_script(start_script_name, kwargs)
        while True:
            state = self.tick()
            if state != ExecState.RUNNING:
                return state

    def resume_execute(self, value: Any) -> ExecState:
        """BLOCKED 상태에서 재개한 뒤 다시 BLOCKED 또는 FINISHED 상태가 될 때까지 실행합니다."""
        state = self.resume(value)
        if state != ExecState.RUNNING:
            return state
        while True:
            state = self.tick()
            if state != ExecState.RUNNING:
                return state

    def is_finished(self) -> bool:
        return self.exec_state == ExecState.FINISHED

    def is_blocked(self) -> bool:
        return self.exec_state == ExecState.BLOCKED

    def get_exec_state(self) -> ExecState:
        return self.exec_state

    def tick(self) -> ExecState:
        """한 스텝(Oper)을 평가하고 현재 실행 상태(ExecState)를 반환합니다."""
        if self.exec_state == ExecState.BLOCKED:
            return self.exec_state

        if not self.script_stack:
            self.exec_state = ExecState.FINISHED
            return self.exec_state

        top_script = self.get_top_script()
        current_step = top_script.get_current_step()

        if current_step is not None:
            current_step.eval(self)
            if self._block_flag:
                self._block_flag = False
                self.exec_state = ExecState.BLOCKED
                return self.exec_state
        else:
            top_frame = top_script.get_top_frame()
            if top_frame.frame_type == FrameType.SCRIPT:
                self.return_script(None)
            else:
                top_script.pop_frame()

        if not self.script_stack:
            self.exec_state = ExecState.FINISHED
        elif self.exec_state != ExecState.BLOCKED:
            self.exec_state = ExecState.RUNNING

        return self.exec_state

    def resume(self, value: Any) -> ExecState:
        """BLOCKED 상태에서 현재 스텝을 재개하기 위한 값을 주입합니다."""
        if self.exec_state != ExecState.BLOCKED:
            return self.exec_state

        if not self.script_stack:
            self.exec_state = ExecState.FINISHED
            return self.exec_state

        current_step = self.get_top_script().get_current_step()
        if current_step is None:
            self.exec_state = ExecState.RUNNING
            return self.tick()

        resume_fn = getattr(current_step, "resume", None)
        if not callable(resume_fn):
            raise RuntimeError("Current step is not resumable")

        self.exec_state = ExecState.RUNNING
        resume_fn(self, value)

        if self._block_flag:
            self._block_flag = False
            self.exec_state = ExecState.BLOCKED
            return self.exec_state

        if not self.script_stack:
            self.exec_state = ExecState.FINISHED

        return self.exec_state

    def get_top_script(self) -> Script:
        if not self.script_stack:
            raise RuntimeError("Script stack is empty")
        return self.script_stack[-1]

    def get_top_frame(self) -> Frame:
        return self.get_top_script().get_top_frame()

    def inc_pc(self) -> None:
        self.get_top_frame().inc_pc()

    def push_frame(self, scripts: List[Oper], frame_type: FrameType) -> None:
        self.get_top_script().frame_stack.append(Frame(scripts, frame_type))

    def end_loop(self) -> None:
        script = self.get_top_script()
        while script.frame_stack:
            frame = script.frame_stack[-1]
            if frame.frame_type == FrameType.LOOP:
                script.pop_frame()
                break
            if frame.frame_type == FrameType.SCRIPT:
                raise RuntimeError("Cannot break/continue outside of a loop")
            script.pop_frame()

    def set_else_flag(self, value: bool = True) -> None:
        self.get_top_frame().set_else_flag(value)

    def get_else_flag(self) -> bool:
        return self.get_top_frame().get_else_flag()

    def set_block_flag(self, value: bool = True) -> None:
        self._block_flag = value

    def get_block_flag(self) -> bool:
        return self._block_flag

    def block(self) -> None:
        self._block_flag = True

    def call_script(self, name: str, params: Union[List[Any], Dict[str, Any]]) -> None:
        if name not in self._parsed_registry:
            raise ValueError(f"Script {name!r} not found in registry")

        script_def = self._parsed_registry[name]
        param_keys = script_def.param_keys or []

        if isinstance(params, list):
            kwargs = dict(zip(param_keys, params))
        elif isinstance(params, dict):
            kwargs = {k: params.get(k) for k in param_keys}
        else:
            raise TypeError("params must be either a list or a dict")
        steps = script_def.steps
        
        new_script = Script(name, kwargs, steps)
        self.script_stack.append(new_script)
        self.exec_state = ExecState.RUNNING

    def pop_script(self) -> None:
        self.script_stack.pop()

    def call_func(self, name: str, params: List[Any]) -> Any:
        if name not in self.function_registry:
            raise ValueError(f"Function {name!r} is not registered in function_registry.")
        func = self.function_registry[name]
        return func(*params)

    def get_return_flag(self) -> bool:
        return self.get_top_frame().get_return_flag()

    def set_return_flag(self, val: bool = True) -> None:
        self.get_top_frame().set_return_flag(val)

    def get_result_value(self) -> Any:
        return self.get_top_frame().get_result_value()

    def set_return_value(self, val: Any) -> None:
        self.get_top_frame().set_return_value(val)

    def return_script(self, return_value: Any) -> None:
        self.pop_script()
        if self.script_stack:
            self.set_return_value(return_value)
            self.set_return_flag()
        else:
            self.exec_state = ExecState.FINISHED

    def _traverse_path(self, base: Any, path: List[str]) -> Any:
        curr = base
        for key in path:
            if isinstance(curr, dict) and key in curr:
                curr = curr[key]
            else:
                raise KeyError(f"Key {key!r} not found in path {path}")
        return curr

    def _set_path(self, base: dict, path: List[str], value: Any) -> None:
        if not path:
            return
        curr = base
        for key in path[:-1]:
            if key not in curr or not isinstance(curr[key], dict):
                curr[key] = {}
            curr = curr[key]
        curr[path[-1]] = value
    
    def get(self, scope: ScopeType, path: List[str]) -> Any:
        top_script = self.get_top_script()

        if not path:
            raise ValueError("Path is required to get a variable.")

        if scope == ScopeType.LOCAL:
            root_key = path[0]
            for frame in reversed(top_script.frame_stack):
                if root_key in frame.vars:
                    return self._traverse_path(frame.vars, path)
            raise KeyError(f"Key {root_key!r} not found in any local frames")

        if scope == ScopeType.FRAME:
            base = top_script.get_top_frame().vars
        elif scope == ScopeType.KWARGS:
            base = top_script.kwargs
        elif scope == ScopeType.GLOBAL:
            base = self.global_vars
        else:
            raise ValueError(f"Unknown scope: {scope}")

        return self._traverse_path(base, path)
    
    def set(self, scope: ScopeType, path: List[str], value: Any) -> None:
        try:
            json.dumps(value)
        except (TypeError, OverflowError):
            raise TypeError(f"직렬화 불가능한 타입은 변수에 저장할 수 없습니다: {type(value).__name__}")
        
        top_script = self.get_top_script()

        if not path:
            raise ValueError("Path is required to set a variable.")

        if scope == ScopeType.LOCAL:
            root_key = path[0]
            target_frame: Optional[Frame] = None

            for frame in reversed(top_script.frame_stack):
                if root_key in frame.vars:
                    target_frame = frame
                    break

            if target_frame is None:
                target_frame = top_script.frame_stack[0]

            self._set_path(target_frame.vars, path, value)
            return

        if scope == ScopeType.FRAME:
            base = top_script.get_top_frame().vars
        elif scope == ScopeType.KWARGS:
            raise ValueError("Cannot modify 'kwargs' scope directly.")
        elif scope == ScopeType.GLOBAL:
            base = self.global_vars
        else:
            raise ValueError(f"Unknown scope: {scope}")

        self._set_path(base, path, value)

    def save_state(self) -> dict:
        """현재 인터프리터의 실행 상태와 원본 스크립트 레지스트리를 모두 저장합니다."""
        return {
            "exec_state": self.exec_state.name,
            "block_flag": self._block_flag,
            "global_vars": self.global_vars,
            "script_registry": self.script_registry,
            "script_stack": [s.to_dict() for s in self.script_stack]
        }

    def load_state(self, state_data: dict) -> None:
        """저장된 딕셔너리로부터 전체 상태와 스크립트를 복구합니다."""
        self.exec_state = ExecState[state_data["exec_state"]]
        self._block_flag = state_data["block_flag"]
        self.global_vars = state_data["global_vars"]
        self.script_registry = state_data["script_registry"]
        self.script_stack = [Script.from_dict(s) for s in state_data["script_stack"]]


