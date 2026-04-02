# npc.py
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
    PRINT_DEATH_EVENTS,
)


class NPC:
    def __init__(self, name, node, faction="kalchakra"):
        self.name = name
        self.node = node
        self.faction = faction

        self.mind = brain_logic.NpcMind(name)

        # combat
        self.hp = NPC_MAX_HP
        self.is_dead = False
        self.attack_cooldown = 0.0

        # state
        self.tick_timer = 0.0
        self.contagion_cooldown = 0.0
        self.last_bark = None

        with open(f"data/factions/{faction}.json") as f:
            self.faction_data = json.load(f)

    def get_pos(self):
        return self.node.getPos()

    def get_lod_mode(self, player_pos):
        dist = (self.get_pos() - player_pos).length()

        if dist < INTERACT_RANGE:
            return "close", NPC_TICK_RATE_CLOSE
        elif dist < BARK_RANGE:
            return "mid", NPC_TICK_RATE_MID
        else:
            return "far", NPC_TICK_RATE_FAR

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

    def apply_faction_bias(self):
        for k, v in self.faction_data["emotion_bias"].items():
            self.mind.nudge(k, v)

    def is_aggressive_enough(self):
        if self.is_dead:
            return False

        return (
            self.mind.fear >= NPC_ATTACK_FEAR_THRESHOLD
            or self.mind.stress >= NPC_ATTACK_STRESS_THRESHOLD
        )

    def can_attack(self, other):
        if self.is_dead or other.is_dead:
            return False
        if other is self:
            return False
        if other.faction == self.faction:
            return False
        if not self.is_aggressive_enough():
            return False
        return True

    def take_damage(self, amount, attacker):
        if self.is_dead:
            return

        self.hp -= amount

        if self.hp <= 0:
            self.hp = 0
            self.is_dead = True
            self.node.hide()

            if PRINT_DEATH_EVENTS:
                print(f"[DEATH] {self.name} killed by {attacker}")

    def maybe_emit_contagion(self):
        if self.is_dead or self.contagion_cooldown > 0:
            return None

        self.contagion_cooldown = CONTAGION_EMIT_COOLDOWN

        return {
            "emotion": "stress",
            "intensity": CONTAGION_STRESS_GAIN,
            "topic": self.mind.active_topic,
        }

    def receive_contagion(self, emotion, intensity, topic):
        if not self.is_dead:
            self.mind.apply_contagion(emotion, intensity, topic)

    def update(self, player_pos, dt):
        if self.is_dead:
            return None

        mode, rate = self.get_lod_mode(player_pos)

        self.tick_timer += dt

        if self.contagion_cooldown > 0:
            self.contagion_cooldown -= dt

        if self.attack_cooldown > 0:
            self.attack_cooldown -= dt

        if self.tick_timer < rate:
            return None

        self.tick_timer = 0

        self.mind.tick()
        self.apply_faction_bias()

        bark = self.choose_bark()
        print(f"[{mode}] {self.name} | {bark}")

        return self.maybe_emit_contagion()