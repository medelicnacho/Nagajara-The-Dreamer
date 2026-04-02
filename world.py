# world.py
# ------------------------------------------------------------
# world orchestration:
# - spawn populations
# - color factions
# - spread contagion
# - wander
# - chase / attack
# - flee
# - chain aggro through nearby allies
#
# THIS VERSION:
# - keeps your exact spawn positions
# - keeps the full system structure
# - fixes broken indentation / class structure
# - keeps Atimarga as solo drifters
# - keeps Nirmanakaya idle
# - makes Kalchakra move and fight as one big dogpile group
#
# IMPORTANT IDEA:
# npc.py decides behavior
# world.py executes behavior in physical space
# ------------------------------------------------------------

import random

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
    NPC_FLEE_SPEED,
    NPC_SAFE_DISTANCE,
    NPC_WANDER_SPEED,
    NPC_MAX_CHASE_DISTANCE_FROM_HOME,
    NPC_ALLY_HELP_RADIUS,
    NPC_AGGRO_RADIUS,
)


class World:
    # ------------------------------------------------------------
    # build the world and spawn populations
    # ------------------------------------------------------------
    def __init__(self, game):
        self.game = game
        self.npcs = []

        # --------------------------------------------------------
        # shared Kalchakra movement state
        #
        # all Kalchakra loosely follow one big group direction
        # --------------------------------------------------------
        self.kalchakra_group_dir = self.random_flat_dir()
        self.kalchakra_group_turn_timer = random.uniform(6.0, 12.0)

        # --------------------------------------------------------
        # shared Kalchakra target state
        #
        # all Kalchakra use one shared target so they dogpile
        # instead of scattering toward different enemies
        # --------------------------------------------------------
        self.kalchakra_group_target = None
        self.kalchakra_group_target_timer = 0.0

        # Kalchakra
        self.spawn_population(
            faction="kalchakra",
            name_prefix="Kal",
            count=50,
            center_x=-100,
            center_y=-50,
            center_z=0,
            spread_radius=50,
        )

        # Atimarga
        self.spawn_population(
            faction="atimarga",
            name_prefix="Ati",
            count=50,
            center_x=0,
            center_y=-100,
            center_z=0,
            spread_radius=50,
        )

        # Nirmanakaya
        self.spawn_population(
            faction="nirmanakaya",
            name_prefix="Nir",
            count=50,
            center_x=30,
            center_y=0,
            center_z=0,
            spread_radius=50,
        )

        self.game.taskMgr.add(self.update, "world_update")

    # ------------------------------------------------------------
    # random flat 2D direction
    # ------------------------------------------------------------
    def random_flat_dir(self):
        dx = random.uniform(-1.0, 1.0)
        dy = random.uniform(-1.0, 1.0)

        dir_vec = Vec3(dx, dy, 0)

        if dir_vec.length_squared() <= 0.0001:
            dir_vec = Vec3(1, 0, 0)

        dir_vec.normalize()
        return dir_vec

    # ------------------------------------------------------------
    # safely normalize a direction
    # ------------------------------------------------------------
    def safe_normalize(self, vec):
        out = Vec3(vec.x, vec.y, 0)

        if out.length_squared() <= 0.0001:
            return Vec3(1, 0, 0)

        out.normalize()
        return out

    # ------------------------------------------------------------
    # blend one direction toward another
    # ------------------------------------------------------------
    def blend_direction(self, current_dir, desired_dir, turn_strength):
        blended = (current_dir * (1.0 - turn_strength)) + (desired_dir * turn_strength)
        return self.safe_normalize(blended)

    # ------------------------------------------------------------
    # update shared Kalchakra roaming direction
    #
    # this makes the whole faction drift together around the map
    # ------------------------------------------------------------
    def update_kalchakra_group_direction(self, dt):
        self.kalchakra_group_turn_timer -= dt

        if self.kalchakra_group_turn_timer <= 0.0:
            new_dir = self.random_flat_dir()

            self.kalchakra_group_dir = self.blend_direction(
                self.kalchakra_group_dir,
                new_dir,
                0.35,
            )

            self.kalchakra_group_turn_timer = random.uniform(6.0, 12.0)

    # ------------------------------------------------------------
    # update shared Kalchakra group target
    #
    # this finds ONE target for the whole Kalchakra faction
    # based on distance to the pack center
    # ------------------------------------------------------------
    def update_kalchakra_group_target(self, dt):
        self.kalchakra_group_target_timer -= dt

        if self.kalchakra_group_target is not None and self.kalchakra_group_target.is_dead:
            self.kalchakra_group_target = None

        if self.kalchakra_group_target is not None and self.kalchakra_group_target_timer > 0.0:
            return

        kal_positions = [
            npc.get_pos()
            for npc in self.npcs
            if not npc.is_dead and npc.faction == "kalchakra"
        ]

        if not kal_positions:
            self.kalchakra_group_target = None
            return

        center = Vec3(0, 0, 0)
        for pos in kal_positions:
            center += pos
        center /= len(kal_positions)

        best = None
        best_dist = float("inf")

        for other in self.npcs:
            if other.is_dead:
                continue
            if other.faction == "kalchakra":
                continue

            dist = (other.get_pos() - center).length()

            if dist < best_dist:
                best = other
                best_dist = dist

        self.kalchakra_group_target = best
        self.kalchakra_group_target_timer = 2.0

    # ------------------------------------------------------------
    # spawn one npc
    # ------------------------------------------------------------
    def spawn_npc(self, name, x, y, z, faction):
        model = self.game.loader.loadModel("models/box")
        model.reparentTo(self.game.render)
        model.setPos(x, y, z)

        if faction == "kalchakra":
            model.setColor(1, 0, 0, 1)
        elif faction == "atimarga":
            model.setColor(0.6, 0, 1, 1)
        elif faction == "nirmanakaya":
            model.setColor(0.2, 0.6, 1, 1)

        npc = NPC(name, model, faction)
        npc.home_pos = Vec3(x, y, z)

        if faction == "kalchakra":
            npc.move_dir = Vec3(self.kalchakra_group_dir)
            npc.turn_timer = random.uniform(1.5, 3.0)
        elif faction == "atimarga":
            npc.move_dir = self.random_flat_dir()
            npc.turn_timer = random.uniform(5.0, 11.0)
        else:
            npc.move_dir = Vec3(0, 0, 0)
            npc.turn_timer = 999999.0

        self.npcs.append(npc)

    # ------------------------------------------------------------
    # spawn a population around a center point
    # ------------------------------------------------------------
    def spawn_population(self, faction, name_prefix, count, center_x, center_y, center_z, spread_radius):
        for i in range(count):
            ox = random.uniform(-spread_radius, spread_radius)
            oy = random.uniform(-spread_radius, spread_radius)

            self.spawn_npc(
                name=f"{name_prefix}_{i}",
                x=center_x + ox,
                y=center_y + oy,
                z=center_z,
                faction=faction,
            )

    # ------------------------------------------------------------
    # placeholder player position
    # ------------------------------------------------------------
    def get_player_pos(self):
        return Vec3(0, 0, 0)

    # ------------------------------------------------------------
    # nearest valid enemy
    # ------------------------------------------------------------
    def find_nearest_enemy(self, npc):
        if npc.aggro_target is not None:
            if npc.can_attack(npc.aggro_target):
                dist = (npc.aggro_target.get_pos() - npc.get_pos()).length()
                return npc.aggro_target, dist

        best = None
        best_dist = 999999.0

        for other in self.npcs:
            if not npc.can_attack(other):
                continue

            dist = (other.get_pos() - npc.get_pos()).length()

            if dist < best_dist:
                best_dist = dist
                best = other

        return best, best_dist

    # ------------------------------------------------------------
    # nearest threat
    # ------------------------------------------------------------
    def find_nearest_threat(self, npc):
        best = None
        best_dist = 999999.0

        for other in self.npcs:
            if other is npc:
                continue
            if other.is_dead:
                continue
            if other.faction == npc.faction:
                continue

            dist = (other.get_pos() - npc.get_pos()).length()

            if dist < best_dist:
                best_dist = dist
                best = other

        return best, best_dist

    # ------------------------------------------------------------
    # nearest ally
    # ------------------------------------------------------------
    def find_nearest_ally(self, npc):
        best = None
        best_dist = 999999.0

        for other in self.npcs:
            if other is npc:
                continue
            if other.is_dead:
                continue
            if other.faction != npc.faction:
                continue

            dist = (other.get_pos() - npc.get_pos()).length()

            if dist < best_dist:
                best_dist = dist
                best = other

        return best, best_dist

    # ------------------------------------------------------------
    # nearby same-faction allies
    # ------------------------------------------------------------
    def find_nearby_allies(self, npc, radius):
        allies = []

        for other in self.npcs:
            if other is npc:
                continue
            if other.is_dead:
                continue
            if other.faction != npc.faction:
                continue

            dist = (other.get_pos() - npc.get_pos()).length()
            if dist <= radius:
                allies.append(other)

        return allies

    # ------------------------------------------------------------
    # find any enemy anywhere
    # ------------------------------------------------------------
    def find_any_enemy(self, npc):
        closest = None
        closest_dist = float("inf")

        npc_pos = npc.get_pos()

        for other in self.npcs:
            if not npc.can_attack(other):
                continue

            dist = (other.get_pos() - npc_pos).length()

            if dist < closest_dist:
                closest = other
                closest_dist = dist

        return closest

    # ------------------------------------------------------------
    # move toward a raw position
    # ------------------------------------------------------------
    def move_toward_position(self, npc, target_pos, dt, speed):
        if npc.is_dead:
            return

        start = npc.get_pos()
        direction = target_pos - start

        if direction.length_squared() <= 0.0001:
            return

        direction = self.safe_normalize(direction)
        step = direction * speed * dt
        npc.node.setPos(start + step)

    # ------------------------------------------------------------
    # move away from a raw position
    # ------------------------------------------------------------
    def move_away_from_position(self, npc, danger_pos, dt, speed):
        if npc.is_dead:
            return

        start = npc.get_pos()
        direction = start - danger_pos

        if direction.length_squared() <= 0.0001:
            return

        direction = self.safe_normalize(direction)
        step = direction * speed * dt
        npc.node.setPos(start + step)

    # ------------------------------------------------------------
    # generic chase/support move
    # ------------------------------------------------------------
    def move_toward_target(self, npc, target, dt, speed=None, stop_distance=None):
        if target is None:
            return

        if npc.is_dead or target.is_dead:
            return

        move_speed = NPC_MOVE_SPEED if speed is None else speed
        stop_dist = NPC_STOP_DISTANCE if stop_distance is None else stop_distance

        start = npc.get_pos()
        end = target.get_pos()

        direction = end - start
        distance = direction.length()

        if distance <= stop_dist:
            return

        direction = self.safe_normalize(direction)
        step = direction * move_speed * dt
        npc.node.setPos(start + step)

    # ------------------------------------------------------------
    # flee move
    # ------------------------------------------------------------
    def move_away_from_threat(self, npc, threat, dt):
        if npc.is_dead or threat.is_dead:
            return

        start = npc.get_pos()
        danger = threat.get_pos()

        direction = start - danger
        if direction.length_squared() <= 0.0001:
            direction = self.random_flat_dir()
        else:
            direction = self.safe_normalize(direction)

        step = direction * NPC_FLEE_SPEED * dt
        npc.node.setPos(start + step)

    # ------------------------------------------------------------
    # calculate desired wander direction
    # ------------------------------------------------------------
    def get_desired_wander_direction(self, npc):
        current_pos = npc.get_pos()

        if npc.faction == "atimarga":
            desired = Vec3(npc.move_dir)

            allies = self.find_nearby_allies(npc, radius=6.0)
            if allies:
                separation = Vec3(0, 0, 0)

                for ally in allies:
                    away = current_pos - ally.get_pos()
                    dist = away.length()

                    if dist > 0.001:
                        away = self.safe_normalize(away)
                        separation += away * (1.0 / max(dist, 0.5))

                if separation.length_squared() > 0.0001:
                    desired += separation * 0.8

            return self.safe_normalize(desired)

        if npc.faction == "kalchakra":
            desired = Vec3(self.kalchakra_group_dir)

            allies = self.find_nearby_allies(npc, radius=10.0)
            separation = Vec3(0, 0, 0)

            for ally in allies:
                offset = current_pos - ally.get_pos()
                dist = offset.length()

                if 0.001 < dist < 3.5:
                    separation += self.safe_normalize(offset) * (1.0 / max(dist, 0.5))

            if separation.length_squared() > 0.0001:
                desired += self.safe_normalize(separation) * 0.6

            desired += self.random_flat_dir() * 0.12
            return self.safe_normalize(desired)

        return Vec3(0, 0, 0)

    # ------------------------------------------------------------
    # refresh idle direction
    # ------------------------------------------------------------
    def refresh_idle_direction(self, npc):
        desired_dir = self.get_desired_wander_direction(npc)

        if npc.faction == "atimarga":
            npc.move_dir = self.blend_direction(npc.move_dir, desired_dir, 0.20)
            npc.turn_timer = random.uniform(5.0, 11.0)
            return

        if npc.faction == "kalchakra":
            npc.move_dir = self.blend_direction(npc.move_dir, desired_dir, 0.55)
            npc.turn_timer = random.uniform(1.5, 3.0)
            return

        npc.move_dir = Vec3(0, 0, 0)
        npc.turn_timer = 999999.0

    # ------------------------------------------------------------
    # idle / alert wander update
    # ------------------------------------------------------------
    def update_idle_wander(self, npc, dt):
        if npc.is_dead:
            return

        if npc.faction == "nirmanakaya":
            npc.move_dir = Vec3(0, 0, 0)
            return

        npc.turn_timer -= dt

        if npc.turn_timer <= 0.0:
            self.refresh_idle_direction(npc)

        if npc.faction == "atimarga":
            move_speed = NPC_WANDER_SPEED * npc.behavior_profile["wander_speed_mult"]
        elif npc.faction == "kalchakra":
            move_speed = NPC_WANDER_SPEED * npc.behavior_profile["wander_speed_mult"]
        else:
            move_speed = 0.0

        step = npc.move_dir * move_speed * dt
        npc.node.setPos(npc.get_pos() + step)

    # ------------------------------------------------------------
    # stop crazy map-wide chases
    # ------------------------------------------------------------
    def is_target_too_far_from_home(self, npc, target):
        if npc.faction == "kalchakra":
            return False

        if npc.home_pos is None:
            return False

        profile = npc.behavior_profile
        adjusted_max_distance = NPC_MAX_CHASE_DISTANCE_FROM_HOME / max(profile["home_attachment"], 0.01)

        dist_from_home = (target.get_pos() - npc.home_pos).length()
        return dist_from_home > adjusted_max_distance

    # ------------------------------------------------------------
    # alert nearby allies
    # ------------------------------------------------------------
    def alert_nearby_allies(self, victim, attacker):
        victim_profile = victim.behavior_profile
        adjusted_radius = NPC_AGGRO_RADIUS * victim_profile["loyalty"]

        for other in self.npcs:
            if other.is_dead:
                continue

            if other is victim:
                continue

            if other.faction != victim.faction:
                continue

            dist = (other.get_pos() - victim.get_pos()).length()

            if dist <= adjusted_radius:
                other.set_aggro(attacker)

    # ------------------------------------------------------------
    # execute movement / combat from current behavior
    # ------------------------------------------------------------
    def update_combat_and_movement(self, dt):
        for npc in self.npcs:
            if npc.is_dead:
                continue

            profile = npc.behavior_profile

            # FLEEING
            if npc.current_behavior == "fleeing":
                threat, threat_dist = self.find_nearest_threat(npc)

                if threat is not None:
                    ally, ally_dist = self.find_nearest_ally(npc)

                    if ally is not None and ally_dist <= NPC_ALLY_HELP_RADIUS * profile["loyalty"]:
                        self.move_toward_target(
                            npc,
                            ally,
                            dt,
                            speed=NPC_FLEE_SPEED,
                            stop_distance=1.5,
                        )
                    else:
                        self.move_away_from_threat(npc, threat, dt)

                    if threat_dist >= NPC_SAFE_DISTANCE:
                        npc.is_fleeing = False

                continue

            # AGGRESSIVE
            if npc.current_behavior == "aggressive":
                # ------------------------------------------------
                # Kalchakra use one shared group target
                # this keeps them as one big dogpile
                # ------------------------------------------------
                if npc.faction == "kalchakra":
                    target = self.kalchakra_group_target

                    if target is None or target.is_dead:
                        self.update_idle_wander(npc, dt)
                        continue

                    npc.attack_target = target
                    self.move_toward_target(npc, target, dt)

                    target_dist = (target.get_pos() - npc.get_pos()).length()

                    if target_dist <= NPC_ATTACK_RANGE and npc.attack_cooldown <= 0:
                        target.take_damage(NPC_ATTACK_DAMAGE, npc.name)
                        npc.attack_cooldown = NPC_ATTACK_COOLDOWN

                        target.set_aggro(npc)
                        self.alert_nearby_allies(target, npc)

                        if PRINT_ATTACK_EVENTS:
                            print(f"[ATTACK] {npc.name} -> {target.name} | hp={target.hp:.1f}")

                    continue

                # ------------------------------------------------
                # normal aggression for non-Kalchakra
                # ------------------------------------------------
                target, target_dist = self.find_nearest_enemy(npc)
                npc.attack_target = target

                if target is None:
                    target = self.find_any_enemy(npc)

                    if target is not None:
                        npc.attack_target = target
                        self.move_toward_target(npc, target, dt)
                    else:
                        self.update_idle_wander(npc, dt)

                    continue

                if self.is_target_too_far_from_home(npc, target):
                    npc.attack_target = None
                    self.update_idle_wander(npc, dt)
                    continue

                self.move_toward_target(npc, target, dt)

                if target_dist <= NPC_ATTACK_RANGE and npc.attack_cooldown <= 0:
                    target.take_damage(NPC_ATTACK_DAMAGE, npc.name)
                    npc.attack_cooldown = NPC_ATTACK_COOLDOWN

                    target.set_aggro(npc)
                    self.alert_nearby_allies(target, npc)

                    if PRINT_ATTACK_EVENTS:
                        print(f"[ATTACK] {npc.name} -> {target.name} | hp={target.hp:.1f}")

                continue

            # ALERT
            if npc.current_behavior == "alert":
                npc.attack_target = None
                self.update_idle_wander(npc, dt)
                continue

            # IDLE
            if npc.current_behavior == "idle":
                npc.attack_target = None
                self.update_idle_wander(npc, dt)
                continue

    # ------------------------------------------------------------
    # spread contagion
    # ------------------------------------------------------------
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

    # ------------------------------------------------------------
    # main world loop
    # ------------------------------------------------------------
    def update(self, task):
        dt = globalClock.getDt()
        player_pos = self.get_player_pos()

        self.update_kalchakra_group_direction(dt)
        self.update_kalchakra_group_target(dt)

        emitted = []

        for npc in self.npcs:
            packet = npc.update(player_pos, dt)
            if packet:
                emitted.append((npc, packet))

        for source, packet in emitted:
            self.spread_contagion(source, packet)

        self.update_combat_and_movement(dt)

        return Task.cont