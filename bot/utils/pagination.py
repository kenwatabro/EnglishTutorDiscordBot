import discord
from typing import List, Optional


def chunk_lines_to_pages(lines: List[str], max_chars: int = 1900) -> List[str]:
    """Split lines into pages that respect Discord's ~2000 char limit.

    max_chars is kept a bit below 2000 for safety when adding headers, etc.
    """
    pages: List[str] = []
    current = ""
    for line in lines:
        # Ensure each line ends with a newline
        if not line.endswith("\n"):
            line = line + "\n"
        if len(current) + len(line) > max_chars:
            if current:
                pages.append(current)
            current = line
        else:
            current += line
    if current:
        pages.append(current)
    return pages


class SimplePaginator(discord.ui.View):
    """A simple button paginator for text pages.

    Only the original author can interact with the paginator.
    """

    def __init__(self, author_id: int, pages: List[str], timeout: Optional[float] = 120):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.pages = pages if pages else ["(no content)"]
        self.index = 0
        # Buttons
        self.prev_button = discord.ui.Button(label="Prev", style=discord.ButtonStyle.secondary)
        self.next_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary)
        self.stop_button = discord.ui.Button(label="Stop", style=discord.ButtonStyle.danger)
        self.prev_button.callback = self.on_prev
        self.next_button.callback = self.on_next
        self.stop_button.callback = self.on_stop
        self.add_item(self.prev_button)
        self.add_item(self.next_button)
        self.add_item(self.stop_button)
        self._update_button_states()

    def _update_button_states(self):
        self.prev_button.disabled = self.index <= 0
        self.next_button.disabled = self.index >= len(self.pages) - 1

    def current_content(self) -> str:
        footer = f"\n\n(Page {self.index + 1}/{len(self.pages)})"
        return self.pages[self.index] + footer

    async def _ensure_author(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("この操作は発行者だけができるよ！", ephemeral=True)
            return False
        return True

    async def on_prev(self, interaction: discord.Interaction):
        if not await self._ensure_author(interaction):
            return
        if self.index > 0:
            self.index -= 1
        self._update_button_states()
        await interaction.response.edit_message(content=self.current_content(), view=self)

    async def on_next(self, interaction: discord.Interaction):
        if not await self._ensure_author(interaction):
            return
        if self.index < len(self.pages) - 1:
            self.index += 1
        self._update_button_states()
        await interaction.response.edit_message(content=self.current_content(), view=self)

    async def on_stop(self, interaction: discord.Interaction):
        if not await self._ensure_author(interaction):
            return
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

