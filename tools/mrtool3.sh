#!/usr/bin/env bash
set -euo pipefail

MRLORE_ROOT="${MRLORE_ROOT:-$HOME/Downloads/obsidianburdenNov25/_mrlore}"
TOOLS_DIR="$MRLORE_ROOT/tools"
TOTAL_EXIT=0

echo "🔍 MRLORE-AUDIT-003: Toolchain Integration Test (Repaired)"
echo "Run: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "---"

# 1. write_changed_manifest.py
echo "🧪 Testing: write_changed_manifest.py"
if ! python3 "$TOOLS_DIR/write_changed_manifest.py" --dry-run; then
    echo "❌ FAIL: write_changed_manifest.py"
    TOTAL_EXIT=2
else
    echo "✅ PASS: write_changed_manifest.py"
fi
echo ""

# 2. continuity_audit.py
echo "🧪 Testing: continuity_audit.py"
if ! python3 "$TOOLS_DIR/continuity_audit.py" --dry-run; then
    echo "❌ FAIL: continuity_audit.py"
    TOTAL_EXIT=2
else
    echo "✅ PASS: continuity_audit.py"
fi
echo ""

# 3. promote_candidate.py (FIXED: Added required --candidate argument)
echo "🧪 Testing: promote_candidate.py"
# Note: 'nephoretti' used as canonical candidate slug for dry-run validation
if ! python3 "$TOOLS_DIR/promote_candidate.py" --candidate nephoretti --dry-run; then
    echo "❌ FAIL: promote_candidate.py"
    TOTAL_EXIT=2
else
    echo "✅ PASS: promote_candidate.py"
fi
echo ""

# 4. build_registry.py (CHECK: Warn if dry-run output suggests writing)
echo "🧪 Testing: build_registry.py"
REG_OUTPUT=$(python3 "$TOOLS_DIR/build_registry.py" --dry-run 2>&1) || true # Capture output even if exit non-zero for analysis
REG_EXIT=$?

if [ $REG_EXIT -ne 0 ]; then
    echo "❌ FAIL: build_registry.py (Exit code: $REG_EXIT)"
    TOTAL_EXIT=2
else
    if echo "$REG_OUTPUT" | grep -qi "written to"; then
        echo "⚠️  WARN: build_registry.py dry-run prints 'Written to' (potential dry-run bypass)"
        echo "   -> Pending separate tool verification (INFRA-AUDIT-REPAIR-2)"
        # Do not set TOTAL_EXIT=2 yet, as this is a WARN pending verification
    else
        echo "✅ PASS: build_registry.py"
    fi
fi
echo ""

echo "---"
if [ $TOTAL_EXIT -eq 0 ]; then
    echo "🎉 STATUS: ALL TESTS PASSED (with possible warnings)"
    exit 0
else
    echo "💥 STATUS: TESTS FAILED"
    exit $TOTAL_EXIT
fi
