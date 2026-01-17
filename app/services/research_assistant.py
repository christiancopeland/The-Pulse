"""
Research Assistant Service - Claude Code Implementation

This module provides the AI-powered research assistant using Claude Code CLI
for subscription-based LLM access. Replaces the previous Ollama implementation.

The interface remains compatible with existing code that uses ResearchAssistant.
"""

from typing import List, Dict, Any, Optional, AsyncGenerator
import json
import asyncio

from app.core.logging import get_logger
from app.services.claude_bridge import (
    get_claude_bridge,
    claude_structured_output,
    ClaudeCodeBridge
)

logger = get_logger(__name__)


class ResearchAssistant:
    """
    AI-powered research assistant using Claude Code.

    Provides:
    - Streaming and non-streaming chat
    - Structured JSON output with schema validation
    - News article and document analysis
    - Knowledge graph generation

    This is a drop-in replacement for the Ollama-based implementation.
    The interface remains the same for backward compatibility.
    """

    def __init__(self, timeout_seconds: int = 120):
        """
        Initialize the Research Assistant.

        Args:
            timeout_seconds: Query timeout (default 120s)
        """
        self.timeout = timeout_seconds
        self._bridge: Optional[ClaudeCodeBridge] = None
        logger.info("ResearchAssistant initialized with Claude Code backend")

    def _get_bridge(self) -> ClaudeCodeBridge:
        """Get or create the Claude bridge instance."""
        if self._bridge is None:
            self._bridge = get_claude_bridge(timeout_seconds=self.timeout)
        return self._bridge

    async def chat(
        self,
        messages: List[Dict[str, str]],
        stream: bool = True
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Chat with Claude, optionally streaming responses.

        Args:
            messages: List of {"role": str, "content": str} messages
            stream: Whether to stream responses (default True)

        Yields:
            {"type": "chunk"|"done"|"error", "message": {"role": "assistant", "content": str}}
        """
        logger.debug(f"Starting chat with {len(messages)} messages, stream={stream}")

        bridge = self._get_bridge()

        try:
            if stream:
                async for chunk in bridge.query_streaming(messages):
                    if chunk["type"] == "chunk":
                        yield {
                            "type": "chunk",
                            "message": {
                                "role": "assistant",
                                "content": chunk.get("content", "")
                            }
                        }
                    elif chunk["type"] == "done":
                        yield {
                            "type": "done",
                            "message": {"role": "assistant", "content": ""}
                        }
                    elif chunk["type"] == "error":
                        logger.error(f"Stream error: {chunk.get('content', 'Unknown error')}")
                        yield {
                            "type": "error",
                            "message": {
                                "role": "assistant",
                                "content": f"Error: {chunk.get('content', 'Unknown error')}"
                            }
                        }
            else:
                # Non-streaming: single response
                response = await bridge.query(messages)
                content = response.get("content", "")

                if content.startswith("Error:"):
                    yield {
                        "type": "error",
                        "message": {"role": "assistant", "content": content}
                    }
                else:
                    yield {
                        "type": "chunk",
                        "message": {"role": "assistant", "content": content}
                    }
                    yield {
                        "type": "done",
                        "message": {"role": "assistant", "content": ""}
                    }

        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            yield {
                "type": "error",
                "message": {
                    "role": "assistant",
                    "content": f"Error: {str(e)}"
                }
            }

    async def structured_chat(
        self,
        messages: List[Dict[str, str]],
        output_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Chat with structured JSON output.

        Args:
            messages: Message list
            output_schema: JSON schema for response

        Returns:
            Parsed JSON matching schema (or error dict)
        """
        logger.debug(f"Structured chat with schema: {list(output_schema.get('properties', {}).keys())}")

        try:
            result = await claude_structured_output(
                messages,
                output_schema,
                timeout_seconds=self.timeout
            )

            if "error" in result:
                logger.error(f"Structured output error: {result.get('error')}")
                # Try to extract content from raw_content if available
                raw = result.get("raw_content", "")
                if raw:
                    return {"analysis": raw} if "analysis" in output_schema.get("properties", {}) else result

            return result

        except Exception as e:
            logger.error(f"Structured chat error: {e}", exc_info=True)
            raise ValueError(f"Error communicating with Claude: {str(e)}")

    async def generate_analysis_from_news_article(
        self,
        messages: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Generate analysis for a news article.

        Args:
            messages: Messages containing the article content

        Returns:
            Dict with 'analysis' key containing markdown-formatted analysis
        """
        logger.debug("Generating news article analysis")

        # Ensure messages is properly formatted
        if isinstance(messages, str):
            try:
                messages = json.loads(messages)
            except json.JSONDecodeError:
                messages = [{"role": "user", "content": messages}]
        elif not isinstance(messages, list):
            messages = [{"role": "user", "content": str(messages)}]

        # Add system message for analysis
        system_message = {
            "role": "system",
            "content": """You are an expert intelligence analyst and journalist. Generate a comprehensive
analysis of the provided news article. Your analysis should be detailed and thorough, covering:

1. **Key Points**: Main findings, claims, and events from the article
2. **Sources & Citations**: Analysis of the sources used and their credibility
3. **Context**: Relevant background information and historical context
4. **Critical Analysis**: Examination of potential biases, missing information, and reliability
5. **Implications**: What this means and potential developments to watch
6. **Further Research**: Related topics and angles for additional investigation

IMPORTANT: Your response must be detailed and at least 500 words long. Format your response in markdown
with clear section headers. Ensure all analysis is based on the article content provided."""
        }

        all_messages = [system_message] + messages

        output_schema = {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "description": "A detailed markdown-formatted analysis of the article (minimum 500 words)"
                }
            },
            "required": ["analysis"]
        }

        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                response = await self.structured_chat(all_messages, output_schema)
                logger.debug(f"Analysis response (attempt {attempt + 1}): {len(str(response))} chars")

                if isinstance(response, dict) and "analysis" in response:
                    analysis_content = response["analysis"]
                    if len(analysis_content) < 100:
                        raise ValueError(f"Analysis response too short: {len(analysis_content)} chars")
                    return response

                # If we got raw content, wrap it
                if isinstance(response, dict) and "raw_content" in response:
                    return {"analysis": response["raw_content"]}

                raise ValueError(f"Unexpected response format: {type(response)}")

            except Exception as e:
                logger.warning(f"Analysis attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                raise

    async def generate_knowledge_graph_from_news_article(
        self,
        messages: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Generate a knowledge graph from a news article.

        Args:
            messages: Messages containing the article content

        Returns:
            Dict with 'entities' and 'relationships' keys
        """
        logger.debug("Generating knowledge graph from news article")

        system_message = {
            "role": "system",
            "content": """Extract a knowledge graph from the provided content. Identify:

1. **Entities**: Key people, organizations, locations, events, and concepts
2. **Relationships**: How these entities are connected to each other
3. **Context**: Background information that explains the relationships

For each entity, provide:
- name: The entity's name
- type: PERSON, ORGANIZATION, LOCATION, EVENT, CONCEPT, or DATE
- description: Brief description of the entity's role

For each relationship, provide:
- source: Name of the source entity
- target: Name of the target entity
- relationship: Description of how they are connected
- confidence: Your confidence level (0.0-1.0)

Be comprehensive but accurate - only include entities and relationships directly supported by the content."""
        }

        output_schema = {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            "description": {"type": "string"}
                        },
                        "required": ["name", "type"]
                    }
                },
                "relationships": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "target": {"type": "string"},
                            "relationship": {"type": "string"},
                            "confidence": {"type": "number"}
                        },
                        "required": ["source", "target", "relationship"]
                    }
                }
            },
            "required": ["entities", "relationships"]
        }

        all_messages = [system_message] + messages
        return await self.structured_chat(all_messages, output_schema)

    async def generate_analysis_from_document(
        self,
        messages: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Generate analysis for a document.

        Args:
            messages: Messages containing the document content

        Returns:
            Dict with 'analysis' key containing markdown-formatted analysis
        """
        logger.debug("Generating document analysis")

        system_message = {
            "role": "system",
            "content": """Generate a comprehensive analysis of the provided document with investigative journalism in mind. Include:

1. **Executive Summary**: Brief overview of the document's purpose and key findings
2. **Key Points**: Bullet points of main findings and claims
3. **Analysis**: Detailed examination of implications and significance
4. **Critical Assessment**: Evaluation of credibility, potential biases, and gaps
5. **Recommendations**: Suggested actions or areas for further investigation

Format with markdown and ensure all claims are supported by document content."""
        }

        output_schema = {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "description": "A detailed analysis with Key Points and Analysis sections"
                }
            },
            "required": ["analysis"]
        }

        all_messages = [system_message] + messages
        return await self.structured_chat(all_messages, output_schema)

    async def generate_knowledge_graph_from_document(
        self,
        messages: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Generate a knowledge graph from a document.

        Args:
            messages: Messages containing the document content

        Returns:
            Dict with 'entities', 'relationships', and optionally 'context' keys
        """
        logger.debug("Generating knowledge graph from document")

        system_message = {
            "role": "system",
            "content": """Create a structured knowledge graph from the document with:

1. **Entities**: Key actors, organizations, policies, locations, and concepts
   - Include name, type, and brief description for each
   - Types: PERSON, ORGANIZATION, LOCATION, POLICY, CONCEPT, DATE, EVENT

2. **Relationships**: Specific connections between entities
   - Include source entity, target entity, relationship type, and confidence score
   - Be specific about the nature of each relationship

3. **Context**: Background information and implications
   - Key contextual facts that explain the relationships
   - Important caveats or limitations

Ensure all elements are directly supported by the document content."""
        }

        output_schema = {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                            "description": {"type": "string"}
                        },
                        "required": ["name", "type"]
                    }
                },
                "relationships": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "target": {"type": "string"},
                            "relationship": {"type": "string"},
                            "confidence": {"type": "number"}
                        },
                        "required": ["source", "target", "relationship"]
                    }
                },
                "context": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["entities", "relationships"]
        }

        all_messages = [system_message] + messages
        return await self.structured_chat(all_messages, output_schema)


# Example usage
async def example_usage():
    """Example usage of the Claude-based ResearchAssistant."""
    assistant = ResearchAssistant()

    # Basic chat example
    messages = [
        {"role": "user", "content": "What is the capital of France?"}
    ]

    # Streaming chat
    print("Streaming response:")
    async for chunk in assistant.chat(messages):
        if chunk.get("message", {}).get("content"):
            print(chunk["message"]["content"], end="")
    print()

    # Structured output example
    print("\nStructured output:")
    schema = {
        "type": "object",
        "properties": {
            "capital": {"type": "string"},
            "country": {"type": "string"},
            "population": {"type": "integer"}
        },
        "required": ["capital", "country"]
    }

    result = await assistant.structured_chat(messages, schema)
    print(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(example_usage())
