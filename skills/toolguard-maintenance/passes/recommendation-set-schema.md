# Recommendation-set schema (inter-pass state artifact)

The passes of the maintenance skill do NOT re-derive each other's work from scratch. They
read and progressively annotate a single JSON document -- the **recommendation set** --
that carries the whole change proposal from raw findings through to the paste-ready TOML.

This file is the contract between passes. Keep every pass's reads/writes to these fields.
Store the document in the session scratchpad (never in the repo).

## Shape

```
{
  "meta": {
    "project_dir": str,            // absolute path audited
    "generated_at": str,           // local ISO timestamp
    "toolguard_version": str,
    "run_kind": "first" | "periodic",
    "trust_level": str             // dial set at install / by the user; governs how much
                                   // is surfaced vs pre-authorized (Phase B)
  },

  "config_settings": {             // NON-permission toolguard/Claude settings that shape
                                   // how the rules behave -- informational, never
                                   // auto-changed (see pass 1 step 6 / pass 3 step 1b)
    "observations": [
      { "key": str,                // e.g. "takeover_mode.enabled", "no_match_fallback"
        "value": "<any>",
        "locus": str, "level": str,          // which config file / level it lives at
        "category": "semantic" | "operational" | "preference",
        "cross_config": bool,      // interacts with Claude-native or another level
        "promotion_candidate": bool,
        "note": str,               // what to tell the user
        "doc_link": str            // pointer to the relevant documentation section
      } ]
  },

  "families": [                    // the unit of understanding AND of user approval
    {
      "family_id": str,            // stable slug, e.g. "uv-run-alembic"
      "label": str,                // human label, e.g. "uv run alembic"
      "tool": str,                 // governed tool, e.g. "Bash"

      "members": [                 // every rule in the family, across ALL sections,
                                   // INCLUDING those with status "no-change"
        {
          "pattern": str,          // current rule body (wrapper-free)
          "section": "allow" | "ask" | "deny" | "hard_deny",
          "locus": str,            // where it lives now (file/level describe string)
          "status": "no-change" | "edit" | "consolidate" | "remove" | "new" | "promote",
          "into": str | null,      // for consolidate/edit/new: the resulting pattern
          "target_level": str|null,// for promote: destination level (Phase D; flag-only)
          "rationale": str,        // plain-English why (fills the narrative)
          "source_finding_ids": [str],   // maintenance finding ids this came from
          "flags": [str],          // e.g. "heterogeneity", "needs-discussion",
                                   //      "cross-level-weld", "guard-overlap"
          "user_decision": "pending" | "accept" | "reject" | "modify",
          "user_note": str | null  // what the user said; drives the ledger later
        }
      ],

      "discussion": [              // open questions this family raises for the user
        { "question": str, "why": str, "resolved": bool, "answer": str | null }
      ],

      "narrative": str | null      // the per-family "understanding" paragraph (later pass)
    }
  ],

  "audit": {                       // filled by the security-audit pass (Phase A/B)
    "before": obj | null,          // audit of current config
    "after": obj | null,           // as-if-enacted audit of the proposal
    "delta": { "introduced": [obj], "resolved": [obj] } | null
  },

  "corpus_validation": obj | null, // filled by the corpus pass (Phase B); replay result.
                                   // NECESSARY, NOT SUFFICIENT -- decision-equivalence over
                                   // observed commands only. Never the sole gate.

  "certification": {               // filled by the finalize pass; author-by-AI/certify-by-tool
    "parses": bool | null,
    "audit_clean": bool | null,
    "corpus_ok": bool | null,
    "notes": str | null
  } | null,

  "final_toml": {                  // the cut/paste-ready output, per file, final-sort order
    "<file path>": str             // rendered TOML section/file the user can paste
  } | null
}
```

## Rules for passes

- A member with `status: "no-change"` is still listed -- the user must be able to
  reconstruct the FINAL state of each family, not just the deltas.
- No pass sets `user_decision` to anything but `pending` without an explicit user choice.
  Bulk acceptance is an explicit user opt-in, applied member-by-member, never a default.
- `flags` are advisory signals for later passes and for the user (e.g. a "heterogeneity"
  flag means the family has an outlier that needs discussion BEFORE any consolidation).
- Consolidation members are CANDIDATES until the targeting pass has confirmed all merged
  members share a target level. A "cross-level-weld" flag blocks the merge.
