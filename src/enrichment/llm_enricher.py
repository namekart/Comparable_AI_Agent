import json
import time
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import config

class LLMEnricher:
    """Handles LLM-based enrichment of domain names"""

    def __init__(self):
        # OpenRouter's `models` list falls through to the next model if one
        # fails; other providers don't understand it.
        extra = {}
        if "openrouter.ai" in config.LLM_BASE_URL:
            extra = {"extra_body": {"models": [config.LLM_MODEL, *config.LLM_FALLBACK_MODELS]}}
        self.llm = ChatOpenAI(
            model=config.LLM_MODEL,
            temperature=0.05,
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
            timeout=120,
            model_kwargs=extra,
        )
    def enrich_domain(self, domain_name:str,prompt_template:str)-> dict:
        """
        Make a single LLM call to generate: 
        -primary_category
        -secondary_category
        - descriptions(1-2)

        Args:
         domain_name: The domain to enrich
         prompt_template: Your pre-defined prompt template

        Returns:
           dict with categories and descriptions

        """
        # Replace placeholder in your prompt
        prompt = prompt_template.replace("{domain_name}", domain_name)

        messages = [
            SystemMessage(content="You are a domain analysis expert. Return valid JSON only."),
            HumanMessage(content=prompt)
        ]

        # Free models intermittently fail (429/503, or HTTP 200 with an error
        # body and no choices, which langchain surfaces as a TypeError).
        for attempt in range(1, config.LLM_MAX_ATTEMPTS + 1):
            try:
                response = self.llm.invoke(messages)
                break
            except Exception:
                if attempt == config.LLM_MAX_ATTEMPTS:
                    raise
                time.sleep(attempt)

        # Parse JSON Response
        try:
            result = json.loads(self._clean_json(response.content))
            self._validate_result(result)
            return result

        except (json.JSONDecodeError, ValueError, TypeError, KeyError) as e:
            raise ValueError(f"Invalid LLM response format: {e}\nResponse: {response.content}")

    @staticmethod
    def _validate_result(result) -> None:
        """Validate the LLM JSON structure. Explicit raises (not assert) so the
        checks still run under `python -O` / PYTHONOPTIMIZE."""
        if not isinstance(result, dict):
            raise ValueError("response is not a JSON object")
        for key in ("primary_category", "secondary_category", "descriptions"):
            if key not in result:
                raise ValueError(f"missing key: {key}")
        if not isinstance(result["descriptions"], list):
            raise ValueError("descriptions is not a list")
        if len(result["descriptions"]) < 1:
            raise ValueError("descriptions is empty")
        if result["primary_category"] == result["secondary_category"]:
            raise ValueError("primary_category equals secondary_category")

    @staticmethod
    def _clean_json(content: str) -> str:
        """
        Tolerate common LLM formatting artifacts before json.loads:
        - ```json ... ``` / ``` ... ``` code fences
        - doubled braces {{ ... }} (some models echo the prompt's escaping)
        - leading/trailing prose around the JSON object
        Only normalizes; a clean response is returned unchanged.
        """
        if not content:
            return content
        s = content.strip()
        # strip code fences
        if s.startswith("```"):
            s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
            if s.lstrip().lower().startswith("json"):
                s = s.lstrip()[4:]
            s = s.strip()
        # slice to the outermost JSON object
        start, end = s.find("{"), s.rfind("}")
        if start != -1 and end != -1 and end > start:
            s = s[start:end + 1]
        # collapse doubled braces -> single
        if "{{" in s or "}}" in s:
            s = s.replace("{{", "{").replace("}}", "}")
        return s