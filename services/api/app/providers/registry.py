from app.errors import AppError
from app.providers.langchain import LangChainProvider

# Only adapters backed by a provider API this repository fully implements
# belong here. Dify and Sim were removed because their APIs cannot be
# configured end to end from this control plane.
_ADAPTERS = {"langchain": LangChainProvider()}


def get_adapter(name: str):
    adapter = _ADAPTERS.get(name)
    if not adapter:
        raise AppError(
            "unsupported_provider",
            f"Provider '{name}' is not supported. Configure an OpenAI-compatible model connection.",
            400,
        )
    return adapter
