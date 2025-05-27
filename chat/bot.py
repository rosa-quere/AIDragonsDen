import logging

from django.conf import settings

from chat.helpers import get_system_prompt, strategies_to_prompt, judge_bot_determination, get_current_segment, has_participated, detect_human_mention
from chat.llm import prompt_llm_messages
from chat.models import Message
from chat.prompt_templates import prompts, items

logger = logging.getLogger(__name__)


def check_turn(conversation, bot):
    messages = list(conversation.messages.all())

    # Human goes first
    if len(messages) == 0:
        return False

    if len(messages) > 0:
        if not settings.DOUBLE_TEXTING and messages[-1].participant.bot and messages[-1].participant.bot.name == bot.name:
            logger.info("[INFO] Bot has already replied")
            return False

        # Make sure the user has replied enough times; but allow answers after a user has replied
        human_replies = [msg for msg in messages[-10:] if msg.participant.user]
        if len(human_replies) < settings.MIN_HUMAN_REPLIES_LAST_10 and len(messages) > settings.NEW_CHAT_GRACE and not messages[-1].participant.user:
            logger.info(f"[INFO] User has not replied enough times ({len(human_replies)} < {settings.MIN_HUMAN_REPLIES_LAST_10})")
            return False

        # bot_replies = [msg for msg in messages[-10:] if msg["name"] == bot.name]
        # if len(bot_replies) >= settings.MAX_THIS_BOT_REPLIES_LAST_10:
        #     logger.info(f"[INFO] Bot has replied too many times ({len(bot_replies)} >= {settings.MAX_THIS_BOT_REPLIES_LAST_10})")
        #     return False

    return True

def check_turn_indirect(conversation, bot):
    last_message = conversation.messages.order_by("timestamp").last()
    system_prompt = get_system_prompt(conversation, bot)
    messages = [{"role": "system", "name": "system", "content": system_prompt}]
    
    if conversation.settings and conversation.settings.context:
        messages.append({"role": "system", "name": "system", "content": conversation.settings.context})
        
    segment = get_current_segment(conversation)
    if segment:
        logger.info(f'[INFO] Segment: {segment.name}')
        messages.append({"role": "system", "name": "system", "content": segment.prompt})
        
    messages.append({
                "role": "user" if last_message.participant.participant_type == "user" else "assistant",
                "name": last_message.participant.user.username if last_message.participant.participant_type == "user" else last_message.participant.bot.name,
                "content": last_message.message,
            })
    
    if messages is False:
        return False
    messages.append(
        {
            "role": "user",
            "name": "System",
            "content": prompts["is_turn"].format(bot_name=bot.name),
        }
    )
    bot_response = prompt_llm_messages(messages, model=bot.model, temperature=bot.temperature)
    return judge_bot_determination(bot_response)
    

def check_message(new_message, bot):
    # Self-Referential @mention
    if not new_message:
        return False
    if f"@{bot.name.lower()}" in new_message.lower().strip():
        logger.info("[INFO] Self-referential response")
        return False
    else:
        return True

def set_up(conversation, bot, override_turn=False):
    if not override_turn:
        if not check_turn(conversation, bot):
            return False

    # Prepare the system message using the bot's prompt
    system_prompt = get_system_prompt(conversation, bot)
    messages = [{"role": "system", "name": "system", "content": system_prompt}]
    
    if conversation.settings and conversation.settings.context:
        messages.append({"role": "system", "name": "system", "content": conversation.settings.context})
        
    segment = get_current_segment(conversation)
    if segment:
        logger.info(f'[INFO] Segment: {segment.name}')
        messages.append({"role": "system", "name": "system", "content": segment.prompt})
        
    # Retrieve all messages for the conversation ordered by timestamp
    conversation_messages = Message.objects.filter(conversation=conversation).order_by("timestamp")

    # Convert each message into the format required by LLM
    for msg in conversation_messages:
        role = "user" if msg.participant.participant_type == "user" else "assistant"
        messages.append(
            {
                "role": role,
                "name": msg.participant.user.username if msg.participant.participant_type == "user" else msg.participant.bot.name,
                "content": msg.message,
            }
        )
    return messages

def synthesize(conversation, bot, reply, strat_response):
    # Prepare the system message using the bot's prompt
    system_prompt = get_system_prompt(conversation, bot)
    messages = [{"role": "system", "name": "system", "content": system_prompt}]
    
    if conversation.settings and conversation.settings.context:
        messages.append({"role": "system", "name": "system", "content": conversation.settings.context})
    
    segment = get_current_segment(conversation)
    if segment:
        logger.info(f'[INFO] Segment: {segment.name}')
        messages.append({"role": "system", "name": "system", "content": segment.prompt})

    role = "user"
    messages.append(
        {
            "role": role,
            "name": bot.name,
            "content": reply,
        }
    )
    messages.append(
        {
            "role": role,
            "name": bot.name,
            "content": strat_response,
        }
    )
    if messages is False:
        return False
    messages.append(
        {
            "role": "user",
            "name": "System",
            "content": prompts["combine_answers"].format(bot_name=bot.name),
        }
    )
    bot_response = prompt_llm_messages(messages, model=bot.model, temperature=bot.temperature)
    if not check_message(bot_response, bot):
        logger.info(f"[INFO][FINAL] Failed 'check_message' for {bot.name}. Bot response: {bot_response}")
        return False
    logger.info(f"[INFO][FINAL] Generating a new message as {bot.name}")
    return post_message(conversation, bot, bot_response)

def generate_strategy_message(conversation, bot, strategies):
    messages = set_up(conversation, bot)
    if messages is False:
        return False
    last_message = conversation.messages.order_by("timestamp").last()
    if detect_human_mention(last_message):
        logger.info(f"[INFO] Human Mention detected, not bot turn")
        return False
    strategies_list = strategies_to_prompt(strategies)
    messages.append(
        {
            "role": "user",
            "name": "System",
            "content": prompts["combine_strategies"].format(bot_name=bot.name, strategies_list=strategies_list),
        }
    )
    bot_response = prompt_llm_messages(messages, model=bot.model, temperature=bot.temperature)
    if not check_message(bot_response, bot):
        logger.info(f"[INFO][STRAT] Failed 'check_message' for {bot.name}. Bot response: {bot_response}")
        return False

    return bot_response

def generate_message(conversation, bot, strategy, override_turn=False, post=False, **kwargs):
    messages = set_up(conversation, bot, override_turn)
    if messages is False:
        return False
    introduction = items['Introduction'] if not has_participated(conversation, bot) else ''
    messages.append(
        {
            "role": "user",
            "name": "System",
            "content": prompts[strategy].format(bot_name=bot.name, if_intro=introduction, **kwargs),
        }
    )
    bot_response = prompt_llm_messages(messages, model=bot.model, temperature=bot.temperature)
    if not check_message(bot_response, bot):
        logger.info(f"[INFO][{strategy}] Failed 'check_message' for {bot.name}. Bot response: {bot_response}")
        return False
    if post: 
        post_message(conversation, bot, bot_response)
        logger.info(f"[INFO][{strategy}] Generating a new message as {bot.name}: {bot_response}")
    return bot_response

def post_message(conversation, bot, msg):
    Message.objects.create(
        conversation=conversation,
        participant=conversation.participants.get(bot__id=bot.id),
        message=msg,
    )