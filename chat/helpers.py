import logging

from django.conf import settings

from chat.prompt_templates import prompts, items
from chat.llm import prompt_llm_messages
from chat.models import Strategy, Participant

import random

logger = logging.getLogger(__name__)

def strategies_to_prompt(strategies):
    prompt = ""
    for strategy, kwargs in strategies.items():
        prompt += items[strategy].format(**kwargs)
    return prompt

def get_last_active_bot(conversation):
    last_message = conversation.messages.filter(participant__participant_type="bot").order_by("timestamp").last()
    if last_message:
        return last_message.participant.bot 
    else:
        return [participant.bot for participant in conversation.participants.filter(participant_type="bot")][0]
        
def get_random_bot(conversation):
    last_message = conversation.messages.filter(participant__participant_type="bot").order_by("timestamp").last()
    if last_message:
        return last_message.participant.bot 
    else:
        return random.choice([participant.bot for participant in conversation.participants.filter(participant_type="bot")])

def detect_mention(bot_name, messages):
    mentionned = [msg for msg in messages if f"@{bot_name.lower()}" in msg.message.lower()]
    return False if len(mentionned)==0 else mentionned

def detect_human_mention(msg):
    humans = [participant.user.username for participant in Participant.objects.filter(participant_type="user")]
    for human in humans:
        if f"@{human.lower()}" in msg.message.lower(): return True
    return False
    
def detect_question(msg):
    message = {
        "role": "user" if msg.participant.participant_type == "user" else "assistant",
        "name": msg.participant.user.username if msg.participant.participant_type == "user" else msg.participant.bot.name,
        "content": msg.message,
    }
    bot_response = prompt_llm_messages(
        [message, {
            "role": "user",
            "name": "System",
            "content": prompts['is_question'],
        }], model=settings.MUCA["model"], temperature=settings.MUCA["temperature"])
    return judge_bot_determination(bot_response)


def judge_bot_determination(bot_response):
    if bot_response.lower().strip() == "yes" or bot_response.lower().strip() == "yes.":
        return True
    else:
        return False


def get_system_prompt(conversation, bot):
    system_prompt = prompts["bots_in_conversation"].format(
        bot_name=bot.name,
        list_of_bots=conversation.list_of_bots(),
        list_of_humans=conversation.list_of_humans(),
        bot_prompt=bot.prompt,
        core_memories=bot.get_core_memories_for_prompt(n_last_memories=settings.MAX_CORE_MEMORIES_PER_PROMPT),
    )

    return system_prompt

def estimate_delay(conversation):
    last_message = conversation.messages.order_by("timestamp").last()
    if not last_message: # no messages need to send message now
        return 0
    if last_message.participant.bot: # last message was from a bot, need to wait for the user's input
        return 5 # 5min
    else:
        return 0.5 # 30s to give the user a chance to expand on their message
    
def check_waiting(conversation, triggered_at):
    if not triggered_at:
        return True
    if conversation.messages.all().count() <= settings.WAITING_MESSAGE_NB:
        return False
    waiting_timestamp = conversation.messages.order_by("-timestamp")[settings.WAITING_MESSAGE_NB].timestamp
    return triggered_at <= waiting_timestamp