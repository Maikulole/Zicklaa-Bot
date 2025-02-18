import asyncio
import logging
import time
from datetime import datetime
from discord import message

from discord.ext import commands
import discord
from discord.raw_models import RawReactionActionEvent

logger = logging.getLogger("ZicklaaBot.RemindMe")


class Reminder:
    def __init__(
        self, message_id, channel_id, user_id, text, time, id=None, parent_id=None
    ):
        self.message_id = message_id
        self.channel_id = channel_id
        self.user_id = user_id
        self.text = text
        self.time = time
        self._id = id
        self._parent_id = parent_id


def reminder_from_record(record):
    return Reminder(
        record[5], record[4], record[1], record[2], record[3], record[0], record[6]
    )


class RemindMe(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.cursor = db.cursor()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: RawReactionActionEvent):
        try:
            message_id, channel_id, emoji, user_id = self.parse_raw_reaction_event(
                payload)
            channel = self.bot.get_channel(channel_id)
            message = await channel.fetch_message(message_id)
            author_id = message.author.id

            if not self.is_reminder_message(message_id, author_id, emoji, user_id):
                return

            reminder = reminder_from_record(
                self.cursor.execute(
                    "SELECT * FROM reminders WHERE message_id=?", (message.id,)
                ).fetchone()
            )
            if reminder.user_id is user_id:
                return
            reminder._parent_id = reminder._id
            reminder._id = None
            reminder.message_id = -1
            reminder.user_id = user_id
            new_reminder = self.insert_reminder(reminder)
            return
        except Exception as e:
            logger.error("Remindme Fehler: " + e)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: RawReactionActionEvent):
        try:
            message_id, channel_id, emoji, user_id = self.parse_raw_reaction_event(
                payload)
            channel = self.bot.get_channel(channel_id)
            message = await channel.fetch_message(message_id)
            author_id = message.author.id

            if not self.is_reminder_message(message_id, author_id, emoji, user_id):
                return
            parent_reminder = reminder_from_record(
                self.cursor.execute(
                    "SELECT * FROM reminders WHERE message_id=?", (message.id,)
                ).fetchone()
            )
            if parent_reminder.user_id is user_id:
                return
            self.cursor.execute(
                "DELETE FROM reminders WHERE parent_id=? AND user_id=?",
                (parent_reminder._id, user_id),
            )
            self.db.commit()
        except Exception as e:
            logger.error("Remindme Fehler: " + e)

    def parse_raw_reaction_event(self, payload: RawReactionActionEvent):
        try:
            return payload.message_id, payload.channel_id, payload.emoji, payload.user_id
        except Exception as e:
            logger.error("Remindme Fehler: " + e)

    @commands.command()
    async def remindme(self, ctx, method: str, *text: str):
        # try:
        message = ctx.message
        unit_to_second = {
            "s": 1,
            "m": 60,
            "h": 60 * 60,
            "d": 60 * 60 * 24,
            "w": 60 * 60 * 24 * 7,
            "mon": 60 * 60 * 24 * 7 * 30,
        }
        if method == "all":
            await self.get_all_reminders(ctx)
            return
        elif method.isdigit():
            digits = method
            unit = text[0]
            reason = " ".join(text[1:])
        else:
            if "mon" in method:
                unit = "mon"
                digits = method[:-3]
            else:
                unit = method[-1]
                digits = method[:-1]
            print(digits)
            print(unit)
            reason = " ".join(text)
        print(digits)
        print(unit)
        reminder_time = round(
            time.time() + (float(int(digits) *
                                 int(unit_to_second[unit]))), 2
        )
        reminder = Reminder(
            message.id, ctx.channel.id, ctx.author.id, reason, reminder_time
        )
        reminder = self.insert_reminder(reminder)
        await message.add_reaction("\N{THUMBS UP SIGN}")
        return
        '''except Exception as e:
            await ctx.message.reply("Klappt nit lol 🤷")
            logger.error("Remindme Fehler wahrsch falsches Zeitformat?: " + e)'''

    '''async def wait_for_reminder(self, reminder: Reminder):
        try:
            if (reminder.time - time.time()) < 0:
                await self.send_reminder(reminder)
            else:
                logger.info("Nächster Reminder geladen: " + str(reminder._id))
                await asyncio.sleep(reminder.time - time.time())
                await self.send_reminder(reminder)
        except Exception as e:
            logger.error(e)'''

    async def check_reminder(self):
        try:
            while True:
                self.cursor.execute(
                    "SELECT * FROM reminders ORDER BY reminder_time ASC LIMIT 1")
                results = self.cursor.fetchall()
                reminder = reminder_from_record(results[0])
                if (reminder.time - time.time()) < 0:
                    await self.send_reminder(reminder)
                    await asyncio.sleep(1)
                else:
                    await asyncio.sleep(5)
        except Exception as e:
            logger.error(e)

    async def get_all_reminders(self, ctx):
        try:
            user_id = ctx.author.id
            all_reminders = self.cursor.execute(
                "SELECT * FROM reminders WHERE user_id=? ORDER BY reminder_time ASC",
                (user_id,),
            ).fetchall()
            if not all_reminders:
                await ctx.message.reply(
                    "Du hast keine Reminder, du Megabrain", mention_author=True
                )
            else:
                msg_text = "Ich werde dich demnächst wissen lassen:\n"
                for reminder in all_reminders:
                    remind_dt = datetime.fromtimestamp(reminder[3])
                    remind_date = remind_dt.date().strftime("%d-%b-%Y")
                    remind_time = remind_dt.time().strftime("%H:%M:%S")
                    text = reminder[2]
                    msg_text += "Am **{}** um **{}** werde ich dich wissen lassen, dass:\n**{}**\n\n".format(
                        remind_date, remind_time, text
                    )
                await ctx.message.reply(msg_text, mention_author=True)
        except Exception as e:
            logger.error("Remindme Fehler get_all_reminders(): " + e)

    def insert_reminder(self, reminder: Reminder):
        try:
            sql = "INSERT INTO reminders (user_id, reminder_text, reminder_time, channel, message_id, parent_id) VALUES (?, ?, ?, ?, ?, ?)"
            val = (
                reminder.user_id,
                reminder.text,
                reminder.time,
                reminder.channel_id,
                reminder.message_id,
                reminder._parent_id,
            )
            self.cursor.execute(sql, val)
            self.db.commit()
            self.cursor.execute(
                "SELECT id FROM reminders WHERE user_id=? AND reminder_text=? AND reminder_time=? AND message_id=?",
                (reminder.user_id, reminder.text,
                 reminder.time, reminder.message_id),
            )
            id = self.cursor.fetchall()[0][0]
            logger.info("Neuer Reminder in die DB gepusht: " + str(id))
            reminder._id = id
            return reminder
        except Exception as e:
            logger.error("Remindme Fehler insert_reminder(): " + e)

    async def send_reminder(self, reminder: Reminder):
        try:
            if not await self.check_reminder_exists(reminder):
                self.delete_reminder(reminder)
                return
            channel = self.bot.get_channel(reminder.channel_id)
            if reminder.message_id > 0:
                message = await channel.fetch_message(reminder.message_id)
                await message.reply(
                    "Ich werde dich wissen lassen:\n**{}**".format(
                        reminder.text),
                    mention_author=True,
                )
                logger.info("Auf Reminder geantortet: " + str(reminder._id))
            else:
                await channel.send(
                    "<@{}>: Ich werde dich wissen lassen:\n**{}**".format(
                        reminder.user_id, reminder.text
                    )
                )
                logger.info("Auf Reminder geantortet: " + str(reminder._id))
        except Exception as e:
            logger.error(f"Error while sending reminder: {e}")
        finally:
            self.delete_reminder(reminder)

    async def check_reminder_exists(self, reminder: Reminder):
        try:
            res = self.cursor.execute(
                "SELECT * FROM reminders where id=?", (reminder._id,)
            ).fetchone()
            if not res:
                return False
            if res[6] is not None:
                parent_reminder_record = self.cursor.execute(
                    "SELECT * FROM reminders where id=?", (res[6],)
                ).fetchone()
                if not parent_reminder_record:
                    return False
                try:
                    parent_reminder = reminder_from_record(
                        parent_reminder_record)
                    await self.bot.get_channel(parent_reminder.channel_id).fetch_message(
                        parent_reminder.message_id
                    )
                    return True
                except:
                    return False
            return True
        except Exception as e:
            logger.error("Remindme Fehler check_reminder_exists(): " + e)

    def is_reminder_message(self, message_id, author_id, emoji, user_id):
        try:
            all_reminder_ids = [
                x[0]
                for x in self.cursor.execute("SELECT message_id FROM reminders").fetchall()
            ]
            if (
                (message_id not in all_reminder_ids)
                or (str(emoji) != "\N{THUMBS UP SIGN}")
                or (user_id == self.bot.user.id)
                or (user_id == author_id)
            ):
                return False
            return True
        except Exception as e:
            logger.error("Remindme Fehler is_reminder_message(): " + e)

    def delete_reminder(self, reminder: Reminder):
        try:
            self.cursor.execute(
                "DELETE FROM reminders WHERE id=?", (reminder._id,))
            self.db.commit()
            logger.info("Reminder gelöscht: " + str(reminder._id))
        except Exception as e:
            logger.error("Remindme Fehler delete_reminder(): " + e)


def setup(bot):
    bot.add_cog(RemindMe(bot, bot.db))
