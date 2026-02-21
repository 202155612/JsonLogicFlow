from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, TypeAdapter
from typing_extensions import Annotated

from expr import Expr 
from constant import FrameType, ScopeType

if TYPE_CHECKING:
    from .interpreter import Interpreter



# -----------------------------------------------------------------------------
# 1. 연산자 인수(Args) 스키마 정의
# -----------------------------------------------------------------------------
class IfArgs(BaseModel):
    cond: Expr
    scripts: List['Oper']

class ElseIfArgs(BaseModel):
    cond: Expr
    scripts: List['Oper']

class ElseArgs(BaseModel):
    scripts: List['Oper']

class WhileArgs(BaseModel):
    cond: Expr
    scripts: List['Oper']

class SetArgs(BaseModel):
    value: Expr
    scope: ScopeType
    path: List[str]

class ScriptArgs(BaseModel):
    name: Expr
    params: List[Expr]
    scope: Optional[ScopeType] = None
    path: Optional[List[str]] = None

class ReturnArgs(BaseModel):
    scope: Optional[ScopeType] = None
    path: Optional[List[str]] = None

class InvokeArgs(BaseModel):
    name: Expr
    params: List[Expr]
    scope: Optional[ScopeType] = None
    path: Optional[List[str]] = None


# -----------------------------------------------------------------------------
# 2. 동작(Oper) 모델 정의
# -----------------------------------------------------------------------------

class IfOper(BaseModel):
    op: Literal["$If"] = Field(alias="$op")
    args: IfArgs

    def eval(self, interpreter: Interpreter) -> Any:
        interpreter.inc_pc()
        if self.args.cond.eval(interpreter):
            interpreter.push_frame(self.args.scripts, FrameType.BLOCK)
        else:
            interpreter.set_else_flag()


class ElseIfOper(BaseModel):
    op: Literal["$ElseIf"] = Field(alias="$op")
    args: ElseIfArgs

    def eval(self, interpreter: Interpreter) -> Any:
        should_check = interpreter.get_else_flag()
        interpreter.inc_pc()
        if should_check:
            if self.args.cond.eval(interpreter):
                interpreter.push_frame(self.args.scripts, FrameType.BLOCK)
            else:
                interpreter.set_else_flag()


class ElseOper(BaseModel):
    op: Literal["$Else"] = Field(alias="$op")
    args: ElseArgs

    def eval(self, interpreter: Interpreter) -> Any:
        if interpreter.get_else_flag():
            interpreter.inc_pc()
            interpreter.push_frame(self.args.scripts, FrameType.BLOCK)
        else:
            interpreter.inc_pc()


class WhileOper(BaseModel):
    op: Literal["$While"] = Field(alias="$op")
    args: WhileArgs

    def eval(self, interpreter: Interpreter) -> Any:
        if self.args.cond.eval(interpreter):
            interpreter.push_frame(self.args.scripts, FrameType.LOOP)
        else:
            interpreter.inc_pc()


class BreakOper(BaseModel):
    op: Literal["$Break"] = Field(alias="$op")
    # args가 없거나 {} 여도 통과하도록 허용
    args: Optional[Dict[str, Any]] = Field(default_factory=dict)

    def eval(self, interpreter: Interpreter) -> Any:
        interpreter.end_loop()
        interpreter.inc_pc()


class ContinueOper(BaseModel):
    op: Literal["$Continue"] = Field(alias="$op")
    args: Optional[Dict[str, Any]] = Field(default_factory=dict)

    def eval(self, interpreter: Interpreter) -> Any:
        interpreter.end_loop()


class SetOper(BaseModel):
    op: Literal["$Set"] = Field(alias="$op")
    args: SetArgs

    def eval(self, interpreter: Interpreter) -> Any:
        val = self.args.value.eval(interpreter)
        interpreter.set(self.args.scope, self.args.path, val)
        interpreter.inc_pc()


class ScriptOper(BaseModel):
    op: Literal["$Script"] = Field(alias="$op")
    args: ScriptArgs

    def eval(self, interpreter: Interpreter) -> Any:
        if interpreter.get_return_flag():
            result = interpreter.get_result_value()
            interpreter.set_return_flag(False)
            if self.args.scope and self.args.path:
                interpreter.set(self.args.scope, self.args.path, result)
            interpreter.inc_pc()
        else:
            name = self.args.name.eval(interpreter)
            params = [p.eval(interpreter) for p in self.args.params]
            interpreter.call_script(name, params)  # type: ignore


class ReturnOper(BaseModel):
    op: Literal["$Return"] = Field(alias="$op")
    # Return의 경우 args 자체가 생략될 수 있으므로 기본값을 dict로 줍니다.
    args: ReturnArgs = Field(default_factory=ReturnArgs)

    def eval(self, interpreter: Interpreter) -> Any:
        return_value = None
        if self.args.scope and self.args.path:
            return_value = interpreter.get(self.args.scope, self.args.path)
        interpreter.return_script(return_value)


class InvokeOper(BaseModel):
    op: Literal["$Invoke"] = Field(alias="$op")
    args: InvokeArgs

    def eval(self, interpreter: Interpreter) -> Any:
        interpreter.inc_pc()

        name = self.args.name.eval(interpreter)
        params_values = [p.eval(interpreter) for p in self.args.params]

        result = interpreter.call_func(name, params_values)  # type: ignore

        if self.args.scope and self.args.path:
            interpreter.set(self.args.scope, self.args.path, result)

        return result

class AsyncInvokeOper(BaseModel):
    op: Literal["$AsyncInvoke"] = Field(alias="$op")
    args: InvokeArgs

    def eval(self, interpreter: "Interpreter") -> Any:
        interpreter.block()
        return None

    def resume(self, interpreter: "Interpreter", value: Any) -> Any:
        if self.args.scope and self.args.path:
            interpreter.set(self.args.scope, self.args.path, value)
        interpreter.inc_pc()
        return value

# -----------------------------------------------------------------------------
# 3. 타입 매핑 및 팩토리 어댑터 설정
# -----------------------------------------------------------------------------

# $op 값에 따라 올바른 Oper 클래스로 자동 라우팅 (Discriminated Union)
Oper = Annotated[
    Union[
        IfOper, ElseIfOper, ElseOper, WhileOper,
        BreakOper, ContinueOper, SetOper, ScriptOper,
        ReturnOper, InvokeOper, AsyncInvokeOper
    ],
    Field(discriminator="op")
]

OperAdapter = TypeAdapter(Oper)

def create_oper(data: Any) -> Oper:
    return OperAdapter.validate_python(data)
