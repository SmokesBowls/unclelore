# Semantic Entity Contract Specification (Cut 2 - Entity Passport)

## Core Philosophy
To fully immunize EngAIn's universal simulation runtime from author-specific naming variables, character titles, and linguistic extraction dependencies. Downstream execution layers must operate exclusively on fixed, strongly typed simulation primitive enums. 

## Structural Blueprint
All compliant Cut 2 entity passport payloads must be valid JSON structures enforcing the following keys:

### 1. Controlled Primitive Vocabularies
* **`archetype`**: `caster`, `warrior`, `guardian`, `civilian`
* **`placeholder_type`**: `humanoid`, `humanoid_tall`, `creature_large`
* **`placeholder_color`**: `blue`, `red`, `green`, `gray`
* **`capabilities`**: `cast`, `command`, `move`, `speak`, `guard`
* **`ontology_status`**: `verified`, `provisional`

### 2. The Constitutional Firewall Rules
1. `provenance` belongs exclusively to Mr. Lore's upstream audit trails and review queues. It may contain prose, raw names, text excerpts, and frequency metrics.
2. The runtime engine is constitutionally banned from reading keys inside `provenance` to evaluate behavior trees, state mutations, or navigation parameters.
3. If an entity payload is executed with `provenance` completely removed, the simulation must still successfully instantiate the capsule using only the raw typed attributes.