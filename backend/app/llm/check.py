"""Check the Anthropic API key and model access without spending credits.

Retrieving model metadata is free (no tokens are generated), so this confirms the key works and
the configured model is available.  Run:  uv run python -m app.llm.check
"""

import sys

import anthropic

from app.config import get_settings


def main() -> int:
    settings = get_settings()
    if not settings.anthropic_api_key:
        print("No ANTHROPIC_API_KEY found. Add it to backend/.env and try again.")
        return 1
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=1, timeout=15.0)
    try:
        model = client.models.retrieve(settings.llm_model)
    except anthropic.AuthenticationError:
        print("The API key was rejected. Check it was copied in full, then try again.")
        return 1
    except anthropic.PermissionDeniedError:
        print(f"The key works but doesn't have access to {settings.llm_model}.")
        return 1
    except anthropic.NotFoundError:
        print(f"Model {settings.llm_model} wasn't found. Check the model name in settings.")
        return 1
    except anthropic.APIConnectionError:
        print("Couldn't reach the Anthropic API. Check your internet connection.")
        return 1
    print(f"OK: key accepted, {model.display_name} ({model.id}) is available. No credits used.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
