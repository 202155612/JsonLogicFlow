from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Dict, Type
import inspect
from expr import Expr

from constant import FrameType, ScopeType

if TYPE_CHECKING:
    from .interpreter import Interpreter

class Oper(ABC):
    _op_dict: ClassVar[Dict[str, Type["Oper"]]] = {}
    register: ClassVar[bool] = True
    SPEC: ClassVar[dict[str, Any] | None] = None
    
    def __init__(self, x: dict[str, Any]):
        """모든 Oper 서브클래스는 x(데이터 딕셔너리)를 인자로 받아야 함을 명시"""
        pass

    def __init_subclass__(cls, **kwargs):
        """
        자동으로 구체 Oper 서브클래스를 연산자 문자열로 등록합니다.
        Base 클래스, 추상 클래스, 혹은 register=False인 경우 제외됩니다.
        """
        super().__init_subclass__(**kwargs)

        if cls is Oper:
            return
        if not getattr(cls, "register", True):
            return
        if inspect.isabstract(cls):
            return

        op = cls.get_op()
        if op in Oper._op_dict:
            raise ValueError(f"Duplicate op registered: {op!r}")
        Oper._op_dict[op] = cls

    @classmethod
    def _get_spec(cls) -> dict[str, Any]:
        spec = getattr(cls, "SPEC", None)
        if not isinstance(spec, dict):
            raise ValueError(f"{cls.__name__} must define SPEC as dict")
        return spec

    @classmethod
    def get_op(cls) -> str:
        """연산자 문자열 반환 (예: '$If')."""
        spec = cls._get_spec()
        op = spec.get("op")
        if not isinstance(op, str) or not op:
            raise ValueError(f"{cls.__name__}.SPEC['op'] must be a non-empty str")
        return op

    @classmethod
    def get_required_keys(cls) -> list[str]:
        """args 딕셔너리에서 요구하는 필수 키 목록 반환."""
        spec = cls._get_spec()
        required = spec.get("required", [])
        if required is None:
            required = []
        if not isinstance(required, list) or not all(isinstance(k, str) for k in required):
            raise ValueError(f"{cls.__name__}.SPEC['required'] must be list[str]")
        return required

    @classmethod
    def get_optional_keys(cls) -> list[str]:
        spec = cls._get_spec()
        optional = spec.get("optional", [])
        if optional is None:
            optional = []
        if not isinstance(optional, list) or not all(isinstance(k, str) for k in optional):
            raise ValueError(f"{cls.__name__}.SPEC['optional'] must be list[str]")
        return optional

    @classmethod
    def create(cls, x: Any) -> "Oper":
        """
        입력값을 Oper 노드로 파싱합니다.
        유효한 '$op' 키를 포함한 딕셔너리만 허용됩니다.
        """
        if isinstance(x, Oper):
            return x

        if isinstance(x, dict) and "$op" in x:
            op = x["$op"]
            if op not in cls._op_dict:
                raise ValueError(f"Unknown Oper op: {op!r}")
            return cls._op_dict[op](x)

        raise ValueError(f"Invalid format: {x!r}. Must be a dictionary containing an '$op' key.")

    def check_args(self, x_dict: dict[str, Any]) -> dict[str, Any]:
        """
        입력된 전체 딕셔너리(x_dict)에서 'args'를 추출하고 검증합니다.
        요구하는 키가 없다면 args가 없거나 비어 있어도 통과합니다.
        """
        args = x_dict.get("args")
        required = set(self.get_required_keys())
        optional = set(self.get_optional_keys())
        allowed = required | optional

        if not required:
            if args is None:
                return {}
            if not isinstance(args, dict):
                raise ValueError(f"{self.get_op()} args must be a dictionary if provided.")
            unknown = [k for k in args.keys() if k not in allowed]
            if unknown:
                raise ValueError(f"{self.get_op()} got unknown arg key(s): {unknown!r}")
            return args

        if not isinstance(args, dict):
            raise ValueError(f"{self.get_op()} requires 'args' to be a dictionary, got {type(args)}")

        missing = [k for k in required if k not in args]
        if missing:
            raise ValueError(f"{self.get_op()} missing required arg key(s): {missing!r}")

        unknown = [k for k in args.keys() if k not in allowed]
        if unknown:
            raise ValueError(f"{self.get_op()} got unknown arg key(s): {unknown!r}")

        return args

    @abstractmethod
    def eval(self, interpreter: Interpreter) -> Any:
        """이 동작을 엔진/컨텍스트를 사용하여 평가(실행)합니다."""
        ...

class IfOper(Oper):
    """
    설명: 주어진 조건이 참일 경우 지정된 스크립트 블록을 실행하는 조건문 연산자입니다.
    args 형식: {"cond": condition_expr, "scripts": [oper1, oper2, ...]}
    예시: {"$op": "$If", "args": {"cond": {"$op": "$eq", "args": {"value": [1, 1]}}, "scripts": [...]}}
    """
    SPEC = {"op": "$If", "required": ["cond", "scripts"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x)
        self.cond = Expr.create(args["cond"])

        if not isinstance(args["scripts"], list):
            raise ValueError(f"$If 'scripts' must be a list.")
        self.scripts = [Oper.create(i) for i in args["scripts"]]

    def eval(self, interpreter: Interpreter) -> Any:
        interpreter.inc_pc()
        if self.cond.eval(interpreter):
            interpreter.push_frame(self.scripts, FrameType.BLOCK)
        else:
            interpreter.set_else_flag()


class ElseIfOper(Oper):
    """
    설명: 이전 조건이 거짓이고 현재 조건이 참일 경우 스크립트 블록을 실행하는 조건문 연산자입니다.
    args 형식: {"cond": condition_expr, "scripts": [oper1, oper2, ...]}
    예시: {"$op": "$ElseIf", "args": {"cond": {"$op": "$gt", "args": {"value": [5, 3]}}, "scripts": [...]}}
    """
    SPEC = {"op": "$ElseIf", "required": ["cond", "scripts"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x)
        self.cond = Expr.create(args["cond"])

        if not isinstance(args["scripts"], list):
            raise ValueError(f"$ElseIf 'scripts' must be a list.")
        self.scripts = [Oper.create(i) for i in args["scripts"]]

    def eval(self, interpreter: Interpreter) -> Any:
        should_check = interpreter.get_else_flag()
        interpreter.inc_pc()
        if should_check:
            if self.cond.eval(interpreter):
                interpreter.push_frame(self.scripts, FrameType.BLOCK)
            else:
                interpreter.set_else_flag()


class ElseOper(Oper):
    """
    설명: 이전의 모든 IF/ElseIf 조건들이 거짓일 경우 스크립트 블록을 실행하는 조건문 연산자입니다.
    args 형식: {"scripts": [oper1, oper2, ...]}
    예시: {"$op": "$Else", "args": {"scripts": [{"$op": "$Set", "args": {...}}]}}
    """
    SPEC = {"op": "$Else", "required": ["scripts"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x)

        if not isinstance(args["scripts"], list):
            raise ValueError(f"$Else 'scripts' must be a list.")
        self.scripts = [Oper.create(i) for i in args["scripts"]]

    def eval(self, interpreter: Interpreter) -> Any:
        if interpreter.get_else_flag():
            interpreter.inc_pc()
            interpreter.push_frame(self.scripts, FrameType.BLOCK)
        else:
            interpreter.inc_pc()


class WhileOper(Oper):
    """
    설명: 주어진 조건이 참인 동안 스크립트 블록을 반복 실행하는 루프 연산자입니다.
    args 형식: {"cond": condition_expr, "scripts": [oper1, oper2, ...]}
    예시: {"$op": "$While", "args": {"cond": {"$op": "$lt", "args": {"value": [{"$op": "$get", "args": {"scope": "var", "path": ["i"]}}, 10]}}, "scripts": [...]}}
    """
    SPEC = {"op": "$While", "required": ["cond", "scripts"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x)
        self.cond = Expr.create(args["cond"])

        if not isinstance(args["scripts"], list):
            raise ValueError(f"$While 'scripts' must be a list.")
        self.scripts = [Oper.create(i) for i in args["scripts"]]

    def eval(self, interpreter: Interpreter) -> Any:
        if self.cond.eval(interpreter):
            interpreter.push_frame(self.scripts, FrameType.LOOP)
        else:
            interpreter.inc_pc()


class BreakOper(Oper):
    """
    설명: 현재 실행 중인 루프를 즉시 종료하고 빠져나가는 연산자입니다.
    args 형식: {} (또는 args 생략)
    예시: {"$op": "$Break", "args": {}}
    """
    SPEC = {"op": "$Break", "required": [], "optional": []}

    def __init__(self, x: dict[str, Any]):
        self.check_args(x)

    def eval(self, interpreter: Interpreter) -> Any:
        interpreter.end_loop()
        interpreter.inc_pc()


class ContinueOper(Oper):
    """
    설명: 현재 루프의 남은 블록을 건너뛰고 다음 반복 조건 검사로 넘어가는 연산자입니다.
    args 형식: {} (또는 args 생략)
    예시: {"$op": "$Continue", "args": {}}
    """
    SPEC = {"op": "$Continue", "required": [], "optional": []}

    def __init__(self, x: dict[str, Any]):
        self.check_args(x)

    def eval(self, interpreter: Interpreter) -> Any:
        interpreter.end_loop()


class SetOper(Oper):
    """
    설명: 지정된 스코프 내 특정 경로에 평가된 값을 할당(저장)하는 연산자입니다.
    args 형식: {"value": value_expr, "scope": "scope_name", "path": ["path", "to", "key"]}
    예시: {"$op": "$Set", "args": {"value": 100, "scope": "local", "path": ["user", "score"]}}
    """
    SPEC = {"op": "$Set", "required": ["value", "scope", "path"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x)
        self.value = Expr.create(args["value"])

        self.scope = args["scope"]
        if not isinstance(self.scope, str):
            raise ValueError(f"$Set 'scope' must be a string, got {type(self.scope)}")

        self.path = args["path"]
        if not isinstance(self.path, list):
            raise ValueError(f"$Set 'path' must be a list, got {type(self.path)}")

    def eval(self, interpreter: Interpreter) -> Any:
        interpreter.set(self.scope, self.path, self.value.eval(interpreter))
        interpreter.inc_pc()


class ScriptOper(Oper):
    """
    설명: 사용자 정의 스크립트를 호출하며, 완료 후 선택적으로 반환값을 저장하는 연산자입니다.
    args 형식: {"name": name_expr, "params": [param1, ...], "scope": (선택), "path": (선택)}
    예시: {"$op": "$Script", "args": {"name": "calc_tax", "params": [1000], "scope": "local", "path": ["tax"]}}
    """
    SPEC = {"op": "$Script", "required": ["name", "params"], "optional": ["scope", "path"]}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x)
        self.script_name = Expr.create(args["name"])

        if not isinstance(args["params"], list):
            raise ValueError(f"$Script 'params' must be a list.")
        self.script_params = [Expr.create(i) for i in args["params"]]

        self.scope = args.get("scope")
        if self.scope and not isinstance(self.scope, str):
            raise ValueError(f"$Script 'scope' must be a string, got {type(self.scope)}")

        self.path = args.get("path")
        if self.path and not isinstance(self.path, list):
            raise ValueError(f"$Script 'path' must be a list, got {type(self.path)}")

    def eval(self, interpreter: Interpreter) -> Any:
        if interpreter.get_return_flag():
            result = interpreter.get_result_value()
            interpreter.set_return_flag(False)
            if self.scope and self.path:
                interpreter.set(self.scope, self.path, result)
            interpreter.inc_pc()
        else:
            name = self.script_name.eval(interpreter)
            params = [p.eval(interpreter) for p in self.script_params]
            interpreter.call_script(name, params)


class ReturnOper(Oper):
    """
    설명: 현재 실행 중인 스크립트를 종료하고, 지정된 스코프의 값을 꺼내어 반환하는 연산자입니다.
    args 형식: {"scope": (선택), "path": (선택)}
    예시: {"$op": "$Return", "args": {"scope": "local", "path": ["result_data"]}}
    """
    SPEC = {"op": "$Return", "required": [], "optional": ["scope", "path"]}
    
    # interpreter는 script의 pc가 끝에 도달할 경우 ReturnOper를 생성해서 실행함
    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x)

        self.scope = args.get("scope")
        if self.scope and not isinstance(self.scope, str):
            raise ValueError(f"$Return 'scope' must be a string, got {type(self.scope)}")

        self.path = args.get("path")
        if self.path and not isinstance(self.path, list):
            raise ValueError(f"$Return 'path' must be a list, got {type(self.path)}")

    def eval(self, interpreter: Interpreter) -> Any:
        return_value = None
        if self.scope and self.path:
            return_value = interpreter.get(self.scope, self.path)
            interpreter.set(self.scope, self.path, None)
        interpreter.pop_script()
        interpreter.set_return_value(return_value)  
        interpreter.set_return_flag()


class InvokeOper(Oper):
    """
    설명: 외부 파이썬 함수나 네이티브 메서드를 동적으로 호출하고 결과를 반환받는 연산자입니다.
    args 형식: {"name": name_expr, "params": [param1, ...], "scope": (선택), "path": (선택)}
    예시: {"$op": "$Invoke", "args": {"name": "print_log", "params": ["Hello!"], "scope": "global", "path": ["log"]}}
    """
    SPEC = {"op": "$Invoke", "required": ["name", "params"], "optional": ["scope", "path"]}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x)

        self.script_name = Expr.create(args["name"])

        params = args["params"]
        if not isinstance(params, list):
            raise ValueError(f"$Invoke 'params' must be a list.")
        self.script_params = [Expr.create(i) for i in params]

        self.scope = args.get("scope")
        if self.scope and not isinstance(self.scope, str):
            raise ValueError(f"$Invoke 'scope' must be a string, got {type(self.scope)}")

        self.path = args.get("path")
        if self.path and not isinstance(self.path, list):
            raise ValueError(f"$Invoke 'path' must be a list, got {type(self.path)}")

    def eval(self, interpreter: Interpreter) -> Any:
        interpreter.inc_pc()

        name = self.script_name.eval(interpreter)
        params_values = [p.eval(interpreter) for p in self.script_params]

        result = interpreter.call_func(name, params_values)

        if self.scope and self.path:
            interpreter.set(self.scope, self.path, result)

        return result