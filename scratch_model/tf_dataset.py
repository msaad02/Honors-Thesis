"""
This script creates a tensorflow dataset for the brockport-gpt-4-qa dataset to feed into the model.

This also does some preprocessing of the data, such as adding start and end tokens, and standardizing the text.
"""

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2' # stop showing tensorflow logs...
from datasets import load_dataset
import tensorflow as tf
import numpy as np

dataset = load_dataset("msaad02/brockport-gpt-4-qa")
dataset = dataset['train'].to_pandas()

prompt = lambda question, answer: f"""Below is an inquiery related to SUNY Brockport - from academics, admissions, and faculty support to student life. Prioritize accuracy and brevity.\n\n### Instruction:\n{question}\n\n### Response:\n{answer}"""

dataset = [prompt(question, answer) for question, answer in zip(dataset['question'], dataset['answer'])]

def split_input_output(s):
    """
    Splits a string into a question and answer pair
    """
    output_split = s.split('\n\n### Response:\n')
    input_split = output_split[0].split('### Instruction:\n')[1]
    return input_split, output_split[1]

def tf_lower_and_split_punct(text):
    """
    Text standardization function. Tries to make things uniform.
    """
    text = tf.strings.lower(text) # Lowercase everything
    text = tf.strings.regex_replace(text, '[^ a-z.?!,¿]', '') # Keep space, a to z and punctuation.
    text = tf.strings.regex_replace(text, '[.?!,¿]', r' \0 ') # Add spaces around punctuation.
    text = tf.strings.strip(text) # Strip whitespace.

    text = tf.strings.join(['[START]', text, '[END]'], separator=' ') # Add start and end token
    return text

def get_datasets(batch_size: int = 64):
    """
    Return train_ds, val_ds, and text_processor
    """
    context_raw, target_raw = [list(t) for t in zip(*[split_input_output(string) for string in dataset])]

    BUFFER_SIZE = len(context_raw)
    BATCH_SIZE = batch_size

    is_train_mask = np.random.uniform(size=(len(target_raw),)) < 0.8

    train_context = np.array(context_raw)[is_train_mask]
    train_target = np.array(target_raw)[is_train_mask]

    val_context = np.array(context_raw)[~is_train_mask]
    val_target = np.array(target_raw)[~is_train_mask]

    train_raw = (
        tf.data.Dataset
        .from_tensor_slices((train_context, train_target))
        .shuffle(BUFFER_SIZE)
        .batch(BATCH_SIZE)
    )
    val_raw = (
        tf.data.Dataset
        .from_tensor_slices((val_context, val_target))
        .shuffle(BUFFER_SIZE)
        .batch(BATCH_SIZE)
    )

    MAX_VOCAB_SIZE = 5000

    text_processor = tf.keras.layers.TextVectorization(
        standardize=tf_lower_and_split_punct,
        max_tokens=MAX_VOCAB_SIZE,
        ragged=True
    )

    text_processor.adapt(train_raw.map(lambda context, target: context))
    text_processor.adapt(train_raw.map(lambda context, target: target))

    def process_text(context, target):
        context = text_processor(context).to_tensor()
        target  = text_processor(target)
        targ_in = target[:,:-1].to_tensor()
        targ_out = target[:,1:].to_tensor()
        return (context, targ_in), targ_out

    train_ds = train_raw.map(process_text, tf.data.AUTOTUNE)
    val_ds = val_raw.map(process_text, tf.data.AUTOTUNE)

    return train_ds, val_ds, text_processor