# npc.py
# handles npc behavior, ticking, barking, and contagion emission

import json
import random
import brain_logic

from mind_bridge import build_prompt_from_mind
from settings import (
    INTERACT_RANGE,
    BARK_RANGE,
    NPC_TICK_RATE_FAR,
    NPC_TICK_RATE_MID,
    NPC_TICK_RATE_CLOSE,
    CONTAGION_FEAR_GAIN,
    CONTAGION_STRESS_GAIN,
    CONTAGION_CURIOSITY_GAIN,
    CONTAGION_TRUST_GAIN,
    CONTAGION_FEAR_THRESHOLD,
    CONTAGION_STRESS_THRESHOLD,
    CONTAGION_CURIOSITY_THRESHOLD,
    CONTAGION_TRUST_THRESHOLD,
    CONTAGION_EMIT_COOLDOWN,
    CONTAGION_EMIT_CHANCE,
)


class NPC:
    def __init__(self, name, node, faction="kalchakra"):
        self.name = name                       # npc display/debug name
        self.node = node                       # Panda3D node in the world
        self.faction = faction                 # faction id string

        self.mind = brain_logic.NpcMind(name)  # Rust brain object
        self.tick_timer = 0.0                  # timer for cheap LOD brain ticks
        self.contagion_cooldown = 0.0          # timer that limits contagion spam
        self.last_bark = None                  # stores previous bark to reduce repeats

        # load faction json once on startup
        with open(f"data/factions/{faction}.json") as f:
            self.faction_data = json.load(f)

    # ============================================================
    # POSITION HELPER
    # small wrapper so other systems do not touch self.node directly
    # ============================================================
    def get_pos(self):
        return self.node.getPos()

    # ============================================================
    # LOD HELPER
    # decides how often this npc should think based on player distance
    # ============================================================
    def get_lod_mode(self, player_pos):
        npc_pos = self.get_pos()                      # current npc world position
        distance = (npc_pos - player_pos).length()   # distance from player to npc

        if distance < INTERACT_RANGE:
            return "close", NPC_TICK_RATE_CLOSE      # player is near, think often
        elif distance < BARK_RANGE:
            return "mid", NPC_TICK_RATE_MID          # middle distance, medium ticking
        else:
            return "far", NPC_TICK_RATE_FAR          # far away, cheap slow ticking

    # ============================================================
    # BARK CHOICE
    # picks one bark line while avoiding immediate repetition
    # ============================================================
    def choose_bark(self):
        barks = self.faction_data["barks"]           # bark lines from faction json

        if not barks:
            return "..."                             # safe fallback if list is empty

        # remove last bark from choices so the npc does not repeat instantly
        choices = [b for b in barks if b != self.last_bark]

        if not choices:
            choices = barks                          # if all filtered out, use full list

        bark = random.choice(choices)                # choose one bark randomly
        self.last_bark = bark                        # remember it for next time
        return bark

    # ============================================================
    # FACTION BIAS
    # faction slowly nudges the rust emotional values after each tick
    # ============================================================
    def apply_faction_bias(self):
        bias = self.faction_data["emotion_bias"]     # dict like fear/stress/curiosity/trust

        for key, value in bias.items():
            self.mind.nudge(key, value)              # Rust handles clamp/storage

    # ============================================================
    # CONTAGION EMISSION
    # returns a tiny packet if this npc should socially influence others
    # returns None if nothing should be emitted right now
    # ============================================================
    def maybe_emit_contagion(self):
        # --------------------------------------------------------
        # cooldown gate
        # if cooldown is still active, this npc is not allowed
        # to emit contagion yet
        # --------------------------------------------------------
        if self.contagion_cooldown > 0.0:
            return None

        # read current emotional values directly from the Rust brain
        fear = self.mind.fear
        stress = self.mind.stress
        curiosity = self.mind.curiosity
        trust = self.mind.trust
        topic = self.mind.active_topic

        # --------------------------------------------------------
        # fear packet
        # if fear is high enough, sometimes emit fear contagion
        # --------------------------------------------------------
        if fear >= CONTAGION_FEAR_THRESHOLD:
            if random.random() < CONTAGION_EMIT_CHANCE:
                self.contagion_cooldown = CONTAGION_EMIT_COOLDOWN
                return {
                    "source_name": self.name,
                    "emotion": "fear",
                    "intensity": CONTAGION_FEAR_GAIN,
                    "topic": topic,
                }

        # --------------------------------------------------------
        # stress packet
        # --------------------------------------------------------
        if stress >= CONTAGION_STRESS_THRESHOLD:
            if random.random() < CONTAGION_EMIT_CHANCE:
                self.contagion_cooldown = CONTAGION_EMIT_COOLDOWN
                return {
                    "source_name": self.name,
                    "emotion": "stress",
                    "intensity": CONTAGION_STRESS_GAIN,
                    "topic": topic,
                }

        # --------------------------------------------------------
        # curiosity packet
        # --------------------------------------------------------
        if curiosity >= CONTAGION_CURIOSITY_THRESHOLD:
            if random.random() < CONTAGION_EMIT_CHANCE:
                self.contagion_cooldown = CONTAGION_EMIT_COOLDOWN
                return {
                    "source_name": self.name,
                    "emotion": "curiosity",
                    "intensity": CONTAGION_CURIOSITY_GAIN,
                    "topic": topic,
                }

        # --------------------------------------------------------
        # trust packet
        # --------------------------------------------------------
        if trust >= CONTAGION_TRUST_THRESHOLD:
            if random.random() < CONTAGION_EMIT_CHANCE:
                self.contagion_cooldown = CONTAGION_EMIT_COOLDOWN
                return {
                    "source_name": self.name,
                    "emotion": "trust",
                    "intensity": CONTAGION_TRUST_GAIN,
                    "topic": topic,
                }

        # no emotion passed the checks this tick
        return None

    # ============================================================
    # CONTAGION RECEIVE
    # called by world when another npc affects this one
    # ============================================================
    def receive_contagion(self, emotion, intensity, topic):
        self.mind.apply_contagion(emotion, intensity, topic)

    # ============================================================
    # MAIN UPDATE
    # runs every frame
    #
    # returns:
    #   None          -> no contagion emitted
    #   dict packet   -> world should spread contagion to nearby npcs
    # ============================================================
    def update(self, player_pos, dt):
        mode, tick_rate = self.get_lod_mode(player_pos)  # choose lod mode for this frame

        self.tick_timer += dt                            # advance brain tick timer

        # slowly count down contagion cooldown every frame
        if self.contagion_cooldown > 0.0:
            self.contagion_cooldown -= dt

        # if not enough time has passed, skip expensive brain work
        if self.tick_timer < tick_rate:
            return None

        # enough time has passed, so do one Rust brain tick
        self.tick_timer = 0.0
        self.mind.tick()

        # after ticking, apply faction flavor
        self.apply_faction_bias()

        # read packet from Rust for debug / prompt building
        dominant, sub, topic, thoughts, memory, speech = self.mind.get_bridge_packet()

        # cheap bark output
        bark = self.choose_bark()
        print(f"[{mode}] {self.name} ({self.faction_data['name']}) | {bark}")

        # only build prompt when player is close
        if mode == "close":
            prompt = build_prompt_from_mind(self.mind)

            print("\n--- PROMPT ---")
            print(prompt)

        # ask if this npc should emit one contagion packet now
        contagion_packet = self.maybe_emit_contagion()

        return contagion_packet
