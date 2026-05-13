#!/usr/bin/env bash
set -euo pipefail

MRLORE_ROOT="$HOME/Downloads/obsidianburdenNov25/_mrlore"
cd "$MRLORE_ROOT"

# 1. Initialize wiki/log.md per §17 Contract
if [ ! -s wiki/log.md ]; then
  echo "Initializing wiki/log.md with seed entry..."
  cat > wiki/log.md << 'EOF'
# MrLore Wiki Activity Log

This log is append-only. Entries record ingests, audits, proposals, and promotions.
Do not rewrite history except for typo correction.

---

## [2026-05-11] audit | System Initialization (MRLORE-AUDIT-001)

Summary:
- First structural & schema compliance validation of _mrlore v2 directory tree.
- Validated directory contract, schema files, tooling inventory, and raw/ immutability.
- Detected wiki/log.md empty; initialized to satisfy §17 Log Contract.

Pages changed:
- wiki/log.md (created)

Contradictions opened:
- None

Unresolved questions opened:
- None
EOF
  echo "✅ wiki/log.md initialized."
else
  echo "⚠️ wiki/log.md already exists; skipping initialization."
fi

# 2. Patch deprecation warning in audit_mrlore_system.py
echo "Patching audit_mrlore_system.py for timezone-aware datetime..."
sed -i 's/datetime.datetime.utcnow()/datetime.datetime.now(datetime.UTC)/' tools/audit_mrlore_system.py
echo "✅ Patch applied."

# 3. Re-run audit
echo ""
echo "Running post-remediation audit..."
python3 tools/audit_mrlore_system.py