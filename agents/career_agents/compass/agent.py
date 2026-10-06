"""The Compass conversation loop (Claude tool runner + web search)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from .. import config, llm
from .tools import CLIENT_TOOLS, SERVER_TOOLS

SYSTEM = """You are Compass: a candid chief of staff and strategist for one person, whose profile is below. You help them make high-stakes decisions about their career, where to live, immigration sequencing, caring for their parents and young child, building wealth, and eventually founding a company.

How you work:
- Lead with a clear recommendation, then the reasoning and the numbers. Quantify money, timelines and odds wherever you can, and say how confident you are.
- Use tools for numbers and facts: evaluate_offer and compare_locations for money and trade-offs (never do tax maths in your head), location_details for visa/parent/school facts, job_pipeline for what Scout has found.
- Immigration rules, visa bulletins, fees and draws change month to month. The knowledge base is dated; when a recommendation depends on a current rule, confirm it with web search and cite the source.
- Be honest when a goal is unrealistic on the stated timeline, and offer the strongest realistic version of it. Flattery wastes their time.
- At the start of a planning conversation, check read_notes. When the user makes a decision, sets a goal or commits to an action, record it with save_note.
- Keep answers tight: short paragraphs or bullets, a table when comparing options. No filler.

<profile>
{profile}
</profile>

<knowledge_base>
{knowledge}
</knowledge_base>"""


class Compass:
    def __init__(self, effort: str = "high", on_tool: Callable[[str], None] | None = None):
        self.effort = effort
        self.on_tool = on_tool or (lambda name: None)
        self.messages: list = []
        self.system = [
            {
                "type": "text",
                "text": SYSTEM.format(profile=config.profile_yaml(), knowledge=config.knowledge_text("relocation.md")),
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": f"Today's date: {date.today():%d %B %Y}."},  # after the cached prefix
        ]

    def ask(self, text: str) -> str:
        checkpoint = len(self.messages)
        try:
            return self._ask(text)
        except BaseException:
            del self.messages[checkpoint:]  # drop the failed turn so the conversation can continue
            raise

    def _ask(self, text: str) -> str:
        self.messages.append({"role": "user", "content": text})
        last = None
        for _ in range(6):  # restart the runner when a server-tool turn pauses (pause_turn)
            runner = llm.client().beta.messages.tool_runner(
                model=llm.model(),
                max_tokens=16000,
                system=self.system,
                tools=[*CLIENT_TOOLS, *SERVER_TOOLS],
                messages=self.messages,
                output_config={"effort": self.effort},
                **llm.FALLBACK_KWARGS,
            )
            for message in runner:
                last = message
                for block in message.content:
                    if block.type in ("tool_use", "server_tool_use"):
                        self.on_tool(block.name)
                # The runner keeps its own history; mirror it so the next turn has full context.
                self.messages.append({"role": "assistant", "content": message.content})
                tool_response = runner.generate_tool_call_response()
                if tool_response is not None:
                    self.messages.append(tool_response)
            if last is None or last.stop_reason != "pause_turn":
                break
        if last is None:
            return ""
        llm.check_refusal(last)
        return llm.text_of(last)
