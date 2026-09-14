import sys
import os
import json

sys.path.insert(0, os.path.dirname(__file__))
from tools import TOOL_SCHEMAS, TOOL_FUNCTIONS
from llm_interface import get_llm_provider

try:
    from groq import Groq
    from dotenv import load_dotenv
    load_dotenv()
except ImportError as e:
    raise ImportError("Run: pip install groq python-dotenv") from e

SYSTEM_PROMPT = """You are a business analytics assistant for an Indian retail company. You have access to tools that query REAL, VERIFIED data -- never answer with numbers you weren't given by a tool call. If a question needs data you don't have (e.g. asking about a date range or dimension no tool call returned), say so rather than guessing.

The data covers 2019-01-01 to 2023-12-31. There is no "today" -- if asked about "this week" or "recent" performance, ask the user to clarify a date, or use the most recent available date (2023-12-31) and say so explicitly.

When asked a general question like "what's wrong" or "what are the anomalies", start with tool_list_known_anomalies before drilling into specifics with other tools.

Always cite the specific numbers your tools returned. Clearly separate what the data shows (fact) from your own reasoning about why it might have happened (label this as your hypothesis, not fact)."""


def ask(question: str, max_tool_rounds: int = 5, model: str = "openai/gpt-oss-120b") -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY not set in .env")
    client = Groq(api_key=api_key)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    for round_num in range(max_tool_rounds):
        response = client.chat.completions.create(
            model=model, messages=messages, tools=TOOL_SCHEMAS, tool_choice="auto", temperature=0.2,
        )
        message = response.choices[0].message

        if not message.tool_calls:
            return message.content  

        messages.append({"role": "assistant", "content": message.content, "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in message.tool_calls
        ]})

        for tool_call in message.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments)
            fn_args = {k: v for k, v in fn_args.items() if v is not None}  # drop explicit nulls, let our functions' own defaults apply
            print(f"  [tool call] {fn_name}({fn_args})")

            if fn_name not in TOOL_FUNCTIONS:
                result = {"error": f"Unknown tool '{fn_name}'"}
            else:
                try:
                    result = TOOL_FUNCTIONS[fn_name](**fn_args)
                except Exception as e:
                    result = {"error": str(e)}

            messages.append({
                "role": "tool", "tool_call_id": tool_call.id,
                "content": json.dumps(result, default=str),
            })

    return "Reached max tool-calling rounds without a final answer -- something may be looping."


if __name__ == "__main__":
    questions = [
        "What are the current anomalies in the business?",
        "Why did profit fall in North during September 2021?",
        "Which region is responsible for the revenue decline in June 2022?",
        "How much revenue was lost during the South region issue?",
    ]

    for q in questions:
        print(f"\n{'='*70}\nQ: {q}\n{'='*70}")
        answer = ask(q)
        print(f"\nA: {answer}")