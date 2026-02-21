"""
example.py

JSON Script Interpreter 데모 스크립트.

이 파일은 다음 기능이 "실제로 실행"되도록 구성되어 있습니다.
- $If / $ElseIf / $Else
- $While
- $Break / $Continue
- $Script / $Return (조건부 return 포함)
- $Invoke (파이썬 함수 연동)
- scope: local / frame / kwargs / global
- Expr: $get / $in / $and / $not / $list / $dict

실행 방법:
    python example.py
"""

from __future__ import annotations

from interpreter import Interpreter


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
    # 각 branch는 result 세팅 후 즉시 $Return -> 하나의 branch만 실행되도록 구성
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
    # ComputeStats: while loop에서 continue/break, frame/local/global 스코프를 사용
    # - i를 1씩 증가
    # - 짝수면 continue (skipped 증가)
    # - 홀수면 seen_odds에 append, total에 더함
    # - total > threshold AND i > 3 이면 break
    # - 결과는 $dict / $list로 만들어 return
    #
    # NOTE: "frame" 스코프는 "현재 top_frame"에만 존재합니다.
    #       If 블록 내부로 들어가면 top_frame이 BLOCK으로 바뀌므로,
    #       LOOP 프레임에서 set한 frame 변수를 BLOCK 안에서 get하면 KeyError가 날 수 있습니다.
    #       그래서 반복마다 공통으로 쓰고 싶은 값(i 등)은 local에 저장해두고,
    #       frame은 "그 프레임 내부"에서만 쓰도록 예제를 구성했습니다.
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

                    # local.iteration = i  (BLOCK에서도 접근 가능)
                    {"$op": "$Set", "args": {
                        "value": {"$op": "$get", "args": {"scope": "local", "path": ["i"]}},
                        "scope": "local",
                        "path": ["iteration"],
                    }},

                    # LOOP 프레임(frame 스코프)에서만 쓰는 note/snapshot
                    {"$op": "$Set", "args": {"value": "", "scope": "frame", "path": ["note"]}},

                    # 짝수면 continue
                    {"$op": "$If", "args": {
                        "cond": {"$op": "$in", "args": {
                            "item": {"$op": "$get", "args": {"scope": "local", "path": ["i"]}},
                            "container": [2, 4, 6, 8, 10, 12, 14, 16, 18, 20],
                        }},
                        "scripts": [
                            # (BLOCK frame) frame.block_tag = "EVEN_BLOCK" 데모
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

                            # 글로벌 로그 + 출력 (local.iteration 사용)
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

                    # frame.snapshot = $dict( i, total, note )  (LOOP 프레임에서 생성/조회)
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

            # summary_list = $list([total, skipped_evens, seen_odds])
            {"$op": "$Set", "args": {
                "value": {"$op": "$list", "args": {"value": [
                    {"$op": "$get", "args": {"scope": "local", "path": ["total"]}},
                    {"$op": "$get", "args": {"scope": "local", "path": ["skipped_evens"]}},
                    {"$op": "$get", "args": {"scope": "local", "path": ["seen_odds"]}},
                ]}},
                "scope": "local",
                "path": ["summary_list"],
            }},

            # result = $dict(...)
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
# 3) Tick 기반 실행 루프
# ---------------------------------------------------------------------------

def run_case(user_name: str, mode: str, n: int, threshold: int) -> None:
    engine = Interpreter(script_registry, function_registry)

    # param_keys = ["user_name", "mode", "n", "threshold"] 순서대로 params를 넣어야 합니다.
    engine.call_script("Main", [user_name, mode, n, threshold])

    ticks = 0
    while not engine.is_finished():
        ticks += 1
        engine.tick()

    print(f"--- finished (ticks={ticks}) ---")
    print("global_vars =", engine.global_vars)


if __name__ == "__main__":
    # 1) mode="A" -> ChooseMode에서 $If branch 실행
    run_case("Alice", "A", n=10, threshold=15)

    # 2) mode="B" -> ChooseMode에서 $ElseIf branch 실행
    run_case("Bob", "B", n=10, threshold=17)

    # 3) mode="Z" -> ChooseMode에서 $Else branch 실행
    run_case("Charlie", "Z", n=10, threshold=12)

    # 4) mode="STOP" -> MaybeEarlyReturn이 조건부 return (early) 실행
    run_case("Dana", "STOP", n=10, threshold=12)