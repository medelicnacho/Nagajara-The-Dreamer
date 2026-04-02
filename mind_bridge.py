def build_prompt_from_mind(mind):
    dominant_state, subconscious_state, active_topic, thought_buffer, memory, speech_desire = mind.get_bridge_packet()

    joined_thoughts = " | ".join(thought_buffer[-5:])
    joined_memory = ", ".join(memory[-4:]) if memory else "none"

    return f"""
You are an NPC in Nagajara.
Dominant mood: {dominant_state}
Current subconscious state: {subconscious_state}
Active topic: {active_topic}
Recent inner thoughts: {joined_thoughts}
Recent memory tags: {joined_memory}

Speak in 1-2 sentences max.
Stay in character.
""".strip()
