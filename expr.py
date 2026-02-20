from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Dict, Type
import inspect

from constant import FrameType, ScopeType

if TYPE_CHECKING:
    from .interpreter import Interpreter

class Expr(ABC):
    _op_dict: ClassVar[Dict[str, Type["Expr"]]] = {}
    register: ClassVar[bool] = True
    SPEC: ClassVar[dict[str, Any] | None] = None
    
    def __init__(self, x: dict[str, Any]):
        """모든 Expr 서브클래스는 x(데이터 딕셔너리)를 인자로 받아야 함을 명시"""
        pass

    def __init_subclass__(cls, **kwargs):
        """
        자동으로 구체 Expr 서브클래스를 연산자 문자열로 등록합니다.
        Base 클래스, 추상 클래스, 혹은 register=False인 경우 제외됩니다.
        """
        super().__init_subclass__(**kwargs)

        if cls is Expr:
            return
        if not getattr(cls, "register", True):
            return
        if inspect.isabstract(cls):
            return

        op = cls.get_op()
        if op in Expr._op_dict:
            raise ValueError(f"Duplicate op registered: {op!r}")
        Expr._op_dict[op] = cls

    @classmethod
    def _get_spec(cls) -> dict[str, Any]:
        spec = getattr(cls, "SPEC", None)
        if not isinstance(spec, dict):
            raise ValueError(f"{cls.__name__} must define SPEC as dict")
        return spec

    @classmethod
    def get_op(cls) -> str:
        """연산자 문자열 반환 (예: '$eq', '$and')."""
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
    def create(cls, x: Any) -> "Expr":
        """
        입력값을 Expr 노드로 파싱합니다.
        입력값이 '$op' 키를 포함한 딕셔너리면 해당 연산자 클래스로 라우팅하고,
        그 외에는 리터럴(list, dict, 단일 값)로 파싱합니다.
        """
        if isinstance(x, Expr):
            return x

        if isinstance(x, dict) and "$op" in x:
            op = x["$op"]
            if op not in cls._op_dict:
                raise ValueError(f"Unknown Expr op: {op!r}")
            return cls._op_dict[op](x)

        if isinstance(x, list):
            return ListLiteralExpr(x)
        if isinstance(x, dict):
            return DictLiteralExpr(x)

        return ValueExpr(x)

    def check_args(self, args: Any) -> dict[str, Any]:
        """
        서브클래스 초기화 시 호출되어 args가 딕셔너리인지 확인하고,
        get_required_keys에서 정의한 필수 키가 모두 존재하는지 검증합니다.
        """
        if not isinstance(args, dict):
            raise ValueError(f"{self.get_op()} requires args to be a dictionary, got {type(args)}")

        required = set(self.get_required_keys())
        optional = set(self.get_optional_keys())
        allowed = required | optional

        missing = [k for k in required if k not in args]
        if missing:
            raise ValueError(f"{self.get_op()} missing required arg key(s): {missing!r}")

        unknown = [k for k in args.keys() if k not in allowed]
        if unknown:
            raise ValueError(f"{self.get_op()} got unknown arg key(s): {unknown!r}")

        return args

    @abstractmethod
    def eval(self, interpreter: Interpreter) -> Any:
        """표현식 동적 평가."""
        ...

class ValueExpr(Expr):
    register = False
    SPEC = None

    def __init__(self, value: Any):
        self.value = value

    def eval(self, interpreter: Interpreter) -> Any:
        return self.value


class ListLiteralExpr(Expr):
    register = False
    SPEC = None

    def __init__(self, items: list[Any]):
        self.items = [Expr.create(i) for i in items]

    def eval(self, interpreter: Interpreter) -> list[Any]:
        return [it.eval(interpreter) for it in self.items]


class DictLiteralExpr(Expr):
    register = False
    SPEC = None

    def __init__(self, obj: dict[Any, Any]):
        self.items = [(Expr.create(k), Expr.create(v)) for k, v in obj.items()]

    def eval(self, interpreter: Interpreter) -> dict[Any, Any]:
        return {k_expr.eval(interpreter): v_expr.eval(interpreter) for k_expr, v_expr in self.items}

class ListOpExpr(Expr):
    """
    설명: 여러 하위 표현식을 리스트 형태로 명시적으로 생성하고 평가하는 연산자입니다.
    args 형식: {"value": [expr1, expr2, ...]}
    예시: {"$op": "$list", "args": {"value": [1, 2, {"$op": "$get", "args": {"scope": "var", "path": ["x"]}}]}}
    """
    SPEC = {"op": "$list", "required": ["value"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x.get("args", {}))
        val = args["value"]
        if not isinstance(val, list):
            raise ValueError(f"$list 'value' must be a list, got {type(val)}")
        self.items = [Expr.create(i) for i in val]

    def eval(self, interpreter: Interpreter) -> list[Any]:
        return [it.eval(interpreter) for it in self.items]


class DictOpExpr(Expr):
    """
    설명: 딕셔너리를 명시적으로 생성하며, 키와 값 모두 하위 표현식으로 평가되는 연산자입니다.
    args 형식: {"value": {"key1": expr1, "key2": expr2, ...}}
    예시: {"$op": "$dict", "args": {"value": {"name": "Alice", "age": 20}}}
    """
    SPEC = {"op": "$dict", "required": ["value"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x.get("args", {}))
        val = args["value"]
        if not isinstance(val, dict):
            raise ValueError(f"$dict 'value' must be a single dictionary, got {type(val)}")
        self.items = [(Expr.create(k), Expr.create(v)) for k, v in val.items()]

    def eval(self, interpreter: Interpreter) -> dict[Any, Any]:
        return {k_expr.eval(interpreter): v_expr.eval(interpreter) for k_expr, v_expr in self.items}

class EqExpr(Expr):
    """
    설명: 두 값의 동등성(==)을 비교하는 논리 연산자입니다.
    args 형식: {"value": [left_expr, right_expr]}
    예시: {"$op": "$eq", "args": {"value": [{"$op": "$get", "args": {"scope": "var", "path": ["id"]}}, 10]}}
    """
    SPEC = {"op": "$eq", "required": ["value"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x.get("args", {}))
        val = args["value"]
        if not isinstance(val, list) or len(val) != 2:
            raise ValueError(f"$eq requires 'value' to be a list of exactly 2 elements.")
        self.left = Expr.create(val[0])
        self.right = Expr.create(val[1])

    def eval(self, interpreter: Interpreter) -> bool:
        return self.left.eval(interpreter) == self.right.eval(interpreter)


class NeExpr(Expr):
    """
    설명: 두 값이 서로 다른지(!=) 비교하는 논리 연산자입니다.
    args 형식: {"value": [left_expr, right_expr]}
    예시: {"$op": "$ne", "args": {"value": ["status", "closed"]}}
    """
    SPEC = {"op": "$ne", "required": ["value"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x.get("args", {}))
        val = args["value"]
        if not isinstance(val, list) or len(val) != 2:
            raise ValueError(f"$ne requires 'value' to be a list of exactly 2 elements.")
        self.left = Expr.create(val[0])
        self.right = Expr.create(val[1])

    def eval(self, interpreter: Interpreter) -> bool:
        return self.left.eval(interpreter) != self.right.eval(interpreter)


class LtExpr(Expr):
    """
    설명: 왼쪽 값이 오른쪽 값보다 작은지(<) 비교하는 논리 연산자입니다.
    args 형식: {"value": [left_expr, right_expr]}
    예시: {"$op": "$lt", "args": {"value": [5, 10]}}
    """
    SPEC = {"op": "$lt", "required": ["value"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x.get("args", {}))
        val = args["value"]
        if not isinstance(val, list) or len(val) != 2:
            raise ValueError(f"$lt requires 'value' to be a list of exactly 2 elements.")
        self.left = Expr.create(val[0])
        self.right = Expr.create(val[1])

    def eval(self, interpreter: Interpreter) -> bool:
        return self.left.eval(interpreter) < self.right.eval(interpreter)


class LeExpr(Expr):
    """
    설명: 왼쪽 값이 오른쪽 값보다 작거나 같은지(<=) 비교하는 논리 연산자입니다.
    args 형식: {"value": [left_expr, right_expr]}
    예시: {"$op": "$le", "args": {"value": [10, 10]}}
    """
    SPEC = {"op": "$le", "required": ["value"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x.get("args", {}))
        val = args["value"]
        if not isinstance(val, list) or len(val) != 2:
            raise ValueError(f"$le requires 'value' to be a list of exactly 2 elements.")
        self.left = Expr.create(val[0])
        self.right = Expr.create(val[1])

    def eval(self, interpreter: Interpreter) -> bool:
        return self.left.eval(interpreter) <= self.right.eval(interpreter)


class GtExpr(Expr):
    """
    설명: 왼쪽 값이 오른쪽 값보다 큰지(>) 비교하는 논리 연산자입니다.
    args 형식: {"value": [left_expr, right_expr]}
    예시: {"$op": "$gt", "args": {"value": [15, 10]}}
    """
    SPEC = {"op": "$gt", "required": ["value"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x.get("args", {}))
        val = args["value"]
        if not isinstance(val, list) or len(val) != 2:
            raise ValueError(f"$gt requires 'value' to be a list of exactly 2 elements.")
        self.left = Expr.create(val[0])
        self.right = Expr.create(val[1])

    def eval(self, interpreter: Interpreter) -> bool:
        return self.left.eval(interpreter) > self.right.eval(interpreter)


class GeExpr(Expr):
    """
    설명: 왼쪽 값이 오른쪽 값보다 크거나 같은지(>=) 비교하는 논리 연산자입니다.
    args 형식: {"value": [left_expr, right_expr]}
    예시: {"$op": "$ge", "args": {"value": [20, 10]}}
    """
    SPEC = {"op": "$ge", "required": ["value"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x.get("args", {}))
        val = args["value"]
        if not isinstance(val, list) or len(val) != 2:
            raise ValueError(f"$ge requires 'value' to be a list of exactly 2 elements.")
        self.left = Expr.create(val[0])
        self.right = Expr.create(val[1])

    def eval(self, interpreter: Interpreter) -> bool:
        return self.left.eval(interpreter) >= self.right.eval(interpreter)


class InExpr(Expr):
    """
    설명: 특정 항목이 컨테이너(리스트 등) 내에 포함되어 있는지(in) 확인하는 연산자입니다.
    args 형식: {"item": item_expr, "container": container_expr}
    예시: {"$op": "$in", "args": {"item": "apple", "container": ["apple", "banana", "cherry"]}}
    """
    SPEC = {"op": "$in", "required": ["item", "container"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x.get("args", {}))
        self.item = Expr.create(args["item"])
        self.container = Expr.create(args["container"])

    def eval(self, interpreter: Interpreter) -> bool:
        return self.item.eval(interpreter) in self.container.eval(interpreter)

class AndExpr(Expr):
    """
    설명: 여러 하위 표현식이 모두 참인지(AND) 확인하는 논리곱 연산자입니다.
    args 형식: {"value": [expr1, expr2, ...]}
    예시: {"$op": "$and", "args": {"value": [{"$op": "$eq", "args": {"value": [1, 1]}}, {"$op": "$gt", "args": {"value": [5, 3]}}]}}
    """
    SPEC = {"op": "$and", "required": ["value"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x.get("args", {}))
        val = args["value"]
        if not isinstance(val, list):
            raise ValueError(f"$and requires 'value' to be a list.")
        self.items = [Expr.create(a) for a in val]

    def eval(self, interpreter: Interpreter) -> bool:
        return all(a.eval(interpreter) for a in self.items)


class OrExpr(Expr):
    """
    설명: 하위 표현식 중 하나라도 참인지(OR) 확인하는 논리합 연산자입니다.
    args 형식: {"value": [expr1, expr2, ...]}
    예시: {"$op": "$or", "args": {"value": [{"$op": "$lt", "args": {"value": [10, 5]}}, {"$op": "$eq", "args": {"value": [1, 1]}}]}}
    """
    SPEC = {"op": "$or", "required": ["value"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x.get("args", {}))
        val = args["value"]
        if not isinstance(val, list):
            raise ValueError(f"$or requires 'value' to be a list.")
        self.items = [Expr.create(a) for a in val]

    def eval(self, interpreter: Interpreter) -> bool:
        return any(a.eval(interpreter) for a in self.items)


class NotExpr(Expr):
    """
    설명: 단일 하위 표현식의 논리값을 반전시키는(NOT) 연산자입니다.
    args 형식: {"value": [expr]}
    예시: {"$op": "$not", "args": {"value": [{"$op": "$eq", "args": {"value": [1, 2]}}]}}
    """
    SPEC = {"op": "$not", "required": ["value"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x.get("args", {}))
        val = args["value"]
        if not isinstance(val, list) or len(val) != 1:
            raise ValueError(f"$not requires 'value' to be a list of exactly 1 element.")
        self.arg = Expr.create(val[0])

    def eval(self, interpreter: Interpreter) -> bool:
        return not self.arg.eval(interpreter)


class GetExpr(Expr):
    """
    설명: 지정된 스코프 내에서 특정 경로(path)에 있는 값을 추출하는 접근 연산자입니다.
    args 형식: {"scope": "scope_name", "path": ["path", "to", "key"]}
    예시: {"$op": "$get", "args": {"scope": "global", "path": ["user", "profile", "age"]}}
    """
    SPEC = {"op": "$get", "required": ["scope", "path"], "optional": []}

    def __init__(self, x: dict[str, Any]):
        args = self.check_args(x.get("args", {}))

        self.scope = args["scope"]
        if not isinstance(self.scope, str):
            raise ValueError(f"$get 'scope' must be a string, got {type(self.scope)}")

        self.path = args["path"]
        if not isinstance(self.path, list):
            raise ValueError(f"$get 'path' must be a list, got {type(self.path)}")

    def eval(self, interpreter: Interpreter) -> Any:
        return interpreter.get(self.scope, self.path)