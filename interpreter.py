from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Union

from constant import ExecState, FrameType, ScopeType
from oper import Oper, create_oper


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


class Interpreter:
    """전체 실행을 조율하고 API를 제공하는 메인 엔진입니다."""

    def __init__(
        self,
        script_registry: Dict[str, dict],
        function_registry: Optional[Dict[str, Callable]] = None,
    ):
        self.script_registry: Dict[str, Dict[str, Any]] = script_registry
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
        """인터프리터 실행이 종료(FINISHED) 상태인지 확인합니다."""
        return self.exec_state == ExecState.FINISHED

    def is_blocked(self) -> bool:
        """인터프리터 실행이 중단(BLOCKED) 상태인지 확인합니다."""
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
        """Break나 Continue 호출 시 가장 가까운 LOOP 프레임을 찾아 정리합니다."""
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
        """이름으로 스크립트를 찾아 파라미터(list 또는 dict)를 매핑하고 스택에 추가합니다."""
        if name not in self.script_registry:
            raise ValueError(f"Script {name!r} not found in registry")

        script_data = self.script_registry[name]
        param_keys = script_data.get("param_keys", [])

        if isinstance(params, list):
            kwargs = dict(zip(param_keys, params))
        elif isinstance(params, dict):
            kwargs = {k: params.get(k) for k in param_keys}
        else:
            raise TypeError("params must be either a list or a dict")

        steps = [create_oper(s) for s in script_data["steps"]]
        new_script = Script(name, kwargs, steps)
        self.script_stack.append(new_script)
        self.exec_state = ExecState.RUNNING

    def pop_script(self) -> None:
        self.script_stack.pop()

    def call_func(self, name: str, params: List[Any]) -> Any:
        """$Invoke 처리를 위한 외부 파이썬 함수 호출용"""
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

    def _normalize_scope(self, scope: Union[str, ScopeType]) -> str:
        if isinstance(scope, ScopeType):
            return scope.value
        return scope

    def _traverse_path(self, base: Any, path: List[str]) -> Any:
        """path(['user', 'name']) 기반으로 딕셔너리 트리를 깊게 탐색합니다."""
        curr = base
        for key in path:
            if isinstance(curr, dict) and key in curr:
                curr = curr[key]
            else:
                raise KeyError(f"Key {key!r} not found in path {path}")
        return curr

    def _set_path(self, base: dict, path: List[str], value: Any) -> None:
        """path에 맞게 딕셔너리를 파고들어가 값을 세팅합니다."""
        if not path:
            return
        curr = base
        for key in path[:-1]:
            if key not in curr or not isinstance(curr[key], dict):
                curr[key] = {}
            curr = curr[key]
        curr[path[-1]] = value

    def get(self, scope: Union[str, ScopeType], path: List[str]) -> Any:
        scope_str = self._normalize_scope(scope)
        top_script = self.get_top_script()

        if not path:
            raise ValueError("Path is required to get a variable.")

        if scope_str == "local":
            root_key = path[0]
            for frame in reversed(top_script.frame_stack):
                if root_key in frame.vars:
                    return self._traverse_path(frame.vars, path)
            raise KeyError(f"Key {root_key!r} not found in any local frames")

        if scope_str == "frame":
            base = top_script.get_top_frame().vars
        elif scope_str == "kwargs":
            base = top_script.kwargs
        elif scope_str == "global":
            base = self.global_vars
        else:
            raise ValueError(f"Unknown scope: {scope_str}")

        return self._traverse_path(base, path)

    def set(self, scope: Union[str, ScopeType], path: List[str], value: Any) -> None:
        scope_str = self._normalize_scope(scope)
        top_script = self.get_top_script()

        if not path:
            raise ValueError("Path is required to set a variable.")

        if scope_str == "local":
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

        if scope_str == "frame":
            base = top_script.get_top_frame().vars
        elif scope_str == "kwargs":
            raise ValueError("Cannot modify 'kwargs' scope directly.")
        elif scope_str == "global":
            base = self.global_vars
        else:
            raise ValueError(f"Unknown scope: {scope_str}")

        self._set_path(base, path, value)