import os
import logging

logger = logging.getLogger(__name__)

_tracer_provider = None

def setup_tracing():
    global _tracer_provider
    if _tracer_provider is not None:
        return _tracer_provider

    space_id = os.getenv("ARIZE_SPACE_ID")
    api_key = os.getenv("ARIZE_API_KEY")
    project_name = os.getenv("ARIZE_PROJECT_NAME", "policy-agent")

    if not space_id or not api_key:
        logger.warning("ARIZE_SPACE_ID and ARIZE_API_KEY not set — Arize tracing disabled")
        return None

    try:
        from arize.otel import register
        from openinference.instrumentation.langchain import LangChainInstrumentor

        tracer_provider = register(
            space_id=space_id,
            api_key=api_key,
            project_name=project_name,
        )

        LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
        _tracer_provider = tracer_provider
        logger.info("Arize AX tracing initialized for project=%s", project_name)
        return tracer_provider
    except Exception as e:
        logger.warning("Failed to initialize Arize tracing: %s", e)
        return None


def get_tracer_provider():
    return _tracer_provider
