import json
import logging
import re
from typing import Protocol
from pydantic import ValidationError
import openai

from app.ai.contracts import RecoveryDecisionContext, RecoveryDecision
from app.ai.exceptions import AIDecisionError
from app.config.settings import AI_BASE_URL, AI_MODEL, AI_API_KEY, AI_TIMEOUT

logger = logging.getLogger(__name__)

class RecoveryDecisionProvider(Protocol):
    def decide(self, context: RecoveryDecisionContext) -> RecoveryDecision:
        ...

class NemotronProvider(RecoveryDecisionProvider):
    def __init__(self):
        self.client = openai.OpenAI(
            api_key=AI_API_KEY,
            base_url=AI_BASE_URL,
            timeout=AI_TIMEOUT
        )
        self.model = AI_MODEL

    def _extract_json(self, content: str) -> str:
        content = content.strip()
        # If it natively parses, great
        if content.startswith("{") and content.endswith("}"):
            return content
            
        # Try to find a markdown JSON block
        matches = re.findall(r"`(?:json)?\s*(\{.*?\})\s*`", content, re.DOTALL)
        if len(matches) == 1:
            return matches[0]
        
        if len(matches) > 1:
            raise AIDecisionError("Multiple JSON objects returned, ambiguous response")
            
        # Fallback to finding outermost brackets
        # re.DOTALL makes . match newlines
        matches = re.findall(r"(\{.*?\})", content, re.DOTALL)
        if len(matches) == 1:
            return matches[0]
            
        if len(matches) > 1:
            raise AIDecisionError("Multiple JSON objects returned, ambiguous response")
            
        raise AIDecisionError("No valid JSON object found in response")

    def decide(self, context: RecoveryDecisionContext) -> RecoveryDecision:
        try:
            system_prompt = (
                "You are an AI recovery decision engine. Analyze the context and return a JSON object. "
                "The 'action' MUST be one of 'CHARGE', 'ABORT', or 'DELAY'. "
                "Provide a brief 'reason', and a 'confidence' score between 0.0 and 1.0. "
                "Return ONLY valid JSON. Absolutely no markdown or preamble."
            )
            user_prompt = context.model_dump_json()

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            if not content:
                raise AIDecisionError("Empty response from Nemotron provider")
            
            json_str = self._extract_json(content)
            
            return RecoveryDecision.model_validate_json(json_str)
            
        except ValidationError as e:
            raise AIDecisionError(f"Invalid structured output: {str(e)}")
        except openai.OpenAIError as e:
            raise AIDecisionError(f"Provider error: {str(e)}")
        except Exception as e:
            if isinstance(e, AIDecisionError):
                raise
            raise AIDecisionError(f"Unexpected AI failure: {str(e)}")
