from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

from constant import FrameType, ScopeType
from expr import Expr
from oper import Oper

class Frame:
    """분기점과 분기점 사이의 코드(Oper) 덩어리를 담당합니다."""
    def __init__(self, step_list: List['Oper'], frame_type: FrameType):
        self.step_list = step_list
        self.frame_type = frame_type
        self.pc: int = 0
        self.vars: Dict[str, Any] = {}
        self.else_flag: bool = False

    def get_current_step(self) -> Optional['Oper']:
        if self.pc < len(self.step_list):
            return self.step_list[self.pc]
        return None

    def inc_pc(self) -> None:
        self.pc += 1


class Script:
    """함수처럼 인자를 받고 실행되는 코드 덩어리를 담당합니다."""
    def __init__(self, name: str, kwargs: Dict[str, Any], steps: List['Oper']):
        self.name = name
        self.kwargs = kwargs
        # 스크립트가 시작될 때 전체 코드를 담은 최상위 프레임을 생성합니다.
        self.frame_stack: List[Frame] = [Frame(steps, FrameType.SCRIPT)]

    def get_top_frame(self) -> Frame:
        if not self.frame_stack:
            raise RuntimeError("Frame stack is empty")
        return self.frame_stack[-1]

    def pop_frame(self) -> Frame:
        return self.frame_stack.pop()

    def get_current_step(self) -> Optional['Oper']:
        if not self.frame_stack:
            return None
        return self.get_top_frame().get_current_step()


class Interpreter:
    """전체 실행을 조율하고 API를 제공하는 메인 엔진입니다."""
    def __init__(
        self, 
        script_registry: Dict[str, dict], 
        function_registry: Optional[Dict[str, Callable]] = None
    ):
        """
        script_registry 형태 예시:
        {
            "Main": {"param_keys": ["arg1"], "steps": [{"$op": "$If", ...}, ...]},
            "Calc": {"param_keys": ["a", "b"], "steps": [...]}
        }
        function_registry 형태 예시:
        {
            "print_log": print,
            "add_numbers": lambda a, b: a + b
        }
        """
        self.script_registry = script_registry
        self.function_registry = function_registry or {}
        self.script_stack: List[Script] = []
        self.global_vars: Dict[str, Any] = {}
        
        # 반환값 관리를 위한 멤버
        self.return_flag: bool = False
        self.return_value: Any = None

    def execute(self, start_script_name: str, kwargs: Optional[Dict[str, Any]] = None):
        """인터프리터 실행의 진입점입니다."""
        if kwargs is None:
            kwargs = {}
        
        self.call_script(start_script_name, list(kwargs.values()))
        
        while self.script_stack:
            self.tick()

    def is_working(self):
        """실행할 Oper이 있는지 확인합니다."""
        if self.script_stack:
            return True
        return False

    def tick(self) -> None:
        """한 스텝(Oper)을 평가합니다."""
        if not self.script_stack:
            return

        top_script = self.get_top_script()
        current_step = top_script.get_current_step()

        if current_step is not None:
            # Step이 존재하면 해당 Oper의 eval을 실행 (내부에서 알아서 inc_pc 호출)
            current_step.eval(self)
        else:
            # 현재 프레임의 끝(pc 도달)에 다다랐을 때
            top_frame = top_script.get_top_frame()
            
            if top_frame.frame_type == FrameType.SCRIPT:
                # 스크립트 최상위 프레임이 끝났다면 암시적으로 Return 처리
                # ReturnOper의 동작을 모방하여 인터프리터가 직접 종료시킵니다.
                self.pop_script()
                # 필요에 따라 암시적 리턴 시 None 세팅
                self.set_return_flag(True)
                self.set_return_value(None)
            else:
                # If/While 등 일반 프레임이 끝났다면 프레임만 pop하고 계속 진행
                top_script.pop_frame()

    def get_top_script(self) -> Script:
        if not self.script_stack:
            raise RuntimeError("Script stack is empty")
        return self.script_stack[-1]

    def inc_pc(self) -> None:
        self.get_top_script().get_top_frame().inc_pc()

    def push_frame(self, scripts: List['Oper'], frame_type: FrameType) -> None:
        self.get_top_script().frame_stack.append(Frame(scripts, frame_type))

    def end_loop(self) -> None:
        """Break나 Continue 호출 시 가장 가까운 LOOP 프레임을 찾아 정리합니다."""
        script = self.get_top_script()
        while script.frame_stack:
            frame = script.frame_stack[-1]
            if frame.frame_type == FrameType.LOOP:
                # Break의 경우 이 프레임을 pop해야 루프를 탈출합니다.
                # Continue의 경우는 Oper 내에서 판단에 따라 다르게 설계할 수 있으나
                # 일반적인 While 구조에서는 현재 프레임을 종료시키면 상위 WhileOper로 돌아갑니다.
                script.pop_frame()
                break
            elif frame.frame_type == FrameType.SCRIPT:
                raise RuntimeError("Cannot break/continue outside of a loop")
            else:
                script.pop_frame()

    def set_else_flag(self, value: bool = True) -> None:
        self.get_top_script().get_top_frame().else_flag = value

    def get_else_flag(self) -> bool:
        return self.get_top_script().get_top_frame().else_flag
    
    def call_script(self, name: str, params: List[Any]) -> None:
        if name not in self.script_registry:
            raise ValueError(f"Script {name!r} not found in registry")
        
        script_data = self.script_registry[name]
        param_keys = script_data.get("param_keys", [])
        
        # 인자 리스트를 kwargs 딕셔너리로 매핑
        kwargs = dict(zip(param_keys, params))
        
        # JSON의 steps 딕셔너리를 파싱하여 Oper 리스트로 변환
        steps = [Oper.create(s) for s in script_data["steps"]]
        
        new_script = Script(name, kwargs, steps)
        self.script_stack.append(new_script)

    def pop_script(self) -> None:
        self.script_stack.pop()

    def call_func(self, name: str, params: List[Any]) -> Any:
        """$Invoke 처리를 위한 외부 파이썬 함수 호출용"""
        if name not in self.function_registry:
            raise ValueError(f"Function {name!r} is not registered in function_registry.")
        
        func = self.function_registry[name]
        # 리스트로 전달된 params를 언패킹하여 실제 파이썬 함수 인자로 넘겨줍니다.
        return func(*params)

    def get_return_flag(self) -> bool:
        return self.return_flag

    def set_return_flag(self, val: bool = True) -> None:
        self.return_flag = val

    def get_result_value(self) -> Any:
        return self.return_value

    def set_return_value(self, val: Any) -> None:
        self.return_value = val
        
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
                curr[key] = {}  # 경로가 없으면 생성
            curr = curr[key]
        curr[path[-1]] = value # interpreter.py 내부의 get, set 메서드 교체

    def get(self, scope: str, path: List[str]) -> Any:
        top_script = self.get_top_script()
        
        if not path:
            raise ValueError("Path is required to get a variable.")

        if scope == "local":
            root_key = path[0]
            # 상위 프레임부터 역순으로 탐색
            for frame in reversed(top_script.frame_stack):
                if root_key in frame.vars:
                    return self._traverse_path(frame.vars, path)
            raise KeyError(f"Key {root_key!r} not found in any local frames")
            
        elif scope == "frame":
            base = top_script.get_top_frame().vars
        elif scope == "kwargs":
            base = top_script.kwargs
        elif scope == "global":
            base = self.global_vars
        else:
            raise ValueError(f"Unknown scope: {scope}")
            
        return self._traverse_path(base, path)

    def set(self, scope: str, path: List[str], value: Any) -> None:
        top_script = self.get_top_script()
        
        if not path:
            raise ValueError("Path is required to set a variable.")

        if scope == "local":
            root_key = path[0]
            target_frame = None
            
            for frame in reversed(top_script.frame_stack):
                if root_key in frame.vars:
                    target_frame = frame
                    break
            
            if target_frame is None:
                target_frame = top_script.frame_stack[0]
                
            self._set_path(target_frame.vars, path, value)
            return

        elif scope == "frame":
            base = top_script.get_top_frame().vars
        elif scope == "kwargs":
            raise ValueError("Cannot modify 'kwargs' scope directly.")
        elif scope == "global":
            base = self.global_vars
        else:
            raise ValueError(f"Unknown scope: {scope}")
            
        self._set_path(base, path, value)