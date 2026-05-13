#!/usr/bin/env bash
set -euo pipefail

MRLORE_ROOT="$HOME/Downloads/obsidianburdenNov25/_mrlore"
TOOLS_DIR="$MRLORE_ROOT/tools"
FILE="$TOOLS_DIR/build_registry.py"
BAK="$FILE.bak"

echo "🛠️ Restoring and Patching build_registry.py (v5 - Export Fixed)..."

# 1. Restore Backup
if [ -f "$BAK" ]; then
    cp "$BAK" "$FILE"
    echo "✅ Restored from backup."
else
    echo "❌ Backup missing. Cannot proceed safely."
    exit 1
fi

# 2. Export FILE for the Python subprocess
export FILE

python3 << 'PYEOF'
import sys
import os

file_path = os.environ.get('FILE')
if not file_path:
    print("❌ FILE variable not set.")
    sys.exit(1)

with open(file_path, 'r') as f:
    lines = f.readlines()

# Ensure sys is imported
sys_import_found = any(l.strip().startswith('import sys') for l in lines)
if not sys_import_found:
    lines.insert(1, 'import sys\n')
    print("✅ Added 'import sys'.")

# Target line to patch
target_str = 'REGISTRY_PATH.write_text("\\n".join(lines), encoding="utf-8")'
new_lines = []
patched = False

for line in lines:
    stripped = line.rstrip()
    if not patched and target_str in stripped:
        # Extract indentation from the target line
        indent = line[:len(line) - len(line.lstrip())]
        
        # Build replacement block
        block = [
            f"{indent}if '--dry-run' in sys.argv:\n",
            f"{indent}    print('[registry] DRY-RUN: Registry update skipped (no mutation).')\n",
            f"{indent}    try:\n",
            f"{indent}        print(f\"[registry] {{len(entities)}} entities registered (Preview only)\")\n",
            f"{indent}    except NameError:\n",
            f"{indent}        pass\n",
            f"{indent}    return 0\n",
            line
        ]
        new_lines.extend(block)
        patched = True
        print("✅ Injected dry-run guard with correct indentation.")
    else:
        new_lines.append(line)

if not patched:
    print("❌ Target write line not found.")
    sys.exit(1)

# Write back
with open(file_path, 'w') as f:
    f.writelines(new_lines)

# Verify syntax
try:
    import py_compile
    py_compile.compile(file_path, doraise=True)
    print("✅ Syntax check passed.")
except py_compile.PyCompileError as e:
    print(f"❌ Syntax error after patch: {e}")
    sys.exit(1)
PYEOF

# 3. Verify
echo ""
echo "🧪 Testing dry-run execution..."
python3 "$FILE" --dry-run

echo ""
echo "📊 Checking git diff..."
git diff -- "$FILE"