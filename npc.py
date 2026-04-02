# npc.py
# ------------------------------------------------------------
# one npc:
# - has a Panda3D body
# - has a Rust mind
# - can bark
# - can spread contagion
# - can fight
# - can flee
# - can remember a current aggro target for a short time
#
# THIS VERSION:
# - keeps the behavior state system
# - keeps faction behavior profiles
# - tunes faction personality harder
#
# FACTION GOALS:
# Kalchakra:
# - moves in packs
# - raids
# - aggressive
# - runs less
#
# Atimarga:
# - wanders more individually
# - spreads out through the world
# - avoids violence unless kin are threatened
#
# Nirmanakaya:
# - stable
# - grouped
# - base-focused
# - defensive / even
#
# IMPORTANT IDEA:
# this file decides what the npc WANTS to do
# world.py handles how movement happens in space
# ------------------------------------------------------------

import json
import random
import brain_logic

from settings import (
    INTERACT_RANGE,
    BARK_RANGE,
    NPC_TICK_RATE_FAR,
    NPC_TICK_RATE_MID,
    NPC_TICK_RATE_CLOSE,
    CONTAGION_STRESS_GAIN,
    CONTAGION_EMIT_COOLDOWN,
    NPC_MAX_HP,
    NPC_ATTACK_FEAR_THRESHOLD,
    NPC_ATTACK_STRESS_THRESHOLD,
    NPC_FLEE_HP_THRESHOLD,
    NPC_FLEE_FEAR_THRESHOLD,
    NPC_AGGRO_DURATION,
    PRINT_DEATH_EVENTS,
)


class NPC:
    # ------------------------------------------------------------
    # build one npc
    #
    # plain english:
    # this sets up the npc's local state:
    # - name
    # - Panda3D node
    # - faction
    # - Rust mind
    # - hp and combat data
    # - aggro memory
    # - roaming data
    # - timers
    # - faction behavior profile
    # ------------------------------------------------------------
    def __init__(self, name, node, faction="kalchakra"):
        self.name = name
        self.node = node
        self.faction = faction

        # cheap Rust cognition layer
        self.mind = brain_logic.NpcMind(name)

        # ---------------- combat / life ----------------
        self.hp = NPC_MAX_HP
        self.is_dead = False
        self.attack_cooldown = 0.0
        self.attack_target = None

        # ---------------- flee state ----------------
        # kept for compatibility with existing logic
        self.is_fleeing = False

        # ---------------- behavior state ----------------
        self.current_behavior = "idle"

        # ---------------- aggro state ----------------
        self.aggro_target = None
        self.aggro_timer = 0.0

        # ---------------- world / roaming ----------------
        self.home_pos = None
        self.wander_target = None
        self.wander_timer = 0.0

        # ---------------- general timers ----------------
        self.tick_timer = 0.0
        self.contagion_cooldown = 0.0
        self.last_bark = None

        # load faction bark + emotional bias data
        with open(f"data/factions/{faction}.json") as f:
            self.faction_data = json.load(f)

        # build faction personality profile
        self.behavior_profile = self.get_behavior_profile()

    # ------------------------------------------------------------
    # build faction behavior profile
    #
    # plain english:
    # each faction gets modifiers for:
    # - aggression
    # - flee tendency
    # - loyalty to allies
    # - grouping preference
    # - roaming amount
    # - movement speed while roaming
    # - home attachment
    #
    # grouping:
    # positive = likes allies nearby
    # negative = prefers space / lone drifting
    # ------------------------------------------------------------
    def get_behavior_profile(self):
        if self.faction == "kalchakra":
            return {
                "aggression_mult": 1.70,
                "flee_mult": 0.55,
                "loyalty": 1.25,
                "grouping": 1.20,
                "wander_radius_mult": 1.60,
                "wander_speed_mult": 1.20,
                "home_attachment": 0.55,
            }

        if self.faction == "atimarga":
            return {
                "aggression_mult": 0.60,
                "flee_mult": 1.20,
                "loyalty": 1.45,
                "grouping": -1.40,
                "wander_radius_mult": 2.40,
                "wander_speed_mult": 1.30,
                "home_attachment": 0.25,
            }

        # nirmanakaya
        return {
            "aggression_mult": 1.0,
            "flee_mult": 1.0,
            "loyalty": 1.0,
            "grouping": 0.75,
            "wander_radius_mult": 0.65,
            "wander_speed_mult": 0.90,
            "home_attachment": 1.50,
        }

    # ------------------------------------------------------------
    # get current world position
    # ------------------------------------------------------------
    def get_pos(self):
        return self.node.getPos()

    # ------------------------------------------------------------
    # pick LOD mode from distance to player
    # ------------------------------------------------------------
    def get_lod_mode(self, player_pos):
        dist = (self.get_pos() - player_pos).length()

        if dist < INTERACT_RANGE:
            return "close", NPC_TICK_RATE_CLOSE
        elif dist < BARK_RANGE:
            return "mid", NPC_TICK_RATE_MID
        else:
            return "far", NPC_TICK_RATE_FAR

    # ------------------------------------------------------------
    # choose a faction bark
    # ------------------------------------------------------------
    def choose_bark(self):
        barks = self.faction_data["barks"]

        if not barks:
            return "..."

        choices = [b for b in barks if b != self.last_bark]
        if not choices:
            choices = barks

        bark = random.choice(choices)
        self.last_bark = bark
        return bark

    # ------------------------------------------------------------
    # apply faction emotional bias
    # ------------------------------------------------------------
    def apply_faction_bias(self):
        for key, value in self.faction_data["emotion_bias"].items():
            self.mind.nudge(key, value)

    # ------------------------------------------------------------
    # decide if this npc should flee
    #
    # plain english:
    # lower flee_mult = harder to flee
    # higher flee_mult = easier to flee
    # ------------------------------------------------------------
    def should_flee(self):
        if self.is_dead:
            return False

        profile = self.behavior_profile

        adjusted_hp_threshold = NPC_FLEE_HP_THRESHOLD * profile["flee_mult"]
        adjusted_fear_threshold = NPC_FLEE_FEAR_THRESHOLD / max(profile["flee_mult"], 0.01)

        if self.hp <= adjusted_hp_threshold:
            return True

        if self.mind.fear >= adjusted_fear_threshold:
            return True

        return False

        # ------------------------------------------------------------
    # decide if this npc is aggressive enough
    #
    # plain english:
    # higher aggression_mult = easier to enter aggression
    # now also checks real aggression emotion
    # ------------------------------------------------------------
    def is_aggressive_enough(self):
        if self.is_dead:
            return False

        # Kalchakra are always battle-ready
        if self.faction == "kalchakra":
            return True

        profile = self.behavior_profile

        adjusted_fear_threshold = NPC_ATTACK_FEAR_THRESHOLD / max(profile["aggression_mult"], 0.01)
        adjusted_stress_threshold = NPC_ATTACK_STRESS_THRESHOLD / max(profile["aggression_mult"], 0.01)
        adjusted_aggression_threshold = 0.55 / max(profile["aggression_mult"], 0.01)

        return (
            self.mind.aggression >= adjusted_aggression_threshold
            or self.mind.fear >= adjusted_fear_threshold
            or self.mind.stress >= adjusted_stress_threshold
        )

    # ------------------------------------------------------------
    # decide if this npc is willing to help an ally
    #
    # plain english:
    # especially important for Atimarga:
    # they prefer not to start violence,
    # but they WILL respond to pressure on their own
    # ------------------------------------------------------------
    def is_loyal_enough_to_help(self):
        if self.is_dead:
            return False

        profile = self.behavior_profile
        help_threshold = 0.55 / max(profile["loyalty"], 0.01)

        return (
            self.mind.stress >= help_threshold
            or self.mind.fear >= help_threshold
        )

    # ------------------------------------------------------------
    # start or refresh aggro on a target
    # ------------------------------------------------------------
    def set_aggro(self, target):
        if self.is_dead:
            return

        if target is None:
            return

        if target.is_dead:
            return

        self.aggro_target = target
        self.aggro_timer = NPC_AGGRO_DURATION

    # ------------------------------------------------------------
    # decide whether this npc can attack another
    # ------------------------------------------------------------
    def can_attack(self, other):
        if self.is_dead or other.is_dead:
            return False

        if self.is_fleeing:
            return False

        if other is self:
            return False

        if other.faction == self.faction:
            return False

        if not self.is_aggressive_enough():
            return False

        return True

    # ------------------------------------------------------------
    # take damage
    # ------------------------------------------------------------
    def take_damage(self, amount, attacker):
        if self.is_dead:
            return

        self.hp -= amount

        if self.hp <= 0:
            self.hp = 0
            self.is_dead = True
            self.node.hide()
            self.attack_target = None
            self.aggro_target = None
            self.aggro_timer = 0.0
            self.is_fleeing = False
            self.current_behavior = "idle"

            if PRINT_DEATH_EVENTS:
                print(f"[DEATH] {self.name} killed by {attacker}")

    # ------------------------------------------------------------
    # maybe emit contagion packet
    # ------------------------------------------------------------
    def maybe_emit_contagion(self):
        if self.is_dead or self.contagion_cooldown > 0:
            return None

        self.contagion_cooldown = CONTAGION_EMIT_COOLDOWN

        return {
            "emotion": "stress",
            "intensity": CONTAGION_STRESS_GAIN,
            "topic": self.mind.active_topic,
        }

    # ------------------------------------------------------------
    # receive contagion
    # ------------------------------------------------------------
    def receive_contagion(self, emotion, intensity, topic):
        if not self.is_dead:
            self.mind.apply_contagion(emotion, intensity, topic)

    # ------------------------------------------------------------
    # decide high-level behavior
    #
    # plain english:
    # this is the local decision layer
    #
    # special faction flavor:
    # Atimarga does not proactively start fights
    # unless future design changes that
    # ------------------------------------------------------------
    def decide_behavior(self):
        if self.is_dead:
            self.current_behavior = "idle"
            self.is_fleeing = False
            return self.current_behavior

        # survival first
        if self.should_flee():
            self.current_behavior = "fleeing"
            self.is_fleeing = True
            return self.current_behavior

        self.is_fleeing = False

        # existing aggro still matters
        if self.aggro_target is not None and not self.aggro_target.is_dead:
            self.current_behavior = "aggressive"
            return self.current_behavior

            if self.is_aggressive_enough():
                self.current_behavior = "aggressive"
                return self.current_behavior

        # proactive aggression for non-Atimarga factions
        if self.faction != "atimarga":
            if self.is_aggressive_enough():
                self.current_behavior = "aggressive"
                return self.current_behavior

        # middle tension state
        if self.mind.fear >= 0.35 or self.mind.stress >= 0.35:
            self.current_behavior = "alert"
            return self.current_behavior

        # calm fallback
        self.current_behavior = "idle"
        return self.current_behavior

    # ------------------------------------------------------------
    # main internal update
    # ------------------------------------------------------------
    def update(self, player_pos, dt):
        if self.is_dead:
            return None

        mode, rate = self.get_lod_mode(player_pos)

        self.tick_timer += dt

        if self.contagion_cooldown > 0:
            self.contagion_cooldown -= dt

        if self.attack_cooldown > 0:
            self.attack_cooldown -= dt

        if self.aggro_timer > 0:
            self.aggro_timer -= dt
        else:
            self.aggro_target = None
            self.aggro_timer = 0.0

        if self.tick_timer < rate:
            return None

        self.tick_timer = 0

        self.mind.tick()
        self.apply_faction_bias()
        self.decide_behavior()

        bark = self.choose_bark()
        print(f"[{mode}] {self.name} | behavior={self.current_behavior} | {bark}")

        return self.maybe_emit_contagion()