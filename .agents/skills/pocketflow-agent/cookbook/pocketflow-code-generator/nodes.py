from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator
from utils.call_llm import get_instructor_client
from utils.code_executor import execute_python

from pocketflow import BatchNode, Node, StructuredNode


class TestCaseSchema(BaseModel):
    name: str = Field(description="Name of the test case")
    input: Dict[str, Any] = Field(
        description="Dictionary of input parameters and their values"
    )
    expected: Any = Field(description="Expected output of the function")


class GenerateTestCasesSchema(BaseModel):
    reasoning: str = Field(description="Reasoning process for generating test cases")
    test_cases: List[TestCaseSchema] = Field(description="List of generated test cases")


class ImplementFunctionSchema(BaseModel):
    reasoning: str = Field(
        description="Reasoning process for implementing the function"
    )
    function_code: str = Field(
        description="Python function code, must be named 'run_code'"
    )

    @field_validator("function_code")
    @classmethod
    def validate_function_name(cls, v: str) -> str:
        if "def run_code" not in v:
            raise ValueError("Function must be named 'run_code'")
        return v


class ReviseSchema(BaseModel):
    reasoning: str = Field(
        description="Reasoning process for revising the test cases and/or function code"
    )
    test_cases: Optional[Dict[str, TestCaseSchema]] = Field(
        default=None,
        description="Dictionary mapping 1-based test case index (as string) to revised test case",
    )
    function_code: Optional[str] = Field(
        default=None,
        description="Revised Python function code, must be named 'run_code'",
    )

    @field_validator("function_code")
    @classmethod
    def validate_function_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and "def run_code" not in v:
            raise ValueError("Function must be named 'run_code'")
        return v


class GenerateTestCases(StructuredNode):
    def __init__(self):
        super().__init__(
            response_model=GenerateTestCasesSchema,
            client=get_instructor_client(),
            model="claude-sonnet-4-20250514",
        )

    def prep(self, shared):
        return shared["problem"]

    def post(self, shared, prep_res, exec_res):
        result = exec_res.model_dump()
        shared["test_cases"] = result["test_cases"]

        # Print all generated test cases
        print(f"\n=== Generated {len(result['test_cases'])} Test Cases ===")
        for i, test_case in enumerate(result["test_cases"], 1):
            print(f"{i}. {test_case['name']}")
            print(f"   input: {test_case['input']}")
            print(f"   expected: {test_case['expected']}")


class ImplementFunction(StructuredNode):
    def __init__(self):
        super().__init__(
            response_model=ImplementFunctionSchema,
            client=get_instructor_client(),
            model="claude-sonnet-4-20250514",
        )

    def prep(self, shared):
        problem = shared["problem"]
        test_cases = shared["test_cases"]

        # Format test cases nicely for the prompt
        formatted_tests = ""
        for i, test in enumerate(test_cases, 1):
            formatted_tests += f"{i}. {test['name']}\n"
            formatted_tests += f"   input: {test['input']}\n"
            formatted_tests += f"   expected: {test['expected']}\n\n"

        prompt = f"""Implement a solution for this problem:

{problem}

Test cases to consider:
{formatted_tests}

IMPORTANT: The function name must be exactly "run_code"
"""
        return prompt

    def post(self, shared, prep_res, exec_res):
        result = exec_res.model_dump()
        shared["function_code"] = result["function_code"]

        # Print the implemented function
        print(f"\n=== Implemented Function ===")
        print(result["function_code"])


class RunTests(BatchNode):
    def prep(self, shared):
        function_code = shared["function_code"]
        test_cases = shared["test_cases"]
        # Return list of tuples (function_code, test_case)
        return [(function_code, test_case) for test_case in test_cases]

    def exec(self, test_data):
        function_code, test_case = test_data
        output, error = execute_python(function_code, test_case["input"])

        if error:
            return {
                "test_case": test_case,
                "passed": False,
                "actual": None,
                "expected": test_case["expected"],
                "error": error,
            }

        passed = output == test_case["expected"]
        return {
            "test_case": test_case,
            "passed": passed,
            "actual": output,
            "expected": test_case["expected"],
            "error": None
            if passed
            else f"Expected {test_case['expected']}, got {output}",
        }

    def post(self, shared, prep_res, exec_res_list):
        shared["test_results"] = exec_res_list
        all_passed = all(result["passed"] for result in exec_res_list)
        shared["iteration_count"] = shared.get("iteration_count", 0) + 1

        # Print test results
        passed_count = len([r for r in exec_res_list if r["passed"]])
        total_count = len(exec_res_list)
        print(f"\n=== Test Results: {passed_count}/{total_count} Passed ===")

        failed_tests = [r for r in exec_res_list if not r["passed"]]
        if failed_tests:
            print("Failed tests:")
            for i, result in enumerate(failed_tests, 1):
                test_case = result["test_case"]
                print(f"{i}. {test_case['name']}:")
                if result["error"]:
                    print(f"   error: {result['error']}")
                else:
                    print(f"   output: {result['actual']}")
                print(f"   expected: {result['expected']}")

        if all_passed:
            return "success"
        elif shared["iteration_count"] >= shared.get("max_iterations", 5):
            return "max_iterations"
        else:
            return "failure"


class Revise(StructuredNode):
    def __init__(self):
        super().__init__(
            response_model=ReviseSchema,
            client=get_instructor_client(),
            model="claude-sonnet-4-20250514",
        )

    def prep(self, shared):
        failed_tests = [r for r in shared["test_results"] if not r["passed"]]
        problem = shared["problem"]
        test_cases = shared["test_cases"]
        function_code = shared["function_code"]

        # Format current test cases nicely
        formatted_tests = ""
        for i, test in enumerate(test_cases, 1):
            formatted_tests += f"{i}. {test['name']}\n"
            formatted_tests += f"   input: {test['input']}\n"
            formatted_tests += f"   expected: {test['expected']}\n\n"

        # Format failed tests nicely
        formatted_failures = ""
        for i, result in enumerate(failed_tests, 1):
            test_case = result["test_case"]
            formatted_failures += f"{i}. {test_case['name']}:\n"
            if result["error"]:
                formatted_failures += f"   error: {result['error']}\n"
            else:
                formatted_failures += f"   output: {result['actual']}\n"
            formatted_failures += f"   expected: {result['expected']}\n\n"

        prompt = f"""Problem: {problem}

Current test cases:
{formatted_tests}

Current function:
```python
{function_code}
```

Failed tests:
{formatted_failures}

Analyze the failures and output revisions. You can revise test cases, function code, or both.
"""
        return prompt

    def post(self, shared, prep_res, exec_res):
        result = exec_res.model_dump()
        # Print what is being revised
        print(f"\n=== Revisions (Iteration {shared['iteration_count']}) ===")

        # Handle test case revisions - map indices to actual test cases
        if result.get("test_cases"):
            current_tests = shared["test_cases"].copy()
            print("Revising test cases:")
            for index_str, revised_test in result["test_cases"].items():
                index = int(index_str) - 1  # Convert to 0-based
                if 0 <= index < len(current_tests):
                    old_test = current_tests[index]
                    print(
                        f"  Test {index_str}: '{old_test['name']}' -> '{revised_test['name']}'"
                    )
                    print(f"    old input: {old_test['input']}")
                    print(f"    new input: {revised_test['input']}")
                    print(f"    old expected: {old_test['expected']}")
                    print(f"    new expected: {revised_test['expected']}")
                    current_tests[index] = revised_test
            shared["test_cases"] = current_tests

        if result.get("function_code"):
            print("Revising function code:")
            print("New function:")
            print(result["function_code"])
            shared["function_code"] = result["function_code"]
