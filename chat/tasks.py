from django_q.tasks import async_task, result, schedule
from django.conf import settings
from django.core.cache import cache

from chat.llm import llm_conversation_title, llm_form_core_memories
from chat.models import Conversation
from chat.strategies import fallback_chime, mention, summarize, encourage, transition, resolve, chime_in, indirect
from chat.bot import synthesize, post_message
from chat.helpers import estimate_delay
from collections import defaultdict
from django.utils import timezone


import logging
import time

logger = logging.getLogger(__name__)

STRATEGIES_TASKS = {
    "Mention": mention,
    "Indirect": indirect,
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

def run_strategies(conversation):
    enabled_strategy = set(strategy.name for strategy in conversation.strategies.all())
    task_ids = []
    responses = defaultdict(list)
    
    for strategy in STRATEGIES_TASKS.keys():
        if strategy in enabled_strategy:
            task = STRATEGIES_TASKS[strategy]
            task_id = async_task(task, conversation)
            task_ids.append(task_id)
    
    for task_id in task_ids:
        while True:
            time.sleep(0.5)
            res = result(task_id)
            if res is False:
                break
            if isinstance(res, dict):
                for bot, response in res.items():
                    if response and isinstance(response, str):
                        responses[bot].append(response)
                break
            
    logging.info(f'[INFO] Responses from strategies: {responses}')
    
    responses_dict = dict(responses) if responses else False
    logger.info(f'[INFO] Responses dict: {responses_dict}')
    return (conversation, responses_dict)


def generate_messages(conversation_id): 
    conversation = Conversation.objects.get(id=conversation_id)

    async_task("chat.tasks.run_strategies", conversation, hook="chat.tasks.synthesize_responses")
    
def synthesize_responses(task):
    conversation, responses_dict = task.result
    if responses_dict:
        for bot, results in responses_dict.items():
            synthesize(conversation, bot, results)
        return
    
    logger.info(f'[INFO] No responses returned for conversation {conversation.id}')
    
    delay = estimate_delay(conversation)
    
    logger.info(f'[INFO] Estimated delay: {delay}')
    
    schedule(
        "chat.strategies.fallback_chime",
        conversation.id,
        timezone.now().isoformat(),
        name=f"chime_fallback_{conversation.id}",
        schedule_type='O',
        minutes=delay / 60,  # Django Q uses minutes
    )
    
def generate_core_memories(conversation):
    bots = [participant.bot for participant in conversation.participants.filter(participant_type="bot")]
    for bot in bots:
        llm_form_core_memories(conversation, bot)
