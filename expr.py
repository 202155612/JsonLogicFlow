from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Literal, Union
from pydantic import BaseModel, Field, RootModel, TypeAdapter, model_validator
from typing_extensions import Annotated
from constant import ScopeType

if TYPE_CHECKING:
    from .interpreter import Interpreter


# -----------------------------------------------------------------------------
# 1. 연산자 인수(Args) 스키마 정의
# -----------------------------------------------------------------------------
# Pydantic이 리스트 길이, 타입 검증을 자동으로 수행합니다.

class ListOpArgs(BaseModel):
    value: List['Expr']

class DictOpArgs(BaseModel):
    value: Dict[Any, 'Expr']

class CompareArgs(BaseModel):
    """$eq, $ne, $lt, $le, $gt, $ge 등 2개의 피연산자를 받는 연산자의 공통 Args"""
    value: List['Expr'] = Field(min_length=2, max_length=2)

class InArgs(BaseModel):
    item: 'Expr'
    container: 'Expr'

class LogicalArgs(BaseModel):
    """$and, $or 등 가변 개수의 피연산자를 받는 연산자의 공통 Args"""
    value: List['Expr']

class NotArgs(BaseModel):
    value: List['Expr'] = Field(min_length=1, max_length=1)

class GetArgs(BaseModel):
    scope: ScopeType
    path: List[str]


# -----------------------------------------------------------------------------
# 2. 연산자(Op) 표현식 모델 정의
# -----------------------------------------------------------------------------
# alias="$op"를 사용하여 JSON의 {"$op": "..."} 구조를 파싱합니다.

class ListOpExpr(BaseModel):
    """설명: 여러 하위 표현식을 리스트 형태로 명시적으로 생성하고 평가하는 연산자"""
    op: Literal["$list"] = Field(alias="$op")
    args: ListOpArgs

    def eval(self, interpreter: Interpreter) -> list[Any]:
        return [it.eval(interpreter) for it in self.args.value]


class DictOpExpr(BaseModel):
    """설명: 딕셔너리를 명시적으로 생성하며, 키와 값 모두 하위 표현식으로 평가되는 연산자"""
    op: Literal["$dict"] = Field(alias="$op")
    args: DictOpArgs

    def eval(self, interpreter: Interpreter) -> dict[Any, Any]:
        return {k: v.eval(interpreter) for k, v in self.args.value.items()}


class EqExpr(BaseModel):
    op: Literal["$eq"] = Field(alias="$op")
    args: CompareArgs

    def eval(self, interpreter: Interpreter) -> bool:
        return self.args.value[0].eval(interpreter) == self.args.value[1].eval(interpreter)


class NeExpr(BaseModel):
    op: Literal["$ne"] = Field(alias="$op")
    args: CompareArgs

    def eval(self, interpreter: Interpreter) -> bool:
        return self.args.value[0].eval(interpreter) != self.args.value[1].eval(interpreter)


class LtExpr(BaseModel):
    op: Literal["$lt"] = Field(alias="$op")
    args: CompareArgs

    def eval(self, interpreter: Interpreter) -> bool:
        return self.args.value[0].eval(interpreter) < self.args.value[1].eval(interpreter)  # type: ignore


class LeExpr(BaseModel):
    op: Literal["$le"] = Field(alias="$op")
    args: CompareArgs

    def eval(self, interpreter: Interpreter) -> bool:
        return self.args.value[0].eval(interpreter) <= self.args.value[1].eval(interpreter)  # type: ignore


class GtExpr(BaseModel):
    op: Literal["$gt"] = Field(alias="$op")
    args: CompareArgs

    def eval(self, interpreter: Interpreter) -> bool:
        return self.args.value[0].eval(interpreter) > self.args.value[1].eval(interpreter)  # type: ignore


class GeExpr(BaseModel):
    op: Literal["$ge"] = Field(alias="$op")
    args: CompareArgs

    def eval(self, interpreter: Interpreter) -> bool:
        return self.args.value[0].eval(interpreter) >= self.args.value[1].eval(interpreter)  # type: ignore


class InExpr(BaseModel):
    op: Literal["$in"] = Field(alias="$op")
    args: InArgs

    def eval(self, interpreter: Interpreter) -> bool:
        return self.args.item.eval(interpreter) in self.args.container.eval(interpreter)  # type: ignore


class AndExpr(BaseModel):
    op: Literal["$and"] = Field(alias="$op")
    args: LogicalArgs

    def eval(self, interpreter: Interpreter) -> bool:
        return all(a.eval(interpreter) for a in self.args.value)


class OrExpr(BaseModel):
    op: Literal["$or"] = Field(alias="$op")
    args: LogicalArgs

    def eval(self, interpreter: Interpreter) -> bool:
        return any(a.eval(interpreter) for a in self.args.value)


class NotExpr(BaseModel):
    op: Literal["$not"] = Field(alias="$op")
    args: NotArgs

    def eval(self, interpreter: Interpreter) -> bool:
        return not self.args.value[0].eval(interpreter)


class GetExpr(BaseModel):
    op: Literal["$get"] = Field(alias="$op")
    args: GetArgs

    def eval(self, interpreter: Interpreter) -> Any:
        return interpreter.get(self.args.scope, self.args.path)


# -----------------------------------------------------------------------------
# 3. 리터럴 및 기본 값 표현식 모델 (RootModel 활용)
# -----------------------------------------------------------------------------
# RootModel을 사용하면 {"$op": ...} 형태가 아닌 일반 리스트, 딕셔너리, 값을
# 기존의 ListLiteralExpr 등과 동일하게 노드로 파싱할 수 있습니다.

class DictLiteralExpr(RootModel):
    root: Dict[Any, 'Expr']

    @model_validator(mode='before')
    @classmethod
    def check_not_op(cls, data: Any) -> Any:
        if isinstance(data, dict) and "$op" in data:
            raise ValueError('Dictionaries with "$op" are operators, not DictLiteralExpr.')
        return data

    def eval(self, interpreter: Interpreter) -> dict[Any, Any]:
        return {k: v.eval(interpreter) for k, v in self.root.items()}

class ListLiteralExpr(RootModel):
    root: List['Expr']

    def eval(self, interpreter: Interpreter) -> list[Any]:
        return [it.eval(interpreter) for it in self.root]

class ValueExpr(RootModel):
    root: Any
    
    @model_validator(mode='before')
    @classmethod
    def check_not_op(cls, data: Any) -> Any:
        if isinstance(data, dict) and "$op" in data:
            raise ValueError('Dictionaries with "$op" are operators, not ValueExpr.')
        return data

    def eval(self, interpreter: Interpreter) -> Any:
        return self.root


# -----------------------------------------------------------------------------
# 4. 타입 매핑 및 팩토리 어댑터 설정
# -----------------------------------------------------------------------------

# $op 값에 따라 올바른 클래스로 자동 라우팅되는 Discriminated Union
OpExpr = Annotated[
    Union[
        ListOpExpr, DictOpExpr,
        EqExpr, NeExpr, LtExpr, LeExpr, GtExpr, GeExpr, InExpr,
        AndExpr, OrExpr, NotExpr,
        GetExpr
    ],
    Field(discriminator="op")
]

Expr = Union[OpExpr, DictLiteralExpr, ListLiteralExpr, ValueExpr]

ExprAdapter = TypeAdapter(Expr)

def create_expr(data: Any) -> Expr:
    """Expr를 생성해 반환합니다."""
    return ExprAdapter.validate_python(data)