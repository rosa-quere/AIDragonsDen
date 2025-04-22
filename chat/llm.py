import json
import logging
import time

#import openai
import mistralai
from django.conf import settings
from django.utils import timezone

from chat.models import LLMRequest
from chat.prompt_templates import prompts

logger = logging.getLogger(__name__)


def prompt_llm_messages(
    messages,
    model=settings.LLM["mistral_basic_model"],
    response_format=None,
    temperature=0.8,
):
    client = mistralai.Mistral(api_key=settings.MISTRAL_API_KEY)
    max_retries = settings.MAX_RETRIES
    retry_delay = settings.RETRY_DELAY
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.complete(
                model=settings.LLM["mistral_basic_model"],
                temperature=temperature,
                messages=messages,
                response_format=response_format,
            )

            bot_response = response.choices[0].message.content
            print(bot_response)
            # We store the last prompt/message
            LLMRequest.objects.create(
                model=model,
                temperature=temperature,
                request_type="llm_messages",
                prompt=messages[-1]["content"],
                response=bot_response,
                total_tokens=response.usage.total_tokens,
                completion_tokens=response.usage.completion_tokens,
            )
            return bot_response

        except mistralai.models.SDKError as e:
            if "429" in str(e) or "Too Many Requests" in str(e):
                logger.warning(f"[{attempt}/{max_retries}] Rate limit hit. Retrying in {retry_delay}s...")
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    continue
            logger.error(f"SDKError on attempt {attempt}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unhandled exception during LLM request (attempt {attempt}): {e}")
            return False
    
    # If all retries failed
    logger.error("Failed to complete LLM prompt after all retries.")
    return False


def llm_conversation_title(conversation):
    try:
        conversation_text = "\n".join([msg.message for msg in conversation.messages.all()])

        messages = [
            {
                "role": "system",
                "name": "system",
                "content": prompts["conversation_summary"].format(conversation_text=conversation_text),
            }
        ]

        bot_response = prompt_llm_messages(messages)

        # Santized bot response with only ASCII characters
        bot_response_sanitized = bot_response
        bot_response_sanitized = bot_response_sanitized.replace('"', "")
        bot_response_sanitized = "".join([i if ord(i) < 128 else " " for i in bot_response_sanitized])

        conversation.title = bot_response_sanitized
        conversation.title_update_date = timezone.now()
        conversation.save()

        return bot_response_sanitized
    except Exception as e:
        logger.error(f"Error generating conversation title: {e}")
        return conversation


def llm_form_core_memories(conversation, bot):
    if len(conversation.participants.filter(participant_type="bot")) == 0:
        return False

    # Only generate core memories if there are at least 5 messages in the conversation
    if len(conversation.messages.all()) < 5:
        logger.info(f"Conversation {conversation.uuid} has less than 5 messages, skipping core memory generation")
        return False

    conversation_text = "\n".join([f"{msg.participant.name()}: {msg.message}" for msg in conversation.messages.all()])

    messages = [
        {
            "role": "system",
            "name": "system",
            "content": prompts["core_memories"].format(conversation_text=conversation_text, bot_name=bot.name),
        }
    ]

    bot_response = prompt_llm_messages(messages, response_format={"type": "json_object"})

    try:
        core_memories = json.loads(bot_response)
        logger.info(f"{len(core_memories['core_memories'])} core memories generated for {bot.name}")
        for core_memory in core_memories["core_memories"]:
            bot.core_memories.create(memory=core_memory)

        return True
    except Exception as e:
        logger.error(f"Error generating core memories: {e}")
        return False
