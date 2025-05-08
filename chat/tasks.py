from django_q.tasks import async_task
from django_q.models import Schedule

from chat.llm import llm_conversation_title, llm_form_core_memories
from chat.models import Conversation
from chat.strategies import mention, summarize, encourage, transition, resolve, chime_in, indirect
from chat.bot import synthesize, post_message, generate_strategy_message
from chat.helpers import estimate_delay, get_random_bot
from chat.dialog_analyzer import update_sub_topics_status, update_accumulative_summary
from django.utils import timezone
from datetime import timedelta

import random
import logging

logger = logging.getLogger(__name__)

STRATEGIES_TASKS = {
    "Summarize": summarize,
    "Encourage": encourage,
    "Transition": transition,
    "Resolve": resolve,
    "Chime-in": chime_in,
}

def update_conversation_title(conversation_id):
    conversation = Conversation.objects.get(id=conversation_id)
    
    try:
        if conversation.messages.last().timestamp > conversation.title_update_date or conversation.title is None:
            llm_conversation_title(conversation)
    except AttributeError:
        pass

    return True

def update_conversation_subtopics(conversation_id):
    conversation = Conversation.objects.get(id=conversation_id)
    try:
        if conversation.messages.last().timestamp > conversation.subtopics_updated_at or conversation.sub_topics.all() is None:
            update_sub_topics_status(conversation)
    except AttributeError:
        pass

    return True


def update_conversation_summary(conversation_id):
    conversation = Conversation.objects.get(id=conversation_id)
    try:
        if conversation.messages.last().timestamp > conversation.summary_update_date or conversation.summary is None:
            update_accumulative_summary(conversation)
    except AttributeError:
        pass

    return True

def reply(conversation):
    response = mention(conversation)
    logger.info(f"[IFNO] Mention response: {response}")
    if not response:
        response = indirect(conversation)
        logger.info(f"[IFNO] Indirect response: {response}")
    return response if response else False

def detect_triggers(conversation):
    enabled_strategies = set(strategy.name for strategy in conversation.strategies.all().exclude(name="Mention").exclude(name="Indirect"))
    strategies = {}
    for strategy in enabled_strategies:
        output = STRATEGIES_TASKS[strategy](conversation)
        
        if output is False:
            continue
        elif output is True:
            strategies[strategy] = {}
        elif isinstance(output, dict):
            strategies[strategy] = output

    return strategies

def generate_messages(conversation_id): 
    conversation = Conversation.objects.get(id=conversation_id)
    responses = reply(conversation)
    strategies = detect_triggers(conversation) #format: [{strategy.name : kwargs}]
    logger.info(f"[INFO] Detected triggers: {strategies}")
    random_bot = random.choice(list(responses.keys())) if responses else get_random_bot(conversation)
    
    response_strat = generate_strategy_message(conversation, random_bot, strategies) if strategies else None
    
    if responses:
        for bot, response_reply in responses.items():
            if response_strat and bot is random_bot:
                async_task(synthesize, conversation, bot, response_reply, response_strat)
            else:
                post_message(conversation, bot, response_reply)
        return
    
    if response_strat:
        post_message(conversation, random_bot, response_strat)
        return
    
    logger.info(f'[INFO] No responses returned for conversation {conversation.id}')
    
    delay = estimate_delay(conversation) # in minutes
    
    logger.info(f'[INFO] Estimated delay: {delay}')
    
    Schedule.objects.create(
        name=f"chime_fallback_{conversation.id}",
        func="chat.strategies.fallback_chime",
        args=f"{conversation.id}, '{timezone.now().isoformat()}'",
        schedule_type='O',
        next_run=timezone.now() + timedelta(minutes=delay)
    )
    
def generate_core_memories(conversation):
    bots = [participant.bot for participant in conversation.participants.filter(participant_type="bot")]
    for bot in bots:
        llm_form_core_memories(conversation, bot)