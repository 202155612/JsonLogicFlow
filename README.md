# JSON Script Interpreter

이 프로젝트는 JSON 형태로 작성된 스크립트를 파이썬 환경에서 순차적으로 실행할 수 있는 경량 인터프리터 엔진입니다. 스크립트 실행 흐름을 제어하는 `Oper`(Statement) 노드와 값을 평가하는 `Expr`(Expression) 노드로 구성되어 있으며, 각 단계를 스텝 단위로 제어할 수 있는 구조를 제공합니다.

## 주요 특징

* **JSON 기반 AST**: 모든 코드 로직(조건문, 반복문, 변수 할당 등)을 순수 JSON 딕셔너리로 정의하여 실행할 수 있습니다.
* **스텝 단위 제어 (Tick-based Execution)**: 전체 스크립트를 한 번에 실행하는 `execute()` 메서드뿐만 아니라, 외부 루프에서 `tick()`을 호출하여 명령어를 한 줄씩(Oper 단위로) 실행하고 멈출 수 있어 디버깅이나 비동기/게임 루프 통합에 유리합니다.
* **파이썬 함수 연동 (`$Invoke`)**: `function_registry`에 파이썬 네이티브 함수를 등록해 두면, JSON 스크립트 내에서 쉽게 호출하고 결과를 받아볼 수 있습니다.
* **체계적인 스코프(Scope) 관리**: `local`, `frame`, `kwargs`, `global`의 4가지 변수 스코프를 제공하여 변수의 생명주기와 접근 범위를 엄격하게 관리합니다.

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
engine.call_script("Main", ["Alice"])
while engine.is_working():
    engine.tick()

```

---

## 언어 명세 및 문법 (Syntax)

모든 노드는 딕셔너리 형태이며, 연산자 종류를 나타내는 `"$op"` 키와 파라미터를 담는 `"args"` 키로 구성됩니다.

### 1. 연산자 (Oper)

실제 로직의 흐름을 제어하거나 상태를 변경하는 문장(Statement) 역할을 합니다.

* **제어 흐름**: `$If`, `$ElseIf`, `$Else`, `$While`, `$Break`, `$Continue`
* **변수 및 실행**:
* `$Set`: 지정된 스코프의 경로에 값을 할당합니다.
* `$Script`: 등록된 다른 JSON 스크립트를 호출합니다 (`script_registry` 참조).
* `$Return`: 현재 스크립트를 종료하고 값을 반환합니다.
* `$Invoke`: 파이썬 네이티브 함수를 호출합니다 (`function_registry` 참조).



### 2. 표현식 (Expr)

변수 접근, 논리 연산, 비교 연산 등 값을 평가하여 반환하는 역할을 합니다.

* **변수 접근**: `$get` (스코프와 경로를 통해 값을 가져옴)
* **비교 연산**: `$eq`(==), `$ne`(!=), `$lt`(<), `$le`(<=), `$gt`(>), `$ge`(>=), `$in`
* **논리 연산**: `$and`, `$or`, `$not`
* **자료구조 생성**: `$list`, `$dict`
* **리터럴**: 위 연산자에 해당하지 않는 일반 값(숫자, 문자열, 단순 리스트/딕셔너리)은 상수로 평가됩니다.

### 3. 스코프 (Scope) 및 경로 (Path)

변수에 접근(`$get`)하거나 할당(`$Set`)할 때 4가지 스코프를 지정할 수 있으며, 깊은 딕셔너리 탐색을 위해 리스트 형태의 `path`를 사용합니다.

* `local`: 현재 스크립트 내의 지역 변수. 가장 가까운 하위 프레임부터 최상위 프레임까지 역순으로 탐색합니다.
* `frame`: 현재 실행 중인 블록(If/While 내부 등)에만 종속되는 좁은 범위의 변수입니다.
* `kwargs`: 스크립트가 호출될 때 전달받은 읽기 전용 인자입니다.
* `global`: 인터프리터 전체에서 공유되는 전역 변수 공간입니다.

*(예: `{"scope": "local", "path": ["user", "profile", "age"]}`는 `local_vars["user"]["profile"]["age"]`에 접근합니다.)*
