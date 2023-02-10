import discord
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Bot(intents=intents)


@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')


class DeleteModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs) -> None:
        self.view = kwargs.pop('view')
        kwargs['title'] = kwargs.get('title', '⚠️Are you sure?⚠️')
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="Enter \"DELETE\""))

    async def callback(self, interaction):
        await interaction.response.defer()
        if (self.children[0].value == "DELETE"):
            await self.view.delete(interaction)


class DateModal(discord.ui.Modal):
    def __init__(self, *args, **kwargs) -> None:
        self.view = kwargs.pop('view')
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.InputText(label="Date \"%d:%m:%Y\"",
                      value=datetime.now().strftime("%d:%m:%Y")))
        self.add_item(discord.ui.InputText(label="Time \"%H:%M\"",
                      value=datetime.now().strftime("%H:%M")))

    async def callback(self, interaction):
        await self.on_callback(interaction, self.children[0].value, self.children[1].value)


class AddDateModal(DateModal):
    async def on_callback(self, interaction, date, time):
        await self.view.add_option(interaction, date, time)


class RemoveDateModal(DateModal):
    async def on_callback(self, interaction, date, time):
        await self.view.remove_option(interaction, date, time)


empty_option = discord.SelectOption(
    label="Empty", description="Press \"📅Add date\"")


class ScheduleView(discord.ui.View):
    def __init__(self, *args, **kwargs) -> None:
        self.name = kwargs.pop('name')
        self.description = kwargs.pop('description')
        self.voice_channel = kwargs.pop('voice_channel')
        self.event = None
        self.options = []
        self.required_votes = kwargs.pop('required_votes')  # TODO via arg
        super().__init__(*args, **kwargs)

    def set_thread(self, thread):
        self.thread = thread

    async def delete(self, interaction):
        await interaction.followup.send(f"{interaction.user.mention} cancelled event")
        if self.event:
            await self.event.delete()
        if self.thread:
            await self.thread.delete()
        await interaction.message.delete()

    async def vote(self, interaction, votes):
        for o in self.options:
            user = interaction.user.name
            date = f"{o['date']} at {o['time']}"
            if date in votes:
                if user in o['votes']:
                    o['votes'].remove(user)
                    await self.thread.send(f"{interaction.user.mention} \"{date}\" 👎")
                else:
                    o['votes'].append(user)
                    await self.thread.send(f"{interaction.user.mention} \"{date}\" 👍")
        await self.apply_changes(interaction)

    async def add_option(self, interaction, date, time):
        await self.thread.send(f"@everyone, new date \"{date} at {time}\" by {interaction.user.mention}")
        self.options.append({'date': date, 'time': time, 'votes': []})
        await self.apply_changes(interaction)

    async def remove_option(self, interaction, date, time):
        for o in self.options:
            if o['date'] == date and o['time'] == time:
                await self.thread.send(f"@everyone, date removed \"{date} at {time}\" by {interaction.user.mention}")
                self.options.remove(o)
                break
        await self.apply_changes(interaction)

    async def apply_changes(self, interaction):
        global empty_option
        select = self.get_item('select')
        if len(self.options) > 0:
            self.options = list(
                sorted(self.options, key=lambda o: len(o['votes']), reverse=True))
            select.options = list(map(lambda o: discord.SelectOption(
                label=f"{o['date']} at {o['time']}",
                description=f"[{len(o['votes'])}/{self.required_votes}] {', '.join(o['votes'])}"
            ), self.options))
        else:
            select.options = [empty_option]
        select.max_values = max(1, len(select.options))
        await interaction.response.edit_message(view=self)

        if len(len(self.options) > 0 and self.options[0]['votes']) >= self.required_votes:
            guild = self.message.guild
            date = f"{self.options[0]['date']} at {self.options[0]['time']}"
            self.get_item("remove_button").disabled = True
            self.get_item("add_button").disabled = True
            select.disabled = True
            self.message.embeds[0].add_field(name="Time", value=date)
            await self.thread.send(f"@everyone ✨✨✨\"{date}\"✨✨✨")
            await self.message.edit(view=self, embeds=self.message.embeds)
            self.event = await guild.create_scheduled_event(
                name=self.name,
                privacy_level=discord.ScheduledEventPrivacyLevel.guild_only,
                location=([v for v in guild.voice_channels if v.name ==
                          self.voice_channel] + [guild.voice_channels[0]])[0],
                description=self.voice_channel,
                start_time=datetime.strptime(
                    date, "%d:%m:%Y at %H:%M") - timedelta(hours=2),
                # TODO oh........... bl thats dumb
                end_time=datetime.now() + timedelta(hours=3))

    @discord.ui.button(custom_id="cancel_button", label="Cancel event", style=discord.ButtonStyle.danger, emoji="💩")
    async def cancel_callback(self, button, interaction):
        await interaction.response.send_modal(DeleteModal(view=self))

    @discord.ui.button(custom_id="remove_button", label="Remove date", style=discord.ButtonStyle.secondary, emoji="❌")
    async def remove_date_callback(self, button, interaction):
        await interaction.response.send_modal(RemoveDateModal(title=" Remove date", view=self))

    @discord.ui.button(custom_id="add_button", label="Add date", style=discord.ButtonStyle.primary, emoji="📅")
    async def add_date_callback(self, button, interaction):
        await interaction.response.send_modal(AddDateModal(title="Add date", view=self))

    @discord.ui.select(custom_id="select", min_values=0, placeholder="Choose Date!!!", options=[empty_option])
    async def select_callback(self, select, interaction):
        await self.vote(interaction, select.values)


@bot.slash_command(description="Start scheduling new event")
@discord.option("event", description="Enter event's name")
@discord.option("required_votes", description="Amount of votes required to schedule event", min_value=0, default=0)
@discord.option("description", description="Description of the event", min_length=20, required=False)
@discord.option("voice_channel", description="Voice channel for event", required=False)
async def schedule(ctx: discord.ApplicationContext, event: str, required_votes: int, description: str, voice_channel: str):
    embed = discord.Embed(
        title=f"***{event}***",
        type='rich',
        description="`🎤🎤🎤            voice chat event            🎤🎤🎤`",
        color=discord.Colour.blurple()
    )
    if description:
        embed.add_field(name="Description", value=description)
    await ctx.respond("Creating new event...", delete_after=1)
    if required_votes == 0:
        required_votes = len(
            list(filter(lambda u: not u.bot, ctx.guild.members)))
    view = ScheduleView(name=event,
                        required_votes=required_votes,
                        description=description,
                        voice_channel=voice_channel,
                        timeout=604800.0)
    message = await ctx.send(f"@everyone!!! {ctx.author.mention} created new event", embed=embed, view=view)
    thread = await message.create_thread(name=event, auto_archive_duration=10080)
    view.set_thread(thread)

bot.run(os.environ["TOKEN"])
