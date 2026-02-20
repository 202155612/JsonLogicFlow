from interpreter import Interpreter

def print_message(*args):
    print(*args)

def subtract_num(a, b):
    return a - b

def add_num(a, b):
    return a + b

script_registry = {
    "Main": {
        "param_keys": ["start_number"],
        "steps": [
            {
                "$op": "$Invoke",
                "args": {
                    "name": "print_msg",
                    "params": ["=== 인터프리터 실행 시작 ==="]
                }
            },
            {
                "$op": "$Script",
                "args": {
                    "name": "Countdown",
                    "params": [{"$op": "$get", "args": {"scope": "kwargs", "path": ["start_number"]}}]
                }
            },
            {
                "$op": "$If",
                "args": {
                    "cond": {
                        "$op": "$eq",
                        "args": {"value": [1, 1]}
                    },
                    "scripts": [
                        {
                            "$op": "$Invoke",
                            "args": {
                                "name": "print_msg",
                                "params": ["$If 테스트 성공: 1은 1과 같습니다."]
                            }
                        }
                    ]
                }
            },
            {
                "$op": "$Invoke",
                "args": {
                    "name": "print_msg",
                    "params": ["=== 인터프리터 실행 완료 ==="]
                }
            }
        ]
    },
    
    "Countdown": {
        "param_keys": ["count"],
        "steps": [
            {
                "$op": "$Set",
                "args": {
                    "value": {"$op": "$get", "args": {"scope": "kwargs", "path": ["count"]}},
                    "scope": "local",
                    "path": ["current_count"]
                }
            },
            {
                "$op": "$While",
                "args": {
                    "cond": {
                        "$op": "$gt",
                        "args": {
                            "value": [
                                {"$op": "$get", "args": {"scope": "local", "path": ["current_count"]}},
                                0
                            ]
                        }
                    },
                    "scripts": [
                        {
                            "$op": "$Invoke",
                            "args": {
                                "name": "print_msg",
                                "params": [
                                    "카운트다운:", 
                                    {"$op": "$get", "args": {"scope": "local", "path": ["current_count"]}}
                                ]
                            }
                        },
                        {
                            "$op": "$Invoke",
                            "args": {
                                "name": "sub",
                                "params": [
                                    {"$op": "$get", "args": {"scope": "local", "path": ["current_count"]}},
                                    1
                                ],
                                "scope": "local",
                                "path": ["current_count"]
                            }
                        }
                    ]
                }
            },
            {
                "$op": "$Invoke",
                "args": {
                    "name": "print_msg",
                    "params": ["발사!"]
                }
            }
        ]
    }
}

function_registry = {
    "print_msg": print_message,
    "sub": subtract_num,
    "add": add_num
}

def main():
    engine = Interpreter(
        script_registry=script_registry, 
        function_registry=function_registry
    )
    
    print(">>> python example.py 실행됨\n")
    
    engine.execute("Main", {"start_number": 3})

if __name__ == "__main__":
    main()