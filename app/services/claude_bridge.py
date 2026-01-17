"""
Claude Code Bridge - Subscription-based Claude Code integration for The Pulse

This module provides a wrapper around the Claude Code CLI that uses subscription
authentication (no per-token billing). It replaces Ollama as the LLM backend.

Usage:
    # Get the shared singleton instance (recommended)
    bridge = get_claude_bridge()
    response = await bridge.query(messages, system_prompt="You are an intelligence analyst...")

    # For streaming responses
    async for chunk in bridge.query_streaming(messages):
        print(chunk["content"])

The response format is compatible with the existing ResearchAssistant interface:
    {"content": "...", "tool_calls": [...]}

Reference: ~/Desktop/workshop-claude-migration/claude_bridge.py
"""

import subprocess
import json
import os
import asyncio
import re
from typing import Optional, List, Dict, Any, AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

from app.core.logging import get_logger

logger = get_logger(__name__)

# Explicit path to Claude Code binary - more secure than PATH lookup
CLAUDE_BINARY = os.path.expanduser("~/.local/bin/claude")

# Session persistence path
PULSE_SESSION_DIR = Path.home() / ".pulse" / "sessions"
CLAUDE_SESSION_FILE = PULSE_SESSION_DIR / "claude_session.json"


@dataclass
class ClaudeResponse:
    """Structured response from Claude Code CLI."""
    content: str
    session_id: Optional[str] = None
    cost_usd: float = 0.0  # Will be 0 with subscription
    model: str = "claude-sonnet-4-20250514"
    tool_calls: List[Dict] = field(default_factory=list)
    raw_output: Optional[Dict] = None


class ClaudeCodeBridge:
    """
    Wrapper for Claude Code CLI that uses subscription authentication.
    No API key required - uses browser-authenticated session.

    This is the core replacement for Ollama in The Pulse's architecture.
    """

    def __init__(
        self,
        working_dir: Optional[str] = None,
        timeout_seconds: int = 120
    ):
        self.working_dir = working_dir or os.getcwd()
        self.timeout = timeout_seconds
        self._session_id: Optional[str] = None
        self._verify_installation()

    def _verify_installation(self):
        """Ensure Claude Code is installed and no API key is set."""
        # Check for API key that would override subscription
        if os.environ.get('ANTHROPIC_API_KEY'):
            logger.warning(
                "ANTHROPIC_API_KEY is set! This will cause per-token billing. "
                "Consider removing it from your environment to use subscription auth."
            )

        # Verify Claude Code is installed at expected path
        if not os.path.isfile(CLAUDE_BINARY):
            raise RuntimeError(
                f"Claude Code not found at {CLAUDE_BINARY}. "
                "Install with: curl -fsSL https://claude.ai/install.sh | sh"
            )

        try:
            result = subprocess.run(
                [CLAUDE_BINARY, '--version'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                raise RuntimeError(f"Claude Code not working: {result.stderr}")
            logger.info(f"Claude Code version: {result.stdout.strip()}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude Code --version timed out")

    def _clean_env(self) -> Dict[str, str]:
        """Return environment with ANTHROPIC_API_KEY removed to ensure subscription auth."""
        return {k: v for k, v in os.environ.items() if k != 'ANTHROPIC_API_KEY'}

    def _messages_to_prompt(self, messages: List[Dict]) -> str:
        """
        Convert OpenAI-style messages array to a single prompt string.

        Claude Code CLI takes a single prompt, not a messages array.
        We need to format the conversation history appropriately.
        """
        prompt_parts = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                # System messages are handled separately via --append-system-prompt
                continue
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
            elif role == "tool":
                # Tool results from previous calls
                tool_name = msg.get("name", "tool")
                prompt_parts.append(f"Tool Result ({tool_name}): {content}")

        return "\n\n".join(prompt_parts)

    def _extract_system_prompt(self, messages: List[Dict]) -> Optional[str]:
        """Extract system prompt from messages array."""
        for msg in messages:
            if msg.get("role") == "system":
                return msg.get("content", "")
        return None

    def _extract_tool_calls(self, content: str) -> List[Dict]:
        """
        Extract <tool_call> formatted tool calls from response content.

        This maintains compatibility with tool calling format if needed.
        """
        tool_calls = []

        # Strategy 1: XML-style <tool_call> tags (primary format)
        for match in re.finditer(r'<tool_call>(.*?)</tool_call>', content, re.DOTALL):
            try:
                call = json.loads(match.group(1).strip())
                if call not in tool_calls:
                    tool_calls.append(call)
                    logger.debug(f"Extracted tool call: {call.get('tool', 'unknown')}")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse tool call: {e}")

        # Strategy 2: JSON in code blocks (fallback)
        for match in re.finditer(r'```(?:json)?\s*(\{[^`]+\})\s*```', content, re.DOTALL):
            try:
                data = json.loads(match.group(1))
                if "tool" in data and data not in tool_calls:
                    tool_calls.append(data)
                    logger.debug(f"Extracted tool call (code block): {data.get('tool', 'unknown')}")
            except json.JSONDecodeError:
                pass

        return tool_calls

    async def query(
        self,
        messages: List[Dict],
        system_prompt: Optional[str] = None,
        continue_session: bool = False,
        max_turns: int = 1,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a query to Claude Code using subscription auth.

        Args:
            messages: OpenAI-style conversation messages
            system_prompt: System prompt (if not in messages)
            continue_session: Continue the most recent conversation
            max_turns: Max agentic turns (1 = single response)
            model: Model override (sonnet, opus, haiku)

        Returns:
            Dict with 'content' (str) and 'tool_calls' (list)
        """
        # Extract or use provided system prompt
        msg_system_prompt = self._extract_system_prompt(messages)
        effective_system_prompt = system_prompt or msg_system_prompt

        # Convert messages to prompt
        prompt = self._messages_to_prompt(messages)

        if not prompt.strip():
            return {"content": "Error: Empty prompt", "tool_calls": []}

        # Build command - use stdin for prompt to avoid "Argument list too long" error
        cmd = [CLAUDE_BINARY, '-p', '-', '--output-format', 'json']

        # Add system prompt if we have one
        if effective_system_prompt:
            # Check if system prompt is small enough for command line (limit ~100KB to be safe)
            if len(effective_system_prompt) < 100000:
                cmd.extend(['--append-system-prompt', effective_system_prompt])
            else:
                # For very large system prompts, prepend to the prompt instead
                prompt = f"[System Context]\n{effective_system_prompt}\n\n[User Request]\n{prompt}"
                logger.warning(f"System prompt too large ({len(effective_system_prompt)} chars), prepending to prompt")

        # Session management
        if continue_session and self._session_id:
            cmd.extend(['--resume', self._session_id])
        elif continue_session:
            cmd.append('--continue')

        # Max turns (limit agentic behavior)
        cmd.extend(['--max-turns', str(max_turns)])

        # Model selection (optional)
        if model:
            cmd.extend(['--model', model])

        # Disable Claude's native tools so we handle tool execution ourselves
        cmd.extend(['--tools', ''])

        logger.debug(f"Claude query: {len(prompt)} chars, session={continue_session}")

        try:
            # Run Claude Code subprocess - pass prompt via stdin to avoid arg list limits
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    input=prompt,  # Pass prompt via stdin
                    capture_output=True,
                    text=True,
                    cwd=self.working_dir,
                    env=self._clean_env(),
                    timeout=self.timeout
                )
            )

            if result.returncode != 0:
                error_msg = result.stderr or "Unknown error"
                logger.error(f"Claude Code error (exit {result.returncode}): {error_msg}")
                return {
                    "content": f"Error: Claude Code returned exit code {result.returncode}: {error_msg}",
                    "tool_calls": []
                }

            # Parse JSON output
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Claude Code output: {e}")
                logger.debug(f"Raw output: {result.stdout[:500]}")
                # Fall back to treating output as plain text
                return {
                    "content": result.stdout,
                    "tool_calls": []
                }

            # Extract content from response
            content = ""
            if isinstance(data, dict):
                # JSON output format has 'result' field
                content = data.get('result', data.get('content', ''))
                self._session_id = data.get('session_id')

                # Log cost/usage info if present
                if data.get('cost_usd'):
                    logger.info(f"Query cost: ${data.get('cost_usd', 0):.4f}")
                if data.get('model'):
                    logger.debug(f"Model used: {data.get('model')}")
            elif isinstance(data, str):
                content = data
            else:
                content = str(data)

            # Extract tool calls from content
            tool_calls = self._extract_tool_calls(content)

            logger.debug(f"Response length: {len(content)} chars")
            if tool_calls:
                logger.info(f"Extracted {len(tool_calls)} tool calls from response")

            return {
                "content": content,
                "tool_calls": tool_calls
            }

        except subprocess.TimeoutExpired:
            logger.error(f"Claude Code timed out after {self.timeout}s")
            return {
                "content": f"Error: Claude Code timed out after {self.timeout} seconds",
                "tool_calls": []
            }
        except Exception as e:
            logger.error(f"Unexpected error calling Claude Code: {e}", exc_info=True)
            return {
                "content": f"Error: {e}",
                "tool_calls": []
            }

    async def query_streaming(
        self,
        messages: List[Dict],
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream responses for real-time output.

        Yields:
            Dict with 'type' (chunk/done/error) and 'content'
        """
        msg_system_prompt = self._extract_system_prompt(messages)
        effective_system_prompt = system_prompt or msg_system_prompt
        prompt = self._messages_to_prompt(messages)

        if not prompt.strip():
            yield {"type": "error", "content": "Empty prompt"}
            return

        cmd = [CLAUDE_BINARY, '-p', '-', '--output-format', 'stream-json', '--verbose']

        if effective_system_prompt and len(effective_system_prompt) < 100000:
            cmd.extend(['--append-system-prompt', effective_system_prompt])
        elif effective_system_prompt:
            prompt = f"[System Context]\n{effective_system_prompt}\n\n[User Request]\n{prompt}"

        if kwargs.get('continue_session') and self._session_id:
            cmd.extend(['--resume', self._session_id])
        elif kwargs.get('continue_session'):
            cmd.append('--continue')

        cmd.extend(['--max-turns', '1'])
        cmd.extend(['--tools', ''])

        logger.debug(f"Claude streaming query: {len(prompt)} chars")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_dir,
                env=self._clean_env()
            )

            # Send prompt via stdin
            process.stdin.write(prompt.encode())
            await process.stdin.drain()
            process.stdin.close()

            # Yield chunks as they arrive
            full_content = []
            async for line in process.stdout:
                line_str = line.decode().strip()
                if line_str:
                    try:
                        data = json.loads(line_str)
                        # Handle different event types from Claude's stream-json format
                        event_type = data.get('type', 'text')

                        if event_type == 'assistant':
                            # Content block
                            text = data.get('message', {}).get('content', [])
                            if text and isinstance(text, list):
                                for block in text:
                                    if block.get('type') == 'text':
                                        chunk_text = block.get('text', '')
                                        full_content.append(chunk_text)
                                        yield {"type": "chunk", "content": chunk_text}
                        elif event_type == 'result':
                            # Final result
                            content = data.get('result', '')
                            if content and content not in ''.join(full_content):
                                yield {"type": "chunk", "content": content}
                            self._session_id = data.get('session_id')
                        elif 'content' in data:
                            # Fallback for simple content
                            yield {"type": "chunk", "content": data['content']}
                        elif 'text' in data:
                            yield {"type": "chunk", "content": data['text']}
                    except json.JSONDecodeError:
                        # Plain text line
                        yield {"type": "chunk", "content": line_str}

            await process.wait()

            if process.returncode != 0:
                stderr = await process.stderr.read()
                logger.error(f"Claude streaming error: {stderr.decode()}")
                yield {"type": "error", "content": stderr.decode()}
            else:
                yield {"type": "done", "content": ""}

        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield {"type": "error", "content": str(e)}

    def reset_session(self):
        """Reset session state for a new conversation."""
        self._session_id = None
        logger.debug("Session reset")

    @property
    def session_id(self) -> Optional[str]:
        """Get current session ID if any."""
        return self._session_id

    def set_session_id(self, session_id: str):
        """Set the Claude session ID (for resuming from persisted state)."""
        self._session_id = session_id
        logger.debug(f"Session ID set to: {session_id}")


# ============================================================================
# Session Persistence and Singleton Management
# ============================================================================

class ClaudeSessionState:
    """
    Persisted state linking Pulse sessions to Claude Code sessions.

    This allows multi-turn conversations to maintain context across:
    - Multiple Pulse components (API routes, WebSocket, services)
    - Application restarts (if session is still valid)
    """

    def __init__(self):
        self.user_id: Optional[str] = None
        self.conversation_id: Optional[str] = None
        self.claude_session_id: Optional[str] = None
        self.started_at: Optional[datetime] = None
        self.last_used_at: Optional[datetime] = None
        self.turn_count: int = 0
        self.context_tokens_estimated: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "claude_session_id": self.claude_session_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "turn_count": self.turn_count,
            "context_tokens_estimated": self.context_tokens_estimated,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClaudeSessionState":
        state = cls()
        state.user_id = data.get("user_id")
        state.conversation_id = data.get("conversation_id")
        state.claude_session_id = data.get("claude_session_id")
        state.started_at = datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
        state.last_used_at = datetime.fromisoformat(data["last_used_at"]) if data.get("last_used_at") else None
        state.turn_count = data.get("turn_count", 0)
        state.context_tokens_estimated = data.get("context_tokens_estimated", 0)
        return state


class ClaudeBridgeManager:
    """
    Singleton manager for the Claude Code bridge.

    Provides:
    - Single shared bridge instance for session continuity
    - Session state persistence across application restarts
    - Automatic session linking with user/conversation contexts
    - Context usage tracking for efficiency monitoring
    """

    _instance: Optional["ClaudeBridgeManager"] = None

    def __init__(self):
        self._bridge: Optional[ClaudeCodeBridge] = None
        self._state: Optional[ClaudeSessionState] = None
        self._current_conversation_id: Optional[str] = None
        self._load_state()

    @classmethod
    def get_instance(cls) -> "ClaudeBridgeManager":
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_state(self):
        """Load persisted session state."""
        if CLAUDE_SESSION_FILE.exists():
            try:
                with open(CLAUDE_SESSION_FILE) as f:
                    data = json.load(f)
                self._state = ClaudeSessionState.from_dict(data)
                logger.debug(f"Loaded Claude session state: {self._state.claude_session_id}")
            except Exception as e:
                logger.warning(f"Could not load Claude session state: {e}")
                self._state = ClaudeSessionState()
        else:
            self._state = ClaudeSessionState()

    def _save_state(self):
        """Persist session state to disk."""
        try:
            PULSE_SESSION_DIR.mkdir(parents=True, exist_ok=True)
            with open(CLAUDE_SESSION_FILE, "w") as f:
                json.dump(self._state.to_dict(), f, indent=2)
            logger.debug("Saved Claude session state")
        except Exception as e:
            logger.warning(f"Could not save Claude session state: {e}")

    def get_bridge(self, timeout_seconds: int = 120) -> ClaudeCodeBridge:
        """
        Get the shared bridge instance.

        Creates a new bridge if none exists, or returns the existing one
        with session continuity preserved.
        """
        if self._bridge is None:
            self._bridge = ClaudeCodeBridge(timeout_seconds=timeout_seconds)

            # Restore session ID if we have a valid one
            if (self._state.claude_session_id and
                self._state.conversation_id == self._current_conversation_id):
                self._bridge.set_session_id(self._state.claude_session_id)
                logger.info(f"Restored Claude session: {self._state.claude_session_id}")

        return self._bridge

    def bind_to_conversation(self, conversation_id: str, user_id: Optional[str] = None):
        """
        Bind the Claude bridge to a conversation.

        If the conversation changes, we may start a new Claude session
        depending on session management preferences.
        """
        if self._current_conversation_id != conversation_id:
            logger.info(f"Binding to conversation: {conversation_id}")

            # Check if we're resuming the same conversation
            if (self._state.conversation_id == conversation_id and
                self._state.claude_session_id):
                # Resume the previous Claude session
                self._current_conversation_id = conversation_id
                if self._bridge:
                    self._bridge.set_session_id(self._state.claude_session_id)
                logger.info(f"Resuming Claude session for conversation: {conversation_id}")
            else:
                # New conversation = new Claude session
                self._current_conversation_id = conversation_id
                self._state.conversation_id = conversation_id
                self._state.user_id = user_id
                self._state.claude_session_id = None
                self._state.started_at = datetime.now()
                self._state.turn_count = 0
                self._state.context_tokens_estimated = 0

                if self._bridge:
                    self._bridge.reset_session()

                self._save_state()
                logger.info(f"Started new Claude session for conversation: {conversation_id}")

    def record_turn(self, claude_session_id: Optional[str] = None, estimated_tokens: int = 0):
        """
        Record a conversation turn and update session state.

        Called after each successful Claude query to track:
        - Claude session ID (from response)
        - Turn count for the session
        - Estimated token usage
        """
        if claude_session_id:
            self._state.claude_session_id = claude_session_id
        elif self._bridge and self._bridge.session_id:
            self._state.claude_session_id = self._bridge.session_id

        self._state.last_used_at = datetime.now()
        self._state.turn_count += 1
        self._state.context_tokens_estimated += estimated_tokens

        self._save_state()
        logger.debug(f"Recorded turn {self._state.turn_count}, session: {self._state.claude_session_id}")

    def get_session_info(self) -> Dict[str, Any]:
        """Get current session information for debugging/dashboard."""
        return {
            "conversation_id": self._current_conversation_id,
            "claude_session_id": self._state.claude_session_id if self._state else None,
            "turn_count": self._state.turn_count if self._state else 0,
            "context_tokens_estimated": self._state.context_tokens_estimated if self._state else 0,
            "started_at": self._state.started_at.isoformat() if self._state and self._state.started_at else None,
            "last_used_at": self._state.last_used_at.isoformat() if self._state and self._state.last_used_at else None,
        }

    def reset(self):
        """Reset the bridge and session state (for new conversations)."""
        if self._bridge:
            self._bridge.reset_session()

        self._state = ClaudeSessionState()
        self._state.conversation_id = self._current_conversation_id
        self._save_state()
        logger.info("Claude session reset")


# Singleton instance
_bridge_manager: Optional[ClaudeBridgeManager] = None


def get_claude_bridge_manager() -> ClaudeBridgeManager:
    """Get the global ClaudeBridgeManager singleton."""
    global _bridge_manager
    if _bridge_manager is None:
        _bridge_manager = ClaudeBridgeManager.get_instance()
    return _bridge_manager


def get_claude_bridge(timeout_seconds: int = 120) -> ClaudeCodeBridge:
    """
    Get the shared Claude Code bridge instance.

    This is the recommended way to get a bridge for most use cases.
    The shared instance maintains session continuity across components.

    For isolated contexts, create a dedicated ClaudeCodeBridge() instance.
    """
    return get_claude_bridge_manager().get_bridge(timeout_seconds)


# ============================================================================
# Convenience Functions
# ============================================================================

async def claude_chat(
    messages: List[Dict],
    system_prompt: Optional[str] = None,
    stream: bool = False,
    timeout_seconds: int = 120
) -> Dict[str, Any]:
    """
    Convenience function for Claude chat.

    Args:
        messages: OpenAI-style message list
        system_prompt: Optional system prompt
        stream: Whether to stream (if True, returns generator)
        timeout_seconds: Query timeout

    Returns:
        Dict with 'content' and 'tool_calls'
    """
    bridge = get_claude_bridge(timeout_seconds=timeout_seconds)

    if stream:
        # For streaming, collect all chunks
        content_parts = []
        async for chunk in bridge.query_streaming(messages, system_prompt):
            if chunk["type"] == "chunk":
                content_parts.append(chunk["content"])
        return {"content": "".join(content_parts), "tool_calls": []}
    else:
        return await bridge.query(messages, system_prompt)


async def claude_structured_output(
    messages: List[Dict],
    output_schema: Dict[str, Any],
    system_prompt: Optional[str] = None,
    timeout_seconds: int = 180
) -> Dict[str, Any]:
    """
    Get structured JSON output from Claude.

    Args:
        messages: Message list
        output_schema: JSON schema for output
        system_prompt: Base system prompt

    Returns:
        Parsed JSON matching schema (or error dict)
    """
    # Append schema instructions to system prompt
    schema_instruction = f"""

IMPORTANT: You must respond with valid JSON matching this schema:
```json
{json.dumps(output_schema, indent=2)}
```

Respond ONLY with the JSON object, no additional text or markdown code blocks.
"""

    full_system = (system_prompt or "") + schema_instruction

    bridge = get_claude_bridge(timeout_seconds=timeout_seconds)
    response = await bridge.query(messages, system_prompt=full_system)

    # Parse JSON from response
    content = response.get("content", "").strip()

    # Remove markdown code blocks if present
    if content.startswith("```"):
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse structured output: {e}")
        logger.debug(f"Raw content: {content[:500]}")
        return {"error": str(e), "raw_content": content}


# Quick one-off query
async def quick_query(prompt: str, system_prompt: Optional[str] = None) -> str:
    """
    Quick one-off query to Claude Code.

    Usage:
        result = await quick_query("What is 2 + 2?")
    """
    bridge = ClaudeCodeBridge()
    messages = [{"role": "user", "content": prompt}]
    response = await bridge.query(messages, system_prompt=system_prompt)
    return response.get("content", "")


# ============================================================================
# Test Function
# ============================================================================

async def _test_bridge():
    """Test the Claude Code bridge."""
    print("Testing Claude Code Bridge for The Pulse...")

    bridge = ClaudeCodeBridge()

    # Test 1: Simple query
    print("\n1. Simple query test:")
    messages = [{"role": "user", "content": "What is 2 + 2? Reply with just the number."}]
    response = await bridge.query(messages)
    print(f"   Response: {response['content'][:100]}")

    # Test 2: With system prompt
    print("\n2. System prompt test:")
    messages = [{"role": "user", "content": "Introduce yourself briefly."}]
    response = await bridge.query(
        messages,
        system_prompt="You are The Pulse, an intelligence analysis platform. Keep responses under 50 words."
    )
    print(f"   Response: {response['content'][:200]}")

    # Test 3: Streaming
    print("\n3. Streaming test:")
    messages = [{"role": "user", "content": "Count from 1 to 5."}]
    print("   Streaming: ", end="", flush=True)
    async for chunk in bridge.query_streaming(messages):
        if chunk["type"] == "chunk":
            print(chunk["content"], end="", flush=True)
    print()

    print("\nAll tests completed!")


if __name__ == "__main__":
    asyncio.run(_test_bridge())
