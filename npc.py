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
)


class NPC:
    def __init__(self, name, node, faction="kalchakra"):
        self.name = name                       # display / debug name for this npc
        self.node = node                       # Panda3D node for world position / body
        self.faction = faction                 # save faction id for future logic

        self.mind = brain_logic.NpcMind(name)  # rust-powered cheap cognition object
        self.tick_timer = 0.0                  # accumulates time until next brain tick
        self.last_bark = None                  # prevents same bark twice in a row
        self.last_mode = None                  # used so we can detect lod changes later

        # load faction json once at startup
        with open(f"data/factions/{faction}.json") as f:
            self.faction_data = json.load(f)

    # ============================================================
    # BASIC POSITION HELPER
    # keeps position access in one place
    # ============================================================
    def get_pos(self):
        return self.node.getPos()

    # ============================================================
    # LOD HELPER
    # decides how "awake" the npc is based on player distance
    # ============================================================
    def get_lod_mode(self, player_pos):
        npc_pos = self.get_pos()                      # get this npc world position
        distance = (npc_pos - player_pos).length()   # distance from player to npc

        if distance < INTERACT_RANGE:
            return "close", NPC_TICK_RATE_CLOSE      # close = frequent ticking
        elif distance < BARK_RANGE:
            return "mid", NPC_TICK_RATE_MID          # mid = medium ticking
        else:
            return "far", NPC_TICK_RATE_FAR          # far = cheap slow ticking

    # ============================================================
    # CHOOSE BARK
    # cheap bark line from faction json without immediate repetition
    # ============================================================
    def choose_bark(self):
        barks = self.faction_data["barks"]           # read bark list from faction data

        if not barks:
            return "..."                             # safe fallback if list is empty

        # make a list excluding the previous bark to reduce repetition
        choices = [b for b in barks if b != self.last_bark]

        # if all lines were filtered out, fall back to the full bark list
        if not choices:
            choices = barks

        bark = random.choice(choices)                # choose one line at random
        self.last_bark = bark                        # store it so next tick can avoid it
        return bark

    # ============================================================
    # APPLY FACTION BIAS
    # faction gently nudges the rust emotion values every brain tick
    # ============================================================
    def apply_faction_bias(self):
        bias = self.faction_data["emotion_bias"]     # ex: fear/stress/curiosity/trust

        for key, value in bias.items():
            self.mind.nudge(key, value)              # let rust clamp and store the change

    # ============================================================
    # MAYBE EMIT CONTAGION
    # returns a tiny packet describing what this npc is leaking
    # returns None if no emotion is strong enough to spread
    # ============================================================
    def maybe_emit_contagion(self):
        # read current cheap scalar emotion values directly from rust
        fear = self.mind.fear
        stress = self.mind.stress
        curiosity = self.mind.curiosity
        trust = self.mind.trust
        topic = self.mind.active_topic

        # priority order matters
        # we choose one dominant outgoing contagion packet for simplicity
        # fear/stress first because they tend to feel more urgent
        if fear >= CONTAGION_FEAR_THRESHOLD:
            return {
                "source_name": self.name,
                "emotion": "fear",
                "intensity": CONTAGION_FEAR_GAIN,
                "topic": topic,
            }

        if stress >= CONTAGION_STRESS_THRESHOLD:
            return {
                "source_name": self.name,
                "emotion": "stress",
                "intensity": CONTAGION_STRESS_GAIN,
                "topic": topic,
            }

        if curiosity >= CONTAGION_CURIOSITY_THRESHOLD:
            return {
                "source_name": self.name,
                "emotion": "curiosity",
                "intensity": CONTAGION_CURIOSITY_GAIN,
                "topic": topic,
            }

        if trust >= CONTAGION_TRUST_THRESHOLD:
            return {
                "source_name": self.name,
                "emotion": "trust",
                "intensity": CONTAGION_TRUST_GAIN,
                "topic": topic,
            }

        return None

    # ============================================================
    # RECEIVE CONTAGION
    # world calls this when another npc leaks emotion into this one
    # ============================================================
    def receive_contagion(self, emotion, intensity, topic):
        self.mind.apply_contagion(emotion, intensity, topic)

    # ============================================================
    # UPDATE
    # main per-frame update for this npc
    #
    # IMPORTANT:
    # this returns either:
    # - None                       -> no brain tick happened / no contagion packet
    # - contagion packet dict      -> world can distribute this to nearby npcs
    #
    # that makes npc responsible for "inner life"
    # and world responsible for "who is near whom"
    # ============================================================
    def update(self, player_pos, dt):
        mode, tick_rate = self.get_lod_mode(player_pos)  # decide lod mode for this frame
        self.tick_timer += dt                            # accumulate time toward next tick

        # if not enough time has passed yet, do nothing expensive this frame
        if self.tick_timer < tick_rate:
            return None

        # enough time has passed, so do one cheap rust brain update
        self.tick_timer = 0.0
        self.mind.tick()

        # after the rust mind ticks, apply faction flavor
        self.apply_faction_bias()

        # pull the bridge packet for debug / prompt building
        dominant, sub, topic, thoughts, memory, speech = self.mind.get_bridge_packet()

        bark = self.choose_bark()
        print(f"[{mode}] {self.name} ({self.faction_data['name']}) | {bark}")

        # only build the llm prompt when the player is close
        # this keeps the expensive layer out of faraway simulation
        if mode == "close":
            prompt = build_prompt_from_mind(self.mind)

            print("\n--- PROMPT ---")
            print(prompt)

        # after the internal update is done, ask:
        # "is this npc emotionally loud enough to spread something?"
        contagion_packet = self.maybe_emit_contagion()

        # return packet to the world so world can handle nearby receivers
        return contagion_packet
