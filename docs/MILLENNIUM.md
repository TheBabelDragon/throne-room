# Millennium Lab

The Duck does not ask an LLM to solve seven problems.

MetaField treats each Millennium Prize problem as an adversarial
mathematical environment. Collatz is an eighth pond.

```
                    🦆 DUCK
                      │
              Millennium Lab
                      │
     ┌───────────────┼───────────────┐
     ↓                ↓                ↓
   RH             Yang–Mills        Navier–Stokes
     ↓                ↓                ↓
  BSD             Hodge            P vs NP
     └───────────────┴───────────────┘
                     ↓
                  Collatz
                     │
                     ↓
          conjecture → experiment
                ↓          ↑
             proof attempt │
                ↓          │
          adversarial attack
                ↓          │
          formal verification
                ↓
           survives / dies
                ↓
              MEMORY
                ↓
          better Duck
```

## The rule

The Duck is rewarded for progress, not for being right.

It may accumulate verified lemmas, counterexamples, useful
transformations, conjectures, failed proof strategies, computational
evidence, formal proofs (only with a checker certificate), and
connections between ponds.

Every claimed breakthrough is thrown at the proof-killer before
MetaField will accept it. Declaring a prize solved is a kill
condition. Unbounded sentences are rejected once per pond and dropped.
Lab journals stay `victory_legal: false`. A workbench
VictoryCertificate is a separate typed admission, not a pond speech act.

Duck Gate remains the scientific method. The seven problems are the
Duck's seven biggest ponds. Poincaré is archival — CMI already
accepted Perelman; the Duck studies a discrete Ricci toy and cannot
re-claim that prize.

## Ponds

| Pond | Official | Environment |
|------|----------|-------------|
| `rh` | open | Hardy Z sign-changes on a named height window |
| `yang_mills` | open | U(1) Wilson lattice, plaquette correlator gap proxy |
| `navier_stokes` | open | named viscous Burgers window + inviscid steepening attack |
| `bsd` | open | named short Weierstrass models, box points + truncated Euler product |
| `hodge` | open | F2 Betti numbers of a named simplicial complex |
| `p_vs_np` | open | 2SAT vs brute; greedy 3SAT counterexamples |
| `poincare` | solved | archival + combinatorial curvature flow |
| `collatz` | extra | named Collatz termination windows |

None of these is the Clay problem. Status files always carry
`not_a_millennium_proof: true` and `victory_legal: false`.

## Start

```bash
python -m qwuack.millennium --once
python -m qwuack.millennium --pond rh --once --cycles 3
python -m qwuack --desk millennium --once --cycles 8
python -m qwuack.startup --body millennium --once
python -m qwuack.startup --body all
```

`--full` does not start this process.

Journals under `/tmp/metafield/`:

| File | Role |
|------|------|
| `millennium_status.json` | last admitted batch |
| `millennium_memory.jsonl` | append-only artifacts |
| `millennium_lab.json` | generation / progress score |
| `millennium_latest.txt` | one-line desk |

Progress score weights lemmas, counterexamples, evidence, failed
strategies, and connections. There is no victory term in the
progress score. Legal victory is a workbench certificate, not a
lab generation counter.
