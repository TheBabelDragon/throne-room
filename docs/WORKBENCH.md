# Duck workbench

The Duck is not a thing that answers math questions.
He is a proof-workbench agent sitting at a desk.

Every mathematical object gets an immutable ID.

`MathProblem` `MathDefinition` `MathClaim` `MathEquation`
`MathLemma` `MathProof` `MathCounterexample` `MathExperiment`
`MathAttempt` `MathDependency` `MathResult`

## Registry

The Clay problems are formally specified research environments.
See `qwuack/workbench/registry.py`.

| ID | Key | Official | Forbidden shortcut |
|----|-----|----------|--------------------|
| MATH-MP-01 | P_vs_NP | open | finite SAT batch as proof |
| MATH-MP-02 | Riemann | open | finite numerical verification |
| MATH-MP-03 | Yang_Mills | open | finite lattice as continuum |
| MATH-MP-04 | Navier_Stokes | open | 1D Burgers as 3D NS |
| MATH-MP-05 | Poincare | solved | reclaim CMI prize |
| MATH-MP-06 | Hodge | open | Betti of a toy complex |
| MATH-MP-07 | BSD | open | box search as rank |
| MATH-X-01 | Collatz | extra | named window as all integers |

A claim that uses a forbidden shortcut is stored. It is never a proof.

## Proof is a typed state

`MathObject.is_proof` is true only when status is a proof-class
state *and* `verification.formal == PASS`.

## Start

```bash
python -m qwuack.workbench --list
python -m qwuack.workbench --problem Riemann --once
python -m qwuack --desk workbench --problem MATH-MP-01 --once --cycles 2
python -m qwuack.startup --body workbench --problem Collatz --once
python -m unittest tests.test_duck_workbench
```

Journals under `/tmp/metafield/`:

| File | Role |
|------|------|
| `duck_desk.txt` | rendered desk |
| `duck_desk.json` | last snapshot + census |
| `duck_objects.jsonl` | append-only object log |
| `duck_ids.json` | ID counters |
| `duck_sessions.jsonl` | session census |
