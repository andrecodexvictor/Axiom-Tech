import os
import requests
from typing import List, Dict, Any
from app.config import settings

class UnifiedNVIDIAClient:
    """
    Unified LLM Client managing 3-tier NVIDIA NIM API models:
    1. Kimi K2.6 (moonshotai/kimi-k2.6) for Supervisor Reasoning
    2. MiniMax M3 (minimaxai/minimax-m3) for Domain Specialist Inferences
    3. DeepSeek V4 Pro (deepseek-ai/deepseek-v4-pro) for RAG Deep Search & Evaluation
    """

    def __init__(self):
        self.kimi_key = settings.KIMI_API_KEY
        self.minimax_key = settings.MINIMAX_API_KEY
        self.deepseek_key = settings.DEEPSEEK_API_KEY

    def invoke_kimi(self, prompt: str, system_prompt: str = "") -> str:
        """
        Invokes Moonshot AI Kimi K2.6 for reasoning & supervisor classification.
        """
        try:
            from langchain_nvidia_ai_endpoints import ChatNVIDIA
            client = ChatNVIDIA(
                model="moonshotai/kimi-k2.6",
                api_key=self.kimi_key,
                temperature=1,
                top_p=1,
                max_completion_tokens=16384
            )
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.invoke(messages)
            return str(response.content)
        except Exception as e:
            print(f"[Kimi K2.6 Fallback Warning]: {e}")
            return self._fallback_response("Kimi K2.6", prompt)

    def invoke_minimax(self, prompt: str, system_prompt: str = "") -> str:
        """
        Invokes MiniMax M3 via NVIDIA Chat Completions API endpoint.
        """
        try:
            invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.minimax_key}",
                "Accept": "application/json"
            }
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": "minimaxai/minimax-m3",
                "messages": messages,
                "temperature": 1,
                "top_p": 0.95,
                "max_tokens": 8192,
                "stream": False
            }
            resp = requests.post(invoke_url, headers=headers, json=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            else:
                raise ValueError(f"Status {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"[MiniMax M3 Fallback Warning]: {e}")
            return self._fallback_response("MiniMax M3", prompt)

    def invoke_deepseek_rag(self, prompt: str, context_docs: str = "") -> str:
        """
        Invokes DeepSeek V4 Pro via OpenAI client for RAG Deep Search & Document Synthesis.
        """
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=self.deepseek_key
            )
            full_prompt = f"Retrieved Context Documents:\n{context_docs}\n\nUser Question:\n{prompt}"
            
            completion = client.chat.completions.create(
                model="deepseek-ai/deepseek-v4-pro",
                messages=[
                    {"role": "system", "content": "You are Axiom Tech's Grounded RAG Synthesizer powered by DeepSeek V4 Pro. Provide precise answers strictly citing the provided documents."},
                    {"role": "user", "content": full_prompt}
                ],
                temperature=1,
                top_p=0.95,
                max_tokens=16384,
                extra_body={"chat_template_kwargs": {"thinking": False}},
                stream=False
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"[DeepSeek V4 Pro Fallback Warning]: {e}")
            return self._fallback_response("DeepSeek V4 Pro", prompt)

    def _fallback_response(self, model_name: str, prompt: str) -> str:
        return f"[{model_name} Response] Processed query: '{prompt[:60]}...'"

nvidia_client = UnifiedNVIDIAClient()
