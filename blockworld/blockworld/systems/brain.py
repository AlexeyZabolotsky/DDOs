"""Минимальная нейросеть на блоках."""

from __future__ import annotations

from ursina import color


class BrainNetwork:
    def __init__(self, block_manager):
        self.block_manager = block_manager
        self.neurons = {}
        self.connections = {}
        self.activation_threshold = 0.5

    def add_neuron(self, block, neuron_type="hidden"):
        if not hasattr(block, "block_id"):
            return False
        bid = block.block_id
        self.neurons[bid] = {"type": neuron_type}
        block.block_data.setdefault("activation", 0.0)
        block.block_data["neuron_type"] = neuron_type
        colors = {"input": color.azure, "output": color.magenta, "hidden": color.lime}
        block.color = colors.get(neuron_type, color.lime)
        return True

    def add_connection(self, from_block, to_block, weight=1.0):
        if not hasattr(from_block, "block_id") or not hasattr(to_block, "block_id"):
            return False
        self.connections[(from_block.block_id, to_block.block_id)] = float(weight)
        return True

    def step(self):
        activations = {}
        for block in self.block_manager.blocks:
            bid = getattr(block, "block_id", None)
            if bid not in self.neurons:
                continue
            act = float(block.block_data.get("activation", 0.0))
            if self.neurons[bid]["type"] == "input" and getattr(block, "state", 0) == 1:
                act = 1.0
            activations[bid] = act
        new_act = dict(activations)
        for (fid, tid), w in self.connections.items():
            if fid in activations and tid in new_act:
                new_act[tid] = new_act.get(tid, 0) + activations[fid] * w
        for block in self.block_manager.blocks:
            bid = getattr(block, "block_id", None)
            if bid in self.neurons:
                raw = new_act.get(bid, 0)
                block.block_data["activation"] = 1.0 if raw >= self.activation_threshold else max(0, raw)
