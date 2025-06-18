import logging
import os
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from collections import Counter
from itertools import chain

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

def get_metrics_baseline(conversation_dict):
    metrics = {
        "Avg words/conv: ": engt_words_conv(conversation_dict, baseline=True),
        "Avg words/utterance: ": engt_words_utt(conversation_dict, baseline=True),
        "Evenness: ": evenness(conversation_dict, baseline=True),
    }
    logger.info("[INFO] Updated metrics")
    return metrics
        

def engt_words_conv(conversation, baseline=False):
    """Average number of words exchanged per conversation"""
    if baseline:
        messages = list(chain.from_iterable(conversation.values()))
        word_count = [len(msg["content"].split()) for msg in messages]
    else:
        messages = conversation.messages.filter(participant__participant_type="bot")
        word_count = [len(msg.message.split()) for msg in messages]
    return int(np.sum(word_count))

def engt_words_utt(conversation, baseline=False):
    """Average number of words per utterance """
    if baseline:
        messages = list(chain.from_iterable(conversation.values()))
        word_count = [len(msg["content"].split()) for msg in messages]
    else:
        messages = conversation.messages.filter(participant__participant_type="bot")
        word_count = [len(msg.message.split()) for msg in messages]
    return round(float(np.mean(word_count)), 2)

def evenness(conversation, baseline=False):
    """Evenness is assessed by calculating the sample standard deviation 
    (STD) of the word count input by each participant, expressed as a percentage of the mean."""
    word_counts = {}
    if baseline:
        messages = list(chain.from_iterable(conversation.values()))
    else:
        messages = conversation.messages.all()
    for msg in messages:
        participant = msg["name"] if baseline else msg.participant
        if not participant:
            continue
        if baseline:
            word_counts.setdefault(participant, 0)
            word_counts[participant] += len(msg["content"].split())
        else:
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
        "Feel pressured to respond",
        "Feel embarrassed or isolated",
        "Feel annoyed or attacked",
        "Feel comfortable to chat"
    ],
    "humanness": [
        "Yes",
        "No"
    ]
}

EVALUATION_SCORES_METRICS = ["conciseness", "usefulness", "purposefulness"]

RATING_OPTIONS = {
    "Very Good": 100,
    "Good": 75,
    "Fair": 50,
    "Poor": 25,
    "Very Poor": 0
}

def plot(data, path):
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
    ax.set_yticks(sorted(set(counts)))

    # Add legend on the side
    legend_elements = [
        plt.Line2D([0], [0], marker='s', color='w', label=cat,
                   markerfacecolor=colors[i], markersize=12)
        for i, cat in enumerate(categories)
    ]
    ax.legend(handles=legend_elements, loc='center left', bbox_to_anchor=(1, 0.5))

    plt.tight_layout()
    plt.savefig(path)
    
def compute_percentages(labels):
    """Compute percentage for each rating category."""
    count = Counter(labels)
    total = sum(count.values())
    return {key: (count.get(key, 0) / total) * 100 for key in RATING_OPTIONS.keys()}

def plot_evaluation_scores(data_dict, path):
    keys = list(RATING_OPTIONS.keys())
    n = len(data_dict)
    
    # Generate colors using colormap
    cmap = cm.get_cmap('tab20', len(keys))
    color_map = {key: cmap(i) for i, key in enumerate(keys)}

    # Prepare figure
    fig, ax = plt.subplots(figsize=(8, 1.2 * len(keys)))

    for i, (item_label, ratings) in enumerate(data_dict.items()):
        percentages = compute_percentages(ratings)

        left_keys = ["Very Good", "Good"]
        center_key = "Fair"
        right_keys = ["Poor", "Very Poor"]

        y_pos = n - 1 - i  # top-down
        
        center_width = percentages.get(center_key, 0)
        
        start = center_width/2
        for key in reversed(left_keys):
            width = percentages[key]
            ax.barh(y_pos, -width, left=-start, color=color_map[key])
            start += width
        
        ax.barh(y_pos, center_width, left=-center_width / 2, color=color_map[center_key])

        start = center_width/2
        for key in right_keys:
            width = percentages[key]
            ax.barh(y_pos, width, left=start, color=color_map[key])
            start += width

    # Format axis
    ax.set_xlim(-100, 100)
    ax.set_xticks([-100, 0, 100])
    ax.set_xticklabels(['100%', '0%', '100%'])
    ax.set_yticks(range(n))
    ax.set_yticklabels(list(reversed(list(data_dict.keys()))))
    ax.axvline(0, color='black', linewidth=1)
    ax.set_title("Evaluation Scores")

    # Legend
    legend_handles = [
        plt.Rectangle((0, 0), 1, 1, color=color_map[key]) for key in keys
    ]
    ax.legend(legend_handles, keys, bbox_to_anchor=(1.05, 1), loc='upper left')

    plt.tight_layout()
    plt.savefig(path)
    
def get_conversation_dict(conversation):
    messages = conversation.messages.order_by("timestamp")
    conversation_dict = {}
    current_key = None
    
    for message in messages:
        if message.participant.participant_type == "user":
            user_message = {
                "role": "user",
                "name": message.participant.user.username,
                "content": message.message
            }
            current_key = json.dumps(user_message)
            conversation_dict[current_key] = []
        elif message.participant.participant_type == "bot" and current_key:
            msg = {
                "role": "user",
                "name": message.participant.bot.name,
                "content": message.message
            }
            conversation_dict[current_key].append(msg)
    
    return conversation_dict

def run_baseline(conversation):
    """
    Returns a dictionary where keys are user messages and values are lists of each bot's response at that turn.
    """
    user_messages = conversation.messages.filter(participant__participant_type="user").order_by("timestamp")
    baseline_conversation = {}
    
    for message in user_messages:
        msg = {
            "role": "user",
            "name": message.participant.user.username,
            "content": message.message,
        }
        messages = [msg, (
            {
                "role": "user",
                "name": "System",
                "content": prompts["baseline"].format(
                    #context=conversation.settings.context,
                    strategies=items["strategies"],
                    bots=[participant.bot.name for participant in conversation.participants.filter(participant_type="bot")]
                ),
            }
        )]
        baseline_response = prompt_llm_messages(messages, model=settings.MUCA["model"], temperature=settings.MUCA["temperature"])
        
        bot_responses = []
        baseline_response = baseline_response.split("\n")
        for response in baseline_response:
            if response == '':
                continue
            response = response.split(":", 1)
            if response[1]!="":
                baseline_msg = {
                    "role": "user",
                    "name": response[0],
                    "content": response[1]
                }
                bot_responses.append(baseline_msg)
        baseline_conversation[json.dumps(msg)] = bot_responses
    return baseline_conversation
    
def evaluate_per_message(conversation_dict, conversation, metric):
    options = METRICS_OPTIONS[metric]
    ratings_count = dict.fromkeys(options, 0)
    
    for msg, bot_responses in conversation_dict.items():
        msg = json.loads(msg)
        messages = [msg] + bot_responses
        messages.append(
            {
                "role": "user",
                "name": "System",
                "content": prompts["evaluation"].format(
                    context=conversation.settings.context, 
                    metric=items[metric], 
                    options = options,
                    bots=[participant.bot.name for participant in conversation.participants.filter(participant_type="bot")]
                ),
            }
        )
    
        bot_response = prompt_llm_messages(messages, model=settings.MUCA["model"], temperature=settings.MUCA["temperature"])
        bot_response = bot_response.strip('\'"')
        bot_response = bot_response.strip(".")
        if bot_response is False:
            return False
        else:
            ratings_count[bot_response] += 1
            
    return ratings_count

def evaluate_overall(conversation_dict, conversation, metric):
    messages = list(chain.from_iterable(conversation_dict.values()))
    
    messages.append(
        {
            "role": "user",
            "name": "System",
            "content": prompts["overall_evaluation"].format(
                context=conversation.settings.context, 
                metric=items[metric], 
                options = list(RATING_OPTIONS.keys()),
            ),
        }
    )
    bot_response = prompt_llm_messages(messages, model=settings.MUCA["model"], temperature=settings.MUCA["temperature"])
    bot_response = bot_response.strip('\'"')
    
    return bot_response

def evaluate_user_study(conversation, baseline=False):
    """Evaluates the framwork's capacity to: 
        - have the bots chime-in at the correct time
        - have the bots chime-in with the correct content
        - have a balanced participation across users
        - 
    """
    folder_path = f"evaluation_data/conv_{conversation.id}"
    os.makedirs(folder_path, exist_ok=True)
    
    if baseline:
        data = run_baseline(conversation)
        metrics = get_metrics_baseline(data)
        file_path = os.path.join(folder_path, f"metrics_baseline.json")
    else:
        data = get_conversation_dict(conversation)
        metrics = get_metrics(conversation)
        file_path = os.path.join(folder_path, f"metrics.json")
        
    with open(file_path, "w") as f:
        json.dump(metrics, f)
            
    for metric in METRICS_OPTIONS.keys():
        ratings = evaluate_per_message(data, conversation, metric)
        file_name = f"{metric}_baseline_plot.png" if baseline else f"{metric}_polybot_plot.png"
        plot(ratings, path=os.path.join(folder_path, file_name))
    
    evaluation_scores = {metric:[] for metric in EVALUATION_SCORES_METRICS}
    for metric in EVALUATION_SCORES_METRICS:
        for _ in range(settings.EVALUATIONS):
            rating = evaluate_overall(data, conversation, metric)
            evaluation_scores[metric].append(rating)
    file_name = "evaluation_scores_baseline_plot.png" if baseline else "evaluation_scores_polybot_plot.png"
    plot_evaluation_scores(evaluation_scores, path=os.path.join(folder_path, file_name))