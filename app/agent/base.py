from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from app.llm import LLM
from app.logger import logger
from app.sandbox.client import SANDBOX_CLIENT
from app.schema import ROLE_TYPE, AgentState, Memory, Message


class BaseAgent(BaseModel, ABC):
    """Abstract base class for managing agent state and execution.

    Provides foundational functionality for state transitions, memory management,
    and a step-based execution loop. Subclasses must implement the `step` method.
    """

    # Core attributes
    name: str = Field(..., description="Unique name of the agent")
    description: Optional[str] = Field(None, description="Optional agent description")

    # Prompts
    system_prompt: Optional[str] = Field(
        None, description="System-level instruction prompt"
    )
    next_step_prompt: Optional[str] = Field(
        None, description="Prompt for determining next action"
    )

    # Dependencies
    llm: LLM = Field(default_factory=LLM, description="Language model instance")
    memory: Memory = Field(default_factory=Memory, description="Agent's memory store")
    state: AgentState = Field(
        default=AgentState.IDLE, description="Current agent state"
    )

    # Execution control
    max_steps: int = Field(default=20, description="Maximum steps before termination")
    current_step: int = Field(default=0, description="Current step in execution")

    # Loop detection settings
    duplicate_threshold: int = 2
    empty_response_threshold: int = 3
    consecutive_empty_responses: int = 0
    consecutive_timeouts: int = 0
    timeout_threshold: int = 2

    class Config:
        arbitrary_types_allowed = True
        extra = "allow"  # Allow extra fields for flexibility in subclasses

    @model_validator(mode="after")
    def initialize_agent(self) -> "BaseAgent":
        """Initialize agent with default settings if not provided."""
        if self.llm is None or not isinstance(self.llm, LLM):
            self.llm = LLM(config_name=self.name.lower())
        if not isinstance(self.memory, Memory):
            self.memory = Memory()
        return self

    @asynccontextmanager
    async def state_context(self, new_state: AgentState):
        """Context manager for safe agent state transitions.

        Args:
            new_state: The state to transition to during the context.

        Yields:
            None: Allows execution within the new state.

        Raises:
            ValueError: If the new_state is invalid.
        """
        if not isinstance(new_state, AgentState):
            raise ValueError(f"Invalid state: {new_state}")

        previous_state = self.state
        self.state = new_state
        try:
            yield
        except Exception as e:
            self.state = AgentState.ERROR  # Transition to ERROR on failure
            raise e
        finally:
            self.state = previous_state  # Revert to previous state

    def update_memory(
        self,
        role: ROLE_TYPE,  # type: ignore
        content: str,
        base64_image: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Add a message to the agent's memory.

        Args:
            role: The role of the message sender (user, system, assistant, tool).
            content: The message content.
            base64_image: Optional base64 encoded image.
            **kwargs: Additional arguments (e.g., tool_call_id for tool messages).

        Raises:
            ValueError: If the role is unsupported.
        """
        message_map = {
            "user": Message.user_message,
            "system": Message.system_message,
            "assistant": Message.assistant_message,
            "tool": lambda content, **kw: Message.tool_message(content, **kw),
        }

        if role not in message_map:
            raise ValueError(f"Unsupported message role: {role}")

        # Create message with appropriate parameters based on role
        kwargs = {"base64_image": base64_image, **(kwargs if role == "tool" else {})}
        self.memory.add_message(message_map[role](content, **kwargs))

    async def run(self, request: Optional[str] = None) -> str:
        """Execute the agent's main loop asynchronously.

        Args:
            request: Optional initial user request to process.

        Returns:
            A string summarizing the execution results.

        Raises:
            RuntimeError: If the agent is not in IDLE state at start.
        """
        if self.state != AgentState.IDLE:
            raise RuntimeError(f"Cannot run agent from state: {self.state}")

        if request:
            self.update_memory("user", request)

        results: List[str] = []
        async with self.state_context(AgentState.RUNNING):
            while (
                self.current_step < self.max_steps and self.state != AgentState.FINISHED
            ):
                self.current_step += 1
                logger.info(f"Executing step {self.current_step}/{self.max_steps}")
                step_result = await self.step()

                # Check for stuck state
                if self.is_stuck():
                    self.handle_stuck_state()

                results.append(f"Step {self.current_step}: {step_result}")

            if self.current_step >= self.max_steps:
                self.current_step = 0
                self.state = AgentState.IDLE
                results.append(f"Terminated: Reached max steps ({self.max_steps})")
        await SANDBOX_CLIENT.cleanup()
        return "\n".join(results) if results else "No steps executed"

    @abstractmethod
    async def step(self) -> str:
        """Execute a single step in the agent's workflow.

        Must be implemented by subclasses to define specific behavior.
        """

    def handle_stuck_state(self):
        """Handle stuck state by adding a prompt to change strategy
        and implementing recovery actions based on detected issues"""
        # First reset any previous prompt additions
        if hasattr(self, 'next_step_prompt') and self.next_step_prompt:
            original_prompt = getattr(self.__class__, 'next_step_prompt', "")
            self.next_step_prompt = original_prompt
        
        # Determine type of stuck state and add appropriate prompt
        stuck_prompt = ""
        if self.consecutive_empty_responses >= self.empty_response_threshold:
            stuck_prompt = "\
            Detected multiple empty responses. Please provide a simple analysis of what you can observe \
            from the available data. Focus on basic facts rather than complex analysis."
            # Reset counter after handling
            self.consecutive_empty_responses = 0
        elif self.consecutive_timeouts >= self.timeout_threshold:
            stuck_prompt = "\
            Detected multiple timeout errors. Please process the available information in smaller chunks \
            rather than attempting a comprehensive analysis at once."
            # Reset counter after handling
            self.consecutive_timeouts = 0
        else:
            stuck_prompt = "\
            Observed duplicate responses. Consider new strategies and avoid repeating ineffective paths already attempted."
            
        # Add the prompt
        self.next_step_prompt = f"{stuck_prompt}\n{self.next_step_prompt}"
        logger.warning(f"Agent detected stuck state. Added prompt: {stuck_prompt}")
        
        # Add a system message to provide more context
        if hasattr(self, 'memory') and self.memory:
            self.memory.add_message(Message.system_message(
                "The agent detected a potential loop or issue. Changing approach to simpler, more direct analysis."
            ))
            
            # If we have multiple timeouts/empty responses, try to simplify the analysis
            if self.consecutive_timeouts > 0 or self.consecutive_empty_responses > 0:
                # Add a more direct instruction
                self.memory.add_message(Message.system_message(
                    "Please provide a simple, concise analysis based on available information without further tool calls."
                ))

    def is_stuck(self) -> bool:
        """Check if the agent is stuck in a loop by detecting duplicate content,
        multiple empty responses, or consecutive timeouts"""
        # Not enough messages to be stuck
        if len(self.memory.messages) < 2:
            return False

        last_message = self.memory.messages[-1]
        
        # Check for empty responses
        if last_message.role == "assistant" and (not last_message.content or last_message.content.strip() == ""):
            self.consecutive_empty_responses += 1
            logger.warning(f"Detected empty response ({self.consecutive_empty_responses}/{self.empty_response_threshold})")
            if self.consecutive_empty_responses >= self.empty_response_threshold:
                return True
        else:
            self.consecutive_empty_responses = 0
        
        # Check for timeout indicators
        if last_message.role == "system" and "timeout" in last_message.content.lower():
            self.consecutive_timeouts += 1
            logger.warning(f"Detected timeout ({self.consecutive_timeouts}/{self.timeout_threshold})")
            if self.consecutive_timeouts >= self.timeout_threshold:
                return True
        else:
            self.consecutive_timeouts = 0

        # Count identical content occurrences (traditional loop detection)
        if last_message.content:
            duplicate_count = sum(
                1
                for msg in reversed(self.memory.messages[:-1])
                if msg.role == "assistant" and msg.content == last_message.content
            )
            if duplicate_count >= self.duplicate_threshold:
                return True

        return False

    @property
    def messages(self) -> List[Message]:
        """Retrieve a list of messages from the agent's memory."""
        return self.memory.messages

    @messages.setter
    def messages(self, value: List[Message]):
        """Set the list of messages in the agent's memory."""
        self.memory.messages = value
