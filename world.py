from direct.task import Task
from panda3d.core import Vec3

from npc import NPC
from settings import (
    CONTAGION_RADIUS,
    CONTAGION_USE_DISTANCE_FALLOFF,
    PRINT_CONTAGION_EVENTS,
    NPC_ATTACK_RANGE,
    NPC_ATTACK_DAMAGE,
    NPC_ATTACK_COOLDOWN,
    PRINT_ATTACK_EVENTS,
    NPC_MOVE_SPEED,
    NPC_STOP_DISTANCE,
)


class World:
    def __init__(self, game):
        self.game = game
        self.npcs = []

        # kalchakra
        self.spawn_group(
            faction="kalchakra",
            names=["Ralph", "Mira", "Tovin"],
            center_x=-4,
            center_y=10,
            center_z=0,
        )

        # atimarga
        self.spawn_group(
            faction="atimarga",
            names=["Suri", "Veya", "Oren"],
            center_x=0,
            center_y=10,
            center_z=0,
        )

        # nirmanakaya
        self.spawn_group(
            faction="nirmanakaya",
            names=["Isha", "Leth", "Koro"],
            center_x=4,
            center_y=10,
            center_z=0,
        )

        self.game.taskMgr.add(self.update, "world_update")

    def spawn_npc(self, name, x, y, z, faction):
        model = self.game.loader.loadModel("models/box")
        model.reparentTo(self.game.render)
        model.setPos(x, y, z)
        if faction == "kalchakra":
            model.setColor(1, 0, 0, 1) # blood red

        elif faction == "atimarga":
            model.setColor(0.6, 0, 1, 1)

        elif faction == "nirmanakaya":
            model.setColor(0.2, 0.6, 1, 1)
        npc = NPC(name, model, faction)
        self.npcs.append(npc)

    def spawn_group(self, faction, names, center_x, center_y, center_z):
        offsets = [(-2, 0, 0), (0, 2, 0), (2, 0, 0)]

        for name, (ox, oy, oz) in zip(names, offsets):
            self.spawn_npc(
                name,
                center_x + ox,
                center_y + oy,
                center_z + oz,
                faction,
            )

    def get_player_pos(self):
        return Vec3(0, 0, 0)

    def find_enemy(self, npc):
        best = None
        best_dist = NPC_ATTACK_RANGE

        for other in self.npcs:
            if not npc.can_attack(other):
                continue

            dist = (other.get_pos() - npc.get_pos()).length()

            if dist < best_dist:
                best_dist = dist
                best = other

        return best

    def move_toward_target(self, npc, target, dt):
        if npc.is_dead or target.is_dead:
            return

        start = npc.get_pos()
        end = target.get_pos()

        direction = end - start
        distance = direction.length()

        if distance <= NPC_STOP_DISTANCE:
            return

        direction.normalize()

        step = direction * NPC_MOVE_SPEED * dt
        npc.node.setPos(start + step)

    def update_combat(self, dt):
        for npc in self.npcs:
            if npc.is_dead:
                continue

            target = self.find_enemy(npc)
            npc.attack_target = target

            if target is not None:
                self.move_toward_target(npc, target, dt)

            if target is None:
                continue

            if npc.attack_cooldown > 0:
                continue

            target.take_damage(NPC_ATTACK_DAMAGE, npc.name)
            npc.attack_cooldown = NPC_ATTACK_COOLDOWN

            if PRINT_ATTACK_EVENTS:
                print(f"[ATTACK] {npc.name} -> {target.name} | hp={target.hp:.1f}")

    def spread_contagion(self, source, packet):
        if packet is None:
            return

        for target in self.npcs:
            if target is source or target.is_dead:
                continue

            dist = (target.get_pos() - source.get_pos()).length()

            if dist > CONTAGION_RADIUS:
                continue

            falloff = 1.0
            if CONTAGION_USE_DISTANCE_FALLOFF:
                falloff = 1.0 - (dist / CONTAGION_RADIUS)

            intensity = packet["intensity"] * falloff

            target.receive_contagion(
                packet["emotion"],
                intensity,
                packet["topic"],
            )

            if PRINT_CONTAGION_EVENTS:
                print(
                    f"[CONTAGION] {source.name} -> {target.name} "
                    f"| {packet['emotion']} {intensity:.2f}"
                )

    def update(self, task):
        dt = globalClock.getDt()
        player_pos = self.get_player_pos()

        emitted = []

        for npc in self.npcs:
            packet = npc.update(player_pos, dt)
            if packet:
                emitted.append((npc, packet))

        for source, packet in emitted:
            self.spread_contagion(source, packet)

        self.update_combat(dt)

        return Task.cont