import brain_logic
from mind_bridge import build_prompt_from_mind
from settings import (
    INTERACT_RANGE,
    BARK_RANGE,
    NPC_TICK_RATE_FAR,
    NPC_TICK_RATE_MID,
    NPC_TICK_RATE_CLOSE,
)


class NPC:
    def __init__(self, name, node):
        self.name = name
        self.node = node

        self.mind = brain_logic.NpcMind(name)
        self.tick_timer = 0.0

    def update(self, player_pos, dt):
        # distance check
        npc_pos = self.node.getPos()
        distance = (npc_pos - player_pos).length()

        # LOD logic
        if distance < INTERACT_RANGE:
            mode = "close"
            tick_rate = NPC_TICK_RATE_CLOSE
        elif distance < BARK_RANGE:
            mode = "mid"
            tick_rate = NPC_TICK_RATE_MID
        else:
            mode = "far"
            tick_rate = NPC_TICK_RATE_FAR

        # timer update
        self.tick_timer += dt

        # tick brain only when ready
        if self.tick_timer >= tick_rate:
            self.tick_timer = 0.0
            self.mind.tick()

            packet = self.mind.get_bridge_packet()
            dominant, sub, topic, thoughts, memory, speech = packet

            print(f"[{mode}] {sub} | {topic} | {thoughts[-1] if thoughts else '...'}")

            if mode == "close":
                prompt = build_prompt_from_mind(self.mind)

                print("\n--- PROMPT ---")
                print(prompt)
