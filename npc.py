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
    # explanation:
    # build one npc object.
    #
    # what this block does:
    # - stores identity, node, faction
    # - builds the Rust mind
    # - sets hp and combat state
    # - sets aggro memory
    # - loads faction data
    # - builds faction behavior profile
    #
    # how it fits into the code:
    # this is the full local state container for one npc.
    # ------------------------------------------------------------
    def __init__(self, name, node, faction="kalchakra"):
        self.name = name
        self.node = node
        self.faction = faction

        self.mind = brain_logic.NpcMind(name)

        self.hp = NPC_MAX_HP
        self.is_dead = False
        self.attack_cooldown = 0.0
        self.attack_target = None

        self.is_fleeing = False
        self.current_behavior = "idle"

        self.aggro_target = None
        self.aggro_timer = 0.0

        self.home_pos = None
        self.wander_target = None
        self.wander_timer = 0.0

        self.tick_timer = 0.0
        self.contagion_cooldown = 0.0
        self.last_bark = None

        with open(f"data/factions/{faction}.json") as f:
            self.faction_data = json.load(f)

        self.behavior_profile = self.get_behavior_profile()

    # ------------------------------------------------------------
    # explanation:
    # build a behavior profile from faction.
    #
    # what this block does:
    # - returns a dictionary of multipliers
    # - controls aggression, flee tendency, loyalty, grouping,
    #   roaming size, roaming speed, and home attachment
    #
    # how it fits into the code:
    # this is how one shared npc class can still feel like three
    # very different faction personalities.
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
    # explanation:
    # get world position.
    #
    # what this block does:
    # - returns Panda3D node position
    #
    # how it fits into the code:
    # tiny helper used all over the rest of the file.
    # ------------------------------------------------------------
    def get_pos(self):
        return self.node.getPos()

    # ------------------------------------------------------------
    # explanation:
    # choose lod mode from player distance.
    #
    # what this block does:
    # - returns close / mid / far
    # - also returns internal tick rate for that lod
    #
    # how it fits into the code:
    # this keeps far-away npcs cheaper to update.
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
    # explanation:
    # choose one bark line.
    #
    # what this block does:
    # - picks a line from faction bark data
    # - tries not to repeat the exact last bark
    #
    # how it fits into the code:
    # this gives the simulation audible / visible flavor without
    # needing expensive dialogue generation every frame.
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
    # explanation:
    # apply faction emotional bias.
    #
    # what this block does:
    # - pushes the Rust mind with faction emotion values
    #
    # how it fits into the code:
    # this is how faction identity constantly colors npc inner state.
    # ------------------------------------------------------------
    def apply_faction_bias(self):
        for key, value in self.faction_data["emotion_bias"].items():
            self.mind.nudge(key, value)

    # ------------------------------------------------------------
    # explanation:
    # decide if npc should flee.
    #
    # what this block does:
    # - checks low hp
    # - checks high fear
    # - modifies thresholds by faction flee tendency
    #
    # how it fits into the code:
    # this is the survival-first branch that can override aggression.
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
    # explanation:
    # decide if npc is aggressive enough.
    #
    # what this block does:
    # - Kalchakra always returns true
    # - other factions check aggression, fear, or stress thresholds
    #
    # how it fits into the code:
    # this is the main gate that controls whether tension becomes combat.
    # ------------------------------------------------------------
    def is_aggressive_enough(self):
        if self.is_dead:
            return False

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
    # explanation:
    # decide if npc is willing to help allies.
    #
    # what this block does:
    # - checks stress and fear against a loyalty-based threshold
    #
    # how it fits into the code:
    # this is mainly extra support flavor for factions that may not
    # start fights as freely on their own.
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
    # explanation:
    # set or refresh aggro.
    #
    # what this block does:
    # - stores an aggro target
    # - refreshes aggro memory timer
    #
    # how it fits into the code:
    # this is the local memory hook used by world.py ally alerts.
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
    # explanation:
    # decide whether this npc can attack another.
    #
    # what this block does:
    # - blocks dead / same-faction / fleeing / self-targeting cases
    # - blocks aggression if this npc is not aggressive enough
    #
    # how it fits into the code:
    # this is the final local permission check for combat.
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
    # explanation:
    # take damage and possibly die.
    #
    # what this block does:
    # - subtracts hp
    # - hides dead npcs
    # - clears their combat state
    # - prints death logs if enabled
    #
    # how it fits into the code:
    # world.py handles group reaction to death, but this block handles
    # the actual local state transition from alive to dead.
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
    # explanation:
    # maybe emit a contagion packet.
    #
    # what this block does:
    # - rate-limits contagion output
    # - emits a stress packet using current active topic
    #
    # how it fits into the code:
    # this lets local cognition feed back into the world simulation.
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
    # explanation:
    # receive contagion.
    #
    # what this block does:
    # - forwards emotional input into the Rust mind
    #
    # how it fits into the code:
    # this is how world-level contagion changes local npc state.
    # ------------------------------------------------------------
    def receive_contagion(self, emotion, intensity, topic):
        if not self.is_dead:
            self.mind.apply_contagion(emotion, intensity, topic)

    # ------------------------------------------------------------
    # explanation:
    # decide high-level behavior.
    #
    # what this block does:
    # - dead units become idle
    # - fleeing has top priority
    # - any living aggro target forces aggressive behavior
    # - non-Atimarga can also become proactively aggressive
    # - medium tension becomes alert
    # - otherwise falls back to idle
    #
    # how it fits into the code:
    # this is the local intention selector.
    # world.py reads this and turns it into physical action.
    # ------------------------------------------------------------
    def decide_behavior(self):
        if self.is_dead:
            self.current_behavior = "idle"
            self.is_fleeing = False
            return self.current_behavior

        if self.should_flee():
            self.current_behavior = "fleeing"
            self.is_fleeing = True
            return self.current_behavior

        self.is_fleeing = False

        if self.aggro_target is not None and not self.aggro_target.is_dead:
            self.current_behavior = "aggressive"
            return self.current_behavior

        if self.faction != "atimarga":
            if self.is_aggressive_enough():
                self.current_behavior = "aggressive"
                return self.current_behavior

        if self.mind.fear >= 0.35 or self.mind.stress >= 0.35:
            self.current_behavior = "alert"
            return self.current_behavior

        self.current_behavior = "idle"
        return self.current_behavior

    # ------------------------------------------------------------
    # explanation:
    # main npc internal update.
    #
    # what this block does:
    # - handles lod update timing
    # - cools down contagion and attack timers
    # - expires aggro memory
    # - ticks the Rust mind
    # - applies faction bias
    # - decides current behavior
    # - prints bark / behavior log
    # - may emit a contagion packet
    #
    # how it fits into the code:
    # this is the local heartbeat for one npc.
    # world.py collects the results and handles the space-level outcomes.
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