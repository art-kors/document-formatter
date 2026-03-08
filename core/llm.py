import os
from typing import List, Dict, Optional, Generator
from mistralai import Mistral
from mistralai.exceptions import MistralException


class MistralLLM:
    def __init__(
            self,
            api_key: Optional[str] = None,
            model: str = "mistral-small-latest",
            temperature: float = 0.7,
            max_tokens: Optional[int] = None,
            system_prompt: Optional[str] = None
    ):
        """
        Initialize the Mistral LLM Client.

        Args:
            api_key: Your Mistral API Key. If None, looks for MISTRAL_API_KEY env var.
            model: The model ID to use (e.g., mistral-small-latest).
            temperature: Controls randomness (0.0 to 1.0).
            max_tokens: Maximum tokens in the response.
            system_prompt: Optional system instruction to set behavior.
        """
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")
        if not self.api_key:
            raise ValueError("Mistral API Key not found. Set it via argument or MISTRAL_API_KEY env var.")

        self.client = Mistral(api_key=self.api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Initialize conversation history
        self.history: List[Dict[str, str]] = []

        if system_prompt:
            self.history.append({"role": "system", "content": system_prompt})

    def reset_history(self):
        """Clears conversation history but keeps system prompt if it existed."""
        if self.history and self.history[0].get("role") == "system":
            self.history = [self.history[0]]
        else:
            self.history = []

    def chat(self, message: str, save_history: bool = True) -> str:
        """
        Send a message and get a response (Blocking).

        Args:
            message: The user's input message.
            save_history: Whether to add this exchange to the conversation history.

        Returns:
            The assistant's response string.
        """
        # Add user message to temporary payload
        messages_payload = self.history + [{"role": "user", "content": message}]

        try:
            response = self.client.chat.complete(
                model=self.model,
                messages=messages_payload,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            content = response.choices[0].message.content

            # Update history if requested
            if save_history:
                self.history.append({"role": "user", "content": message})
                self.history.append({"role": "assistant", "content": content})

            return content

        except MistralException as e:
            return f"Error: {str(e)}"

    def stream(self, message: str, save_history: bool = True) -> Generator[str, None, None]:
        """
        Stream a response token by token.

        Args:
            message: The user's input message.
            save_history: Whether to save the full response to history after streaming.

        Yields:
            Chunks of text as they are generated.
        """
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

            # Update history after stream completes
            if save_history:
                self.history.append({"role": "user", "content": message})
                self.history.append({"role": "assistant", "content": full_response})

        except MistralException as e:
            yield f"\nError: {str(e)}"

    def __call__(self, message: str) -> str:
        """Allows the instance to be called like a function: llm('hello')"""
        return self.chat(message)

    def get_history(self) -> List[Dict[str, str]]:
        """Return the current conversation history."""
        return self.history