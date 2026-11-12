"""Local language-arm train loop (numpy). No network."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

from agent.language.dataset import Example, from_trajectories, split_hold, synthesize
from agent.language.tokenizer import ArmTokenizer
from agent.language.transformer import (
    ACTION_ORDER,
    DecoderTransformer,
    MODEL_VERSION,
    hashed_ngrams,
)

# NOTE: remainder of train.py is large; this placeholder is replaced below.
