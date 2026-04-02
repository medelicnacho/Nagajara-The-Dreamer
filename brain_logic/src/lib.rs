use pyo3::prelude::*;
use pyo3::types::PyModule;
use rand::seq::SliceRandom;
use rand::thread_rng;
use std::collections::HashMap;

// ------------------------------------------------------------
// WHAT THIS FILE DOES
//
// this is the cheap Rust brain for each npc
//
// in simple language:
// - layer 1 picks a subconscious mood/state
// - layer 2 picks a topic based on that state
// - layer 3 picks a short thought fragment
// - scalar emotions (fear, stress, curiosity, trust, aggression) bias the result
// - python asks this brain what the npc feels/thinks
//
// python handles:
// - movement
// - combat
// - faction colors
// - spacing / distance / neighbors
//
// Rust handles:
// - cheap inner cognition
// ------------------------------------------------------------


// ============================================================
// LAYER 1 - SUBCONSCIOUS STATE GRAPH
// cheap emotional drift that can run on lots of NPCs
// ============================================================

fn get_subconscious_transitions(state: &str) -> Vec<&'static str> {
    match state {
        "drifting"   => vec!["curious", "watchful", "drifting", "uneasy"],
        "curious"    => vec!["curious", "drifting", "hopeful", "watchful"],
        "watchful"   => vec!["watchful", "uneasy", "suspicious", "curious"],
        "uneasy"     => vec!["uneasy", "fearful", "suspicious", "watchful"],
        "fearful"    => vec!["fearful", "uneasy", "resigned", "desperate"],
        "desperate"  => vec!["desperate", "fearful", "angry"],
        "angry"      => vec!["angry", "aggressive", "uneasy"],
        "aggressive" => vec!["aggressive", "angry", "watchful"],
        "suspicious" => vec!["suspicious", "watchful", "uneasy", "curious"],
        "hopeful"    => vec!["hopeful", "curious", "drifting"],
        "resigned"   => vec!["resigned", "sad", "drifting"],
        "sad"        => vec!["sad", "resigned", "uneasy", "drifting"],
        _ => vec!["drifting"],
    }
}

// ============================================================
// LAYER 2 - TOPIC MARKOV
// subconscious state nudges what kind of thought becomes active
// ============================================================

fn get_topic_candidates(state: &str) -> Vec<&'static str> {
    match state {
        "drifting"   => vec!["place", "place", "presence", "memory"],
        "curious"    => vec!["mystery", "path", "ruin", "discovery"],
        "watchful"   => vec!["danger", "presence", "movement", "guard"],
        "uneasy"     => vec!["wrongness", "ground", "danger", "presence"],
        "fearful"    => vec!["danger", "hunt", "escape", "collapse"],
        "desperate"  => vec!["help", "escape", "collapse"],
        "angry"      => vec!["revenge", "challenge", "threat"],
        "aggressive" => vec!["challenge", "threat", "dominate"],
        "suspicious" => vec!["lie", "presence", "threat", "motive"],
        "hopeful"    => vec!["change", "future", "discovery"],
        "resigned"   => vec!["ending", "acceptance", "memory"],
        "sad"        => vec!["loss", "memory", "ending"],
        _ => vec!["place"],
    }
}

// ============================================================
// LAYER 3 - THOUGHT FRAGMENTS
// short thought seeds; python can pass recent 5 to the llm server
// ============================================================

fn get_thought_fragments(topic: &str) -> Vec<&'static str> {
    match topic {
        "place"      => vec!["this place feels familiar", "the air remembers something", "the dream folds strangely here"],
        "presence"   => vec!["something is nearby", "I am not alone here", "eyes are on me"],
        "memory"     => vec!["I almost remember", "something old is surfacing", "this feeling has happened before"],
        "mystery"    => vec!["there is something worth knowing", "something waits beyond this", "the answer is close"],
        "path"       => vec!["where does this road lead", "the path is pulling me onward", "I should follow this trail"],
        "ruin"       => vec!["these ruins hide a meaning", "stone keeps old secrets", "someone left signs here"],
        "discovery"  => vec!["I have not seen this before", "there is a pattern here", "something can be learned"],
        "danger"     => vec!["something is wrong", "danger presses in", "I should be careful now"],
        "movement"   => vec!["movement at the edge", "something shifted nearby", "I caught something moving"],
        "guard"      => vec!["do not show weakness", "stay sharp", "hold yourself together"],
        "ground"     => vec!["the ground does not feel stable", "the world beneath me is uncertain", "this land is not still"],
        "wrongness"  => vec!["this place is off somehow", "something here is deeply wrong", "the dream is bending badly"],
        "hunt"       => vec!["something hunts me", "I feel like prey", "I am being tracked"],
        "escape"     => vec!["I need a way out", "I should leave while I still can", "staying here is a mistake"],
        "collapse"   => vec!["this could all come apart", "the dream feels fragile", "everything could break open"],
        "help"       => vec!["someone must hear me", "I cannot carry this alone", "I need help now"],
        "revenge"    => vec!["they took what was mine", "I have not forgotten", "something in me wants repayment"],
        "challenge"  => vec!["test me and see", "someone will answer for this", "step forward if you dare"],
        "threat"     => vec!["I do not trust what is near", "there is threat in this moment", "someone here means harm"],
        "dominate"   => vec!["step aside", "I will not yield", "I can force this open"],
        "lie"        => vec!["someone is hiding something", "the truth is being bent", "I do not believe what I hear"],
        "motive"     => vec!["why are you here", "what do they really want", "there is a hidden reason"],
        "change"     => vec!["maybe things can be different", "something good could still happen", "the pattern may yet change"],
        "future"     => vec!["there may be another way", "this does not have to end here", "something better is possible"],
        "ending"     => vec!["it may be ending", "some things are already gone", "this feels like a final turn"],
        "acceptance" => vec!["I have made my peace", "some things must pass", "I can let this settle"],
        "loss"       => vec!["I miss what was", "something has been lost", "I feel the absence again"],
        _ => vec!["..."],
    }
}

// ------------------------------------------------------------
// helper: clamp a float into 0.0 to 1.0
// used for emotion values
// ------------------------------------------------------------
fn clamp01(v: f32) -> f32 {
    v.clamp(0.0, 1.0)
}

// ------------------------------------------------------------
// helper: push into a vector but keep it capped
// used for thought buffers, memory, and state history
// ------------------------------------------------------------
fn capped_push(buffer: &mut Vec<String>, value: String, max_len: usize) {
    buffer.push(value);
    if buffer.len() > max_len {
        buffer.remove(0);
    }
}

// ------------------------------------------------------------
// bias subconscious transitions based on current scalar emotions
//
// simple idea:
// - high fear pushes fearful/suspicious states
// - high stress pushes uneasy/desperate states
// - high curiosity pushes curious more often
// - high trust pushes hopeful/drifting more often
// - high aggression pushes angry/aggressive states
// ------------------------------------------------------------
fn get_biased_transitions(
    state: &str,
    fear: f32,
    stress: f32,
    curiosity: f32,
    trust: f32,
    aggression: f32,
) -> Vec<&'static str> {
    let mut options = get_subconscious_transitions(state);

    if fear > 0.6 {
        options.push("fearful");
        options.push("suspicious");
    }

    if stress > 0.7 {
        options.push("uneasy");
        options.push("desperate");
    }

    if curiosity > 0.6 {
        options.push("curious");
        options.push("curious");
    }

    if trust > 0.6 {
        options.push("hopeful");
        options.push("drifting");
    }

    if aggression > 0.6 {
        options.push("angry");
        options.push("aggressive");
        options.push("aggressive");
    }

    options
}

// ------------------------------------------------------------
// cheap numeric guess for how much the npc wants to speak
//
// this is useful later for LLM gating
// ------------------------------------------------------------
fn calculate_speech_desire(
    state: &str,
    fear: f32,
    stress: f32,
    curiosity: f32,
    aggression: f32,
) -> f32 {
    let base = match state {
        "desperate" | "angry" | "aggressive" => 0.85,
        "fearful" | "suspicious" | "watchful" => 0.65,
        "curious" | "hopeful" => 0.45,
        _ => 0.25,
    };

    clamp01(base + (fear * 0.15) + (stress * 0.1) + (curiosity * 0.1) + (aggression * 0.15))
}

// ============================================================
// NPC BRAIN
// this struct is what Python creates for each npc
// ============================================================

#[pyclass]
pub struct NpcMind {
    #[pyo3(get)]
    pub name: String,

    // --------------------------------------------------------
    // scalar emotions
    // these are the cheap numeric emotional values
    // --------------------------------------------------------
    #[pyo3(get)]
    pub fear: f32,
    #[pyo3(get)]
    pub stress: f32,
    #[pyo3(get)]
    pub curiosity: f32,
    #[pyo3(get)]
    pub trust: f32,
    #[pyo3(get)]
    pub aggression: f32,

    // layer 1
    #[pyo3(get)]
    pub subconscious_state: String,

    // layer 2
    #[pyo3(get)]
    pub active_topic: String,

    // layer 3
    #[pyo3(get)]
    pub last_thought: String,
    #[pyo3(get)]
    pub thought_buffer: Vec<String>,

    // memory-ish short buffers
    #[pyo3(get)]
    pub memory: Vec<String>,
    #[pyo3(get)]
    pub state_history: Vec<String>,

    // cheap speech desire value
    #[pyo3(get)]
    pub speech_desire: f32,
}

#[pymethods]
impl NpcMind {
    // --------------------------------------------------------
    // create a brand-new npc mind
    // --------------------------------------------------------
    #[new]
    fn new(name: String) -> Self {
        Self {
            name,
            fear: 0.0,
            stress: 0.0,
            curiosity: 0.5,
            trust: 0.0,
            aggression: 0.0,
            subconscious_state: "drifting".to_string(),
            active_topic: "place".to_string(),
            last_thought: "...".to_string(),
            thought_buffer: Vec::new(),
            memory: Vec::new(),
            state_history: vec!["drifting".to_string()],
            speech_desire: 0.0,
        }
    }

    // --------------------------------------------------------
    // one cheap cognition step
    //
    // order:
    // 1. pick subconscious state
    // 2. pick topic
    // 3. pick thought fragment
    // 4. update speech desire
    // 5. apply passive emotional decay
    // --------------------------------------------------------
    fn tick(&mut self) {
        let mut rng = thread_rng();

        // ---------------- layer 1: subconscious drift ----------------
        let state_options = get_biased_transitions(
            &self.subconscious_state,
            self.fear,
            self.stress,
            self.curiosity,
            self.trust,
            self.aggression,
        );

        let next_state = state_options
            .choose(&mut rng)
            .unwrap_or(&"drifting")
            .to_string();

        self.subconscious_state = next_state;
        capped_push(&mut self.state_history, self.subconscious_state.clone(), 10);

        // ---------------- layer 2: topic selection ----------------
        let topic_options = get_topic_candidates(&self.subconscious_state);

        let topic = topic_options
            .choose(&mut rng)
            .unwrap_or(&"place")
            .to_string();

        self.active_topic = topic;

        // ---------------- layer 3: thought generation ----------------
        let thought_options = get_thought_fragments(&self.active_topic);

        let thought = thought_options
            .choose(&mut rng)
            .unwrap_or(&"...")
            .to_string();

        self.last_thought = thought.clone();
        capped_push(&mut self.thought_buffer, thought, 5);

        self.speech_desire = calculate_speech_desire(
            &self.subconscious_state,
            self.fear,
            self.stress,
            self.curiosity,
            self.aggression,
        );

        // light passive decay
        self.fear = clamp01(self.fear * 0.97);
        self.stress = clamp01(self.stress * 0.97);
        self.curiosity = clamp01((self.curiosity * 0.99).max(0.15));
        self.aggression = clamp01(self.aggression * 0.98);
    }

    // --------------------------------------------------------
    // directly nudge one emotion
    // python faction bias uses this
    // --------------------------------------------------------
    fn nudge(&mut self, kind: String, amount: f32) {
        match kind.as_str() {
            "fear" => self.fear = clamp01(self.fear + amount),
            "stress" => self.stress = clamp01(self.stress + amount),
            "curiosity" => self.curiosity = clamp01(self.curiosity + amount),
            "trust" => self.trust = clamp01(self.trust + amount),
            "aggression" => self.aggression = clamp01(self.aggression + amount),
            _ => {}
        }
    }

    // --------------------------------------------------------
    // apply contagion from another npc
    //
    // also writes a small memory tag like:
    // heard_stress_danger
    // --------------------------------------------------------
    fn apply_contagion(&mut self, emotion: String, intensity: f32, topic: String) {
        match emotion.as_str() {
            "fear" => {
                self.fear = clamp01(self.fear + intensity);
                self.stress = clamp01(self.stress + intensity * 0.5);
            }
            "stress" => {
                self.stress = clamp01(self.stress + intensity);
            }
            "curiosity" => {
                self.curiosity = clamp01(self.curiosity + intensity);
            }
            "trust" => {
                self.trust = clamp01(self.trust + intensity);
            }
            "aggression" => {
                self.aggression = clamp01(self.aggression + intensity);
            }
            _ => {}
        }

        let tag = format!("heard_{}_{}", emotion, topic);
        capped_push(&mut self.memory, tag, 8);
    }

    // --------------------------------------------------------
    // lets python add a memory tag directly
    // --------------------------------------------------------
    fn add_memory_tag(&mut self, tag: String) {
        capped_push(&mut self.memory, tag, 8);
    }

    // --------------------------------------------------------
    // gets the most common recent subconscious state
    // --------------------------------------------------------
    fn get_dominant_state(&self) -> String {
        let mut counts: HashMap<&String, i32> = HashMap::new();

        for state in &self.state_history {
            *counts.entry(state).or_insert(0) += 1;
        }

        let mut best = "drifting".to_string();
        let mut best_count = -1;

        for (state, count) in counts {
            if count > best_count {
                best_count = count;
                best = state.clone();
            }
        }

        best
    }

    // --------------------------------------------------------
    // compact bundle for python bridge / future llm use
    // --------------------------------------------------------
    fn get_bridge_packet(&self) -> (String, String, String, Vec<String>, Vec<String>, f32) {
        (
            self.get_dominant_state(),
            self.subconscious_state.clone(),
            self.active_topic.clone(),
            self.thought_buffer.clone(),
            self.memory.clone(),
            self.speech_desire,
        )
    }

    // --------------------------------------------------------
    // clears recent thought buffer
    // useful after python consumes it
    // --------------------------------------------------------
    fn clear_thought_buffer(&mut self) {
        self.thought_buffer.clear();
    }
}

// ------------------------------------------------------------
// python module export
//
// this is what makes `brain_logic.NpcMind` available in Python
// ------------------------------------------------------------
#[pymodule]
fn brain_logic(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<NpcMind>()?;
    Ok(())
}