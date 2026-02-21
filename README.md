# JSON Script Interpreter

이 프로젝트는 JSON 형태로 작성된 스크립트를 파이썬 환경에서 순차적으로 실행할 수 있는 경량 인터프리터 엔진입니다. 스크립트 실행 흐름을 제어하는 `Oper`(Statement) 노드와 값을 평가하는 `Expr`(Expression) 노드로 구성되어 있으며, 각 단계를 스텝 단위로 제어할 수 있는 구조를 제공합니다.

## 주요 특징

* JSON 기반 AST: 모든 코드 로직(조건문, 반복문, 변수 할당 등)을 순수 JSON 딕셔너리로 정의하여 실행할 수 있습니다.
* 스텝 단위 제어 (Tick-based Execution): 전체 스크립트를 한 번에 실행하는 `execute()` 메서드뿐만 아니라, 외부 루프에서 `tick()`을 호출하여 명령어를 한 줄씩(Oper 단위로) 실행하고 멈출 수 있어 디버깅이나 비동기/게임 루프 통합에 유리합니다.
* 파이썬 함수 연동 (`$Invoke`): `function_registry`에 파이썬 네이티브 함수를 등록해 두면, JSON 스크립트 내에서 쉽게 호출하고 결과를 받아볼 수 있습니다.
* 체계적인 스코프(Scope) 관리: `local`, `frame`, `kwargs`, `global`의 4가지 변수 스코프를 제공하여 변수의 생명주기와 접근 범위를 엄격하게 관리합니다.

---

## 빠른 시작 (Quick Start)

인터프리터는 실행할 JSON 스크립트들이 담긴 `script_registry`와 파이썬 함수들이 담긴 `function_registry`를 인자로 받아 초기화됩니다.

```python
from interpreter import Interpreter

# 1. 실행할 JSON 스크립트 정의
script_registry = {
    "Main": {
        "param_keys": ["user_name"],
        "steps": [
            {
                "$op": "$Set",
                "args": {
                    "value": "Hello, ",
                    "scope": "local",
                    "path": ["greeting"]
                }
            },
            {
                "$op": "$Invoke",
                "args": {
                    "name": "print_msg",
                    "params": [
                        {"$op": "$get", "args": {"scope": "local", "path": ["greeting"]}},
                        {"$op": "$get", "args": {"scope": "kwargs", "path": ["user_name"]}}
                    ]
                }
            }
        ]
    }
}

# 2. 연동할 파이썬 함수 정의
def my_print(greeting, name):
    print(f"{greeting}{name}!")

function_registry = {
    "print_msg": my_print
}

# 3. 인터프리터 생성 및 실행
engine = Interpreter(script_registry, function_registry)

# 방법 A: 한 번에 끝까지 실행하기
# engine.execute("Main", {"user_name": "Alice"})

# 방법 B: 스텝 단위로 제어하며 실행하기 (Tick 방식)
engine.call_script("Main", ["Alice"])   # engine.call_script("Main", {"user_name": "Alice"})
while not engine.is_finished():
    engine.tick()

```

## 언어 명세 및 문법 (Syntax)

모든 노드는 딕셔너리 형태이며, 연산자 종류를 나타내는 `"$op"` 키와 파라미터를 담는 `"args"` 키로 구성됩니다.

### 1. 연산자 (Oper)

실제 로직의 흐름을 제어하거나 상태를 변경하는 문장(Statement) 역할을 합니다.

* `$If` (조건문)
* 설명: 주어진 조건이 참일 경우 지정된 스크립트 블록을 실행합니다.
* args 형식: `{"cond": condition_expr, "scripts": [oper1, oper2, ...]}`
* 예시: `{"$op": "$If", "args": {"cond": {"$op": "$eq", "args": {"value": [1, 1]}}, "scripts": [...]}}`


* `$ElseIf` (조건문)
* 설명: 이전 조건이 거짓이고 현재 조건이 참일 경우 스크립트 블록을 실행합니다.
* args 형식: `{"cond": condition_expr, "scripts": [oper1, oper2, ...]}`
* 예시: `{"$op": "$ElseIf", "args": {"cond": {"$op": "$gt", "args": {"value": [5, 3]}}, "scripts": [...]}}`


* `$Else` (조건문)
* 설명: 이전의 모든 IF/ElseIf 조건들이 거짓일 경우 스크립트 블록을 실행합니다.
* args 형식: `{"scripts": [oper1, oper2, ...]}`
* 예시: `{"$op": "$Else", "args": {"scripts": [{"$op": "$Set", "args": {...}}]}}`


* `$While` (반복문)
* 설명: 주어진 조건이 참인 동안 스크립트 블록을 반복 실행합니다.
* args 형식: `{"cond": condition_expr, "scripts": [oper1, oper2, ...]}`
* 예시: `{"$op": "$While", "args": {"cond": {"$op": "$lt", "args": {"value": [{"$op": "$get", "args": {"scope": "var", "path": ["i"]}}, 10]}}, "scripts": [...]}}`


* `$Break` (제어)
* 설명: 현재 실행 중인 루프를 즉시 종료하고 빠져나갑니다.
* args 형식: `{}` (또는 생략)
* 예시: `{"$op": "$Break", "args": {}}`


* `$Continue` (제어)
* 설명: 현재 루프의 남은 블록을 건너뛰고 다음 반복 조건 검사로 넘어갑니다.
* args 형식: `{}` (또는 생략)
* 예시: `{"$op": "$Continue", "args": {}}`


* `$Set` (변수 할당)
* 설명: 지정된 스코프 내 특정 경로에 평가된 값을 할당(저장)합니다.
* args 형식: `{"value": value_expr, "scope": "scope_name", "path": ["path", "to", "key"]}`
* 예시: `{"$op": "$Set", "args": {"value": 100, "scope": "local", "path": ["user", "score"]}}`
* `$Script` (스크립트 호출)
* 설명: 사용자 정의 스크립트를 호출하며, 완료 후 선택적으로 반환값을 저장합니다.
* args 형식: `{"name": name_expr, "params": [param1, ...], "scope": (선택), "path": (선택)}`
* 예시: `{"$op": "$Script", "args": {"name": "calc_tax", "params": [1000], "scope": "local", "path": ["tax"]}}`


* `$Return` (반환)
* 설명: 현재 실행 중인 스크립트를 종료하고, 지정된 스코프의 값을 꺼내어 반환합니다.
* args 형식: `{"scope": (선택), "path": (선택)}`
* 예시: `{"$op": "$Return", "args": {"scope": "local", "path": ["result_data"]}}`


* `$Invoke` (외부 함수 호출)
* 설명: 외부 파이썬 함수나 네이티브 메서드를 동적으로 호출하고 결과를 반환받습니다.
* args 형식: `{"name": name_expr, "params": [param1, ...], "scope": (선택), "path": (선택)}`
* 예시: `{"$op": "$Invoke", "args": {"name": "print_log", "params": ["Hello!"], "scope": "global", "path": ["log"]}}`



### 2. 표현식 (Expr)

변수 접근, 논리 연산, 비교 연산 등 값을 평가하여 반환하는 역할을 합니다.

* `$get` (변수 접근)
* 설명: 지정된 스코프 내에서 특정 경로(path)에 있는 값을 추출합니다.
* args 형식: `{"scope": "scope_name", "path": ["path", "to", "key"]}`
* 예시: `{"$op": "$get", "args": {"scope": "global", "path": ["user", "profile", "age"]}}`


* `$list` (자료구조)
* 설명: 여러 하위 표현식을 리스트 형태로 명시적으로 생성하고 평가합니다.
* args 형식: `{"value": [expr1, expr2, ...]}`
* 예시: `{"$op": "$list", "args": {"value": [1, 2, {"$op": "$get", "args": {"scope": "var", "path": ["x"]}}]}}`


* `$dict` (자료구조)
* 설명: 딕셔너리를 명시적으로 생성하며, 키와 값 모두 하위 표현식으로 평가됩니다.
* args 형식: `{"value": {"key1": expr1, "key2": expr2, ...}}`
* 예시: `{"$op": "$dict", "args": {"value": {"name": "Alice", "age": 20}}}`


* `$eq` (==), `$ne` (!=), `$lt` (<), `$le` (<=), `$gt` (>), `$ge` (>=) (비교 연산)
* 설명: 두 값을 비교하여 참/거짓을 반환합니다.
* args 형식: `{"value": [left_expr, right_expr]}`
* 예시 (`$eq`): `{"$op": "$eq", "args": {"value": [{"$op": "$get", "args": {"scope": "var", "path": ["id"]}}, 10]}}`


* `$in` (포함 여부)
* 설명: 특정 항목이 컨테이너(리스트 등) 내에 포함되어 있는지 확인합니다.
* args 형식: `{"item": item_expr, "container": container_expr}`
* 예시: `{"$op": "$in", "args": {"item": "apple", "container": ["apple", "banana", "cherry"]}}`


* `$and`, `$or` (논리 연산)
* 설명: 여러 하위 표현식에 대해 논리곱(AND) 또는 논리합(OR)을 수행합니다.
* args 형식: `{"value": [expr1, expr2, ...]}`
* 예시 (`$and`): `{"$op": "$and", "args": {"value": [{"$op": "$eq", "args": {"value": [1, 1]}}, {"$op": "$gt", "args": {"value": [5, 3]}}]}}`


* `$not` (논리 반전)
* 설명: 단일 하위 표현식의 논리값을 반전시킵니다.
* args 형식: `{"value": [expr]}`
* 예시: `{"$op": "$not", "args": {"value": [{"$op": "$eq", "args": {"value": [1, 2]}}]}}`



*(리터럴의 경우, 위 연산자에 해당하지 않는 일반 값들은 상수로 평가됩니다.)*

### 3. 스코프 (Scope) 및 경로 (Path)

변수에 접근(`$get`)하거나 할당(`$Set`)할 때 4가지 스코프를 지정할 수 있으며, 깊은 딕셔너리 탐색을 위해 리스트 형태의 `path`를 사용합니다.

* `local`: 현재 스크립트 내의 지역 변수. 가장 가까운 하위 프레임부터 최상위 프레임까지 역순으로 탐색합니다.
* `frame`: 현재 실행 중인 블록(If/While 내부 등)에만 종속되는 좁은 범위의 변수입니다.
* `kwargs`: 스크립트가 호출될 때 전달받은 읽기 전용 인자입니다.
* `global`: 인터프리터 전체에서 공유되는 전역 변수 공간입니다.

*(예: `{"scope": "local", "path": ["user", "profile", "age"]}`는 `local_vars["user"]["profile"]["age"]`에 접근합니다.)*
