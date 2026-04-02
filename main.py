from direct.showbase.ShowBase import ShowBase

from world import World


class Game(ShowBase):
    def __init__(self):
        super().__init__()

        # make the world and pass the game into it
        self.world = World(self)


game = Game()
game.run()
