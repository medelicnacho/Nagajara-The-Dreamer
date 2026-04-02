# ============================================================
# settings.py
# central tuning file for nagajara
# keep easy-to-change gameplay and ai values here
# ============================================================


# ============================================================
# PLAYER SETTINGS
# values for player movement and player collision body
# ============================================================

PLAYER_SPEED = 8              # how fast the player moves
PLAYER_HEIGHT = 1.75          # height of the player collision capsule
PLAYER_RADIUS = 0.4           # radius of the player collision capsule


# ============================================================
# CAMERA SETTINGS
# third-person camera follow values
# ============================================================

CAM_DISTANCE = 12             # how far the camera sits behind the player
CAM_HEIGHT = 4                # how high the camera sits above the player


# ============================================================
# NPC RANGE / LOD SETTINGS
# controls when npcs stay cheap vs when they wake up more
# ============================================================

BARK_RANGE = 18               # within this range npc can show cheap markov bark text
INTERACT_RANGE = 6            # within this range npc can use phi-3 response mode
DIRECT_TALK_RANGE = 4         # very close range for direct conversation / memory writeback


# ============================================================
# NPC BRAIN TICK SETTINGS
# controls cheap rust brain update timing
# ============================================================

NPC_TICK_RATE_FAR = 2.0       # far npc brain updates every 2.0 seconds
NPC_TICK_RATE_MID = 0.75      # mid npc brain updates every 0.75 seconds
NPC_TICK_RATE_CLOSE = 0.25    # close npc brain updates every 0.25 seconds


# ============================================================
# CONTAGION SETTINGS
# controls how social emotion spread works between npcs
# ============================================================

CONTAGION_RADIUS = 8.0        # how close npcs must be to affect each other
CONTAGION_FEAR_GAIN = 0.25    # default fear gain when fear packet is received
CONTAGION_STRESS_GAIN = 0.15  # default stress gain when stress packet is received
CONTAGION_CURIOSITY_GAIN = 0.20   # default curiosity gain from interesting events
CONTAGION_TRUST_GAIN = 0.10   # default trust gain from positive social influence

# thresholds for deciding whether an npc is "emotionally loud"
# enough to broadcast contagion to nearby minds
CONTAGION_FEAR_THRESHOLD = 0.60
CONTAGION_STRESS_THRESHOLD = 0.70
CONTAGION_CURIOSITY_THRESHOLD = 0.65
CONTAGION_TRUST_THRESHOLD = 0.70

# stabilization for contagion
CONTAGION_EMIT_COOLDOWN = 3.0     # npc must wait this many seconds before emitting again
CONTAGION_EMIT_CHANCE = 0.20      # chance to emit when emotion is above threshold

# optional distance falloff control
# if True, closer npcs receive stronger contagion
# if False, everyone in radius receives the same flat intensity
CONTAGION_USE_DISTANCE_FALLOFF = True


# ============================================================
# RUST BRAIN MEMORY SETTINGS
# keeps npc memory/history cheap and scalable
# ============================================================

NPC_MEMORY_LIMIT = 6          # max short memory tags stored per npc
NPC_STATE_HISTORY_LIMIT = 10  # max recent emotional states stored per npc


# ============================================================
# SIMPLE NPC COMBAT SETTINGS
# first pass for npc vs npc killing
# ============================================================

NPC_MAX_HP = 100.0            # base hp for every npc
NPC_ATTACK_RANGE = 3.0        # how close npcs must be to hit each other
NPC_ATTACK_DAMAGE = 10.0      # flat damage per hit
NPC_ATTACK_COOLDOWN = 1.2     # seconds between attacks

# emotional gate for aggression
# npc only attacks enemies if one of these is high enough
NPC_ATTACK_FEAR_THRESHOLD = 0.70
NPC_ATTACK_STRESS_THRESHOLD = 0.70


# ============================================================
# BRAIN SERVER / PHI-3 SETTINGS
# local llm translator settings
# this is only for nearby/direct npc interaction
# ============================================================

BRAIN_SERVER_HOST = "127.0.0.1"      # local brain server address
BRAIN_SERVER_PORT = 50001            # port used by brain_server.py
PHI3_MODEL_PATH = "models/phi3.gguf" # path to local phi-3 gguf file
MAX_TOKENS = 60                      # max response length from phi-3
PHI3_TIMEOUT = 10                    # timeout for llm response in seconds


# ============================================================
# DEBUG SETTINGS
# useful for testing while building the systems
# ============================================================

PRINT_NPC_THOUGHTS = True            # print npc thoughts in terminal for debugging
PRINT_CONTAGION_EVENTS = True        # print contagion packets for debugging
PRINT_LOD_CHANGES = True             # print when npc changes lod mode
PRINT_ATTACK_EVENTS = True           # print attacks for debugging
PRINT_DEATH_EVENTS = True            # print deaths for debugging

# ============================================================
# SIMPLE NPC MOVEMENT SETTINGS
# first pass for npc chasing behavior
# ============================================================

NPC_MOVE_SPEED = 2.5          # how fast npcs move toward targets
NPC_STOP_DISTANCE = 2.2       # stop a little before fully overlapping target