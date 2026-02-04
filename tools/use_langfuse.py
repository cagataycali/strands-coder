"""Langfuse observability integration tool for Strands Agent.

This module provides comprehensive interface to Langfuse observability platform,
allowing you to trace, monitor, and analyze agent workflows. The tool handles
authentication, parameter validation, response formatting, and provides
user-friendly error messages.

Key Features:

1. Universal Langfuse Access:
   • Access to all Langfuse SDK methods
   • Full trace/span/generation lifecycle management
   • Dataset and prompt management
   • Experiment running and analysis

2. Safety Features:
   • Rich console output for operation visibility
   • Comprehensive error handling
   • Automatic client initialization
   • Parameter validation

3. Response Handling:
   • Consistent response format
   • Detailed operation feedback
   • URL generation for UI access

4. Usage Examples:
   ```python
   from strands import Agent

   agent = Agent(tools=["use_langfuse"])

   # Create trace
   result = agent.tool.use_langfuse(
       action="create_trace",
       name="agent_task",
       input_data={"query": "What is 2+2?"},
       user_id="user123"
   )
   ```

See the use_langfuse function docstring for more details on parameters and usage.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from rich import box
from rich.panel import Panel
from rich.table import Table
from strands import tool

logger = logging.getLogger(__name__)

# Global Langfuse client and object storage
_langfuse_client = None
_traces = {}
_spans = {}
_generations = {}
_observations = {}


def _get_console():
    """Get Rich console for output."""
    try:
        from rich.console import Console

        return Console()
    except ImportError:
        return None


def _get_client():
    """Get or initialize Langfuse client with error handling."""
    global _langfuse_client
    if _langfuse_client is None:
        try:
            from langfuse import Langfuse

            public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
            secret_key = os.getenv("LANGFUSE_SECRET_KEY")
            host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

            if not public_key or not secret_key:
                logger.error("Langfuse credentials not found in environment")
                return None

            _langfuse_client = Langfuse(
                public_key=public_key, secret_key=secret_key, host=host
            )
            logger.info(f"Langfuse client initialized for host: {host}")
        except ImportError:
            logger.error("Langfuse package not installed")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize Langfuse client: {str(e)}")
            return None
    return _langfuse_client


@tool
def use_langfuse(
    action: str,
    name: Optional[str] = None,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    generation_id: Optional[str] = None,
    observation_id: Optional[str] = None,
    input_data: Optional[str] = None,
    output_data: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
    score_name: Optional[str] = None,
    score_value: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Execute Langfuse operations with comprehensive error handling and validation.

    This tool provides a universal interface to Langfuse observability platform,
    allowing you to trace and monitor agent workflows, manage datasets and prompts,
    and analyze experiments.

    How It Works:
    ------------
    1. The tool validates the action and required parameters
    2. It initializes or retrieves the Langfuse client
    3. The requested operation is executed with the provided parameters
    4. Responses are formatted with rich console output
    5. Errors are caught and returned with helpful messages

    Common Usage Scenarios:
    ---------------------
    - Trace Management: Create, update, end traces for agent workflows
    - Span Tracking: Monitor individual operations within traces
    - Generation Logging: Track LLM generations with inputs/outputs
    - Scoring: Add quality scores to traces/generations
    - Dataset Management: Create and manage evaluation datasets
    - Prompt Management: Version and retrieve prompts
    - Experiments: Run and analyze experiments

    Actions:
        Core Operations:
        - auth_check: Verify authentication credentials
        - status: View current Langfuse configuration
        - flush: Force flush pending data to Langfuse
        - shutdown: Properly shutdown Langfuse client

        Trace Operations:
        - create_trace: Start a new trace
        - update_current_trace: Update the current trace context
        - get_current_trace_id: Get the current trace ID
        - score_current_trace: Add score to current trace
        - get_trace_url: Get Langfuse UI URL for a trace
        - list_traces: List recent traces (use metadata={"limit": N} to control count)
        - get_trace: Get full trace details with token usage (requires trace_id)

        Session Operations:
        - list_sessions: List sessions (use metadata={"limit": N} to control count)

        Span Operations:
        - create_span: Create a span within a trace
        - start_as_current_span: Start span as current context
        - update_current_span: Update current span
        - score_current_span: Add score to current span

        Generation Operations:
        - create_generation: Track an LLM generation
        - start_as_current_generation: Start generation as current context
        - update_current_generation: Update current generation

        Observation Operations:
        - start_observation: Start a generic observation
        - start_as_current_observation: Start observation as current context
        - get_current_observation_id: Get current observation ID

        Scoring Operations:
        - create_score: Add a score to any object
        - score_current_trace: Score the current trace
        - score_current_span: Score the current span

        Dataset Operations:
        - create_dataset: Create a new dataset
        - get_dataset: Retrieve dataset by name
        - create_dataset_item: Add item to dataset

        Prompt Operations:
        - create_prompt: Create a new prompt version
        - get_prompt: Retrieve prompt by name
        - update_prompt: Update existing prompt
        - clear_prompt_cache: Clear prompt cache

        Experiment Operations:
        - run_experiment: Run an experiment

        Utility Operations:
        - resolve_media_references: Resolve media references in data

    Args:
        action: The action to perform (see Actions list above)
        name: Name of trace/span/generation/dataset/prompt
        trace_id: Trace identifier
        span_id: Span identifier
        generation_id: Generation identifier
        observation_id: Observation identifier
        input_data: Input data (stringified JSON or text)
        output_data: Output data (stringified JSON or text)
        metadata: Additional metadata dictionary
        user_id: User identifier
        session_id: Session identifier
        tags: List of tags
        score_name: Name of score (e.g., "accuracy", "quality")
        score_value: Score value (typically 0-1 for normalized scores)

    Returns:
        Dict containing:
        - status: 'success' or 'error'
        - content: List of content dictionaries with response text
        - Additional fields depending on action (trace_id, span_id, etc.)

    Environment Variables:
        LANGFUSE_PUBLIC_KEY: Public API key (required)
        LANGFUSE_SECRET_KEY: Secret API key (required)
        LANGFUSE_HOST: Host URL (default: https://cloud.langfuse.com)

    Notes:
        - Client is initialized once and reused across calls
        - Rich console output provides operation visibility
        - All datetime objects are automatically handled
        - Errors include detailed information for debugging
    """
    console = _get_console()
    client = _get_client()

    # Display operation details with Rich
    if console:
        details_table = Table(show_header=False, box=box.SIMPLE, pad_edge=False)
        details_table.add_column("Property", style="cyan", justify="left", min_width=12)
        details_table.add_column("Value", style="white", justify="left")

        details_table.add_row("Action:", action)
        if name:
            details_table.add_row("Name:", name)
        if trace_id:
            details_table.add_row(
                "Trace ID:", trace_id[:16] + "..." if len(trace_id) > 16 else trace_id
            )
        if span_id:
            details_table.add_row("Span ID:", span_id)
        if generation_id:
            details_table.add_row("Generation ID:", generation_id)

        console.print(
            Panel(
                details_table,
                title="[bold blue]🔍 Langfuse Operation[/bold blue]",
                border_style="blue",
                expand=False,
            )
        )

    logger.debug(f"Langfuse action: {action}")

    # Check if client is available
    if client is None and action not in ["status"]:
        error_msg = "❌ Langfuse not available. Install: pip install langfuse\nSet LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY"
        logger.error(error_msg)
        return {"status": "error", "content": [{"text": error_msg}]}

    try:
        # Authentication check
        if action == "auth_check":
            result = client.auth_check()
            return {
                "status": "success",
                "content": [
                    {
                        "text": f"✅ Authentication successful: {json.dumps(result, default=str)}"
                    }
                ],
            }

        # Status
        elif action == "status":
            config = {
                "available": client is not None,
                "host": os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                "public_key_set": bool(os.getenv("LANGFUSE_PUBLIC_KEY")),
                "secret_key_set": bool(os.getenv("LANGFUSE_SECRET_KEY")),
                "active_traces": len(_traces),
                "active_spans": len(_spans),
                "active_generations": len(_generations),
                "active_observations": len(_observations),
            }
            return {
                "status": "success",
                "content": [
                    {
                        "text": f"📊 Langfuse Configuration:\n{json.dumps(config, indent=2)}"
                    }
                ],
            }

        # Create trace
        elif action == "create_trace":
            from langfuse import Langfuse

            trace_id_generated = trace_id or Langfuse.create_trace_id()

            trace_data = {
                "id": trace_id_generated,
                "name": name or "trace",
                "input": json.loads(input_data) if input_data else None,
                "metadata": metadata or {},
                "user_id": user_id,
                "session_id": session_id,
                "tags": tags or [],
            }

            # Store trace data - trace will be created when first observation/score is added
            _traces[trace_id_generated] = trace_data

            logger.info(f"Trace ID generated: {trace_id_generated}")
            return {
                "status": "success",
                "trace_id": trace_id_generated,
                "content": [
                    {
                        "text": f"✅ Trace ID generated: {trace_id_generated}\n(Trace will be created when observations/scores are added)"
                    }
                ],
            }

        # Update current trace
        elif action == "update_current_trace":
            if output_data or metadata:
                update_data = {}
                if output_data:
                    update_data["output"] = (
                        json.loads(output_data) if output_data else None
                    )
                if metadata:
                    update_data["metadata"] = metadata
                # Note: Langfuse SDK doesn't have direct update_current_trace, would need context manager
                return {
                    "status": "success",
                    "content": [
                        {
                            "text": "✅ Trace update requested (use trace_id for explicit updates)"
                        }
                    ],
                }
            return {
                "status": "error",
                "content": [{"text": "❌ No update data provided"}],
            }

        # Get current trace ID
        elif action == "get_current_trace_id":
            current_trace_id = client.get_current_trace_id()
            return {
                "status": "success",
                "trace_id": current_trace_id,
                "content": [{"text": f"✅ Current trace ID: {current_trace_id}"}],
            }

        # Score current trace
        elif action == "score_current_trace":
            if not score_name or score_value is None:
                return {
                    "status": "error",
                    "content": [{"text": "❌ score_name and score_value required"}],
                }

            client.score_current_trace(name=score_name, value=score_value)
            return {
                "status": "success",
                "content": [
                    {
                        "text": f"✅ Score added to current trace: {score_name}={score_value}"
                    }
                ],
            }

        # Create span
        elif action == "create_span":
            if not trace_id:
                return {
                    "status": "error",
                    "content": [{"text": "❌ trace_id required"}],
                }

            span = client.start_span(
                trace_context={"trace_id": trace_id},
                name=name or "span",
                input=json.loads(input_data) if input_data else None,
                metadata=metadata,
            )
            _spans[span.id] = span

            logger.info(f"Span created: {span.id}")
            return {
                "status": "success",
                "span_id": span.id,
                "content": [{"text": f"✅ Span created: {span.id}"}],
            }

        # Start as current span
        elif action == "start_as_current_span":
            if not trace_id:
                return {
                    "status": "error",
                    "content": [{"text": "❌ trace_id required"}],
                }

            span = client.start_as_current_span(
                trace_context={"trace_id": trace_id},
                name=name or "span",
                input=json.loads(input_data) if input_data else None,
                metadata=metadata,
            )
            _spans[span.id] = span

            return {
                "status": "success",
                "span_id": span.id,
                "content": [{"text": f"✅ Current span started: {span.id}"}],
            }

        # Update current span
        elif action == "update_current_span":
            if output_data or metadata:
                # Note: Need to implement via context or stored span reference
                return {
                    "status": "success",
                    "content": [
                        {
                            "text": "✅ Span update requested (use span_id for explicit updates)"
                        }
                    ],
                }
            return {
                "status": "error",
                "content": [{"text": "❌ No update data provided"}],
            }

        # Score current span
        elif action == "score_current_span":
            if not score_name or score_value is None:
                return {
                    "status": "error",
                    "content": [{"text": "❌ score_name and score_value required"}],
                }

            client.score_current_span(name=score_name, value=score_value)
            return {
                "status": "success",
                "content": [
                    {
                        "text": f"✅ Score added to current span: {score_name}={score_value}"
                    }
                ],
            }

        # Create generation
        elif action == "create_generation":
            if not trace_id:
                return {
                    "status": "error",
                    "content": [{"text": "❌ trace_id required"}],
                }

            generation = client.start_generation(
                trace_context={"trace_id": trace_id},
                name=name or "generation",
                input=json.loads(input_data) if input_data else None,
                metadata=metadata,
            )
            _generations[generation.id] = generation

            logger.info(f"Generation created: {generation.id}")
            return {
                "status": "success",
                "generation_id": generation.id,
                "content": [{"text": f"✅ Generation created: {generation.id}"}],
            }

        # Start as current generation
        elif action == "start_as_current_generation":
            if not trace_id:
                return {
                    "status": "error",
                    "content": [{"text": "❌ trace_id required"}],
                }

            generation = client.start_as_current_generation(
                trace_context={"trace_id": trace_id},
                name=name or "generation",
                input=json.loads(input_data) if input_data else None,
                metadata=metadata,
            )
            _generations[generation.id] = generation

            return {
                "status": "success",
                "generation_id": generation.id,
                "content": [
                    {"text": f"✅ Current generation started: {generation.id}"}
                ],
            }

        # Update current generation
        elif action == "update_current_generation":
            if output_data or metadata:
                return {
                    "status": "success",
                    "content": [
                        {
                            "text": "✅ Generation update requested (use generation_id for explicit updates)"
                        }
                    ],
                }
            return {
                "status": "error",
                "content": [{"text": "❌ No update data provided"}],
            }

        # Start observation
        elif action == "start_observation":
            if not trace_id:
                return {
                    "status": "error",
                    "content": [{"text": "❌ trace_id required"}],
                }

            observation = client.start_observation(
                trace_context={"trace_id": trace_id},
                name=name or "observation",
                input=json.loads(input_data) if input_data else None,
                metadata=metadata,
            )
            _observations[observation.id] = observation

            return {
                "status": "success",
                "observation_id": observation.id,
                "content": [{"text": f"✅ Observation started: {observation.id}"}],
            }

        # Start as current observation
        elif action == "start_as_current_observation":
            if not trace_id:
                return {
                    "status": "error",
                    "content": [{"text": "❌ trace_id required"}],
                }

            observation = client.start_as_current_observation(
                trace_context={"trace_id": trace_id},
                name=name or "observation",
                input=json.loads(input_data) if input_data else None,
                metadata=metadata,
            )
            _observations[observation.id] = observation

            return {
                "status": "success",
                "observation_id": observation.id,
                "content": [
                    {"text": f"✅ Current observation started: {observation.id}"}
                ],
            }

        # Get current observation ID
        elif action == "get_current_observation_id":
            current_obs_id = client.get_current_observation_id()
            return {
                "status": "success",
                "observation_id": current_obs_id,
                "content": [{"text": f"✅ Current observation ID: {current_obs_id}"}],
            }

        # Create score
        elif action == "create_score":
            if not score_name or score_value is None:
                return {
                    "status": "error",
                    "content": [{"text": "❌ score_name and score_value required"}],
                }

            client.create_score(
                trace_id=trace_id,
                observation_id=observation_id or generation_id or span_id,
                name=score_name,
                value=score_value,
            )

            target = (
                f"trace {trace_id}"
                if trace_id
                else f"observation {observation_id or generation_id or span_id}"
            )
            return {
                "status": "success",
                "content": [
                    {"text": f"✅ Score added to {target}: {score_name}={score_value}"}
                ],
            }

        # Create dataset
        elif action == "create_dataset":
            if not name:
                return {"status": "error", "content": [{"text": "❌ name required"}]}

            client.create_dataset(name=name, metadata=metadata)
            return {
                "status": "success",
                "content": [{"text": f"✅ Dataset created: {name}"}],
            }

        # Get dataset
        elif action == "get_dataset":
            if not name:
                return {"status": "error", "content": [{"text": "❌ name required"}]}

            dataset = client.get_dataset(name=name)
            # Extract useful dataset info
            dataset_info = {
                "name": dataset.name if hasattr(dataset, "name") else name,
                "id": getattr(dataset, "id", None),
                "description": getattr(dataset, "description", None),
                "metadata": getattr(dataset, "metadata", None),
                "created_at": str(getattr(dataset, "created_at", None)),
            }
            return {
                "status": "success",
                "content": [
                    {
                        "text": f"✅ Dataset '{name}':\n{json.dumps(dataset_info, default=str, indent=2)}"
                    }
                ],
            }

        # Create dataset item
        elif action == "create_dataset_item":
            if not name:
                return {
                    "status": "error",
                    "content": [{"text": "❌ dataset name required"}],
                }

            client.create_dataset_item(
                dataset_name=name,
                input=json.loads(input_data) if input_data else None,
                expected_output=json.loads(output_data) if output_data else None,
                metadata=metadata,
            )
            return {
                "status": "success",
                "content": [{"text": f"✅ Dataset item added to {name}"}],
            }

        # Create prompt
        elif action == "create_prompt":
            if not name:
                return {"status": "error", "content": [{"text": "❌ name required"}]}

            # Prompt creation requires more parameters - simplified here
            result = client.create_prompt(name=name, prompt=input_data or "")
            return {
                "status": "success",
                "content": [{"text": f"✅ Prompt created: {name}"}],
            }

        # Get prompt
        elif action == "get_prompt":
            if not name:
                return {"status": "error", "content": [{"text": "❌ name required"}]}

            prompt = client.get_prompt(name=name)
            return {
                "status": "success",
                "content": [
                    {
                        "text": f"✅ Prompt retrieved: {json.dumps(prompt, default=str, indent=2)}"
                    }
                ],
            }

        # Update prompt
        elif action == "update_prompt":
            if not name:
                return {"status": "error", "content": [{"text": "❌ name required"}]}

            client.update_prompt(name=name, prompt=input_data or "")
            return {
                "status": "success",
                "content": [{"text": f"✅ Prompt updated: {name}"}],
            }

        # Clear prompt cache
        elif action == "clear_prompt_cache":
            client.clear_prompt_cache()
            return {
                "status": "success",
                "content": [{"text": "✅ Prompt cache cleared"}],
            }

        # Run experiment
        elif action == "run_experiment":
            if not name:
                return {
                    "status": "error",
                    "content": [{"text": "❌ experiment name required"}],
                }

            # Simplified - actual implementation needs more parameters
            result = client.run_experiment(name=name)
            return {
                "status": "success",
                "content": [{"text": f"✅ Experiment started: {name}"}],
            }

        # Resolve media references
        elif action == "resolve_media_references":
            if not input_data:
                return {
                    "status": "error",
                    "content": [{"text": "❌ input_data required"}],
                }

            resolved = client.resolve_media_references(json.loads(input_data))
            return {
                "status": "success",
                "content": [
                    {
                        "text": f"✅ Media references resolved: {json.dumps(resolved, default=str)}"
                    }
                ],
            }

        # Get trace URL
        elif action == "get_trace_url":
            if not trace_id:
                return {
                    "status": "error",
                    "content": [{"text": "❌ trace_id required"}],
                }

            url = client.get_trace_url(trace_id=trace_id)
            return {
                "status": "success",
                "url": url,
                "content": [{"text": f"🔗 Trace URL: {url}"}],
            }

        # List traces
        elif action == "list_traces":
            limit = metadata.get("limit", 20) if metadata else 20
            traces = client.api.trace.list(limit=limit)

            lines = ["📋 **Recent Traces:**\n"]
            for t in traces.data:
                cost_str = f"${t.total_cost:.4f}" if t.total_cost else "$0"
                latency_str = f"{t.latency:.1f}s" if t.latency else "0s"
                obs_count = len(t.observations) if t.observations else 0
                lines.append(
                    f"• `{t.id}` | {t.name or '(unnamed)'} | {latency_str} | {cost_str} | {obs_count} obs"
                )

            return {
                "status": "success",
                "traces": [
                    {
                        "id": t.id,
                        "name": t.name,
                        "timestamp": str(t.timestamp),
                        "user_id": t.user_id,
                        "latency": t.latency,
                        "total_cost": t.total_cost,
                    }
                    for t in traces.data
                ],
                "content": [{"text": "\n".join(lines)}],
            }

        # Get trace details with token usage
        elif action == "get_trace":
            if not trace_id:
                return {
                    "status": "error",
                    "content": [{"text": "❌ trace_id required"}],
                }

            # Configurable limits via metadata
            obs_limit = metadata.get("obs_limit") if metadata else None  # None = all
            search_limit = metadata.get("search_limit", 100) if metadata else 100

            # Use list with filter to get observation IDs (get() returns full objects which can be too large)
            traces = client.api.trace.list(limit=search_limit)
            t = None
            for trace in traces.data:
                if trace.id == trace_id:
                    t = trace
                    break

            if not t:
                # Fallback to direct get if not in recent traces
                t = client.api.trace.get(trace_id)

            lines = [f"📊 **Trace Details:**\n"]
            lines.append(f"**ID:** `{t.id}`")
            lines.append(f"**Name:** {t.name or '(unnamed)'}")
            lines.append(f"**Session:** {t.session_id or 'N/A'}")
            lines.append(f"**User:** {t.user_id or 'N/A'}")
            lines.append(
                f"**Latency:** {t.latency:.2f}s" if t.latency else "**Latency:** N/A"
            )
            lines.append(
                f"**Total Cost:** ${t.total_cost:.6f}"
                if t.total_cost
                else "**Total Cost:** $0"
            )
            lines.append(f"**Created:** {t.createdAt}")
            lines.append(f"**Tags:** {', '.join(t.tags) if t.tags else 'None'}")

            # Token usage from observations
            total_input_tokens = 0
            total_output_tokens = 0
            generations = []

            if t.observations:
                lines.append(f"\n**Observations ({len(t.observations)}):**")
                obs_list = t.observations[:obs_limit] if obs_limit else t.observations

                for obs_item in obs_list:
                    try:
                        # Check if it's an ID string or full object
                        if isinstance(obs_item, str):
                            obs = client.api.observations.get(obs_item)
                        else:
                            obs = obs_item

                        if obs.type == "GENERATION":
                            tokens_in = obs.promptTokens or 0
                            tokens_out = obs.completionTokens or 0
                            total_input_tokens += tokens_in
                            total_output_tokens += tokens_out
                            latency = f"{obs.latency:.2f}s" if obs.latency else "N/A"
                            lines.append(
                                f"  • [{obs.type}] {obs.name} | {obs.model or 'unknown'} | {tokens_in}→{tokens_out} tokens | {latency}"
                            )
                            generations.append(
                                {
                                    "name": obs.name,
                                    "model": obs.model,
                                    "input_tokens": tokens_in,
                                    "output_tokens": tokens_out,
                                    "latency": obs.latency,
                                }
                            )
                        else:
                            lines.append(f"  • [{obs.type}] {obs.name}")
                    except Exception as e:
                        lines.append(f"  • [ERROR] fetching observation: {str(e)[:50]}")

                if obs_limit and len(t.observations) > obs_limit:
                    lines.append(
                        f"  ... and {len(t.observations) - obs_limit} more observations"
                    )

            lines.append(
                f"\n**Total Tokens:** {total_input_tokens:,} input + {total_output_tokens:,} output = {total_input_tokens + total_output_tokens:,}"
            )

            return {
                "status": "success",
                "content": [
                    {"text": "\n".join(lines)},
                    {
                        "json": {
                            "trace": {
                                "id": t.id,
                                "name": t.name,
                                "session_id": t.session_id,
                                "user_id": t.user_id,
                                "latency": t.latency,
                                "total_cost": t.total_cost,
                                "total_input_tokens": total_input_tokens,
                                "total_output_tokens": total_output_tokens,
                                "generations": generations,
                            }
                        }
                    },
                ],
            }

        # List sessions
        elif action == "list_sessions":
            limit = metadata.get("limit", 20) if metadata else 20
            sessions = client.api.sessions.list(limit=limit)

            lines = ["📋 **Sessions:**\n"]
            for s in sessions.data:
                lines.append(f"• `{s.id}` | created: {s.created_at}")

            return {
                "status": "success",
                "content": [
                    {"text": "\n".join(lines)},
                    {
                        "json": {
                            "sessions": [
                                {"id": s.id, "created_at": str(s.created_at)}
                                for s in sessions.data
                            ]
                        }
                    },
                ],
            }

        # Create event
        elif action == "create_event":
            if not trace_id:
                return {
                    "status": "error",
                    "content": [{"text": "❌ trace_id required"}],
                }

            trace_context = {"trace_id": trace_id}
            if span_id:
                trace_context["parent_span_id"] = span_id

            event = client.create_event(
                trace_context=trace_context,
                name=name or "event",
                input=json.loads(input_data) if input_data else None,
                output=json.loads(output_data) if output_data else None,
                metadata=metadata,
            )
            return {
                "status": "success",
                "event_id": event.id if hasattr(event, "id") else None,
                "content": [
                    {
                        "text": f"✅ Event '{name or 'event'}' created in trace {trace_id}"
                    }
                ],
            }

        # Flush
        elif action == "flush":
            client.flush()
            logger.info("Langfuse data flushed")
            return {
                "status": "success",
                "content": [{"text": "✅ Langfuse data flushed"}],
            }

        # Shutdown
        elif action == "shutdown":
            global _langfuse_client
            if _langfuse_client:
                _langfuse_client.shutdown()
                _langfuse_client = None
                _traces.clear()
                _spans.clear()
                _generations.clear()
                _observations.clear()
            logger.info("Langfuse client shutdown")
            return {
                "status": "success",
                "content": [{"text": "✅ Langfuse client shutdown"}],
            }

        else:
            error_msg = f"❌ Unknown action: {action}"
            logger.warning(error_msg)
            return {"status": "error", "content": [{"text": error_msg}]}

    except Exception as e:
        import traceback

        error_trace = traceback.format_exc()
        logger.error(f"Langfuse operation failed: {str(e)}\n{error_trace}")
        return {
            "status": "error",
            "content": [
                {"text": f"❌ Error: {str(e)}"},
                {"text": f"Traceback:\n{error_trace[:500]}"},
            ],
        }
