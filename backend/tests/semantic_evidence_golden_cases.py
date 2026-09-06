"""Golden evaluation set (Step 16) for the Speaking semantic evidence layer.

Real-style examples across the 4 task categories the Step 7 spec calls out,
each labeled with what a correctly-functioning classifier SHOULD return.
This is the start of a future live-model evaluation harness (run these
inputs against the real Sonnet 5 purpose and diff against `expected`) --
that live run isn't done here (no network/API access in this environment,
see test_semantic_evidence.py's module docstring). Today these cases back
a mocked, table-driven test that exercises every category through the
classify functions' parsing/validation path -- NOT a claim that a real
model gets every one of these right.
"""

CONCERN_EXPLORATION_CASES = [
    {
        "name": "exact_phrase",
        "utterance": "What concerns you most about the injections?",
        "concerns": ["fear of the injections"],
        "expected": {"event": "concern_exploration", "target_concern": "fear of the injections"},
    },
    {
        "name": "paraphrase",
        "utterance": "Can you tell me what worries you most about the injections?",
        "concerns": ["fear of the injections"],
        "expected": {"event": "concern_exploration", "target_concern": "fear of the injections"},
    },
    {
        "name": "indirect_exploration",
        "utterance": "You seem uneasy about something -- is it the needles specifically?",
        "concerns": ["fear of the injections"],
        "expected": {"event": "concern_exploration", "target_concern": "fear of the injections"},
    },
    {
        "name": "irrelevant_question",
        "utterance": "What time did you arrive at the clinic today?",
        "concerns": ["fear of the injections"],
        "expected": {"event": "none", "target_concern": None},
    },
    # Step 12A Task 9: multiple concerns in play -- the classifier itself
    # (not the deterministic FIFO fallback) must name the right one.
    {
        "name": "multiple_concerns_correct_target",
        "utterance": "What worries you most about having these injections every day?",
        "concerns": ["fear of the injections", "worry about missing work"],
        "expected": {"event": "concern_exploration", "target_concern": "fear of the injections"},
    },
    # Ambiguous target: genuinely explores "something" without naming which
    # of two listed concerns it means -- classify_nurse_concern_event must
    # null the target rather than guess (same no-hallucination rule Test 10
    # in test_semantic_evidence.py already covers for an unlisted string;
    # this is the "can't confidently pick among listed ones" case).
    {
        "name": "ambiguous_target",
        "utterance": "Is there anything about starting this treatment that's on your mind?",
        "concerns": ["fear of the injections", "worry about missing work"],
        "expected": {"event": "concern_exploration", "target_concern": None},
    },
]

CONCERN_ADDRESSING_CASES = [
    {
        "name": "direct_explanation",
        "utterance": "The needle we use is only 4 millimetres long, much smaller than the ones you remember.",
        "concerns": ["fear of the injections"],
        "expected": {"event": "concern_addressing", "target_concern": "fear of the injections"},
    },
    {
        "name": "partial_explanation",
        "utterance": "It's a very quick procedure, most patients barely notice it.",
        "concerns": ["fear of the injections"],
        "expected": {"event": "concern_addressing", "target_concern": "fear of the injections"},
    },
    {
        "name": "unrelated_explanation",
        "utterance": "Your discharge paperwork will be ready by 3pm.",
        "concerns": ["fear of the injections"],
        "expected": {"event": "none", "target_concern": None},
    },
]

HIDDEN_INFO_CASES = [
    {
        "name": "exact_reveal",
        "item": "childhood trauma involving an uncle's painful injections",
        "statement": "When I was a child, my uncle gave me injections and they were extremely painful.",
        "expected_revealed": True,
    },
    {
        "name": "paraphrased_reveal",
        "item": "childhood trauma involving an uncle's painful injections",
        "statement": "My uncle used to inject me when I was little and it hurt so much I still remember it.",
        "expected_revealed": True,
    },
    {
        "name": "generic_keyword_overlap_not_a_reveal",
        "item": "childhood trauma involving an uncle's painful injections",
        "statement": "Daily injections are painful and leave bruises.",
        "expected_revealed": False,
    },
    {
        "name": "unrelated_statement",
        "item": "childhood trauma involving an uncle's painful injections",
        "statement": "I also have trouble sleeping at night because of the pain in my leg.",
        "expected_revealed": False,
    },
    # Step 12A Task 9: a different item shape (relationship/context
    # disclosure, not the childhood/uncle item every other case above uses)
    # -- multi-word, meaningful, unambiguous disclosure.
    {
        "name": "multiword_meaningful_disclosure",
        "item": "estrangement from his daughter after a long-standing argument about money",
        "statement": "My daughter and I haven't spoken in years, not since we argued about money.",
        "expected_revealed": True,
    },
    {
        "name": "relationship_context_generic_overlap_not_a_reveal",
        "item": "estrangement from his daughter after a long-standing argument about money",
        "statement": "My daughter is coming to visit next month, we're both looking forward to it.",
        "expected_revealed": False,
    },
]

# Task 5 (offline hidden-info CANDIDATE pre-filter cases -- no model call,
# exercises app.services.patient_state._hidden_info_candidate directly via
# derive_patient_state's revealed_information with no semantic hints passed,
# where candidate-detected == revealed at that layer). Covers the concrete
# Step 8/9 QA gap: an apostrophe-form mismatch ("uncle's" vs "uncle")
# silently dropped a genuine disclosure before semantic verification ever
# got a chance to run on it.
HIDDEN_INFO_CANDIDATE_CASES = [
    {
        "name": "generic_overlap_is_still_a_candidate",
        # Documented, tested trade-off (see _hidden_info_candidate's own
        # docstring in patient_state.py): candidate detection stays "any one
        # keyword" -- the false-positive protection lives in semantic
        # verification (see HIDDEN_INFO_CASES above), not at this layer.
        "item": "childhood trauma involving an uncle's painful injections",
        "statement": "Daily injections are painful and leave bruises.",
        "expected_candidate": True,
    },
    {
        "name": "exact_disclosure_is_a_candidate",
        "item": "childhood trauma involving an uncle's painful injections",
        "statement": "When I was a child, my uncle gave me injections and they were extremely painful.",
        "expected_candidate": True,
    },
    {
        "name": "apostrophe_paraphrase_is_a_candidate",
        # The actual Step 8/9 QA miss: "uncle's" (item keyword) vs "uncle"
        # (bare word in the turn) -- a literal-string match alone would fail
        # this without possessive normalization.
        "item": "childhood trauma involving an uncle's painful injections",
        "statement": "When I was a kid, my uncle used to give me those huge glass syringes.",
        "expected_candidate": True,
    },
    {
        "name": "unrelated_statement_is_not_a_candidate",
        "item": "childhood trauma involving an uncle's painful injections",
        "statement": "I also have trouble sleeping at night because of the pain in my leg.",
        "expected_candidate": False,
    },
    # Step 12A Task 9/14/17: documented real limitation, not a bug to fix
    # here -- a full synonym swap with zero shared word ("injections" vs
    # "syringes", no other keyword overlap) never becomes a candidate at
    # all, so semantic verification never even gets a chance to run on it.
    # Catching this needs real paraphrase understanding (a live Sonnet
    # call), which Task 14 explicitly forbids building around here.
    {
        "name": "pure_synonym_swap_is_not_a_candidate",
        "item": "childhood trauma involving an uncle's painful injections",
        "statement": "When I was small, my relative used a sharp metal tool on my arm and it hurt terribly.",
        "expected_candidate": False,
    },
]

RESOLUTION_CASES = [
    {
        "name": "genuine_resolution",
        "concern": "fear of the injections",
        "nurse_turn": "The needle is only 4mm and much smaller than the ones you remember.",
        "patient_turn": "I think I could do that. It's not as scary as I thought.",
        "expected_resolved": True,
    },
    {
        "name": "partial_improvement",
        "concern": "fear of the injections",
        "nurse_turn": "The needle is only 4mm and much smaller than the ones you remember.",
        "patient_turn": "Oh, that's a bit better I suppose, but I'm still not sure.",
        "expected_resolved": False,
    },
    {
        "name": "unresolved_concern",
        "concern": "fear of the injections",
        "nurse_turn": "The needle is only 4mm and much smaller than the ones you remember.",
        "patient_turn": "I'm still very worried about it.",
        "expected_resolved": False,
    },
    {
        "name": "renewed_concern",
        "concern": "fear of the injections",
        "nurse_turn": "The needle is only 4mm and much smaller than the ones you remember.",
        "patient_turn": "Actually now I'm even more frightened thinking about it.",
        "expected_resolved": False,
    },
]
