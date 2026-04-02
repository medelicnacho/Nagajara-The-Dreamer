from direct.task import Task
from panda3d.core import Vec3

from npc import NPC


class World:
    def __init__(self, game):
        self.game = game

        # make one simple npc body in the world
        npc_model = self.game.loader.loadModel("models/box")
        npc_model.reparentTo(self.game.render)
        npc_model.setPos(5, 10, 0)

        # wrap the panda body with your python npc class
        self.npc = NPC("Ralph", npc_model)

        # start update loop
        self.game.taskMgr.add(self.update, "world_update")

    def update(self, task):
        dt = globalClock.getDt()

        # fake player position for now
        player_pos = Vec3(0, 0, 0)

        # update npc brain/body logic
        self.npc.update(player_pos, dt)

        return Task.cont
