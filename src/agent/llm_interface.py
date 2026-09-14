import os
import json
from abc import ABC, abstractmethod
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send a prompt, return the model's text response."""
        raise NotImplementedError


class GroqProvider(LLMProvider):

    def __init__(self, model: str = "openai/gpt-oss-120b"):
        try:
            from groq import Groq
        except ImportError as e:
            raise ImportError("Run: pip install groq") from e

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError("GROQ_API_KEY not set in .env")

        self.client = Groq(api_key=api_key)
        self.model = model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,  
        )
        return response.choices[0].message.content


class GeminiProvider(LLMProvider):

    def __init__(self, model: str = "gemini-2.0-flash"):
        try:
            import google.generativeai as genai
        except ImportError as e:
            raise ImportError("Run: pip install google-generativeai") from e

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY not set in .env")

        genai.configure(api_key=api_key)
        self.genai = genai
        self.model_name = model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        model = self.genai.GenerativeModel(self.model_name, system_instruction=system_prompt)
        response = model.generate_content(user_prompt)
        return response.text


def get_llm_provider() -> LLMProvider:
   
    provider_name = os.environ.get("LLM_PROVIDER", "groq").lower()
    if provider_name == "groq":
        return GroqProvider()
    elif provider_name == "gemini":
        return GeminiProvider()
    else:
        raise ValueError(f"Unknown LLM_PROVIDER '{provider_name}' -- expected 'groq' or 'gemini'")


if __name__ == "__main__":
    provider = get_llm_provider()
    result = provider.complete(
        system_prompt="You are a helpful assistant. Answer in one short sentence.",
        user_prompt="What is 2+2?",
    )
    print("LLM response:", result)