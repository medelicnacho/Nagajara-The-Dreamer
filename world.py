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
    # explanation:
    # this builds the whole world state.
    #
    # what this block does:
    # - stores the game reference
    # - stores all npc objects
    # - creates shared Kalchakra movement state
    # - creates shared Kalchakra target state
    # - spawns all three factions
    # - starts the Panda3D update loop
    #
    # how it fits into the code:
    # this is the top-level setup for everything that happens later.
    # if this is wrong, the rest of the simulation has nothing to run on.
    # ------------------------------------------------------------
    def __init__(self, game):
        self.game = game
        self.npcs = []

        # --------------------------------------------------------
        # explanation:
        # shared Kalchakra movement direction.
        #
        # what this block does:
        # - gives the whole red faction one general drift direction
        # - gives them one timer for when that group direction changes
        #
        # how it fits into the code:
        # this is what keeps Kalchakra feeling like one roaming war band
        # instead of 50 independent wanderers.
        # --------------------------------------------------------
        self.kalchakra_group_dir = self.random_flat_dir()
        self.kalchakra_group_turn_timer = random.uniform(6.0, 12.0)

        # --------------------------------------------------------
        # explanation:
        # shared Kalchakra combat target.
        #
        # what this block does:
        # - stores one target for the whole red faction
        # - stores a timer so they do not switch targets every frame
        #
        # how it fits into the code:
        # this is what makes the red faction dogpile one enemy group
        # instead of spreading out toward random individual targets.
        # --------------------------------------------------------
        self.kalchakra_group_target = None
        self.kalchakra_group_target_timer = 0.0

        # --------------------------------------------------------
        # explanation:
        # faction population spawns.
        #
        # what this block does:
        # - spawns Kalchakra in one region
        # - spawns Atimarga in one region
        # - spawns Nirmanakaya in one region
        #
        # how it fits into the code:
        # this gives each faction a starting homeland / pressure zone
        # so the simulation has space and direction.
        # --------------------------------------------------------
        self.spawn_population(
            faction="kalchakra",
            name_prefix="Kal",
            count=50,
            center_x=-100,
            center_y=-50,
            center_z=0,
            spread_radius=50,
        )

        self.spawn_population(
            faction="atimarga",
            name_prefix="Ati",
            count=50,
            center_x=0,
            center_y=-100,
            center_z=0,
            spread_radius=50,
        )

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
    # explanation:
    # make a random flat direction.
    #
    # what this block does:
    # - creates a random x/y vector
    # - keeps z at 0 so movement stays flat on the map
    # - normalizes it so it has clean direction length
    #
    # how it fits into the code:
    # this is the base helper for wandering, fleeing, and group drift.
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
    # explanation:
    # safely normalize a flat direction.
    #
    # what this block does:
    # - strips z movement
    # - prevents divide-by-zero style bad vectors
    # - returns a clean normalized direction
    #
    # how it fits into the code:
    # this keeps all motion helpers stable and prevents weird bad vectors.
    # ------------------------------------------------------------
    def safe_normalize(self, vec):
        out = Vec3(vec.x, vec.y, 0)

        if out.length_squared() <= 0.0001:
            return Vec3(1, 0, 0)

        out.normalize()
        return out

    # ------------------------------------------------------------
    # explanation:
    # blend one direction into another.
    #
    # what this block does:
    # - mixes old direction with new desired direction
    # - makes turning smoother instead of snapping
    #
    # how it fits into the code:
    # this keeps wandering motion from looking robotic or jittery.
    # ------------------------------------------------------------
    def blend_direction(self, current_dir, desired_dir, turn_strength):
        blended = (current_dir * (1.0 - turn_strength)) + (desired_dir * turn_strength)
        return self.safe_normalize(blended)

    # ------------------------------------------------------------
    # explanation:
    # update shared Kalchakra roaming direction.
    #
    # what this block does:
    # - counts down a group turn timer
    # - occasionally picks a new shared direction
    # - blends it so the turn is smooth
    #
    # how it fits into the code:
    # this keeps Kalchakra roaming as one large moving faction.
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
    # explanation:
    # update shared Kalchakra group target.
    #
    # what this block does:
    # - finds the center of the whole Kalchakra pack
    # - finds the nearest non-Kalchakra target to that pack center
    # - locks that target for a short time
    #
    # how it fits into the code:
    # this is the dogpile logic.
    # one target for the whole war band means they stay grouped in combat.
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
    # explanation:
    # spawn one npc.
    #
    # what this block does:
    # - loads a simple box model
    # - colors it by faction
    # - wraps it in the NPC class
    # - stores a home position
    # - gives it initial movement data
    #
    # how it fits into the code:
    # this is the bridge between the visual world and the AI/state object.
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
    # explanation:
    # spawn a full population around a center point.
    #
    # what this block does:
    # - makes many npcs for one faction
    # - spreads them around a region
    #
    # how it fits into the code:
    # this is how each faction becomes a real group instead of one unit.
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
    # explanation:
    # placeholder player position.
    #
    # what this block does:
    # - returns world origin for now
    #
    # how it fits into the code:
    # npc.py still expects a player position for lod / bark timing logic.
    # ------------------------------------------------------------
    def get_player_pos(self):
        return Vec3(0, 0, 0)

    # ------------------------------------------------------------
    # explanation:
    # find nearest current enemy.
    #
    # what this block does:
    # - prefers a saved aggro target if still valid
    # - otherwise finds the nearest attackable enemy
    #
    # how it fits into the code:
    # this is the normal target selection helper for most factions.
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
    # explanation:
    # find nearest threat.
    #
    # what this block does:
    # - finds the nearest living enemy regardless of aggression
    #
    # how it fits into the code:
    # fleeing units use this to know what they are running from.
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
    # explanation:
    # find nearest ally.
    #
    # what this block does:
    # - finds the nearest living same-faction ally
    #
    # how it fits into the code:
    # fleeing units can run toward help instead of always just away.
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
    # explanation:
    # find nearby same-faction allies.
    #
    # what this block does:
    # - returns a list of same-faction allies in a radius
    #
    # how it fits into the code:
    # this powers group spacing, separation, and swarm behavior.
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
    # explanation:
    # find any enemy anywhere.
    #
    # what this block does:
    # - finds the closest attackable enemy without needing current aggro
    #
    # how it fits into the code:
    # this lets aggressive units hunt instead of doing nothing when
    # there is no immediate nearby target.
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
    # explanation:
    # move toward a raw position.
    #
    # what this block does:
    # - computes direction to a point
    # - moves at a given speed
    #
    # how it fits into the code:
    # this is a low-level physical movement helper.
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
    # explanation:
    # move away from a raw position.
    #
    # what this block does:
    # - computes direction away from danger
    # - moves at a given speed
    #
    # how it fits into the code:
    # this is a low-level escape helper.
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
    # explanation:
    # move toward a target npc.
    #
    # what this block does:
    # - moves toward another npc
    # - respects stop distance
    # - supports optional custom speed
    #
    # how it fits into the code:
    # this is the main chase / assist movement helper used in combat.
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
    # explanation:
    # move away from a threat npc.
    #
    # what this block does:
    # - runs directly away from a threat
    # - falls back to random if the direction becomes degenerate
    #
    # how it fits into the code:
    # this is the main fleeing movement helper.
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
    # explanation:
    # choose a desired idle wander direction.
    #
    # what this block does:
    # - Atimarga: long solo drifting with light separation
    # - Kalchakra: shared group drift with slight anti-clump
    # - Nirmanakaya: idle
    #
    # how it fits into the code:
    # this is the faction personality for idle motion.
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
    # explanation:
    # refresh current idle direction.
    #
    # what this block does:
    # - computes desired direction
    # - blends into it
    # - resets turn timers by faction
    #
    # how it fits into the code:
    # this makes idle movement feel smooth and faction-specific.
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
    # explanation:
    # update idle / alert wandering.
    #
    # what this block does:
    # - keeps idle factions moving
    # - keeps Nirmanakaya still
    # - advances direction timers
    #
    # how it fits into the code:
    # this is the default physical movement path when not chasing.
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
    # explanation:
    # decide if a target is too far from home.
    #
    # what this block does:
    # - lets Kalchakra ignore home limits
    # - keeps other factions from map-wide crazy chases
    #
    # how it fits into the code:
    # this keeps more defensive factions grounded while leaving
    # Kalchakra free to raid hard.
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
    # explanation:
    # alert nearby allies on attack.
    #
    # what this block does:
    # - same-faction allies in radius get aggro on the attacker
    #
    # how it fits into the code:
    # this is the normal "you hit one, nearby allies notice" response.
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
    # explanation:
    # alert nearby allies on death.
    #
    # what this block does:
    # - same-faction allies in a bigger radius get aggro
    # - adds an emotional spike so they respond harder
    #
    # how it fits into the code:
    # this fixes the problem where somebody dies too fast and the
    # rest of the faction never really reacts in time.
    # ------------------------------------------------------------
    def alert_allies_on_death(self, victim, killer):
        victim_profile = victim.behavior_profile
        death_radius = NPC_AGGRO_RADIUS * victim_profile["loyalty"] * 2.5

        for other in self.npcs:
            if other.is_dead:
                continue
            if other is victim:
                continue
            if other.faction != victim.faction:
                continue

            dist = (other.get_pos() - victim.get_pos()).length()

            if dist <= death_radius:
                other.set_aggro(killer)
                other.mind.nudge("stress", 0.35)
                other.mind.nudge("fear", 0.15)

                try:
                    other.mind.nudge("aggression", 0.45)
                except Exception:
                    pass

                # give them a specific target to chase
                other.attack_target = killer
                other.revenge_target = killer

    # ------------------------------------------------------------
    # explanation:
    # execute combat and movement from current behavior.
    #
    # what this block does:
    # - fleeing units run or seek allied help
    # - aggressive Kalchakra use one shared target
    # - aggressive non-Kalchakra use nearest valid target
    # - revenge targets ignore home distance limits
    # - attacks can trigger nearby ally aggro
    # - kills trigger stronger death-aggro
    #
    # how it fits into the code:
    # this is the main physical action layer of the simulation.
    # npc.py decides what the npc wants, and this block makes it happen.
    # ------------------------------------------------------------
    def update_combat_and_movement(self, dt):
        for npc in self.npcs:
            if npc.is_dead:
                continue

            profile = npc.behavior_profile

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

            if npc.current_behavior == "aggressive":
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

                        if target.is_dead:
                            self.alert_allies_on_death(target, npc)

                        npc.attack_cooldown = NPC_ATTACK_COOLDOWN

                        target.set_aggro(npc)
                        self.alert_nearby_allies(target, npc)

                        if PRINT_ATTACK_EVENTS:
                            print(f"[ATTACK] {npc.name} -> {target.name} | hp={target.hp:.1f}")

                    continue

                # ------------------------------------------------
                # explanation:
                # non-Kalchakra aggressive behavior with revenge targeting.
                #
                # what this block does:
                # - prefers revenge_target if one exists and is alive
                # - remembers whether the chosen target is a revenge chase
                # - skips the home distance cancel if this is revenge
                #
                # how it fits into the code:
                # this is the rage contagion fix.
                # death aggro should commit to the killer instead of
                # getting canceled by normal tether rules.
                # ------------------------------------------------
                is_revenge_target = False

                if hasattr(npc, "revenge_target") and npc.revenge_target is not None:
                    if not npc.revenge_target.is_dead:
                        target = npc.revenge_target
                        target_dist = (target.get_pos() - npc.get_pos()).length()
                        is_revenge_target = True
                    else:
                        npc.revenge_target = None
                        target, target_dist = self.find_nearest_enemy(npc)
                else:
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

                # ------------------------------------------------
                # explanation:
                # normal home tether check.
                #
                # what this block does:
                # - only cancels far-away targets if this is NOT revenge
                #
                # how it fits into the code:
                # revenge chases are supposed to punch through the usual
                # territorial leash so the killer gets hunted properly.
                # ------------------------------------------------
                if not is_revenge_target:
                    if self.is_target_too_far_from_home(npc, target):
                        npc.attack_target = None
                        self.update_idle_wander(npc, dt)
                        continue

                self.move_toward_target(npc, target, dt)

                if target_dist <= NPC_ATTACK_RANGE and npc.attack_cooldown <= 0:
                    target.take_damage(NPC_ATTACK_DAMAGE, npc.name)

                    if target.is_dead:
                        self.alert_allies_on_death(target, npc)

                        # clear revenge target if the revenge chase succeeded
                        if is_revenge_target and hasattr(npc, "revenge_target"):
                            if npc.revenge_target is target:
                                npc.revenge_target = None

                    npc.attack_cooldown = NPC_ATTACK_COOLDOWN

                    target.set_aggro(npc)
                    self.alert_nearby_allies(target, npc)

                    if PRINT_ATTACK_EVENTS:
                        print(f"[ATTACK] {npc.name} -> {target.name} | hp={target.hp:.1f}")

                continue

            if npc.current_behavior == "alert":
                npc.attack_target = None
                self.update_idle_wander(npc, dt)
                continue

            if npc.current_behavior == "idle":
                npc.attack_target = None
                self.update_idle_wander(npc, dt)
                continue

    # ------------------------------------------------------------
    # explanation:
    # spread contagion.
    #
    # what this block does:
    # - sends emotional packets to nearby npcs
    # - applies optional distance falloff
    #
    # how it fits into the code:
    # this is how moods and pressure ripple through the world.
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
    # explanation:
    # main world loop.
    #
    # what this block does:
    # - updates shared Kalchakra movement state
    # - updates shared Kalchakra target state
    # - ticks npc internal logic
    # - spreads contagion
    # - runs movement and combat
    #
    # how it fits into the code:
    # this is the heartbeat of the whole simulation.
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