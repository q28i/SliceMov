# Universal Clipping Profiles Specification

SliceMov provides six specialized clipping profiles designed to guide both AI analysis and heuristic offline algorithms towards the most valuable moments in different media genres.

---

## 1. Livestream Profile (`livestream`)

### Goal
Identify unexpected, emotional, and spontaneous livestream moments that capture attention on TikTok, YouTube Shorts, and Instagram Reels.

### Target Content
- Sudden chat activity spikes.
- Loud outbursts, laughter, jump scares, or rage.
- Unplanned comedic interruptions.
- Clutch gaming moments during a stream.

### Rules & Heuristics
- **Length Bounds**: 15s to 60s (ideal: ~30s).
- **Setup Preservation**: Captures the context immediately preceding the reaction so the payoff is understandable.
- **Clean End**: Cuts right after the reaction subsides on a complete sentence or breath.
- **Categories**: `funny`, `fail`, `clutch`, `rage`, `shock`, `hype`, `story`, `other`.

---

## 2. Podcast Profile (`podcast`)

### Goal
Extract deep, coherent, standalone thoughts, actionable advice, debates, and memorable revelations from long-form conversations.

### Target Content
- Breakthrough life or career advice.
- Thought-provoking counter-intuitive viewpoints.
- Emotional personal stories with a clear moral.
- Intense but substantive debate arguments.

### Rules & Heuristics
- **Length Bounds**: 30s to 90s (ideal: ~45-60s).
- **Substantive Coherence**: Each clip MUST form a complete, self-contained thought from premise to conclusion.
- **Sentence Integrity**: Never start or end mid-sentence.
- **Low-Noise Priority**: Does not require loud volume; evaluates intellectual substance and vocal cadence.
- **Categories**: `insight`, `advice`, `debate`, `story`, `revelation`, `hot_take`, `quote`, `other`.

---

## 3. Gaming Highlights Profile (`gaming`)

### Goal
Capture gaming action, funny interactions, clutches, and player reactions.

### Target Content
- Incredible clutch plays or game-winning shots.
- Spectacular failures, physics glitches, and misplays.
- Memorable banter between teammates in voice chat.
- High-intensity competitive matches.

### Rules & Heuristics
- **Length Bounds**: 15s to 60s (ideal: ~25-40s).
- **Action Verification**: Does not assume mere loud yelling means good gameplay. Evaluates game context and buildup.
- **Categories**: `clutch`, `fail`, `funny`, `glitch`, `hype`, `reaction`, `victory`, `other`.

---

## 4. Interview & Q&A Profile (`interview`)

### Goal
Surface memorable answers and explanations from guests, ensuring the question is clear.

### Target Content
- Direct answers to high-stakes questions.
- Unfiltered personal admissions.
- Clear explanations of complex experiences.
- Memorable quotes suitable for visual cards.

### Rules & Heuristics
- **Length Bounds**: 20s to 75s (ideal: ~35-50s).
- **Q&A Context**: Includes the interviewer's concise setup question (or overlay text) so the answer is immediately understood.
- **Categories**: `answer`, `revelation`, `quote`, `advice`, `story`, `perspective`, `other`.

---

## 5. Educational & Explainer Profile (`educational`)

### Goal
Condense complex concepts, tutorials, facts, and demonstrations into accessible, high-retention vertical explainers.

### Target Content
- "Did you know?" surprising facts.
- Step-by-step problem-solving tips.
- Scientific and historical insights.
- Practical technical advice.

### Rules & Heuristics
- **Length Bounds**: 25s to 80s (ideal: ~40-60s).
- **Factual Integrity**: Never clip an explanation in a way that distorts facts.
- **Clarity First**: Prioritizes logical flow, clear audio, and punchy hooks.
- **Categories**: `explanation`, `fact`, `tip`, `demonstration`, `science`, `history`, `other`.

---

## 6. General Video Profile (`general`)

### Goal
Default universal clipping engine for general vlog, documentary, review, and unclassified long-form video.

### Target Content
- Memorable narrative points.
- Best one-liners or situational humor.
- Pacing changes and video climax.

### Rules & Heuristics
- **Length Bounds**: 20s to 75s.
- **Categories**: `highlight`, `story`, `funny`, `moment`, `quote`, `takeaway`, `other`.

---

## Non-AI Offline Fallback Engine

When the system operates without an internet connection or without an AI API key:

1. **Speech Cadence Scoring**:
   Measures words-per-second across sliding windows. Normal conversational flow is between 2.0 and 3.2 words per second. Segments falling into this cadence are prioritized over silence or erratic audio.
2. **Discourse Marker Matching**:
   Scans for pivotal semantic words such as `because`, `reason`, `key`, `secret`, `truth`, `important`, `advice`, `solution`, `discovered`, `rule`, `actually`.
3. **Candidate Proposal**:
   Constructs viral clip candidates with word-level boundaries, auto-generated title hooks, hashtags, and virality confidence scores.

