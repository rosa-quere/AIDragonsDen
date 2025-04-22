from django_q.tasks import async_task, fetch

from chat.llm import llm_conversation_title, llm_form_core_memories
from chat.models import Conversation
from chat.triggers import general, mention, summarize, encourage, transition, resolve, chime_in, indirect
from chat.bot import generate_best_message
from collections import defaultdict

import logging
import time

logger = logging.getLogger(__name__)

TRIGGER_TASKS = {
    "Mention": mention,
    "Indirect": indirect,
    "Summarize": summarize,
    "Encourage": encourage,
    "Transition": transition,
    "Resolve": resolve,
    "Chime-in": chime_in,
}

def update_conversation_titles():
    conversations = Conversation.objects.all()

    for conversation in conversations:
        try:
            if conversation.messages.last().timestamp > conversation.title_update_date or conversation.title is None:
                llm_conversation_title(conversation)
        except AttributeError:
            pass

    return True


def generate_messages(conversation_id):
    conversation = Conversation.objects.get(id=conversation_id)
    
    enabled_triggers = set(trigger.name for trigger in conversation.triggers.all())
    logger.info(f'triggers: {enabled_triggers}')
    
    task_ids = []
    for trigger in TRIGGER_TASKS.keys():
        if trigger in enabled_triggers:
            task = TRIGGER_TASKS[trigger]
            task_id = async_task(task, conversation)
            task_ids.append(task_id)
    
    responses = defaultdict(list)
    for task_id in task_ids:
        for _ in range(20):
            time.sleep(0.5)
            result = fetch(task_id)
            if result is not None:
                if isinstance(result, dict):
                    for bot, response in result.items():
                        if response and isinstance(response, str):
                            responses[bot].append(response)
                break
    if not responses:
        logger.info(f'No responses returned for conversation {conversation_id}')
        return
    for bot, results in responses.items():
        generate_best_message(conversation, bot, results)

def generate_core_memories(conversation):
    bots = [participant.bot for participant in conversation.participants.filter(participant_type="bot")]
    for bot in bots:
        llm_form_core_memories(conversation, bot)
