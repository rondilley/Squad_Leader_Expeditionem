"""The tuned model agent family: the traces (FR-60), the fine-tune (FR-61), and the export (IR-08).

transformers reads its backend switches one time, at its first import, and then it imports
each backend library it finds installed. This project fine-tunes with torch. No flax model
and no TensorFlow model is in the path of FR-61, and no module here imports jax.

So a host with a broken jax, flax, or TensorFlow install breaks an import that this project
does not need. The owner's workstation on 2026-09-21 is such a host: the system Python has
jax 0.2.22 beside jaxlib 0.7.1, and jax 0.2.22 reads jaxlib.pocketfft, which jaxlib 0.7.1
does not have. The venv of this checkout has --system-site-packages, so it inherits the
pair, and the transformers import of the smoke run of TR-12 stopped there.

The package names the torch backend here, before the first import of transformers, because
this is the one module that every path to transformers goes through: finetune.py and
export.py are in it, and nothing else in the tree imports transformers or peft. Each switch
is a setdefault, so a value that the owner puts in the environment wins.
"""

from __future__ import annotations

import os

BACKEND_SWITCHES = {"USE_TORCH": "1", "USE_FLAX": "0", "USE_TF": "0"}


def torch_backend_only() -> dict[str, str]:
    """Name the torch backend of transformers. Give the switch values in the environment."""
    for name, value in BACKEND_SWITCHES.items():
        os.environ.setdefault(name, value)
    return {name: os.environ[name] for name in BACKEND_SWITCHES}


torch_backend_only()
