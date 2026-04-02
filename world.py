from panda3d.core import Vec3
from direct.task import Task

from npc import NPC
from settings import (
    CONTAGION_RADIUS,
    CONTAGION_USE_DISTANCE_FALLOFF,
    PRINT_CONTAGION_EVENTS,
)


class World:
    def __init__(self, game):
        self.game = game

        # ============================================================
        # NPC STORAGE
        # world owns the list of all live npc wrappers
        # this makes it easy to do group systems like contagion later
        # ============================================================
        self.npcs = []

        # ============================================================
        # TEST NPC SETUP
        # make a few simple boxes so contagion has someone to spread to
        # ============================================================
        self.spawn_npc("Ralph", 5, 10, 0, faction="kalchakra")
        self.spawn_npc("Mira", 8, 11, 0, faction="kalchakra")
        self.spawn_npc("Tovin", 12, 9, 0, faction="kalchakra")

        # start main update loop
        self.game.taskMgr.add(self.update, "world_update")

    # ============================================================
    # SPAWN NPC
    # tiny helper so npc creation stays clean
    # ============================================================
    def spawn_npc(self, name, x, y, z, faction="kalchakra"):
        npc_model = self.game.loader.loadModel("models/box")  # simple placeholder body
        npc_model.reparentTo(self.game.render)                # attach to the world scene
        npc_model.setPos(x, y, z)                             # place it in the world

        npc = NPC(name, npc_model, faction=faction)           # wrap node with gameplay logic
        self.npcs.append(npc)                                 # store for updates / contagion
        return npc

    # ============================================================
    # PLAYER POSITION
    # right now still fake, because your player system is placeholder
    # later this should come from self.player.node or similar
    # ============================================================
    def get_player_pos(self):
        return Vec3(0, 0, 0)

    # ============================================================
    # DISTANCE FALLOFF
    # closer contagion hits harder, farther contagion hits weaker
    # result is always between 0.0 and 1.0
    # ============================================================
    def get_contagion_falloff(self, distance):
        if distance >= CONTAGION_RADIUS:
            return 0.0

        if not CONTAGION_USE_DISTANCE_FALLOFF:
            return 1.0

        # simple linear falloff:
        # 0 distance  -> 1.0 strength
        # max radius  -> 0.0 strength
        return 1.0 - (distance / CONTAGION_RADIUS)

    # ============================================================
    # DISTRIBUTE CONTAGION
    # source npc already decided what emotion to emit
    # world decides who is close enough to receive it
    # ============================================================
    def spread_contagion_from(self, source_npc, packet):
        if packet is None:
            return

        source_pos = source_npc.get_pos()                     # where the source lives in world
        emotion = packet["emotion"]                           # ex: fear / stress / curiosity
        base_intensity = packet["intensity"]                  # default gain from settings
        topic = packet["topic"]                               # current thought topic tint

        for target_npc in self.npcs:
            if target_npc is source_npc:
                continue                                      # do not infect yourself

            target_pos = target_npc.get_pos()
            distance = (target_pos - source_pos).length()     # source-target distance

            if distance > CONTAGION_RADIUS:
                continue                                      # too far away, ignore

            falloff = self.get_contagion_falloff(distance)    # scale by distance
            final_intensity = base_intensity * falloff        # weaker farther away

            if final_intensity <= 0.0:
                continue                                      # safety check

            target_npc.receive_contagion(
                emotion=emotion,
                intensity=final_intensity,
                topic=topic,
            )

            if PRINT_CONTAGION_EVENTS:
                print(
                    f"[CONTAGION] "
                    f"{source_npc.name} -> {target_npc.name} | "
                    f"emotion={emotion} topic={topic} "
                    f"distance={distance:.2f} intensity={final_intensity:.2f}"
                )

    # ============================================================
    # UPDATE
    # 1) update every npc
    # 2) collect any contagion packets that were emitted
    # 3) spread those packets to nearby npcs
    # ============================================================
    def update(self, task):
        dt = globalClock.getDt()              # frame delta time from Panda3D
        player_pos = self.get_player_pos()    # fake for now until player is real

        emitted_packets = []                  # stores (source_npc, packet) for this frame

        # step 1: update all npc brains / lod / bark logic
        for npc in self.npcs:
            packet = npc.update(player_pos, dt)

            # if npc emitted contagion this tick, remember it for pass 2
            if packet is not None:
                emitted_packets.append((npc, packet))

        # step 2: do contagion after all minds have had their own tick first
        # this avoids order weirdness where earlier npcs affect later npcs
        # before those later npcs got their own normal update
        for source_npc, packet in emitted_packets:
            self.spread_contagion_from(source_npc, packet)

        return Task.cont
