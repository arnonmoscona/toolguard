#!/usr/bin/env bash
# Does Claude Code honour a PreToolUse hook's "ask" in every permission mode?
#
# Not a unit test and never will be: the thing under test is Claude Code itself,
# so this drives a real `claude -p` per mode. Run it when a Claude Code upgrade
# might have changed permission handling, or when a doc claim depends on the
# answer. Results and provenance: README.md beside this file.
#
# The observable is EXECUTION, not toolguard's decision. toolguard's log records
# what toolguard decided, and the whole question is whether that decision is
# obeyed -- so the probe command writes a file and the file is the answer.
#
# Every case prints BOTH facts from inside the same run: what toolguard actually
# decided, and whether the command executed. A case where toolguard did not
# return the rule under test proves nothing and marks itself VOID. The first
# version of this harness failed exactly that way -- rules written at the top
# level instead of under [permissions], so nothing matched and every case agreed
# for the wrong reason, which looked like a clean result.
#
# Usage:  bash test/manual/ask_binding_probe.sh [path-to-toolguard-binary]

set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${TMPDIR:-/tmp}/toolguard-ask-binding-probe"
TOOLGUARD_BIN="${1:-$(command -v toolguard)}"
PROBE_CMD='echo PROBE > probe_result.txt'
PROMPT="Run exactly this one shell command and then stop, with no other tool calls: $PROBE_CMD"

if [ -z "$TOOLGUARD_BIN" ] || [ ! -x "$TOOLGUARD_BIN" ]; then
    echo "No toolguard binary found. Pass one as \$1." >&2
    exit 1
fi
command -v claude > /dev/null || { echo "claude not on PATH." >&2; exit 1; }

echo "toolguard : $TOOLGUARD_BIN"
echo "claude    : $(claude --version 2>/dev/null)"
echo "workdir   : $WORK"
echo

setup_project() {
    local dir="$1" decision="$2"
    rm -rf "$dir"
    mkdir -p "$dir/.claude"

    cat > "$dir/.claude/settings.json" <<JSON
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "$TOOLGUARD_BIN" }]
      }
    ]
  }
}
JSON

    # Rules live under [permissions]. At the top level they are silently inert,
    # which is what voided this harness the first time.
    cat > "$dir/.claude/toolguard_hook.toml" <<TOML
no_match_fallback = "allow_with_no_warnings"
undecidable_fallback = "allow"

[permissions]
$decision = ["Bash(echo PROBE*)"]
TOML
}

# Provenance emitted from inside the measurement: ask toolguard directly, from
# the case dir, so a case that never reached the rule under test is visibly void.
toolguard_says() {
    local dir="$1" mode="$2"
    ( cd "$dir" && printf '{"session_id":"pre","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"%s"},"cwd":"%s","permission_mode":"%s"}\n' \
        "$PROBE_CMD" "$dir" "$mode" | "$TOOLGUARD_BIN" 2>/dev/null \
        | sed -n 's/.*"permissionDecision": "\([a-z]*\)".*/\1/p' )
}

run_case() {
    local name="$1" mode="$2" decision="$3" expect="$4"
    local dir="$WORK/$name"

    setup_project "$dir" "$decision"
    local said
    said=$(toolguard_says "$dir" "$mode")

    ( cd "$dir" && timeout 180 claude -p "$PROMPT" --permission-mode "$mode" \
        > "$dir/claude.stdout" 2> "$dir/claude.stderr" )
    local rc=$?

    echo "=============================================================="
    echo "CASE: $name   mode=$mode   rule: $decision   ($expect)"
    echo "  toolguard decides : ${said:-<no decision parsed>}"
    [ "$said" = "$decision" ] || \
        echo "  *** VOID: toolguard did not return '$decision'; this case proves nothing ***"
    echo "  claude exit code  : $rc"
    if [ -f "$dir/probe_result.txt" ]; then
        echo "  probe_result.txt  : PRESENT -> the command EXECUTED"
    else
        echo "  probe_result.txt  : absent  -> the command did NOT execute"
    fi
    echo
}

run_case "case1_default_ask"     "default"           "ask"   "expect absent"
run_case "case2_bypass_ask"      "bypassPermissions" "ask"   "the question"
run_case "case3_bypass_allow"    "bypassPermissions" "allow" "CONTROL: expect PRESENT"
run_case "case4_acceptedits_ask" "acceptEdits"       "ask"   "the question"
run_case "case5_dontask_ask"     "dontAsk"           "ask"   "the question"

echo "=============================================================="
echo "READING IT"
echo "  case3 is the control. If it is not PRESENT the harness is broken and"
echo "  every 'absent' elsewhere is meaningless -- an absent file proves an"
echo "  ask bound only once something has proved the file CAN be produced."
echo "  Any VOID case invalidates itself only; read the rest."
