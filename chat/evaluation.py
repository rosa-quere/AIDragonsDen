import logging
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm

from django.conf import settings

from chat.llm import prompt_llm_messages
from chat.prompt_templates import prompts, items

logger = logging.getLogger(__name__)

def get_metrics(conversation):
    if conversation.messages.count() != 0:
        metrics = {
            "Avg words/conv: ": engt_words_conv(conversation),
            "Avg words/utterance: ": engt_words_utt(conversation),
            "Evenness: ": evenness(conversation),
        }
        logger.info("[INFO] Updated metrics")
        return metrics
        

def engt_words_conv(conversation):
    """Average number of words exchanged per conversation"""
    messages = conversation.messages.filter(participant__participant_type="bot")
    word_count = [len(msg.message.split()) for msg in messages]
    return int(np.sum(word_count))

def engt_words_utt(conversation):
    """Average number of words per utterance """
    messages = conversation.messages.filter(participant__participant_type="bot")
    word_count = [len(msg.message.split()) for msg in messages]
    return round(float(np.mean(word_count)), 2)

def evenness(conversation):
    """Evenness is assessed by calculating the sample standard deviation 
    (STD) of the word count input by each participant, expressed as a percentage of the mean."""
    word_counts = {}
    messages = conversation.messages.all()
    for msg in messages:
        participant = msg.participant
        if not participant:
            continue
        word_counts.setdefault(participant.id, 0)
        word_counts[participant.id] += len(msg.message.split())
    counts = list(word_counts.values())
    if not counts or np.mean(counts) == 0:
        return 0.0

    std = np.std(counts, ddof=1)
    mean = np.mean(counts)

    evenness = (std / mean) * 100
    return f"{mean}±{round(float(evenness), 2)}%"

METRICS_OPTIONS = {
    "timing": [
        "Chime-in at the wrong timing",
        "Chime-in excessively",
        "Chime-in insufficiently",
        "Chime-in at the right timing"
    ],
    "content": [
        "Repetition of information",
        "Irrelevant content",
        "Redundant questions",
        "Relevant but excessive contents",
        "Unverified or incorrect contents",
        "Appropriate contents"
    ],
    "participation": [
        "The chatbot did not ping anyone",
        "Not applicable",
        "Feel pressured to respond",
        "Feel embarrassed or isolated",
        "Feel annoyed or attacked",
        "Feel comfortable to chat"
    ],
}

RATING_OPTIONS = {
    "Very Good": 1.0,
    "Good": 0.75,
    "Fair": 0.5,
    "Poor": 0.25,
    "Very Poor": 0.0
}

def plot(data, title):
    categories = list(data.keys())
    counts = list(data.values())
    
    cmap = cm.get_cmap('tab20', len(categories))
    colors = [cmap(i) for i in range(len(categories))]
    
    # Plot
    fig, ax = plt.subplots(figsize=(8, 4))

    bars = ax.bar(range(len(categories)), counts, color=colors)

    # Axis labels
    ax.set_ylabel('Count')
    ax.set_xlabel('Options')
    ax.set_xticks([])
    ax.set_yticks([])

    # Title
    ax.set_title(title)

    # Add legend on the side
    legend_elements = [
        plt.Line2D([0], [0], marker='s', color='w', label=cat,
                   markerfacecolor=colors[i], markersize=12)
        for i, cat in enumerate(categories)
    ]
    ax.legend(handles=legend_elements, loc='center left', bbox_to_anchor=(1, 0.5))

    plt.tight_layout()
    plt.show()

def evaluate(conversation, metric):
    messages = conversation.messages.order_by("timestamp")
    options = METRICS_OPTIONS[metric]
    response_count = dict.fromkeys(options, 0)
    
    for i in range(1, messages.count()):
        list_messages = []
        if messages[i].participant.participant_type == "user":
            continue
        for msg in messages[:i+1]:
            list_messages.append(
                {
                    "role": "user",
                    "name": msg.participant.user.username if msg.participant.participant_type == "user" else msg.participant.bot.name,
                    "content": msg.message,
                }
            )
            #logger.info(f"[MSG] {msg.message}")
        list_messages.append(
            {
                "role": "user",
                "name": "System",
                "content": prompts["evaluation"].format(context=conversation.settings.context, metric=items[metric], options = options),
            }
        )
        #logger.info(f"[PROMPT] {prompts["evaluation"].format(metric=items[metric], options = options)}")
        bot_response = prompt_llm_messages(list_messages, model=settings.MUCA["model"], temperature=settings.MUCA["temperature"])
        bot_response = bot_response.strip('\'"')
        if bot_response is False:
            return False
        else:
            response_count[bot_response] += 1
    plot(response_count, metric)

def evaluate_overall(conversation, metric):
    messages = [
        {
                    "role": "user",
                    "name": msg.participant.user.username if msg.participant.participant_type == "user" else msg.participant.bot.name,
                    "content": msg.message,
                }
        for msg in conversation.messages.order_by("timestamp")
    ]
    
    messages.append(
        {
            "role": "user",
            "name": "System",
            "content": prompts["overall_evaluation"].format(context=conversation.settings.context, metric=items[metric], options = RATING_OPTIONS),
        }
    )
    
    responses = []
    for iter in range(settings.EVALUATIONS):
        bot_response = prompt_llm_messages(messages, model=settings.MUCA["model"], temperature=0.1*(iter+5))
        bot_response = bot_response.strip('\'"')
        if bot_response:
            responses.append(RATING_OPTIONS[bot_response])
    
    return round(float(np.mean(responses)), 2)
    

def evaluate_case_study(conversation):
    """Evaluates the framework's capacity to:
        - generate accurate, hallucination-free responses
        - correctly summarize and categorize users' opinions.
    """
    pass

def evaluate_user_study(conversation):
    """Evaluates the framwork's capacity to: 
        - have the bots chime-in at the correct time
        - have the bots chime-in with the correct content
        - have a balanced participation across users
        - 
    """
    for metric in METRICS_OPTIONS.keys():
        evaluate(conversation, metric)