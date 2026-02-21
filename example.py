"""
example.py

JSON Script Interpreter 데모 스크립트.

이 파일은 다음 기능이 "실제로 실행"되도록 구성되어 있습니다.
- $If / $ElseIf / $Else
- $While
- $Break / $Continue
- $Script / $Return (조건부 return 포함)
- $Invoke (파이썬 함수 연동)
- $AsyncInvoke (비동기 처리/일시정지 연동)
- scope: local / frame / kwargs / global
- Expr: $get / $in / $and / $not / $list / $dict
- [NEW] save_state / load_state (상태 저장 및 복구)

실행 방법:
    python example.py
"""

from __future__ import annotations

import json
from interpreter import Interpreter
from constant import ExecState


# ---------------------------------------------------------------------------
# 1) 파이썬 네이티브 함수(Invoke 대상) 등록
# ---------------------------------------------------------------------------

def print_line(*parts):
    """스크립트에서 콘솔 출력용으로 사용."""
    print(*parts)

def add(a, b):
    """숫자 덧셈 (i += 1, total += i 등에서 사용)."""
    return a + b

def append_item(lst, item):
    """리스트에 item을 추가하고(제자리 변경) 리스트를 반환."""
    lst.append(item)
    return lst

def log_event(log_list, *parts):
    """
    global.log(list)에 이벤트 문자열을 append.
    문자열로 만들기 위해 parts를 공백으로 join.
    """
    msg = " ".join(str(p) for p in parts)
    log_list.append(msg)
    return log_list


function_registry = {
    "print_line": print_line,
    "add": add,
    "append_item": append_item,
    "log_event": log_event,
}


# ---------------------------------------------------------------------------
# 2) JSON 스크립트 정의 (script_registry)
# ---------------------------------------------------------------------------

script_registry = {
    # -----------------------------------------------------------------------
    # Main: 전체 데모 실행
    # -----------------------------------------------------------------------
    "Main": {
        "param_keys": ["user_name", "mode", "n", "threshold"],
        "steps": [
            # global.log 초기화
            {"$op": "$Set", "args": {"value": [], "scope": "global", "path": ["log"]}},

            # kwargs 출력
            {"$op": "$Invoke", "args": {
                "name": "print_line",
                "params": [
                    "\n=== Main start ===",
                    "user=", {"$op": "$get", "args": {"scope": "kwargs", "path": ["user_name"]}},
                    "mode=", {"$op": "$get", "args": {"scope": "kwargs", "path": ["mode"]}},
                    "n=", {"$op": "$get", "args": {"scope": "kwargs", "path": ["n"]}},
                    "threshold=", {"$op": "$get", "args": {"scope": "kwargs", "path": ["threshold"]}},
                ]
            }},

            # 사용자 권한(role)을 비동기로 가져온다고 가정
            {"$op": "$AsyncInvoke", "args": {
                "name": "fetch_user_role",
                "params": [{"$op": "$get", "args": {"scope": "kwargs", "path": ["user_name"]}}],
                "scope": "local",
                "path": ["async_role"]
            }},
            {"$op": "$Invoke", "args": {
                "name": "print_line",
                "params": [
                    "[Async Result] Fetched role =", 
                    {"$op": "$get", "args": {"scope": "local", "path": ["async_role"]}}
                ]
            }},
            # -------------------------------

            # $If/$ElseIf/$Else 데모를 별도 스크립트로 분리 (각 branch에서 즉시 $Return)
            {"$op": "$Script", "args": {
                "name": "ChooseMode",
                "params": [{"$op": "$get", "args": {"scope": "kwargs", "path": ["mode"]}}],
                "scope": "local",
                "path": ["mode_class"],
            }},
            {"$op": "$Invoke", "args": {
                "name": "print_line",
                "params": ["mode_class =", {"$op": "$get", "args": {"scope": "local", "path": ["mode_class"]}}],
            }},

            # $While/$Break/$Continue + frame/local/global scope + $list/$dict 등 데모
            {"$op": "$Script", "args": {
                "name": "ComputeStats",
                "params": [
                    {"$op": "$get", "args": {"scope": "kwargs", "path": ["n"]}},
                    {"$op": "$get", "args": {"scope": "kwargs", "path": ["threshold"]}},
                ],
                "scope": "local",
                "path": ["stats"],
            }},
            {"$op": "$Invoke", "args": {
                "name": "print_line",
                "params": ["stats =", {"$op": "$get", "args": {"scope": "local", "path": ["stats"]}}],
            }},

            # 조건부 return 데모
            {"$op": "$Script", "args": {
                "name": "MaybeEarlyReturn",
                "params": [{"$op": "$get", "args": {"scope": "kwargs", "path": ["mode"]}}],
                "scope": "local",
                "path": ["msg"],
            }},
            {"$op": "$Invoke", "args": {
                "name": "print_line",
                "params": ["MaybeEarlyReturn ->", {"$op": "$get", "args": {"scope": "local", "path": ["msg"]}}],
            }},

            # global scope 확인
            {"$op": "$Invoke", "args": {
                "name": "print_line",
                "params": ["global.log =", {"$op": "$get", "args": {"scope": "global", "path": ["log"]}}],
            }},

            # Main 반환
            {"$op": "$Return", "args": {"scope": "local", "path": ["stats"]}},
        ],
    },

    # -----------------------------------------------------------------------
    # ChooseMode: $If/$ElseIf/$Else를 "실제로 실행"하기 위한 스크립트
    # -----------------------------------------------------------------------
    "ChooseMode": {
        "param_keys": ["mode"],
        "steps": [
            {"$op": "$If", "args": {
                "cond": {"$op": "$eq", "args": {"value": [
                    {"$op": "$get", "args": {"scope": "kwargs", "path": ["mode"]}},
                    "A",
                ]}},
                "scripts": [
                    {"$op": "$Set", "args": {"value": "A", "scope": "local", "path": ["result"]}},
                    {"$op": "$Return", "args": {"scope": "local", "path": ["result"]}},
                ],
            }},
            {"$op": "$ElseIf", "args": {
                "cond": {"$op": "$eq", "args": {"value": [
                    {"$op": "$get", "args": {"scope": "kwargs", "path": ["mode"]}},
                    "B",
                ]}},
                "scripts": [
                    {"$op": "$Set", "args": {"value": "B", "scope": "local", "path": ["result"]}},
                    {"$op": "$Return", "args": {"scope": "local", "path": ["result"]}},
                ],
            }},
            {"$op": "$Else", "args": {
                "scripts": [
                    {"$op": "$Set", "args": {"value": "OTHER", "scope": "local", "path": ["result"]}},
                    {"$op": "$Return", "args": {"scope": "local", "path": ["result"]}},
                ],
            }},
        ],
    },

    # -----------------------------------------------------------------------
    # ComputeStats: while loop에서 continue/break, frame/local/global 스코프 사용
    # -----------------------------------------------------------------------
    "ComputeStats": {
        "param_keys": ["n", "threshold"],
        "steps": [
            {"$op": "$Set", "args": {"value": 0, "scope": "local", "path": ["i"]}},
            {"$op": "$Set", "args": {"value": 0, "scope": "local", "path": ["total"]}},
            {"$op": "$Set", "args": {"value": 0, "scope": "local", "path": ["skipped_evens"]}},
            {"$op": "$Set", "args": {"value": [], "scope": "local", "path": ["seen_odds"]}},

            {"$op": "$While", "args": {
                "cond": {"$op": "$lt", "args": {"value": [
                    {"$op": "$get", "args": {"scope": "local", "path": ["i"]}},
                    {"$op": "$get", "args": {"scope": "kwargs", "path": ["n"]}},
                ]}},
                "scripts": [
                    # i += 1
                    {"$op": "$Invoke", "args": {
                        "name": "add",
                        "params": [
                            {"$op": "$get", "args": {"scope": "local", "path": ["i"]}},
                            1,
                        ],
                        "scope": "local",
                        "path": ["i"],
                    }},

                    # local.iteration = i
                    {"$op": "$Set", "args": {
                        "value": {"$op": "$get", "args": {"scope": "local", "path": ["i"]}},
                        "scope": "local",
                        "path": ["iteration"],
                    }},

                    {"$op": "$Set", "args": {"value": "", "scope": "frame", "path": ["note"]}},

                    # 짝수면 continue
                    {"$op": "$If", "args": {
                        "cond": {"$op": "$in", "args": {
                            "item": {"$op": "$get", "args": {"scope": "local", "path": ["i"]}},
                            "container": [2, 4, 6, 8, 10, 12, 14, 16, 18, 20],
                        }},
                        "scripts": [
                            {"$op": "$Set", "args": {"value": "EVEN_BLOCK", "scope": "frame", "path": ["block_tag"]}},

                            # skipped_evens += 1
                            {"$op": "$Invoke", "args": {
                                "name": "add",
                                "params": [
                                    {"$op": "$get", "args": {"scope": "local", "path": ["skipped_evens"]}},
                                    1,
                                ],
                                "scope": "local",
                                "path": ["skipped_evens"],
                            }},

                            {"$op": "$Invoke", "args": {
                                "name": "log_event",
                                "params": [
                                    {"$op": "$get", "args": {"scope": "global", "path": ["log"]}},
                                    "CONTINUE at i",
                                    {"$op": "$get", "args": {"scope": "local", "path": ["iteration"]}},
                                ],
                                "scope": "global",
                                "path": ["log"],
                            }},
                            {"$op": "$Invoke", "args": {
                                "name": "print_line",
                                "params": [
                                    "[continue]",
                                    "i=", {"$op": "$get", "args": {"scope": "local", "path": ["iteration"]}},
                                    "skipped=", {"$op": "$get", "args": {"scope": "local", "path": ["skipped_evens"]}},
                                    "block_tag=", {"$op": "$get", "args": {"scope": "frame", "path": ["block_tag"]}},
                                ],
                            }},

                            {"$op": "$Continue", "args": {}},
                        ],
                    }},

                    # 홀수 처리: seen_odds.append(i)
                    {"$op": "$Invoke", "args": {
                        "name": "append_item",
                        "params": [
                            {"$op": "$get", "args": {"scope": "local", "path": ["seen_odds"]}},
                            {"$op": "$get", "args": {"scope": "local", "path": ["i"]}},
                        ],
                        "scope": "local",
                        "path": ["seen_odds"],
                    }},

                    # total += i
                    {"$op": "$Invoke", "args": {
                        "name": "add",
                        "params": [
                            {"$op": "$get", "args": {"scope": "local", "path": ["total"]}},
                            {"$op": "$get", "args": {"scope": "local", "path": ["i"]}},
                        ],
                        "scope": "local",
                        "path": ["total"],
                    }},

                    {"$op": "$Set", "args": {
                        "value": {"$op": "$dict", "args": {"value": {
                            "i": {"$op": "$get", "args": {"scope": "local", "path": ["iteration"]}},
                            "total": {"$op": "$get", "args": {"scope": "local", "path": ["total"]}},
                            "note": {"$op": "$get", "args": {"scope": "frame", "path": ["note"]}},
                        }}},
                        "scope": "frame",
                        "path": ["snapshot"],
                    }},
                    {"$op": "$Invoke", "args": {
                        "name": "print_line",
                        "params": ["[loop]", {"$op": "$get", "args": {"scope": "frame", "path": ["snapshot"]}}],
                    }},

                    # break 조건: (total > threshold) AND (i > 3)
                    {"$op": "$If", "args": {
                        "cond": {"$op": "$and", "args": {"value": [
                            {"$op": "$gt", "args": {"value": [
                                {"$op": "$get", "args": {"scope": "local", "path": ["total"]}},
                                {"$op": "$get", "args": {"scope": "kwargs", "path": ["threshold"]}},
                            ]}},
                            {"$op": "$gt", "args": {"value": [
                                {"$op": "$get", "args": {"scope": "local", "path": ["iteration"]}},
                                3,
                            ]}},
                        ]}},
                        "scripts": [
                            {"$op": "$Invoke", "args": {
                                "name": "log_event",
                                "params": [
                                    {"$op": "$get", "args": {"scope": "global", "path": ["log"]}},
                                    "BREAK at total",
                                    {"$op": "$get", "args": {"scope": "local", "path": ["total"]}},
                                ],
                                "scope": "global",
                                "path": ["log"],
                            }},
                            {"$op": "$Invoke", "args": {
                                "name": "print_line",
                                "params": [
                                    "[break]",
                                    "total=", {"$op": "$get", "args": {"scope": "local", "path": ["total"]}},
                                    "threshold=", {"$op": "$get", "args": {"scope": "kwargs", "path": ["threshold"]}},
                                ],
                            }},
                            {"$op": "$Break", "args": {}},
                        ],
                    }},
                ],
            }},

            {"$op": "$Set", "args": {
                "value": {"$op": "$list", "args": {"value": [
                    {"$op": "$get", "args": {"scope": "local", "path": ["total"]}},
                    {"$op": "$get", "args": {"scope": "local", "path": ["skipped_evens"]}},
                    {"$op": "$get", "args": {"scope": "local", "path": ["seen_odds"]}},
                ]}},
                "scope": "local",
                "path": ["summary_list"],
            }},

            {"$op": "$Set", "args": {
                "value": {"$op": "$dict", "args": {"value": {
                    "n": {"$op": "$get", "args": {"scope": "kwargs", "path": ["n"]}},
                    "threshold": {"$op": "$get", "args": {"scope": "kwargs", "path": ["threshold"]}},
                    "total": {"$op": "$get", "args": {"scope": "local", "path": ["total"]}},
                    "skipped_evens": {"$op": "$get", "args": {"scope": "local", "path": ["skipped_evens"]}},
                    "seen_odds": {"$op": "$get", "args": {"scope": "local", "path": ["seen_odds"]}},
                    "summary_list": {"$op": "$get", "args": {"scope": "local", "path": ["summary_list"]}},
                }}},
                "scope": "local",
                "path": ["result"],
            }},

            {"$op": "$Return", "args": {"scope": "local", "path": ["result"]}},
        ],
    },

    # -----------------------------------------------------------------------
    # MaybeEarlyReturn: 조건부 return 데모
    # -----------------------------------------------------------------------
    "MaybeEarlyReturn": {
        "param_keys": ["mode"],
        "steps": [
            {"$op": "$If", "args": {
                "cond": {"$op": "$eq", "args": {"value": [
                    {"$op": "$get", "args": {"scope": "kwargs", "path": ["mode"]}},
                    "STOP",
                ]}},
                "scripts": [
                    {"$op": "$Set", "args": {"value": "(early return) mode==STOP", "scope": "local", "path": ["msg"]}},
                    {"$op": "$Return", "args": {"scope": "local", "path": ["msg"]}},
                ],
            }},
            {"$op": "$Else", "args": {
                "scripts": [
                    {"$op": "$Set", "args": {"value": "(normal) mode!=STOP", "scope": "local", "path": ["msg"]}},
                    {"$op": "$Return", "args": {"scope": "local", "path": ["msg"]}},
                ],
            }},
        ],
    },
}


# ---------------------------------------------------------------------------
# 3) Tick 기반 실행 루프 (save_state / load_state 적용)
# ---------------------------------------------------------------------------

def run_case(user_name: str, mode: str, n: int, threshold: int, test_save_load: bool = False) -> None:
    engine = Interpreter(script_registry, function_registry)

    # param_keys = ["user_name", "mode", "n", "threshold"] 순서대로 params를 넣어야 합니다.
    engine.call_script("Main", [user_name, mode, n, threshold])

    ticks = 0
    while not engine.is_finished():
        ticks += 1
        state = engine.tick()

        # $AsyncInvoke 처리 루프 연동
        if state == ExecState.BLOCKED:
            print(f"\n>> [Host] Interpreter BLOCKED at tick {ticks}.")
            
            # [NEW] Save / Load 기능 테스트
            if test_save_load:
                print(">> [Host] --- SAVE / LOAD TEST START ---")
                
                # 1. 현재 상태 저장
                saved_state_dict = engine.save_state()
                
                # DB나 파일에 저장했다가 다시 불러온다고 가정 (JSON 직렬화/역직렬화)
                saved_json_str = json.dumps(saved_state_dict)
                restored_state_dict = json.loads(saved_json_str)
                
                print(">> [Host] State successfully serialized to JSON and deserialized.")
                
                # 2. 완전히 새로운 인터프리터 인스턴스 생성
                # (파이썬 함수 레지스트리는 콜백이므로 인스턴스화 할 때 다시 넘겨주어야 함)
                new_engine = Interpreter(script_registry, function_registry)
                
                # 3. 역직렬화된 상태 로드
                new_engine.load_state(restored_state_dict)
                print(">> [Host] State loaded into the NEW interpreter instance.")
                
                # 4. 기존 엔진을 새 엔진으로 교체
                engine = new_engine
                print(">> [Host] --- SAVE / LOAD TEST COMPLETE ---\n")

            print(">> [Host] Simulating external asynchronous operation...")
            
            # 여기서 실제로는 네트워크 요청이나 DB 조회를 수행하고 완료 콜백을 기다림
            # 데모이므로 즉시 결과를 만들어 주입(resume)합니다.
            simulated_async_result = f"AdminRole_for_{user_name}"
            
            print(f">> [Host] Resuming with value: '{simulated_async_result}'\n")
            engine.resume(simulated_async_result)

    print(f"--- finished (ticks={ticks}) ---")
    print("global_vars =", engine.global_vars)


if __name__ == "__main__":
    # 1) mode="A" -> ChooseMode에서 $If branch 실행
    run_case("Alice", "A", n=10, threshold=15)

    # 2) mode="B" -> ChooseMode에서 $ElseIf branch 실행 
    # (여기서 Save / Load 기능이 제대로 동작하는지 테스트합니다)
    run_case("Bob", "B", n=10, threshold=17, test_save_load=True)

    # 3) mode="Z" -> ChooseMode에서 $Else branch 실행
    run_case("Charlie", "Z", n=10, threshold=12)

    # 4) mode="STOP" -> MaybeEarlyReturn이 조건부 return (early) 실행
    run_case("Dana", "STOP", n=10, threshold=12)