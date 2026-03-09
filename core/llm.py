import os
from typing import List, Dict, Optional, Generator
from mistralai import Mistral

class MistralLLM:
    def __init__(
            self,
            api_key: Optional[str] = None,
            model: str = "mistral-small-latest",
            embedding_model: str = "mistral-embed",
            temperature: float = 0.7,
            max_tokens: Optional[int] = None,
            system_prompt: Optional[str] = None
    ):
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")
        if not self.api_key:
            raise ValueError("Mistral API Key not found.")

        self.client = Mistral(api_key=self.api_key)
        self.model = model
        self.embedding_model = embedding_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.history: List[Dict[str, str]] = []

        if system_prompt:
            self.history.append({"role": "system", "content": system_prompt})

    def reset_history(self):
        if self.history and self.history[0].get("role") == "system":
            self.history = [self.history[0]]
        else:
            self.history = []

    def chat(self, message: str, save_history: bool = True) -> str:
        messages_payload = self.history + [{"role": "user", "content": message}]
        try:
            response = self.client.chat.complete(
                model=self.model,
                messages=messages_payload,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            content = response.choices[0].message.content
            if save_history:
                self.history.append({"role": "user", "content": message})
                self.history.append({"role": "assistant", "content": content})
            return content

        except Exception as e:
            # Ловим обычное исключение, так как MistralException удален
            return f"Error: {str(e)}"

    def stream(self, message: str, save_history: bool = True) -> Generator[str, None, None]:
        messages_payload = self.history + [{"role": "user", "content": message}]
        full_response = ""
        try:
            stream = self.client.chat.stream(
                model=self.model,
                messages=messages_payload,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            for chunk in stream:
                if chunk.data.choices[0].delta.content:
                    text = chunk.data.choices[0].delta.content
                    full_response += text
                    yield text
            if save_history:
                self.history.append({"role": "user", "content": message})
                self.history.append({"role": "assistant", "content": full_response})

        except Exception as e:
            yield f"\nError: {str(e)}"

    def get_embedding(self, text: str) -> List[float]:
        try:
            response = self.client.embeddings.create(
                model=self.embedding_model,
                inputs=[text]
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Embedding error: {e}")
            return []

    def __call__(self, message: str) -> str:
        return self.chat(message)

    def get_history(self) -> List[Dict[str, str]]:
        return self.history